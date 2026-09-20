"""傳一則範例告警到你的 Telegram，確認 token / chat_id 正確、訊息格式好看。

需要 .env：TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID（可先用 get_telegram_chat_id.py 查詢）。

用法：
    python scripts/test_notify.py --dry-run   # 只印出訊息內容，不傳送
    python scripts/test_notify.py             # 實際傳送到你的 Telegram
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from notifier import NotifyError, build_alert_text, send_telegram

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 範例資料（非真實預報）
SAMPLE = [
    {"location_name": "臺北市", "forecast_time_start": "2026-09-21T06:00:00+08:00",
     "forecast_time_end": "2026-09-21T18:00:00+08:00", "label": "進行中",
     "rain_probability": 70, "min_temp": 25.0, "max_temp": 30.0},
    {"location_name": "新北市", "forecast_time_start": "2026-09-21T06:00:00+08:00",
     "forecast_time_end": "2026-09-21T18:00:00+08:00", "label": "進行中",
     "rain_probability": 65, "min_temp": 24.0, "max_temp": 29.0},
    {"location_name": "基隆市", "forecast_time_start": "2026-09-21T18:00:00+08:00",
     "forecast_time_end": "2026-09-22T06:00:00+08:00", "label": "即將開始",
     "rain_probability": 80, "min_temp": 23.0, "max_temp": 27.0},
]


def main() -> None:
    rich, plain = build_alert_text(SAMPLE, "涵蓋 09/21 08:45～14:45", title="🔔 天氣告警（測試訊息）")
    if "--dry-run" in sys.argv:
        print("--- 訊息內容（純文字版） ---")
        print(plain)
        return
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.exit("請先在 .env 設定 TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID")
    try:
        send_telegram(rich, plain, token, chat_id)
    except NotifyError as exc:
        sys.exit(f"傳送失敗：{exc}")
    print("已傳送測試訊息，請到 Telegram 確認。")


if __name__ == "__main__":
    main()
