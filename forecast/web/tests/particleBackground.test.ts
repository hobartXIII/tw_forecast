// @vitest-environment jsdom
/** 背景流場粒子：效能保護（減少動態效果、分頁隱藏、destroy 清除監聽器）與主題切換時重新讀顏色。
jsdom 沒有真的 Canvas，這裡用假的 2D context，只驗證行為、不驗證畫出來的樣子。 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_PARTICLE_OPTIONS, ParticleBackground } from "../src/background/particle-background";

function fakeContext() {
  return {
    clearRect: vi.fn(), fillRect: vi.fn(), drawImage: vi.fn(),
    createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    globalAlpha: 1, globalCompositeOperation: "source-over", fillStyle: "",
  };
}

let reduce = false;
let ctx: ReturnType<typeof fakeContext>;

beforeEach(() => {
  reduce = false;
  ctx = fakeContext();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => ctx as never);
  window.matchMedia = vi.fn((q: string) => ({
    matches: q.includes("reduced-motion") ? reduce : false, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) as never;
  vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1));
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("ParticleBackground", () => {
  it("預設值：100 顆、30fps、尊重減少動態效果", () => {
    expect([DEFAULT_PARTICLE_OPTIONS.count, DEFAULT_PARTICLE_OPTIONS.fps, DEFAULT_PARTICLE_OPTIONS.respectReducedMotion])
      .toEqual([100, 30, true]);
  });

  it("一般情況 start() 會開始動畫；stop() 停止", () => {
    const bg = new ParticleBackground(document.createElement("canvas"));
    bg.start();
    expect(bg.running).toBe(true);
    bg.stop();
    expect(bg.running).toBe(false);
    bg.destroy();
  });

  it("減少動態效果時只畫一張靜態畫面，不開始動畫", () => {
    reduce = true;
    const bg = new ParticleBackground(document.createElement("canvas"));
    ctx.drawImage.mockClear();
    bg.start();
    expect(bg.running).toBe(false);
    expect(ctx.drawImage).toHaveBeenCalled(); // 有畫粒子
    bg.destroy();
  });

  it("分頁隱藏時暫停，回來時繼續", () => {
    const bg = new ParticleBackground(document.createElement("canvas"));
    bg.start();
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(bg.running).toBe(false);
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(bg.running).toBe(true);
    bg.destroy();
  });

  it("destroy() 移除監聽器與隱藏的顏色探測元素；之後 start() 沒有作用", () => {
    const removeWin = vi.spyOn(window, "removeEventListener");
    const removeDoc = vi.spyOn(document, "removeEventListener");
    const bg = new ParticleBackground(document.createElement("canvas"));
    expect(document.body.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(1);
    bg.destroy();
    expect(removeWin).toHaveBeenCalledWith("resize", expect.any(Function));
    expect(removeDoc).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
    expect(document.body.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(0);
    bg.start();
    expect(bg.running).toBe(false);
  });

  it("切換 <html data-theme> 時重新讀取顏色", async () => {
    const bg = new ParticleBackground(document.createElement("canvas"));
    ctx.createRadialGradient.mockClear();
    document.documentElement.setAttribute("data-theme", "dark");
    await new Promise((r) => setTimeout(r, 0)); // MutationObserver 是非同步回呼
    expect(ctx.createRadialGradient).toHaveBeenCalledTimes(DEFAULT_PARTICLE_OPTIONS.colorVars.length); // 每種顏色重畫一張 sprite
    bg.destroy();
    document.documentElement.removeAttribute("data-theme");
  });
});
