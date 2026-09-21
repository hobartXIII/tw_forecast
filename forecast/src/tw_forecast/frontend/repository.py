"""Supabase 唯讀查詢（使用 anon key，權限由 RLS 控制）。

輸入：Supabase 連線（client）與查詢條件。輸出：pandas DataFrame（時間欄位已轉成 Asia/Taipei）。
查詢結果一律不快取（見 SPECIFICATION.md §8.1）；只重用連線物件（見 session.get_client）。
本模組不依賴 Streamlit，測試時傳入假的 client 即可。
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from tw_forecast.config import FORECAST_TABLE, STATUS_TABLE

TZ = ZoneInfo("Asia/Taipei")
TIME_COLUMNS = ["forecast_time_start", "forecast_time_end", "updated_at"]
MAX_ROWS = 1000  # Supabase 單次查詢上限
FULL_PERIOD = pd.Timedelta(hours=12)


def now_taipei() -> datetime:
    """現在的台灣時間（tz-aware）。集中在這裡，測試時可替換成固定時間。"""
    return datetime.now(TZ)


def to_dataframe(rows: list[dict]) -> pd.DataFrame:
    """資料庫列 → DataFrame，時間欄位轉成 Asia/Taipei。"""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in TIME_COLUMNS:
        if col in df:
            df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(TZ)
    return df


def latest_batch(df: pd.DataFrame) -> pd.DataFrame:
    """只保留最新一批寫入的資料。

    每次流程一都以同一個 updated_at 寫入整批預報；但 CWA 第一個時段會隨時間縮短
    （如 06:00~18:00 → 12:00~18:00），主鍵含 end，舊列會留在表中並與新列重疊。
    資料表作為歷史存檔保留舊列，前端則只取最新批次以避免重複。
    """
    if df.empty or "updated_at" not in df:
        return df
    return df[df["updated_at"] == df["updated_at"].max()]


def only_full_periods(df: pd.DataFrame) -> pd.DataFrame:
    """只留完整的 12 小時時段（06:00~18:00、18:00~隔天 06:00）。

    氣象署的第一個時段會隨時間被縮短（如 06:00~18:00 → 12:00~18:00），縮短後是不同主鍵的另一列，
    日期查詢不提供這些被縮短的資料；完整時段的那一列是縮短之前寫入的，不會被覆蓋。
    """
    return df[(df["forecast_time_end"] - df["forecast_time_start"]) == FULL_PERIOD]


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, TZ)


class ForecastQuery:
    """儀表板需要的所有讀取查詢。"""

    def __init__(self, client):
        self._sb = client

    def current(self, now: datetime) -> pd.DataFrame:
        """「目前時段」：start <= now < end；沒有則取最接近現在的最新時段。"""
        sb, iso = self._sb, now.isoformat()
        rows = (sb.table(FORECAST_TABLE).select("*")
                .lte("forecast_time_start", iso).gt("forecast_time_end", iso)
                .limit(MAX_ROWS).execute().data)
        if not rows:  # 先找最近一個已開始的時段，再找最近一個未開始的
            for query in (
                sb.table(FORECAST_TABLE).select("*").lte("forecast_time_start", iso)
                  .order("forecast_time_start", desc=True),
                sb.table(FORECAST_TABLE).select("*").gt("forecast_time_start", iso)
                  .order("forecast_time_start"),
            ):
                rows = query.limit(100).execute().data
                if rows:
                    rows = [r for r in rows if r["forecast_time_start"] == rows[0]["forecast_time_start"]]
                    break
        return latest_batch(to_dataframe(rows))

    def forecast(self, now: datetime) -> pd.DataFrame:
        """尚未結束的所有時段（未來約 7 天，全臺約 330 列），依時段排序。"""
        rows = (self._sb.table(FORECAST_TABLE).select("*")
                .gt("forecast_time_end", now.isoformat())
                .order("forecast_time_start").limit(MAX_ROWS).execute().data)
        return latest_batch(to_dataframe(rows))

    def update_status(self) -> list[dict]:
        """讀 pipeline_status（排程、手動各一列）；時間轉為 Asia/Taipei，讀取失敗會拋例外。"""
        rows = self._sb.table(STATUS_TABLE).select("*").execute().data
        for row in rows:
            for col in ("last_success_at", "last_run_at"):
                row[col] = pd.to_datetime(row[col], utc=True).tz_convert(TZ) if row.get(col) else None
        return rows

    def available_dates(self, now: datetime, probe_city: str, back: int = 3, ahead: int = 7) -> list[date]:
        """日期查詢的可選日期：今天前 back 天到後 ahead 天之間，資料庫裡有完整 12 小時時段的日期（台灣日期，由小到大）。

        所有縣市在同一批寫入，所以只查一個縣市（probe_city）就能得到日期清單，筆數約 30 而不是數百。
        夜間時段（18:00～隔天 06:00）以「起點」的日期歸屬。
        """
        lo = _day_start(now.date() - timedelta(days=back))
        hi = _day_start(now.date() + timedelta(days=ahead + 1))
        rows = (self._sb.table(FORECAST_TABLE).select("forecast_time_start,forecast_time_end")
                .eq("location_name", probe_city)
                .gte("forecast_time_start", lo.isoformat()).lt("forecast_time_start", hi.isoformat())
                .limit(MAX_ROWS).execute().data)
        df = to_dataframe(rows)
        if df.empty:
            return []
        return sorted({s.date() for s in only_full_periods(df)["forecast_time_start"]})

    def day(self, day: date, cities: list[str]) -> pd.DataFrame:
        """指定日期（起點落在該台灣日期）、指定縣市的完整 12 小時時段，約 22 縣市 × 2 個時段。

        完整時段的主鍵（縣市、起、迄）唯一，不會有重複列，所以不需要另外去重，也不能用 latest_batch
        （歷史列的 updated_at 不是全表最大值）。
        """
        lo = _day_start(day)
        rows = (self._sb.table(FORECAST_TABLE).select("*").in_("location_name", cities)
                .gte("forecast_time_start", lo.isoformat())
                .lt("forecast_time_start", (lo + timedelta(days=1)).isoformat())
                .limit(MAX_ROWS).execute().data)
        df = to_dataframe(rows)
        return df if df.empty else only_full_periods(df).reset_index(drop=True)
