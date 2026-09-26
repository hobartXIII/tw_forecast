# 前端改寫到 Vercel 的規劃

這份文件記錄把流程二（儀表板）從 Streamlit 改寫成 Vite + React、部署到 Vercel 的決定與步驟。
目前的前端架構見 [ARCHITECTURE.md](ARCHITECTURE.md)，需求與規格見 [SPECIFICATION.md](SPECIFICATION.md)。

- **建立日期**：2026-09-25
- **狀態**：階段 0 完成（2026-09-25 Vercel 部署成功並讀到資料庫）；階段 1 完成（資料層與純函式移植）；階段 2 完成（唯讀畫面）；階段 3 完成（地圖）；階段 4 完成（視覺細修，Vitest 132 項）；下一步階段 5（立即更新）

## 1. 已確定的決定

| 項目 | 決定 | 理由 |
| :--- | :--- | :--- |
| 框架 | **Vite + React + TypeScript**（靜態頁）＋ Vercel Functions（`api/`） | 地圖、圖表、篩選都在瀏覽器執行，資料即時查詢、不需 SEO，用不到伺服器渲染；只有「立即更新」需要伺服器端，一支 Function 即可。Leaflet／Vega 不必處理伺服器渲染的相容問題 |
| 「立即更新」的觸發後鎖定 | **查 GitHub workflow runs**（方式 A） | 不改資料庫、不動 `sql/`，對 `streamlit` 分支零影響；以 GitHub 上實際排隊中／執行中的 run 判斷，比伺服器記憶體準確，也不會因重啟遺失 |
| 分支 | 在 `main` 開發；Streamlit 版留在 `streamlit` 分支（Community Cloud 跟這個分支） | 兩邊並行，改 `main` 不影響線上 Streamlit |
| 「立即更新」 | 只在 Vercel 版提供 | `streamlit` 分支已用 `update_gate.MANUAL_UPDATE_ENABLED = False` 關閉（v1.16.0） |
| 後端、資料庫 | 不動 | GitHub Actions、`sql/init_supabase.sql`、RLS、RPC 維持原樣 |
| 前端常數（溫度級距、降雨色階、地區分組等） | **直接搬到 TypeScript**，不做 JSON 共用 | 後端沒有匯入 `frontend/`，這些常數只有前端使用；移植後 TypeScript 是唯一版本，不需要同步 |
| `main` 上的 Python 前端 | **凍結到階段 7 再刪除** | 移植期間留作對照、`pytest` 仍可證明其行為；不再修改（需要改 Streamlit 版時改 `streamlit` 分支）。階段 7 刪除 `src/tw_forecast/frontend/`、`streamlit_app/`、`tests/frontend/`、`.streamlit/` 與 Streamlit 相關套件 |

## 2. 目錄與部署

```text
forecast/
├── src/tw_forecast/      後端與 Streamlit 版前端（Python，不動）
├── streamlit_app/        Streamlit 入口（main 上暫時保留，見 §7）
└── web/                  新前端（Vercel 的 Root Directory）
    ├── api/              Vercel Functions（伺服器端，可讀 GH_DISPATCH_TOKEN）
    │   ├── update-status.ts   GET：是否可更新、剩餘秒數、是否有更新進行中
    │   └── dispatch.ts        POST：伺服器端再判斷一次，通過才觸發 workflow
    ├── src/
    │   ├── lib/          純函式與資料存取（對應 Python 的邏輯層，Vitest 測試）
    │   ├── components/   畫面元件（對應 views/）
    │   └── styles/       全域 CSS（主題變數、深色模式）＋ 各元件的 CSS Modules
    ├── tests/            Vitest 單元測試、Playwright 整頁測試
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    └── vite.config.ts
```

- **Vercel 專案設定**：Root Directory 設為 `forecast/web`，Framework Preset 選 Vite。
- **只在前端有變動時建置**：Ignored Build Step 設為 `git diff --quiet HEAD^ HEAD -- .`，只改後端或文件時不會觸發建置。
- **本機開發**：`npm run dev` 只跑頁面；要測 `api/` 用 Vercel CLI 的 `vercel dev`。

### 環境變數

| 變數 | 位置 | 用途 |
| :--- | :--- | :--- |
| `VITE_SUPABASE_URL`、`VITE_SUPABASE_ANON_KEY` | 瀏覽器（`VITE_` 前綴會打包進前端） | 唯讀查詢與告警設定 RPC；安全由 RLS 控制 |
| `SUPABASE_URL`、`SUPABASE_ANON_KEY` | 只在 Function | `api/` 讀 `pipeline_status` 判斷間隔 |
| `GH_REPO`、`GH_DISPATCH_TOKEN` | 只在 Function（**不可**加 `VITE_` 前綴） | 查 workflow runs 與觸發 `workflow_dispatch`；token 需要此 repo 的 `Actions: Read and write` |

`service_role` 金鑰不放進 Vercel。

## 3. 「立即更新」的新流程

```text
頁面載入／每次重新整理
  └─ GET /api/update-status
       ├─ 讀 pipeline_status → 距上次成功更新是否滿 20 分鐘（沿用 update_gate.evaluate 的規則）
       └─ 查 GitHub：weather_worker.yml 有沒有 event=workflow_dispatch 且尚未完成（queued／in_progress）的 run
       → 回傳 { allowed, message, waitSeconds, elapsedMinutes, inProgress, lastSuccess }

按下「立即更新」
  └─ POST /api/dispatch
       ├─ 伺服器端重新做一次上面的判斷（不信任瀏覽器）
       ├─ 通過 → 呼叫 GitHub workflow_dispatch（ref: main）
       └─ 回傳成功與否；前端改為「更新中…」並倒數 60 秒後重新查詢
```

- **取代 `DispatchLog`**：原本「觸發後 5 分鐘內、資料庫還沒有新的成功紀錄就鎖住」改成「GitHub 上有未完成的手動 run 就鎖住」。F5、新分頁、其他使用者看到的都是同一個狀態。
- **保留上限**：run 若卡住，建立超過 10 分鐘的未完成 run 不再算鎖定，避免一直停用（對應原本 `DISPATCH_LOCK_MINUTES` 的用意）。
- **已知空窗**：觸發後到 run 出現在 GitHub API 之間約數秒，這段時間同時按下仍可能多觸發一次；workflow 的 `concurrency: weather-pipeline` 會讓多出的那次排隊，不會同時執行（與現況相同）。
- **失敗時不放行**：讀不到 `pipeline_status` 或 GitHub API 失敗時一律不放行，並顯示原因（遮蔽 token）。

## 4. 技術選擇

| 功能 | 使用 | 對應現在的 Python |
| :--- | :--- | :--- |
| 資料查詢 | `@supabase/supabase-js`，查詢條件照搬 | `frontend/repository.py` |
| 時間與時區 | 固定 `+08:00`（台灣沒有日光節約時間），集中在 `lib/time.ts` | pandas 的 `tz_convert` |
| 趨勢圖 | `react-vega`（Vega-Lite），沿用 `charts.py` 的圖表定義 | Altair |
| 地圖 | `react-leaflet` | Folium／`streamlit-folium` |
| 表格 | 自己寫 `<table>`，溫度欄依級距上色、降雨機率進度條 | `st.dataframe` ＋ pandas Styler |
| 樣式 | 全域 CSS 變數（淺色／深色）＋ CSS Modules；玻璃擬態沿用 `style.py` 的 CSS | `frontend/style.py`、`.streamlit/config.toml` |
| 狀態 | React state；地區／縣市的選擇可放在網址參數，重新整理後保留 | `st.session_state` |
| 測試 | Vitest（純函式）、Playwright（整頁） | pytest、`AppTest` |

## 5. 分階段進行

每個階段完成後先確認，再進下一階段。視覺細修原本排在最後，2026-09-25 提前到地圖之後（階段 4），讓立即更新與告警設定直接沿用同一套樣式。

| 階段 | 內容 | 對應原模組 | 完成條件 |
| :---: | :--- | :--- | :--- |
| 0 | 建立 `forecast/web/` 專案骨架，Vercel 連上 repo、設好環境變數，部署一個能讀出資料筆數的頁面 | `session.py` | Vercel 網址能顯示資料庫筆數 |
| 1 | 資料層與純函式移植，並補 Vitest | `repository`、`scope`、`tables`、`temperature`、`rain`、`regions`、`formatting`、`update_gate`、`countdown` | 單元測試涵蓋原本 pytest 的案例 |
| 2 | 唯讀畫面：標題、地區／縣市篩選、摘要卡片、五個分頁（趨勢、降雨、明細、後續時段、日期查詢） | `views/` 大部分、`charts.py`、`tables.py` | 與 Streamlit 版逐項對照一致 |
| 3 | 地圖 | `map_view.py`、`map_section.py` | 標記、提示框、圖例、被選縣市放大、手機雙指手勢 |
| 4 | 視覺細修：玻璃擬態、漸層背景、卡片發光與動畫、深色模式、手機版（選單、滑動收起提示框、圖例不被切掉） | `style.py` | 電腦與手機、淺色與深色截圖確認 |
| 5 | 「立即更新」：`api/update-status.ts`、`api/dispatch.ts`、按鈕與倒數 | `github_dispatch.py`、`update_gate.py`、`views/header.py` | 實際觸發一次並驗證鎖定與倒數 |
| 6 | 告警設定：登入視窗與設定視窗 | `admin.py`、`admin_ui.py`、`views/admin_dialogs.py` | 以真實密碼登入並儲存成功 |
| 7 | 文件更新與切換 | — | ARCHITECTURE、SPEC、README、CLAUDE.md 反映新前端；決定正式入口 |

## 6. 待討論

- **告警設定的密碼保存方式（階段 6）**：RPC 每次讀寫都要帶密碼。最簡單的做法是登入後把密碼留在頁面記憶體（React state，不寫入 localStorage），閒置 15 分鐘或關閉頁面即清除，與 Streamlit 版「密碼只存在本次連線的記憶體」相當。若要讓瀏覽器完全不持有密碼，需要改由 Function 代為呼叫 RPC 並以加密的 `HttpOnly` cookie 保存登入狀態，複雜度較高。
- **地圖圖磚**：目前用 OpenStreetMap 官方圖磚；若流量變大應改用正式的圖磚服務，並保留「© OpenStreetMap contributors」標示。
- **資料更新後的頁面**：靜態頁每次載入都即時查 Supabase，資料更新後重新整理即可看到，不需要 ISR 或重新建置。

## 7. 不會變的事

- 後端（`src/tw_forecast/backend/`、`scripts/`）、GitHub Actions 排程與 Telegram 告警完全不動。
- 資料庫結構、RLS、RPC 不改；前端仍只用 `anon` 金鑰。
- `streamlit` 分支保留完整的 Streamlit 版，繼續部署於 Community Cloud。
- 後端的 `pytest` 照舊，在 `forecast/` 執行 `python -m pytest`。

## 8. 交接與待辦（2026-09-25，換電腦續作用）

### 目前進度

| 階段 | 狀態 | commit |
| :---: | :--- | :--- |
| 0 骨架與 Vercel 部署 | ✅ 完成，Vercel 已讀到資料庫 | `68de723` |
| 1 資料層與純函式 | ✅ 完成 | `b233df9` |
| 2 唯讀畫面 | ✅ 完成 | `9eaced8` |
| 3 地圖 | ✅ 完成 | `d0ca351` |
| 4 視覺細修 | ✅ 完成 | 見 git log |
| **5 立即更新** | **⏭️ 進行中** | — |
| 6 告警設定 | 未開始 | — |
| 7 文件與切換 | 未開始 | — |

`streamlit` 分支（Community Cloud 部署）：已關閉立即更新（v1.16.0，`0b15eea`）、修正地圖 Ctrl 提示一閃即逝（v1.16.1，`d071f90`）。

### 階段 4 視覺細修（完成）

- `web/src/styles/global.css` 沿用 `style.py`：漸層背景與三個光暈（放在 `body::before`，iOS 不支援 `background-attachment: fixed`）、玻璃卡片與面板、卡片發光邊框、進場淡入、浮起、進度條長出；尊重 `prefers-reduced-motion`；滑鼠移上的效果只在 `(hover: hover)` 的裝置套用
- 手機：圖例每列最多 3 項（`seriesChartSpec` 的 `legendColumns`）；捲動或滑動時收起 Vega 提示框（`lib/tooltipAutoHide.ts`）
- 手機版的「☰ 選單」等到階段 5 標題列有多顆按鈕時再加

### 之後的待辦

- 階段 5「立即更新」：`api/update-status.ts`、`api/dispatch.ts`（見 §3），Vercel 需加 `SUPABASE_URL`、`SUPABASE_ANON_KEY`、`GH_REPO`、`GH_DISPATCH_TOKEN`（不可加 `VITE_` 前綴）；資料過期提示的文字（目前寫「請等待下次排程更新」）屆時改回「請按『立即更新』」
- 階段 6 告警設定：先決定密碼保存方式（§6）
- 使用者待辦：
  - Streamlit Cloud 的 Secrets 可刪除 `GH_REPO`、`GH_DISPATCH_TOKEN`（token 本身保留，Vercel 版要用）
  - 在 Streamlit 版電腦上確認「按住 Ctrl」提示會停留約 1 秒（v1.16.1）

### 新電腦的環境設定

```bash
git clone https://github.com/hobartXIII/tw_forecast.git
cd tw_forecast/forecast/web
npm install
cp .env.example .env.local      # 填入 VITE_SUPABASE_URL、VITE_SUPABASE_ANON_KEY（與 Streamlit secrets 相同的值）
npm run dev                     # http://localhost:5173
npm test                        # Vitest（不連網、不連資料庫）
npm run build                   # 型別檢查 → 測試 → 打包（Vercel 建置時也跑這個）
```

後端與 Streamlit 版的 Python 測試照舊：依 README 建 `.venv`，`pip install -r requirements.txt -r requirements-dev.txt`（兩個檔案都在 repo 根目錄），再到 `forecast/` 執行 `python -m pytest`。

### 注意事項

- **在 `streamlit` 分支 commit 時不要用 `git add -A`**：`forecast/web/` 在該分支沒有被 `.gitignore` 排除，硬碟上的 `node_modules`、`dist`、`.env.local`（含金鑰）會被加進去。一律指定檔案路徑。
- 在 `main` 上的 Python 前端（`src/tw_forecast/frontend/`、`streamlit_app/`）已凍結，不再修改；要改 Streamlit 版就到 `streamlit` 分支改。
- Vercel 的環境變數改了之後要 Redeploy 才生效（`VITE_` 變數是建置時打包進去的）；值不要加引號、貼上前把輸入法切成英文。
- 本機用 `npx vite` 起的開發伺服器，停止時要確認 5173 埠已釋放（背景工作被停止時子行程可能還在）。
