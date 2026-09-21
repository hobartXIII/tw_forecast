# 台灣天氣預報與自動化通報系統

抓取中央氣象署 `F-D0047-091`（未來 1 週各縣市預報），存入 Supabase，並以 Streamlit 儀表板呈現；符合條件時推播 Telegram 告警到個人手機。完整規格見 [SPECIFICATION.md](SPECIFICATION.md)。

```text
[中央氣象署 API] → [GitHub Actions 每 3 小時] → [Supabase] → [Streamlit 儀表板]
                       fetch_and_store.py                     唯讀查詢 (anon key)
```

## 功能

- **後端**：GitHub Actions 於台灣時間 02:45 起每 3 小時（02:45、05:45、08:45……）自動執行，也可手動觸發；抓取預報、清洗後 upsert 至 Supabase，記錄 `updated_at`，並把最後成功更新時間寫入 `pipeline_status`。
- **告警**：只有排程會推播 Telegram，且只在你啟用的發送時段（08:45、14:45、20:45）發送；**預設所有縣市關閉（不發送）**。每個縣市可各自設定降雨／低溫／高溫三個條件的開關與門檻（預設 60％／12°C／35°C）。手動更新只更新資料、不推播。設定存在資料庫，`anon` 讀不到也寫不了；可用儀表板標題列的「⚙️ 告警設定」按鈕（輸入管理者密碼後在視窗中調整），也可以用 Supabase SQL Editor（見下方「啟用告警」）。
- **前端**：地區／縣市互斥篩選（選其一會清除另一個）；重點摘要；Folium 地圖（標記顯示溫度，手機雙指才操作地圖、單指滑動捲動頁面，電腦按 Ctrl 才縮放，另有 ＋／－ 按鈕）；氣溫與降雨機率趨勢圖（全台依地區、地區依縣市各一種顏色，氣象署未提供的降雨機率補 0 並以空心點標示）；明細表格與「後續時段」（每縣市目前時段之後 2 個時段）；天氣圖示區分日夜；「立即更新」按鈕：距上次成功更新（排程或手動，以 `pipeline_status` 為準）滿 20 分鐘才可按，觸發後 60 秒自動重整頁面；排程不受此限制。

## 目錄結構

`HW1/` 是 repo 根目錄，程式碼與文件放在 `forecast/`；`.github/`、`.gitignore`、`requirements.txt` 只在根目錄各留一份。

```text
HW1/
├── .github/workflows/weather_worker.yml   # 排程與手動觸發流程一
├── .gitignore
├── requirements.txt                       # 須在根目錄，Streamlit Cloud 才偵測得到
└── forecast/
    ├── src/tw_forecast/ # 正式程式碼：backend/（流程一）、frontend/（流程二）、config.py
    ├── scripts/         # fetch_and_store.py（流程一入口，Actions 執行）
    ├── tests/           # pytest 單元與整頁測試（不連網、不連資料庫）
    ├── checks/          # 需真實連線的手動檢查：check_cwa_api、check_rls、check_admin_rpc、check_notify
    ├── tools/           # make_admin_hash、get_telegram_chat_id
    ├── sql/             # init_supabase.sql（weather_forecasts、pipeline_status、RLS、updated_at、時區）
    ├── streamlit_app/   # app.py（流程二入口）
    ├── .streamlit/      # secrets.toml.example
    ├── ARCHITECTURE.md  # 每個檔案的功能、資料流與「想改某功能該看哪裡」
    ├── SPECIFICATION.md
    └── README.md
```

## 本機環境建置

以下指令都在 `forecast/` 目錄下執行。

1. 安裝 Python 3.11+，建立虛擬環境並安裝套件：
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r ../requirements.txt
   ```
2. 後端金鑰：複製 `.env.example` 為 `.env`，填入 `WEATHER_API_KEY`、`SUPABASE_URL`、`SUPABASE_KEY`（`service_role`）等值。`.env` 不會被 commit。
3. 驗證氣象署 API 並存下範例回應：
   ```powershell
   python checks/check_cwa_api.py            # 存到 samples/F-D0047-091.json（不會被 commit）
   ```
4. 於 Supabase SQL Editor 執行 `sql/init_supabase.sql` 建表（可重複執行；也會補上 `updated_at` 欄位、觸發器、台灣時區設定，並建立 `pipeline_status` 表）。之後可執行 `python checks/check_rls.py` 驗證 `anon` 可讀不可寫。
5. 設定 Telegram 推播（只推給自己）：
   1. 在 Telegram 搜尋 **@BotFather** → `/newbot` → 取得 token，寫入 `.env` 的 `TELEGRAM_BOT_TOKEN`（**token 不要貼到聊天或 commit**）。
   2. 打開你的機器人，按 **Start**（機器人必須先被你啟動才能傳訊息給你）。
   3. 取得 chat_id：`python tools/get_telegram_chat_id.py`（加 `--write` 可自動寫入 `.env`）。
   4. 確認手機收得到：`python checks/check_notify.py`（加 `--dry-run` 只印出訊息內容）。
6. 啟用告警（在 Supabase SQL Editor 執行；範例也在 `sql/init_supabase.sql` 檔尾）：
   ```sql
   UPDATE public.alert_city_settings SET enabled = true WHERE location_name = '臺北市';          -- 啟用臺北市
   UPDATE public.alert_city_settings SET rain_threshold = 0 WHERE location_name = '臺北市';       -- 降雨門檻 0：一定符合，用來測試推播
   UPDATE public.alert_city_settings SET min_temp_enabled = false WHERE location_name = '臺北市'; -- 關閉低溫條件
   UPDATE public.alert_slot_settings SET enabled = false WHERE slot = '14:45';                  -- 不在 14:45 發送
   ```
   設定在下一個排程時槽生效。判斷視窗為「本次發送時槽到下一個啟用的發送時槽之前」，含進行中的預報時段（訊息標示進行中／即將開始）。
7. 管理者密碼與設定面板（一次性設定）：
   1. 在 Supabase SQL Editor 執行 `sql/init_supabase.sql`（會建立 `private` schema、密碼表與兩個驗證函式）。
   2. 相容性檢查：`pip install bcrypt`（只在本機使用，不在 `requirements.txt`），執行 `python tools/make_admin_hash.py --selftest`，把印出的 SQL 貼到 SQL Editor 執行，結果應為 `true`。
   3. 產生密碼雜湊：執行 `python tools/make_admin_hash.py`，輸入 12 碼以上、大小寫加數字的隨機密碼（輸入時不顯示、不會存檔），把印出的 `INSERT` SQL 貼到 SQL Editor 執行。**不要把密碼明文貼進 SQL Editor。**
   4. 驗證：`python checks/check_admin_rpc.py`（輸入密碼）；再到儀表板標題列按「⚙️ 告警設定」實際登入（先把輸入法切成英文）。若顯示密碼錯誤，可用 `python tools/make_admin_hash.py --verify`（貼上資料庫裡的 `password_hash`、輸入密碼）在本機分辨是「密碼輸入不一致」還是「雜湊本身有問題」；`getpass` 在某些終端機不支援貼上，請手動輸入密碼。
   5. 忘記密碼：重新執行第 3 步寫入新的雜湊值即可（頁面上沒有改密碼功能）。
8. 試跑流程一（不寫入資料庫、不推播）：
   ```powershell
   python scripts/fetch_and_store.py --dry-run                 # 打 API
   python scripts/fetch_and_store.py --dry-run --from-sample   # 讀 samples/ 離線測試
   python scripts/fetch_and_store.py                           # 正式：寫入 Supabase（本機視為手動，不推播；要測推播可設 GITHUB_EVENT_NAME=schedule）
   ```
9. 前端本機執行：複製 `.streamlit/secrets.toml.example` 為 `.streamlit/secrets.toml`，填入 `SUPABASE_URL` 與 `SUPABASE_ANON_KEY`（**只放 `anon` key，不可放 `service_role`**），再啟動：
   ```powershell
   streamlit run streamlit_app/app.py         # http://localhost:8501
   ```
   要使用「立即更新」按鈕，另需 `GH_REPO`（`owner/repo`）與 `GH_DISPATCH_TOKEN`（僅授權 Actions 讀寫的 fine-grained PAT）。

## 測試

```powershell
pip install -r ../requirements-dev.txt   # 只裝 pytest（開發用，不在 requirements.txt）
python -m pytest                          # 在 forecast/ 執行；不連網、不連資料庫、不需要 .env 或 samples/
```

- `tests/`：自動測試（後端與前端的純邏輯、假資料庫、整頁煙霧測試）。
- `checks/`：需要真實連線的手動檢查（CWA、Supabase RLS、管理者函式、Telegram），不屬於自動測試。

## 部署

**GitHub Actions（後端）**：到 repo 的 Settings → Secrets and variables → Actions 新增 `WEATHER_API_KEY`、`SUPABASE_URL`、`SUPABASE_KEY`；要啟用告警再加 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID`（沒設也能執行，只是略過推播）。Secret 的值直接貼上，**不要加引號**。設好後到 Actions 分頁手動執行一次確認。

**Streamlit Community Cloud（前端）**：
1. 於 [share.streamlit.io](https://share.streamlit.io) 選此 repo、分支 `main`，**Main file path** 填 `forecast/streamlit_app/app.py`。
2. Advanced settings → Secrets 以 TOML 格式貼上 `SUPABASE_URL`、`SUPABASE_ANON_KEY`（要用「立即更新」再加 `GH_REPO`、`GH_DISPATCH_TOKEN`）。
3. 之後 push 到 `main` 會自動重新部署；資料由 GitHub Actions 更新，不必重新部署。

## 常見問題

| 現象 | 原因與處理 |
| :--- | :--- |
| 啟用了縣市卻收不到告警 | 依序確認：① 已在 Supabase 執行新版 `init_supabase.sql`；② 該縣市 `enabled = true`；③ 目前排程時槽在啟用的發送時段（08:45／14:45／20:45）；④ 條件有符合（可暫時把降雨門檻設為 0 測試）；⑤ GitHub Secrets 有 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`。日誌會寫明略過的原因。 |
| 「⚙️ 告警設定」登入時顯示「設定功能尚未啟用」 | 資料庫函式不存在：請在 Supabase 執行新版 `sql/init_supabase.sql`。若顯示「密碼錯誤」但確定密碼正確，代表還沒寫入雜湊值（README 上方第 7 步的第 3 點）。 |
| 「立即更新」按鈕是灰的 | 距上次成功更新不滿 20 分鐘（畫面會顯示還需等幾分鐘），或讀不到 `pipeline_status`（未執行新的 SQL、資料庫連線問題）而一律不放行。排程不受影響。 |
| `ModuleNotFoundError: streamlit_folium` | Streamlit Cloud 找不到 `requirements.txt`。它只找主程式所在目錄與 repo 根目錄，須放在根目錄。 |
| 「尚未設定 SUPABASE_URL / SUPABASE_ANON_KEY」 | 雲端要在 Secrets 設定；本機要建立 `.streamlit/secrets.toml`（不會被 commit）。 |
| 儀表板縣市數是 44 而不是 22 | 資料表裡有新舊兩批時段重疊的資料（氣象署第一個時段會隨時間縮短）。前端只取最新一批，因此需要 workflow 至少成功寫入一次帶 `updated_at` 的資料。 |
| `updated_at` 顯示 UTC | 於 Supabase 執行 `sql/init_supabase.sql`（含 `ALTER DATABASE ... SET timezone`），並用新的連線／SQL 分頁查詢。 |
| 本機 `ImportError`（改了程式卻沒生效） | 長時間執行的 Streamlit 會快取舊模組，重啟 `streamlit run` 即可。 |
| Actions 出現 Node.js 20 deprecated 警告 | 只是提醒 `checkout@v4`、`setup-python@v5` 之後會改用 Node 24，不影響執行。 |
