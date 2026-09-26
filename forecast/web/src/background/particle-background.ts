/**
 * 漸層背景上的流場粒子效果（Canvas 2D）
 *
 * 顏色不寫死在 TS 裡，一律從 CSS 變數讀取，所以深淺色主題切換只要改 CSS。
 * 預設值對應範例頁面的設定：100 顆、速度 0.7、大小 0.4、無拖尾、30fps、1x 解析度。
 */

export interface ParticleStats {
  /** 實際幀率 */
  fps: number;
  /** 每幀粒子運算＋繪製的平均 JS 耗時（ms），不含瀏覽器合成成本 */
  frameMs: number;
  count: number;
  width: number;
  height: number;
}

export interface ParticleBackgroundOptions {
  /** 粒子數量 */
  count: number;
  /** 流動速度倍率 */
  speed: number;
  /** 粒子大小倍率 */
  size: number;
  /** 是否有拖尾 */
  trail: boolean;
  /** 幀率上限 */
  fps: number;
  /** 畫布解析度倍率，0.5 = 半解析度 */
  scale: number;
  /** 粒子顏色使用的 CSS 變數（隨機分配） */
  colorVars: readonly string[];
  /** 用來判斷目前是深色或淺色背景的 CSS 變數；深色時粒子用加色混合 */
  backgroundVar: string;
  /** 系統開啟「減少動態效果」時，只畫一張靜態畫面、不做動畫 */
  respectReducedMotion: boolean;
  /** 每 500ms 回報一次效能數據（選用） */
  onStats?: (stats: ParticleStats) => void;
}

export const DEFAULT_PARTICLE_OPTIONS: Readonly<ParticleBackgroundOptions> = {
  count: 100,
  speed: 0.7,
  size: 0.4,
  trail: false,
  fps: 30,
  scale: 1,
  colorVars: ['--p-1', '--p-2', '--p-3'],
  backgroundVar: '--bg-left',
  respectReducedMotion: true,
};

type RGB = readonly [number, number, number];

interface Particle {
  x: number;
  y: number;
  life: number;
  /** 壽命（秒） */
  max: number;
  /** 個別速度係數 */
  k: number;
  /** 基礎大小 */
  b: number;
  alpha: number;
  /** 使用哪個顏色的 sprite */
  c: number;
}

const SPRITE_SIZE = 32;
const TRAIL_FADE = 0.16;
const BASE_VELOCITY = 22; // px/s（1x 解析度時）
const FIELD_FREQ = 0.0021;

export class ParticleBackground {
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
  private opts: ParticleBackgroundOptions;

  private particles: Particle[] = [];
  private sprites: HTMLCanvasElement[] = [];
  private width = 0;
  private height = 0;
  private dark = false;

  private raf = 0;
  private last = 0;
  private statT = 0;
  private frames = 0;
  private costSum = 0;
  private resizeTimer: ReturnType<typeof setTimeout> | undefined;
  private destroyed = false;

  private readonly probe: HTMLSpanElement;
  private readonly reduceMQ = window.matchMedia('(prefers-reduced-motion: reduce)');
  private readonly darkMQ = window.matchMedia('(prefers-color-scheme: dark)');
  private readonly themeObserver: MutationObserver;

  constructor(canvas: HTMLCanvasElement, options: Partial<ParticleBackgroundOptions> = {}) {
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('ParticleBackground：無法取得 Canvas 2D context');
    this.canvas = canvas;
    this.ctx = ctx;
    this.opts = { ...DEFAULT_PARTICLE_OPTIONS, ...options };

    // 用來把 light-dark()、var() 解析成實際顏色的隱藏元素
    this.probe = document.createElement('span');
    this.probe.setAttribute('aria-hidden', 'true');
    Object.assign(this.probe.style, { position: 'absolute', width: '0', height: '0', overflow: 'hidden' });
    document.body.appendChild(this.probe);

    // 主題可能是用 data-theme 或 class 切換的，變動時重新讀顏色
    this.themeObserver = new MutationObserver(this.refreshColors);
    this.themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'class'],
    });

    window.addEventListener('resize', this.onResize);
    document.addEventListener('visibilitychange', this.onVisibility);
    this.darkMQ.addEventListener('change', this.refreshColors);
    this.reduceMQ.addEventListener('change', this.onReduceMotion);

    this.resize();
    this.refreshColors();
    this.syncCount();
  }

  /** 是否正在播放動畫 */
  get running(): boolean {
    return this.raf !== 0;
  }

  /** 開始動畫。分頁隱藏、或使用者偏好減少動態時會改畫靜態畫面 */
  start(): void {
    if (this.destroyed || this.raf) return;
    if (this.reducedMotion) {
      this.drawStatic();
      return;
    }
    if (document.hidden) return;
    this.last = this.statT = performance.now();
    this.frames = 0;
    this.costSum = 0;
    this.raf = requestAnimationFrame(this.frame);
  }

  /** 暫停動畫（畫面保留在最後一幀） */
  stop(): void {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  /** 即時調整參數 */
  setOptions(partial: Partial<ParticleBackgroundOptions>): void {
    const prev = this.opts;
    this.opts = { ...prev, ...partial };

    if (partial.scale !== undefined && partial.scale !== prev.scale) {
      const ratio = this.opts.scale / prev.scale;
      for (const p of this.particles) {
        p.x *= ratio;
        p.y *= ratio;
      }
      this.resize();
    }
    if (partial.count !== undefined) this.syncCount();
    if (partial.colorVars || partial.backgroundVar) this.refreshColors();
    if (partial.respectReducedMotion !== undefined) this.onReduceMotion();
    if (!this.raf) this.drawStatic();
  }

  /** 重新從 CSS 變數讀取顏色（主題切換時會自動呼叫） */
  readonly refreshColors = (): void => {
    if (this.destroyed) return;
    this.dark = luminance(this.readRGB(this.opts.backgroundVar)) < 0.5;
    this.sprites = this.opts.colorVars.map((v) => makeSprite(this.readRGB(v)));
    this.ctx.clearRect(0, 0, this.width, this.height);
    if (!this.raf) this.drawStatic();
  };

  /** 移除所有監聽器並清空畫布，元件卸載時呼叫 */
  destroy(): void {
    this.stop();
    this.destroyed = true;
    clearTimeout(this.resizeTimer);
    window.removeEventListener('resize', this.onResize);
    document.removeEventListener('visibilitychange', this.onVisibility);
    this.darkMQ.removeEventListener('change', this.refreshColors);
    this.reduceMQ.removeEventListener('change', this.onReduceMotion);
    this.themeObserver.disconnect();
    this.probe.remove();
    this.ctx.clearRect(0, 0, this.width, this.height);
    this.particles = [];
    this.sprites = [];
  }

  // ---------------------------------------------------------------- private

  private get reducedMotion(): boolean {
    return this.opts.respectReducedMotion && this.reduceMQ.matches;
  }

  private readonly onResize = (): void => {
    clearTimeout(this.resizeTimer);
    this.resizeTimer = setTimeout(() => {
      this.resize();
      if (!this.raf) this.drawStatic();
    }, 150);
  };

  private readonly onVisibility = (): void => {
    if (document.hidden) this.stop();
    else this.start();
  };

  private readonly onReduceMotion = (): void => {
    this.stop();
    this.start();
  };

  private resize(): void {
    this.width = Math.max(1, Math.round(window.innerWidth * this.opts.scale));
    this.height = Math.max(1, Math.round(window.innerHeight * this.opts.scale));
    this.canvas.width = this.width;
    this.canvas.height = this.height;
  }

  private readRGB(varName: string): RGB {
    this.probe.style.color = `var(${varName})`;
    const m = getComputedStyle(this.probe).color.match(/[\d.]+/g);
    if (!m || m.length < 3) return [255, 255, 255];
    return [Number(m[0]), Number(m[1]), Number(m[2])];
  }

  private syncCount(): void {
    const n = Math.max(0, Math.floor(this.opts.count));
    while (this.particles.length < n) this.particles.push(this.reset(createParticle(), true));
    this.particles.length = n;
  }

  private reset(p: Particle, initial: boolean): Particle {
    p.x = Math.random() * this.width;
    p.y = Math.random() * this.height;
    p.max = 4 + Math.random() * 6;
    p.life = initial ? Math.random() * p.max : 0;
    p.k = 0.6 + Math.random() * 0.8;
    p.b = 1 + Math.random() * 2.5;
    p.alpha = this.dark ? 0.35 + Math.random() * 0.5 : 0.45 + Math.random() * 0.45;
    p.c = Math.floor(Math.random() * Math.max(1, this.opts.colorVars.length));
    return p;
  }

  private readonly frame = (now: number): void => {
    this.raf = requestAnimationFrame(this.frame);
    const interval = 1000 / this.opts.fps;
    const elapsed = now - this.last;
    if (elapsed < interval - 1) return;
    this.last = now - (elapsed % interval);

    const t0 = performance.now();
    this.step(Math.min(elapsed, 100) / 1000, now / 1000);
    this.costSum += performance.now() - t0;
    this.frames++;

    if (this.opts.onStats && now - this.statT >= 500) {
      this.opts.onStats({
        fps: Math.round((this.frames * 1000) / (now - this.statT)),
        frameMs: this.costSum / this.frames,
        count: this.particles.length,
        width: this.width,
        height: this.height,
      });
      this.frames = 0;
      this.costSum = 0;
      this.statT = now;
    }
  };

  /** 不推進時間、只畫一幀（減少動態效果或暫停時使用） */
  private drawStatic(): void {
    if (this.destroyed) return;
    const trail = this.opts.trail;
    this.opts.trail = false;
    this.step(0, performance.now() / 1000);
    this.opts.trail = trail;
  }

  private step(dt: number, t: number): void {
    const { ctx, width: W, height: H, opts } = this;
    if (!this.sprites.length) return;

    if (opts.trail) {
      ctx.globalCompositeOperation = 'destination-out';
      ctx.globalAlpha = 1;
      ctx.fillStyle = `rgba(0,0,0,${TRAIL_FADE})`;
      ctx.fillRect(0, 0, W, H);
    } else {
      ctx.clearRect(0, 0, W, H);
    }

    ctx.globalCompositeOperation = this.dark ? 'lighter' : 'source-over';
    const v = BASE_VELOCITY * opts.speed * opts.scale * dt;
    const f = FIELD_FREQ / opts.scale;
    const sz = 6 * opts.size * opts.scale;

    for (const p of this.particles) {
      // 流場：幾個 sin/cos 疊出平滑、隨時間緩慢變化的方向
      const a =
        Math.sin(p.x * f + t * 0.13) * 1.6 +
        Math.cos(p.y * f * 1.3 - t * 0.1) * 1.6 +
        Math.sin((p.x + p.y) * f * 0.5 + t * 0.05);
      p.x += Math.cos(a) * v * p.k + v * 0.35; // 加一點向右的整體漂移
      p.y += Math.sin(a) * v * p.k;
      p.life += dt;

      if (p.life >= p.max || p.x < -20 || p.x > W + 20 || p.y < -20 || p.y > H + 20) {
        this.reset(p, false);
        continue;
      }

      ctx.globalAlpha = p.alpha * Math.sin((Math.PI * p.life) / p.max); // 淡入淡出
      const d = p.b * sz;
      const sprite = this.sprites[p.c % this.sprites.length];
      ctx.drawImage(sprite, p.x - d / 2, p.y - d / 2, d, d);
    }

    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
  }
}

// ------------------------------------------------------------------ helpers

function createParticle(): Particle {
  return { x: 0, y: 0, life: 0, max: 1, k: 1, b: 1, alpha: 1, c: 0 };
}

function makeSprite([r, g, b]: RGB): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = c.height = SPRITE_SIZE;
  const x = c.getContext('2d');
  if (!x) return c;
  const h = SPRITE_SIZE / 2;
  const grad = x.createRadialGradient(h, h, 0, h, h, h);
  grad.addColorStop(0, `rgba(${r},${g},${b},1)`);
  grad.addColorStop(0.35, `rgba(${r},${g},${b},.5)`);
  grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
  x.fillStyle = grad;
  x.fillRect(0, 0, SPRITE_SIZE, SPRITE_SIZE);
  return c;
}

/** 相對亮度（0~1），用來判斷背景是深色還是淺色 */
function luminance([r, g, b]: RGB): number {
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}
