# 台灣天氣預報與自動化通報系統

抓取中央氣象署 `F-D0047-091`（未來 1 週各縣市預報），存入 Supabase，並以 Streamlit 儀表板呈現；符合條件時推播 Google Chat 告警。完整規格見 [SPECIFICATION.md](SPECIFICATION.md)。

```text
[中央氣象署 API] → [GitHub Actions 每 6 小時] → [Supabase] → [Streamlit 儀表板]
                       fetch_and_store.py                     唯讀查詢 (anon key)
```

## 功能

- **後端**：GitHub Actions 每 6 小時（UTC；台灣 02/08/14/20 時）或手動觸發，抓取預報、清洗後 upsert 至 Supabase，並記錄 `updated_at`；未來 6 小時內開始的時段若降雨機率 ≥ 60% 或極端溫度，推播 Google Chat。
- **前端**：地區／縣市連動篩選；重點摘要；Folium 地圖（標記顯示溫度，滾輪縮放已關閉，以 ＋／－ 按鈕縮放）；氣溫與降雨機率趨勢圖（全台依地區、地區依縣市各一種顏色）；明細表格；「立即更新」按鈕（觸發 workflow）。

## 目錄結構

`HW1/` 是 repo 根目錄，程式碼與文件放在 `forecast/`；`.github/`、`.gitignore`、`requirements.txt` 只在根目錄各留一份。

```text
HW1/
├── .github/workflows/weather_worker.yml   # 排程與手動觸發流程一
├── .gitignore
├── requirements.txt                       # 須在根目錄，Streamlit Cloud 才偵測得到
└── forecast/
    ├── scripts/         # fetch_and_store.py（流程一）、check_cwa_api.py、check_rls.py
    ├── sql/             # init_supabase.sql（建表、RLS、updated_at、時區）
    ├── streamlit_app/   # app.py（流程二）與 components/
    ├── .streamlit/      # secrets.toml.example
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
   python scripts/check_cwa_api.py            # 存到 samples/F-D0047-091.json（不會被 commit）
   ```
4. 於 Supabase SQL Editor 執行 `sql/init_supabase.sql` 建表（可重複執行；也會補上 `updated_at` 欄位、觸發器與台灣時區設定）。
5. 試跑流程一（不寫入資料庫、不推播）：
   ```powershell
   python scripts/fetch_and_store.py --dry-run                 # 打 API
   python scripts/fetch_and_store.py --dry-run --from-sample   # 讀 samples/ 離線測試
   python scripts/fetch_and_store.py                           # 正式：寫入 Supabase 並視情況推播
   ```
6. 前端本機執行：複製 `.streamlit/secrets.toml.example` 為 `.streamlit/secrets.toml`，填入 `SUPABASE_URL` 與 `SUPABASE_ANON_KEY`（**只放 `anon` key，不可放 `service_role`**），再啟動：
   ```powershell
   streamlit run streamlit_app/app.py         # http://localhost:8501
   ```
   要使用「立即更新」按鈕，另需 `GH_REPO`（`owner/repo`）與 `GH_DISPATCH_TOKEN`（僅授權 Actions 讀寫的 fine-grained PAT）。

## 部署

**GitHub Actions（後端）**：到 repo 的 Settings → Secrets and variables → Actions 新增 `WEATHER_API_KEY`、`SUPABASE_URL`、`SUPABASE_KEY`；要啟用告警再加 `GOOGLE_CHAT_WEBHOOK`（沒設也能執行，只是略過推播）。Secret 的值直接貼上，**不要加引號**。設好後到 Actions 分頁手動執行一次確認。

**Streamlit Community Cloud（前端）**：
1. 於 [share.streamlit.io](https://share.streamlit.io) 選此 repo、分支 `main`，**Main file path** 填 `forecast/streamlit_app/app.py`。
2. Advanced settings → Secrets 以 TOML 格式貼上 `SUPABASE_URL`、`SUPABASE_ANON_KEY`（要用「立即更新」再加 `GH_REPO`、`GH_DISPATCH_TOKEN`）。
3. 之後 push 到 `main` 會自動重新部署；資料由 GitHub Actions 更新，不必重新部署。

## 常見問題

| 現象 | 原因與處理 |
| :--- | :--- |
| `ModuleNotFoundError: streamlit_folium` | Streamlit Cloud 找不到 `requirements.txt`。它只找主程式所在目錄與 repo 根目錄，須放在根目錄。 |
| 「尚未設定 SUPABASE_URL / SUPABASE_ANON_KEY」 | 雲端要在 Secrets 設定；本機要建立 `.streamlit/secrets.toml`（不會被 commit）。 |
| 儀表板縣市數是 44 而不是 22 | 資料表裡有新舊兩批時段重疊的資料（氣象署第一個時段會隨時間縮短）。前端只取最新一批，因此需要 workflow 至少成功寫入一次帶 `updated_at` 的資料。 |
| `updated_at` 顯示 UTC | 於 Supabase 執行 `sql/init_supabase.sql`（含 `ALTER DATABASE ... SET timezone`），並用新的連線／SQL 分頁查詢。 |
| 本機 `ImportError`（改了程式卻沒生效） | 長時間執行的 Streamlit 會快取舊模組，重啟 `streamlit run` 即可。 |
| Actions 出現 Node.js 20 deprecated 警告 | 只是提醒 `checkout@v4`、`setup-python@v5` 之後會改用 Node 24，不影響執行。 |
