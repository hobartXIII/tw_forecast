"""後端使用的常數（不含任何機密；金鑰一律由環境變數提供）。"""
from datetime import timedelta, timezone
from pathlib import Path

# 專案根目錄（forecast/）；本檔位於 forecast/src/tw_forecast/
ROOT = Path(__file__).resolve().parents[2]

# ── 氣象署資料集 ──
DATASET = "F-D0047-091"  # 各縣市未來一週天氣預報
CWA_URL = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{DATASET}"
SAMPLE_PATH = ROOT / "samples" / f"{DATASET}.json"  # --from-sample 離線測試用

# ── 時間 ──
TZ = timezone(timedelta(hours=8))  # 台灣時間 (UTC+8)，不依賴系統時區

# 排程時槽：台灣時間 02:45 起每 3 小時。
# ⚠️ 須與 .github/workflows/weather_worker.yml 的 cron `45 */3 * * *` 一致，修改時兩邊一起改。
SLOT_ANCHOR = (2, 45)
SLOT_INTERVAL = timedelta(hours=3)

# ── 資料庫表名 ──
FORECAST_TABLE = "weather_forecasts"
STATUS_TABLE = "pipeline_status"
ALERT_CITY_TABLE = "alert_city_settings"
ALERT_SLOT_TABLE = "alert_slot_settings"
FORECAST_CONFLICT_KEY = "location_name,forecast_time_start,forecast_time_end"

# 告警可選的發送時段；須與資料庫 alert_slot_settings 的 CHECK 一致
SEND_SLOTS = ("08:45", "14:45", "20:45")

# 失敗訊息會寫進 pipeline_status（前端可讀），因此這些環境變數的值一律要遮蔽
SECRET_ENV_VARS = ("TELEGRAM_BOT_TOKEN", "SUPABASE_KEY", "WEATHER_API_KEY")
