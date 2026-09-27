# 台灣天氣預報：給 Claude 的專案指示

詳細說明在 `forecast/`：`ARCHITECTURE.md`（每個檔案的功能、「想改某功能看哪裡」）、`SPECIFICATION.md`（規格與版本紀錄 §10.3）、`VERCEL_PLAN.md`（前端改寫到 Vercel 的決定）。

## 1. 協作規則
- 一律用**繁體中文**回覆；程式碼、指令、檔名維持原樣。
- **先分析、後修改**：說明原因與方案，有取捨就列選項並附建議，等使用者同意才改。
- **畫面修改**：改完先在本機截圖確認（電腦 1280px、手機 390px，淺色與深色），保持 `npm run dev` 讓使用者自己看。
- **使用者說了才 commit／push**；不要自行建立分支。
- 行為或版面有變動時，同步更新 `SPECIFICATION.md` §8.1 與 `ARCHITECTURE.md`。

## 2. 程式位置
- **後端**：`forecast/src/tw_forecast/backend/`，入口 `forecast/scripts/fetch_and_store.py`（GitHub Actions 執行）。
- **前端**：`forecast/web/`（Vite + React + TypeScript，Vercel 的 Root Directory）。
  - `src/lib/` 資料與純函式（不依賴 React）、`src/components/` 畫面、`src/hooks/` 狀態流程、`src/styles/global.css` 全部樣式。
  - `api/`：Vercel Functions，邏輯在 `src/server/updateService.ts`；Node ESM，**相對匯入要寫 `.js`**。
- 前後端**不共用程式碼**，只透過 Supabase 交會。兩邊各有一份、要一起改的：發送時段（`config.SEND_SLOTS`／`lib/admin.ts` 的 `SLOTS`）、資料表名稱、縣市清單。

## 3. 測試與驗證
- 新功能同時補測試；自動測試都不連網、不連資料庫。
  - 後端：在 `forecast/` 執行 `python -m pytest`。
  - 前端：在 `forecast/web/` 執行 `npm test`；純函式寫單元測試，畫面流程加在 `tests/app.test.tsx`。`npm run build` 會先跑型別檢查與測試。
- 本機前端：`npm run dev`（http://localhost:5173，同時提供 `/api/*`，讀 `.env.local`）。停止後確認 5173 埠已釋放。
- 真實瀏覽器：`forecast/.venv` 的 Playwright + Edge（`channel="msedge"`）。
  - 需要登入或特定資料（例如下雨）時，用 `page.route` 攔截 RPC 或 `rest/v1/weather_forecasts` 改回應；不碰資料庫。
  - 地圖標記會重疊，改用 `dispatchEvent(new MouseEvent('mouseover'))` 開提示框，讀最後一個 `.map-tooltip`。
- 需要真實連線的檢查放 `forecast/checks/`，維運工具放 `forecast/tools/`。

## 4. 安全
- 前端只能用 `anon` 金鑰；`service_role` 只在 GitHub Secrets／本機 `.env`。
- 伺服器端變數（`GH_REPO`、`GH_DISPATCH_TOKEN`）**不可**加 `VITE_` 前綴。
- 金鑰與密碼不進程式碼、日誌或錯誤訊息（`mask_secrets`／`maskSecrets`／`translateError`）。
- 告警設定的密碼只放頁面記憶體（`useRef`），不寫 localStorage。

## 5. 部署與分支
- `main`：後端 + Vercel 前端；push 後自動部署（只有 `forecast/web/` 變動才建置）。正式網址 https://tw-forecast.vercel.app 。
- **Vercel 環境變數一律選 Config**（選 Secret 時 Function 讀不到）；改了要 Redeploy。
- `streamlit` 分支：Streamlit 版（Community Cloud）。在該分支 commit **不要用 `git add -A`**（那裡沒忽略 `forecast/web/` 的 `node_modules`、`.env.local`），一律指定路徑。
- `old` 分支：重構前的版本。

## 6. 已定案的前端做法（不要改回去）
細節見 `SPECIFICATION.md` §8.1。
- 主題寫在 `<html data-theme>`，CSS 深色規則只有 `:root[data-theme="dark"]` 一份；圖表配色用 `useDarkMode()`。
- 三套色階各自獨立：氣溫 `lib/temperature.ts`、降雨 `lib/rain.ts`、溫差 `lib/tempRange.ts`。
- 地圖底圖不論主題都是淺色 OpenStreetMap；降雨環在 0% 或沒有值時不畫；被選的縣市只放大、不加外框。
- 左欄版面的可調參數在 `global.css` 的 `.overview`、`.overview-side`（`--carousel-height` 等）。
- 卡片、面板、按鈕、下拉為透明玻璃（不加 `backdrop-filter`）；只有地圖圖例／提示框與告警視窗背後保留模糊。

## 7. 環境注意事項（Windows）
- 長的 bash heredoc 容易解析失敗：把腳本用 Write 寫到 scratchpad 再執行；含 emoji 的替換用 Edit，不用 `sed`。
- 終端機是 cp950：Python 輸出中文前加 `sys.stdout.reconfigure(encoding="utf-8")`。
- 這台電腦關閉了 Windows「動畫效果」，瀏覽器會回報 `prefers-reduced-motion: reduce`；動畫不能讓功能失效。
- 截圖放 scratchpad，使用者不一定看得到：給路徑或用 `Start-Process` 打開。

## 專案現況
- 前端為 **React + TypeScript**（Vite，部署於 Vercel）。背景特效 `ParticleBackground` 是框架無關的類別，由 `main.tsx` 掛載一次，不包成 React 元件。
- 背景視覺效果（漸層 + 流場粒子）已完成第一版，詳細說明見 @forecast/docs/background-effects.md
- 粒子**只在深色主題播放**（`forecast/web/src/background/darkOnly.ts`）；淺色主題停止並隱藏畫布。
- **淺色主題**改為背景（底色漸層＋三個光暈）由左往右水平流動：純 CSS，`global.css` 的 `:root[data-theme="light"] body::before`，只動 `transform`；速度由 `--bg-flow-duration` 控制（60s 一個週期 = 每 30 秒移一個畫面寬；手機改 24s，光暈也加濃）。

## 背景效果的必守規則
- 顏色一律放在 CSS 變數，沿用本專案的 `data-theme` 寫法（粒子顏色 `--p-1～3` 在 `global.css` 的 `:root[data-theme="dark"]`），**不要**在 TS 裡寫死色碼。
- 不要移除效能保護：幀率上限、分頁隱藏時暫停、`prefers-reduced-motion` 處理、`destroy()` 清除監聽器。
- 背景動畫只能動 `transform` / `opacity`；不要動畫 `filter`、`backdrop-filter`、`background-position`。
- 修改 `forecast/web/src/background/particle-background.ts` 後，需通過 `tsc --strict --noEmit`。
