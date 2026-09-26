## 本專案開發流程

> 完整說明見 `forecast/ARCHITECTURE.md`（每個檔案的功能與修改對照表）與 `forecast/SPECIFICATION.md`；前端改寫到 Vercel 的決定與過程見 `forecast/VERCEL_PLAN.md`。

### 程式位置
- **後端（流程一）**：`forecast/src/tw_forecast/backend/`，入口只有 `forecast/scripts/fetch_and_store.py`（GitHub Actions 執行）。
- **前端（流程二）**：`forecast/web/`（Vite + React + TypeScript，Vercel 的 Root Directory）。
  - `src/lib/`：資料存取與純函式（不依賴 React）；`src/components/`：畫面；`src/hooks/`：狀態流程；`src/styles/global.css`：全部樣式。
  - `api/`：Vercel Functions（`update-status`、`dispatch`），邏輯在 `src/server/updateService.ts`；以 Node ESM 執行，**相對匯入要寫 `.js` 副檔名**。
- 後端與前端**不共用程式碼**，只透過 Supabase 交會；發送時段（`config.SEND_SLOTS`／`lib/admin.ts` 的 `SLOTS`）、資料表名稱、縣市清單兩邊各有一份，要一起改。

### 工作方式
- **先分析、後修改**：新想法先說明原因與方案、等使用者同意再改程式。
- **測試**：新功能同時補測試；都不連網、不連資料庫。
  - 後端：在 `forecast/` 執行 `python -m pytest`。
  - 前端：在 `forecast/web/` 執行 `npm test`（Vitest；以 `America/New_York` 時區執行）；純函式寫單元測試，畫面流程加在 `tests/app.test.tsx`。`npm run build` 會先跑型別檢查與測試。
  - 需要真實連線的檢查放 `forecast/checks/`，維運工具放 `forecast/tools/`。
- **本機前端**：在 `forecast/web/` 執行 `npm run dev`（http://localhost:5173，`vite.config.ts` 的 `localApi` 外掛同時提供 `/api/*`，讀 `.env.local`）。停止時確認 5173 埠已釋放（背景工作被停止時 node 子行程可能還在）。
- **截圖確認**：用 `forecast/.venv` 裡的 Playwright + 已安裝的 Edge（`channel="msedge"`）；需要登入的畫面用 `page.route` 攔截 RPC 回傳假資料，不碰資料庫。

### 安全
- **前端只能用 `anon` 金鑰**；`service_role` 只在 GitHub Secrets／本機 `.env`。
- 伺服器端的變數（`GH_REPO`、`GH_DISPATCH_TOKEN`）**不可**加 `VITE_` 前綴，否則會被打包進瀏覽器。
- 金鑰與密碼不可進程式碼、日誌或錯誤訊息（後端用 `mask_secrets`、`api/` 用 `maskSecrets`、告警設定用 `translateError` 遮蔽）。
- 告警設定的密碼只放在頁面記憶體（`useRef`），不寫入 localStorage。

### 部署與分支
- `main`：後端 + Vercel 前端；push 後 Vercel 自動部署（只有 `forecast/web/` 有變動時才建置）。正式網址 https://tw-forecast.vercel.app 。
- **Vercel 環境變數一律選 Config**：選 Secret 的變數在 Function 執行時讀不到；改了變數要 Redeploy 才生效。
- `streamlit` 分支：Streamlit 版（Community Cloud 部署，已關閉「立即更新」）。要改 Streamlit 版就到該分支改；**在該分支 commit 不要用 `git add -A`**（那裡沒有忽略 `forecast/web/` 的 `node_modules`、`.env.local`），一律指定檔案路徑。
- `old` 分支：重構前的版本。
- 不要自行建立新分支，除非使用者明確同意。
