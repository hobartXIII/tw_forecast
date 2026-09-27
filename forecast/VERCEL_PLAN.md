# 前端改寫到 Vercel 的規劃

這份文件記錄把流程二（儀表板）從 Streamlit 改寫成 Vite + React、部署到 Vercel 的決定與步驟。
目前的前端架構見 [ARCHITECTURE.md](ARCHITECTURE.md)，需求與規格見 [SPECIFICATION.md](SPECIFICATION.md)。

- **建立日期**：2026-09-25
- **狀態**：階段 0 完成（2026-09-25 Vercel 部署成功並讀到資料庫）；階段 1 完成（資料層與純函式移植）；階段 2 完成（唯讀畫面）；階段 3 完成（地圖）；階段 4 完成（視覺細修，Vitest 132 項）；階段 5 完成（立即更新，2026-09-26 Vercel 實測通過，Vitest 152 項）；階段 6 完成（告警設定，2026-09-26 本機以真實密碼實測通過，Vitest 182 項）；階段 7 完成（文件與切換，2026-09-26）。**改寫全部完成**，正式入口為 Vercel 版（<https://tw-forecast.vercel.app>），Streamlit 版保留在 `streamlit` 分支作為備用

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

> 以下是規劃時的結構；實際完成的目錄見 [ARCHITECTURE.md](ARCHITECTURE.md) §2、§4（沒有使用 CSS Modules，整頁測試改在 Vitest 的 jsdom 裡執行，`streamlit_app/` 已於階段 7 刪除）。

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
- **本機開發**：`npm run dev` 同時提供頁面與 `api/`（`vite.config.ts` 的 `localApi` 外掛，讀 `.env.local`）；本機沒填 `GH_DISPATCH_TOKEN` 時「立即更新」顯示「尚未設定」並停用。

### 環境變數

| 變數 | 位置 | 用途 |
| :--- | :--- | :--- |
| `VITE_SUPABASE_URL`、`VITE_SUPABASE_ANON_KEY` | 瀏覽器（`VITE_` 前綴會打包進前端） | 唯讀查詢與告警設定 RPC；安全由 RLS 控制 |
| `SUPABASE_URL`、`SUPABASE_ANON_KEY` | 只在 Function | `api/` 讀 `pipeline_status` 判斷間隔；沒設定時沿用 `VITE_SUPABASE_URL`、`VITE_SUPABASE_ANON_KEY`（同一組 anon 值） |
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

> 規劃時的選擇；實際改為直接使用 `vega-embed` 與 `leaflet`（沒有用 `react-vega`、`react-leaflet`），樣式只有一份 `global.css`，整頁測試用 Vitest + jsdom（沒有用 Playwright）。

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
| 4 視覺細修 | ✅ 完成 | `a32638c` |
| 5 立即更新 | ✅ 完成（Vercel 實測通過） | `719e2e4` |
| 6 告警設定 | ✅ 完成（真實密碼實測通過） | 見 git log |
| 7 文件與切換 | ✅ 完成 | 見 git log |

`streamlit` 分支（Community Cloud 部署）：已關閉立即更新（v1.16.0，`0b15eea`）、修正地圖 Ctrl 提示一閃即逝（v1.16.1，`d071f90`）。

### 階段 4 視覺細修（完成）

- `web/src/styles/global.css` 沿用 `style.py`：漸層背景與三個光暈（放在 `body::before`，iOS 不支援 `background-attachment: fixed`）、玻璃卡片與面板、卡片發光邊框、進場淡入、浮起、進度條長出；尊重 `prefers-reduced-motion`；滑鼠移上的效果只在 `(hover: hover)` 的裝置套用
- 手機：圖例每列最多 3 項（`seriesChartSpec` 的 `legendColumns`）；捲動或滑動時收起 Vega 提示框（`lib/tooltipAutoHide.ts`）
- 手機版的「☰ 選單」等到階段 5 標題列有多顆按鈕時再加

### 階段 5 立即更新（完成）

- 伺服器端邏輯在 `web/src/server/updateService.ts`（`getUpdateStatus`、`dispatchUpdate`、`maskSecrets`），`api/update-status.ts`（GET）、`api/dispatch.ts`（POST）只負責串接；`api/` 以 Node ESM 執行，相對匯入寫 `.js` 副檔名
- 瀏覽器端：`lib/updateApi.ts`（呼叫 api/，失敗一律不放行）、`hooks/useUpdateFlow.ts`（流程狀態）、`components/UpdateNotices.tsx`（提示與倒數）
- 過期提示的文字已改回「請按『立即更新』」
- 手機版標題列目前是兩顆按鈕並排；階段 6 加入「⚙️ 告警設定」後再決定是否改成「☰ 選單」
- **實測（2026-09-26 通過）**：Vercel → Settings → Environment Variables 加 `GH_REPO`（`hobartXIII/tw_forecast`）、`GH_DISPATCH_TOKEN`（不可加 `VITE_` 前綴）→ push `main` 觸發部署 → 按一次「立即更新」，確認：按鈕變「更新中…」並倒數 60 秒、另一個分頁／F5 後按鈕仍停用（GitHub 上有未完成的手動 run）、完成後顯示「資料已更新完成」與 20 分鐘間隔倒數

### 階段 6 告警設定（完成）

- 密碼保存採 §6 的方式 A：只放在頁面記憶體（`useRef`），不寫入 localStorage；閒置 15 分鐘、登出、關閉或重新整理分頁即清除
- `lib/admin.ts`（對應 `admin.py`：錯誤轉換遮蔽密碼、驗證、參數、`AlertSettingsService`）、`hooks/useAdminSession.ts`（登入狀態與視窗流程，對應 `admin_ui.py`）、`components/AdminDialogs.tsx`（登入與設定視窗）、`components/Modal.tsx`（原生 `<dialog>`）、`components/Toast.tsx`
- 連續登入失敗越多次，下次送出前等越久（最多 5 秒，資料庫另有 1 秒延遲）
- 手機版標題列的三顆按鈕收進「☰ 選單」
- **實測（2026-09-26 本機通過）**：以真實密碼登入、修改一個值並儲存，再到 Supabase 或重新開啟視窗確認；最後改回原本的設定

### 階段 7 文件與切換（完成）

- 正式入口：Vercel 版；Streamlit 版保留在 `streamlit` 分支（Community Cloud）作為備用
- `main` 刪除 `src/tw_forecast/frontend/`、`streamlit_app/`、`tests/frontend/`、`.streamlit/`（兩份 `config.toml` 與 `secrets.toml.example`）；`tests/fakes.py` 移除只給前端用的 `forecast_rows`；`requirements.txt` 只留後端套件（`requests`、`python-dotenv`、`supabase`）。不另外打 tag：`streamlit` 分支就是對照組，刪除前的內容也在 git 歷史
- 文件：`ARCHITECTURE.md`（前端章節改為 `web/`）、`SPECIFICATION.md`（v2.0.0，§4.2、§8、§9、§10 改為 Vercel 版）、`README.md`（部署網址、技術選型、測試、附錄、改寫心得）、`CLAUDE.md`（刪除 Streamlit 通用慣例，只留本專案做法）、`.devcontainer/devcontainer.json`（改為 Python + Node.js，啟動前端開發伺服器）
- 硬碟上 `forecast/.streamlit/secrets.toml`（未追蹤、含金鑰）保留，切到 `streamlit` 分支本機執行時要用

### 之後的待辦

- README 的截圖（`assets/screenshots/`）已於 2026-09-27 重拍為 Vercel 版；部署網址 QR code 已新增 Vercel 版（`assets/deploy_qrcode_vercel.png`，以 `segno` 產生），Streamlit 版的保留
- 使用者待辦：
  - Streamlit Cloud 的 Secrets 可刪除 `GH_REPO`、`GH_DISPATCH_TOKEN`（token 本身保留，Vercel 版要用）
  - 在 Streamlit 版電腦上確認「按住 Ctrl」提示會停留約 1 秒（v1.16.1）

### 新電腦的環境設定

```bash
git clone https://github.com/hobartXIII/tw_forecast.git
cd tw_forecast/forecast/web
npm install
cp .env.example .env.local      # 填入 VITE_SUPABASE_URL、VITE_SUPABASE_ANON_KEY（anon）；要測「立即更新」再填 GH_REPO、GH_DISPATCH_TOKEN
npm run dev                     # http://localhost:5173
npm test                        # Vitest（不連網、不連資料庫）
npm run build                   # 型別檢查 → 測試 → 打包（Vercel 建置時也跑這個）
```

後端的 Python 測試照舊（Streamlit 版的測試在 `streamlit` 分支）：依 `SPECIFICATION.md` §11.1 建 `.venv`，`pip install -r requirements.txt -r requirements-dev.txt`（兩個檔案都在 repo 根目錄），再到 `forecast/` 執行 `python -m pytest`。

### 注意事項

- **在 `streamlit` 分支 commit 時不要用 `git add -A`**：`forecast/web/` 在該分支沒有被 `.gitignore` 排除，硬碟上的 `node_modules`、`dist`、`.env.local`（含金鑰）會被加進去。一律指定檔案路徑。
- `main` 上已沒有 Python 前端；要改 Streamlit 版就到 `streamlit` 分支改。
- Vercel 環境變數一律選 **Config**：選 Secret 的變數在 Function 執行時讀不到（2026-09-26 `GH_DISPATCH_TOKEN` 設成 Secret 時 `/api/update-status` 一直回「尚未設定」，改成 Config 並 Redeploy 後正常）。token 雖是 Config，只有 `api/` 讀取且訊息會遮蔽；不可取 `VITE_` 開頭的名稱
- Vercel 的環境變數改了之後要 Redeploy 才生效（`VITE_` 變數是建置時打包進去的）；值不要加引號、貼上前把輸入法切成英文。
- 本機用 `npx vite` 起的開發伺服器，停止時要確認 5173 埠已釋放（背景工作被停止時子行程可能還在）。

---

## 附錄：改寫前的評估

### Streamlit Community Cloud 與 Vercel 完整比較（改寫前）

| 面向 | Streamlit Community Cloud（改寫前） | Vercel |
| :--- | :--- | :--- |
| 開發語言 | 全部 Python，可沿用 pandas、Altair、folium 與現有測試 | 前端需改寫成 JavaScript／TypeScript（例如 Next.js）；Streamlit 需要常駐的 WebSocket 伺服器，無法部署在 Vercel |
| 開發速度 | 視熟悉度而定：熟 Python 的人上手快，元件現成，不用寫 API 與前端狀態管理；但它特有的「每次互動整支腳本重跑」、`session_state`、快取機制較少人熟悉，資源也較少 | 視熟悉度而定：HTML／React／TypeScript 是主流技能，資料與範例多，熟前端的人反而較快；但要自己處理版面、狀態、API 路由 |
| 首次載入 | 一段時間沒有流量會休眠，下一位訪客要等喚醒；每個連線都要建立 WebSocket | 靜態頁面走全球 CDN，載入快，沒有休眠問題 |
| 互動模型 | 每次互動整支腳本重跑，靠 `st.cache_*`、`st.fragment` 優化 | 只更新變動的元件，瀏覽器端互動不需回伺服器 |
| 版面與樣式 | 受限於內建元件；玻璃擬態、頁籤等效果依賴 Streamlit 內部 CSS 選擇器，升級版本可能失效 | 完全自訂，手機版與深色主題可精細控制 |
| 快取 | 伺服器記憶體快取，app 重啟或休眠就清空 | 可用 ISR（定時重建頁面），很適合「每 3 小時才更新一次」的資料 |
| 部署流程 | push 到 `main` 自動部署；無預覽環境 | push 自動部署，另外每個 PR 都有預覽網址 |
| 網域 | 只能用 `*.streamlit.app` | 可綁定自訂網域 |
| 資源限制 | 每個 app 約 2.7 GB 記憶體；私有 app 限 1 個 | Serverless Function 有執行時間與次數限制；免費 Hobby 方案僅限非商業使用 |
| 伺服器狀態 | 有常駐行程，`DispatchLog`、登入狀態可放記憶體 | Function 不保留狀態，這類狀態必須移到資料庫或 cookie |
| 維護成本 | 一種語言、一套測試 | Python（後端）與 TypeScript（前端）兩套語言、兩套測試 |

### 當初的改寫建議（未全數採用）

> 實際採用的方案見本文件 §1～§6：框架改用 Vite + React（而非下面第 1 點的 Next.js），「觸發後鎖定」改查 GitHub workflow runs（而非第 3 點的資料庫欄位），告警設定的密碼留在頁面記憶體（而非第 4 點的 cookie），常數直接搬到 TypeScript（而非第 7 點的共用 JSON）。以下保留為當初的評估。

1. **框架**：Next.js（App Router）＋ TypeScript，用 `@supabase/supabase-js` 讀資料。`anon` key 放在 `NEXT_PUBLIC_SUPABASE_URL`、`NEXT_PUBLIC_SUPABASE_ANON_KEY`；`GH_REPO`、`GH_DISPATCH_TOKEN` 只設成伺服器端環境變數（不加 `NEXT_PUBLIC_` 前綴）。Supabase 的 RLS 與 RPC 不用改。
2. **資料更新**：預報頁用 ISR 定時重建。更好的做法是在 `fetch_and_store.py` 成功寫入後，呼叫 Vercel 的重新驗證 API（帶密鑰），資料一更新頁面就重建，不必等下一次定時。
3. **「立即更新」**：改成 Route Handler 呼叫 GitHub API。20 分鐘間隔已經是依資料庫 `pipeline_status` 的最後成功時間判斷，可直接沿用。需要調整的是「觸發後 5 分鐘鎖定」：它用的觸發時間（按下按鈕到 workflow 寫入成功紀錄之間的空窗）目前只存在伺服器記憶體（`DispatchLog`），Vercel 的 Function 不保留記憶體，要改存到 Supabase（例如在 `pipeline_status` 加一個 `last_dispatched_at` 欄位，由 Route Handler 透過專用的 RPC 函式寫入，前端仍只用 `anon` key、不放 `service_role`），才能跨 Function 共用，也順便解決目前「app 重啟就清掉觸發紀錄」的問題。
4. **「⚙️ 告警設定」**：密碼只在登入時送到 Route Handler，由伺服器呼叫 Supabase RPC 驗證；成功後發簽章過、`HttpOnly` 的短效 session cookie（15 分鐘閒置逾時），之後的讀寫都由伺服器端帶憑證呼叫 RPC，瀏覽器不保存密碼。長期可以考慮改用 Supabase Auth 取代自建密碼表。
5. **圖表**：目前的 Altair 圖表本質上是 Vega-Lite 規格，可以用 `react-vega` 或 `vega-embed` 沿用相同的圖表定義，不必整個重畫。
6. **地圖**：folium 底層是 Leaflet，可改用 `react-leaflet`。流量變大時，OpenStreetMap 官方圖磚伺服器不適合大量使用，建議改用正式的圖磚服務，並保留「© OpenStreetMap contributors」標示。
7. **共用設定**：溫度級距、降雨色階、地區分組、告警預設門檻目前寫在 Python 裡。改寫時建議抽成一份 JSON，讓後端（Python）與前端（TypeScript）讀同一份，避免兩邊數值不一致。
8. **測試**：純函式改用 Vitest 寫單元測試，畫面流程用 Playwright 取代現在的 `AppTest` 煙霧測試；後端的 `pytest` 保持不變。
9. **遷移步驟**：先在 Vercel 上並行建置新前端，用 PR 預覽網址逐項對照功能；功能完全一致後再切換正式網址，Streamlit 版保留一段時間作為備援。
