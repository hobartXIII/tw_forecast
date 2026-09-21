"""後端的資料庫存取（Supabase，以 service_role 金鑰）。

輸入：解析後的預報列、流程狀態。輸出：寫入 weather_forecasts / pipeline_status；讀取告警設定。
"""
import os
import sys

from tw_forecast.backend import alerts
from tw_forecast.backend.errors import AbortRun
from tw_forecast.backend.security import mask_secrets
from tw_forecast.config import (ALERT_CITY_TABLE, ALERT_SLOT_TABLE, FORECAST_CONFLICT_KEY, FORECAST_TABLE,
                                STATUS_TABLE)


def create_supabase_client():
    """依環境變數 SUPABASE_URL / SUPABASE_KEY 建立連線；缺任一個拋 AbortRun。"""
    from supabase import create_client  # 延遲載入：離線 dry-run 不需要安裝或連線
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise AbortRun("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


class ForecastRepository:
    """weather_forecasts 表。"""

    def __init__(self, client):
        self._sb = client

    def upsert(self, records: list[dict]) -> None:
        """單次 upsert = 單一交易，前端不會讀到寫一半的批次。"""
        self._sb.table(FORECAST_TABLE).upsert(records, on_conflict=FORECAST_CONFLICT_KEY).execute()


class StatusRepository:
    """pipeline_status 表：記錄排程／手動各自最後一次執行結果，前端「立即更新」的間隔限制依此判斷。"""

    def __init__(self, client):
        self._sb = client

    def record(self, trigger: str, status: str, stamp: str, error: str | None = None) -> None:
        """更新狀態列。失敗時不動 last_success_at，讓失敗不會鎖住手動更新。

        寫入狀態失敗只警告，不影響主流程（資料更新才是主要任務）。
        """
        row = {"trigger_type": trigger, "last_run_at": stamp, "last_status": status, "last_error": error}
        if status == "success":
            row["last_success_at"] = stamp
        try:
            self._sb.table(STATUS_TABLE).upsert(row, on_conflict="trigger_type").execute()
        except Exception as exc:
            print(f"[警告] 無法更新 {STATUS_TABLE}：{exc}", file=sys.stderr)


class AlertSettingsRepository:
    """alert_city_settings / alert_slot_settings 表（只有 service_role 讀得到）。"""

    def __init__(self, client):
        self._sb = client

    def load(self) -> alerts.AlertSettings | None:
        """讀取並驗證告警設定。讀不到（表不存在、連線失敗）回傳 None → 呼叫端不發送（fail closed）。"""
        try:
            cities = self._sb.table(ALERT_CITY_TABLE).select("*").execute().data
            slots = self._sb.table(ALERT_SLOT_TABLE).select("*").execute().data
        except Exception as exc:
            print(f"[警告] 無法讀取告警設定，略過推播：{mask_secrets(str(exc))[:200]}", file=sys.stderr)
            return None
        settings, warnings = alerts.parse_settings(cities, slots)
        for warning in warnings:
            print(f"[警告] {warning}", file=sys.stderr)
        return settings
