# 台灣天氣預報與自動化通報系統

完整規格見 [SPECIFICATION.md](SPECIFICATION.md)。資料來源：中央氣象署 `F-D0047-091`（未來 1 週預報）。

## 環境建置

1. 安裝 Python 3.11+，建立虛擬環境並安裝套件：
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. 建立後端金鑰檔：複製 `.env.example` 為 `.env`，填入 `WEATHER_API_KEY` 等值（`.env` 不會被 commit）。
3. 驗證氣象署 API 並存下範例回應：
   ```powershell
   python scripts/check_cwa_api.py            # 預設 F-D0047-091
   ```
   原始回應存到 `samples/F-D0047-091.json`（不會被 commit），據此確認 SPECIFICATION.md §3.3 的欄位結構。
4. 於 Supabase SQL Editor 執行 `sql/init_supabase.sql` 建表。
5. 前端本地測試：複製 `.streamlit/secrets.toml.example` 為 `.streamlit/secrets.toml` 並填值。
