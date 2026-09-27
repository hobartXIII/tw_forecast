# 背景效果說明

## 目標

網頁與 App 的背景原本是「淺色漸層 + 三個彩色光暈」。希望在不明顯影響效能的前提下，讓漸層有粒子流動的感覺。原本的設計是搭配毛玻璃卡片（`backdrop-filter`）使用，這版暫時關閉毛玻璃。

## 檔案

| 路徑 | 用途 |
|---|---|
| `src/background/particle-background.ts` | `ParticleBackground` 類別，Canvas 2D 流場粒子，框架無關 |
| `src/background/particle-background.css` | 背景漸層、光暈、粒子顏色的 CSS 變數與圖層樣式 |
| `docs/demos/particle-gradient-demo.html` | 粒子版互動範例（可調參數、看效能），單一 HTML 直接開啟 |
| `docs/demos/smoke-gradient-demo.html` | 煙霧版互動範例（WebGL shader），**尚未改寫成 TS** |

## 圖層結構

```html
<div class="pb-bg"></div>             <!-- z-index 0：漸層 + 光暈（靜態） -->
<canvas class="pb-canvas"></canvas>   <!-- z-index 1：粒子，pointer-events: none -->
<div class="pb-content">…</div>       <!-- z-index 2：實際內容 -->
```

## 目前採用的設定

由粒子版範例實際調整後決定：

| 參數 | 值 | 說明 |
|---|---|---|
| 主題 | 深色 | CSS 中 `color-scheme: dark`；改成 `light dark` 即可跟隨系統 |
| 粒子數量 | 100 | |
| 流動速度 | 0.7 | |
| 粒子大小 | 0.4 | |
| 拖尾 | 關 | |
| 光暈漂移 | 關 | 光暈維持靜態 |
| 顆粒質感 | 關 | |
| 毛玻璃 | 關 | 模糊半徑 0 |
| 幀率上限 | 30 fps | |
| 畫布解析度 | 1x | |

這些值就是 `DEFAULT_PARTICLE_OPTIONS` 的預設值。

## ParticleBackground API

```ts
const bg = new ParticleBackground(canvas, options?);  // options 皆為選填
bg.start();                  // 開始動畫
bg.stop();                   // 暫停（保留最後一幀）
bg.setOptions({ count: 150 });  // 即時調整參數
bg.refreshColors();          // 重新讀取 CSS 顏色（通常不需手動呼叫）
bg.destroy();                // 移除監聽器、清空畫布，元件卸載時必須呼叫
bg.running;                  // 是否正在播放
```

選項：`count`、`speed`、`size`、`trail`、`fps`、`scale`、`colorVars`（預設 `['--p-1','--p-2','--p-3']`）、`backgroundVar`（預設 `--bg-left`）、`respectReducedMotion`（預設 `true`）、`onStats`（每 500ms 回報 fps、每幀 JS 耗時等）。

框架掛載方式：React 在 `useEffect` 中建立並 `start()`，cleanup 呼叫 `destroy()`；Vue 分別放在 `onMounted` / `onUnmounted`。

## 設計決策

- **顏色從 CSS 讀取**：CSS 變數若是 `light-dark(...)`，`getPropertyValue` 只會拿到原始字串。因此用一個隱藏的 `<span>` 設定 `color: var(--x)`，再讀 `getComputedStyle().color` 取得實際 RGB。
- **深淺色判斷**：讀 `--bg-left` 的實際亮度，小於 0.5 視為深色。深色時粒子使用 `lighter`（加色混合，較像發光），淺色時使用 `source-over`，避免顏色洗白。
- **主題切換自動更新**：監聽 `<html>` 的 `data-theme`、`class` 變動，以及 `prefers-color-scheme` 變化。
- **流場**：以數個 `sin` / `cos` 疊加出平滑的方向場，不引入 noise 函式庫。另外加上少量向右的整體漂移。
- **粒子繪製**：每種顏色預先畫好一張 32px 的放射漸層 sprite，每幀用 `drawImage` 貼上，比每幀畫 `arc` 加漸層便宜。
- **畫布不乘 devicePixelRatio**：粒子本身是柔和光點，1x 解析度已足夠。

## 效能保護（不要移除）

- 幀率上限（預設 30fps），在 `requestAnimationFrame` 內自行節流。
- `visibilitychange`：分頁隱藏時停止動畫。
- `prefers-reduced-motion: reduce`：只畫一張靜態畫面，不做動畫。
- resize 有 150ms debounce。
- `destroy()` 需移除所有監聽器與 `MutationObserver`，避免 SPA 切頁時記憶體洩漏。

## 已知事項

- **開發者電腦開著「減少動態效果」**：在這台電腦上，預設只會看到靜態畫面。開發時若要看動畫，可暫時傳入 `{ respectReducedMotion: false }`，**正式環境請維持預設 `true`**。
- `light-dark()` 需要較新的瀏覽器支援，若要支援舊版瀏覽器，需改成 `prefers-color-scheme` media query 的寫法。
- 拖尾使用 `destination-out` 淡出，因 8-bit 色彩的捨入誤差，可能殘留極淡的痕跡（肉眼通常看不出來）。目前設定拖尾為關閉。

## 效能判讀

- `onStats` 的 `frameMs` 只包含粒子運算與繪製的 JS 時間，不含瀏覽器合成成本。
- 實際負擔建議用中低階手機實測，觀察幀率、發熱與滑動是否卡頓，或使用 DevTools Performance 面板錄製。
- 若日後重新開啟毛玻璃：背景每一幀變動，`backdrop-filter` 都要重算，模糊半徑是最貴的參數，應優先調低。

## 後續工作

1. ~~決定前端框架後，補上對應的掛載元件（React hook / Vue composable）。~~ 已完成：本專案不包成 React 元件，由 `main.tsx` 掛載一次（見下方「本專案的整合方式」）。
2. 煙霧版（`docs/demos/smoke-gradient-demo.html`）若要採用，需改寫成 TS 模組，並比照粒子版提供 `start` / `stop` / `setOptions` / `destroy`。需一併處理：
   - `webglcontextlost` / `webglcontextrestored`
   - 不支援 WebGL 時的退回方案（例如只顯示靜態漸層）
   - 煙霧的 JS 耗時量不到 GPU 成本，效能以實際幀率判斷
   - 煙霧預設以 0.5x 解析度渲染，0.25x 也幾乎看不出差別

## 本專案的整合方式（2026-09-27）

交接包的 `src/`、`docs/` 路徑對應到本專案：

| 交接包 | 本專案 |
|---|---|
| `src/background/particle-background.ts` | `forecast/web/src/background/particle-background.ts`（原封不動） |
| `src/background/particle-background.css` | 併入 `forecast/web/src/styles/global.css`（見下） |
| `docs/background-effects.md`、`docs/demos/` | `forecast/docs/background-effects.md`、`forecast/docs/demos/` |

- **只在深色主題播放**：`forecast/web/src/background/darkOnly.ts` 的 `playInDarkOnly` 依 `<html data-theme>` 開關；淺色時 `stop()` 並把畫布設為 `hidden`，淺色模式完全不跑動畫。主題按鈕切換、或「自動」時系統改深淺色，都會即時跟著開關。
- **掛載**：`main.tsx` 建立一次（整頁一個、不隨 React 重新渲染）；取不到 Canvas 2D context 時移除畫布，只剩靜態漸層。
- **CSS**：
  - 漸層與光暈（`--bg-left`、`--bg-right`、`--glow-1～3`）本專案原本就有，數值相同，沿用 `body::before`，不另外加 `.pb-bg`。
  - 粒子顏色 `--p-1～3` 只定義在 `:root[data-theme="dark"]`（沿用本專案的 `data-theme` 主題寫法，不用 `light-dark()`；TS 讀的是計算後的顏色，兩種寫法都能用）。
  - 畫布 `.pb-canvas` 與 `body::before` 同為 `z-index: -1`、排在其後，所以畫在光暈之上、內容之下；內容不必另外包 `.pb-content`。
- **毛玻璃**：整合當時卡片與面板保留了 `backdrop-filter`（2026-09-27 在桌機 Edge、1280px、深色量測，開啟粒子前後都維持約 144 fps）。同日改為**透明玻璃**：卡片、面板、按鈕、下拉都拿掉 `backdrop-filter`、刪除 `--glass-blur`，`--glass-bg` 濃度約減半，粒子直接透過卡片可見；只剩地圖圖例／提示框與告警視窗背後保留模糊。背景每幀變動時不必再重算卡片的模糊，手機負擔較小。
- **這台開發電腦**關閉了 Windows「動畫效果」，瀏覽器回報 `prefers-reduced-motion: reduce`，所以只會看到靜態的一幀（預期行為，正式環境維持 `respectReducedMotion: true`）。
- **淺色主題**不播粒子，改用純 CSS 的水平流動：`body::before` 加寬成 400vw、圖樣以 200vw 為週期重複，`translateX(-50% → 0)` 無限循環（`--bg-flow-duration`，預設 60s = 每 30 秒移一個畫面寬），只動 `transform`；減少動態效果時靜止。
- **手機（≤ 640px）**：同樣「每 30 秒一個畫面寬」換算成像素太慢，改為 `--bg-flow-duration: 24s`（約 12 秒一個畫面寬），`--glow-1～3` 的濃度提高約 1.6 倍。
- **手機的光暈改成「小而多」**：桌機版光暈半徑依畫面長邊（vmax）計算，直立手機上約 400px、比畫面還寬，移動時只像整片顏色變深變淺。手機改為每個週期 5 個半徑 60vw 的色團、高低錯落，會一個個從左邊飄進、右邊飄出。
- **淺色主題的光暈顏色**：原本左上角的暖橘（`--glow-1`）在桌機與手機都換成淡青綠 `rgba(70, 200, 185, …)`，與天藍、淡紫同屬冷色系（手機上濃度較高）。深色主題的光暈不變。
