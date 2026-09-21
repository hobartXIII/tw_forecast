"""命令列入口：把環境變數與參數組成 Pipeline 並執行。

用法（由 scripts/fetch_and_store.py 呼叫）：
    python scripts/fetch_and_store.py                       # 正式執行 (打 API、寫 DB)
    python scripts/fetch_and_store.py --dry-run             # 打 API 但不寫 DB、不推播
    python scripts/fetch_and_store.py --dry-run --from-sample   # 讀 samples/ 離線測試

執行來源由 GitHub Actions 的 GITHUB_EVENT_NAME 判斷：schedule 為排程，其餘（workflow_dispatch、本機）
視為手動。只有排程會推播告警（Telegram）；手動與本機只更新資料。告警的縣市、條件與發送時段由資料庫設定
（alert_city_settings / alert_slot_settings，預設全部縣市關閉＝不發送）；要測試推播格式可用 checks/check_notify.py。
"""
import argparse
import json
import os

from dotenv import load_dotenv

from tw_forecast.backend.cwa_client import CwaClient
from tw_forecast.backend.errors import AbortRun
from tw_forecast.backend.notifier import TelegramNotifier
from tw_forecast.backend.parser import ForecastParser
from tw_forecast.backend.pipeline import Pipeline
from tw_forecast.backend.repository import (AlertSettingsRepository, ForecastRepository, StatusRepository,
                                            create_supabase_client)
from tw_forecast.backend.security import mask_secrets
from tw_forecast.config import ROOT, SAMPLE_PATH


def trigger_type() -> str:
    """GitHub Actions 的 schedule 事件為排程；其餘（workflow_dispatch、本機）一律視為手動。"""
    return "schedule" if os.getenv("GITHUB_EVENT_NAME") == "schedule" else "manual"


def build_pipeline(dry_run: bool, from_sample: bool) -> Pipeline:
    """輸入：命令列旗標與環境變數。輸出：組裝好的 Pipeline（dry-run 不建立資料庫連線）。"""
    if from_sample:
        def fetch_raw() -> dict:
            return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    else:
        fetch_raw = CwaClient(os.getenv("WEATHER_API_KEY")).fetch
    pipeline = Pipeline(fetch_raw=fetch_raw, parser=ForecastParser(), dry_run=dry_run)
    if dry_run:
        return pipeline
    client = create_supabase_client()
    pipeline.forecasts = ForecastRepository(client)
    pipeline.status = StatusRepository(client)
    pipeline.alert_settings = AlertSettingsRepository(client)
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    pipeline.notifier = TelegramNotifier(token, chat_id) if token and chat_id else None
    return pipeline


def main(argv: list[str] | None = None) -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="不寫入資料庫、不推播")
    parser.add_argument("--from-sample", action="store_true", help="讀 samples/ 而非呼叫 API")
    args = parser.parse_args(argv)

    trigger = trigger_type()
    try:
        pipeline = build_pipeline(args.dry_run, args.from_sample)
    except AbortRun as exc:  # 缺 SUPABASE 金鑰：連資料庫都沒有，無從記錄失敗
        raise SystemExit(str(exc)) from None
    try:
        pipeline.run(trigger)
    except Exception as exc:
        # AbortRun 的訊息本身就是完整原因；其他例外加上類型名稱。失敗記錄後照常結束（非 0 退出碼）。
        reason = str(exc) if isinstance(exc, AbortRun) else f"{type(exc).__name__}: {exc}"
        pipeline.record_failure(trigger, mask_secrets(reason))
        if isinstance(exc, AbortRun):
            raise SystemExit(str(exc)) from None
        raise
