"""Supabase 唯讀查詢（使用 anon key，權限由 RLS 控制）。

查詢結果一律不快取（見 SPECIFICATION.md §8.1）；只重用連線物件。
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from supabase import Client, create_client

TABLE = "weather_forecasts"
STATUS_TABLE = "pipeline_status"
TZ = ZoneInfo("Asia/Taipei")
TIME_COLUMNS = ["forecast_time_start", "forecast_time_end", "updated_at"]
MAX_ROWS = 1000  # Supabase 單次查詢上限


def now_taipei() -> datetime:
    return datetime.now(TZ)


@st.cache_resource
def get_client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])


def _to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in TIME_COLUMNS:
        if col in df:
            df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(TZ)
    return df


def _latest_batch(df: pd.DataFrame) -> pd.DataFrame:
    """只保留最新一批寫入的資料。

    每次流程一都以同一個 updated_at 寫入整批預報；但 CWA 第一個時段會隨時間縮短
    （如 06:00~18:00 → 12:00~18:00），主鍵含 end，舊列會留在表中並與新列重疊。
    資料表作為歷史存檔保留舊列，前端則只取最新批次以避免重複。
    """
    if df.empty or "updated_at" not in df:
        return df
    return df[df["updated_at"] == df["updated_at"].max()]


def fetch_current(sb: Client, now: datetime) -> pd.DataFrame:
    """「目前時段」：start <= now < end；沒有則取最接近現在的最新時段。"""
    iso = now.isoformat()
    rows = (sb.table(TABLE).select("*")
            .lte("forecast_time_start", iso).gt("forecast_time_end", iso)
            .limit(MAX_ROWS).execute().data)
    if not rows:  # 先找最近一個已開始的時段，再找最近一個未開始的
        for query in (
            sb.table(TABLE).select("*").lte("forecast_time_start", iso)
              .order("forecast_time_start", desc=True),
            sb.table(TABLE).select("*").gt("forecast_time_start", iso)
              .order("forecast_time_start"),
        ):
            rows = query.limit(100).execute().data
            if rows:
                rows = [r for r in rows if r["forecast_time_start"] == rows[0]["forecast_time_start"]]
                break
    return _latest_batch(_to_df(rows))


def fetch_forecast(sb: Client, now: datetime) -> pd.DataFrame:
    """尚未結束的所有時段（未來約 7 天，全臺約 330 列），依時段排序。"""
    rows = (sb.table(TABLE).select("*")
            .gt("forecast_time_end", now.isoformat())
            .order("forecast_time_start").limit(MAX_ROWS).execute().data)
    return _latest_batch(_to_df(rows))


def fetch_update_status(sb: Client) -> list[dict]:
    """讀 pipeline_status（排程、手動各一列）；時間轉為 Asia/Taipei，讀取失敗會拋例外。"""
    rows = sb.table(STATUS_TABLE).select("*").execute().data
    for row in rows:
        for col in ("last_success_at", "last_run_at"):
            row[col] = pd.to_datetime(row[col], utc=True).tz_convert(TZ) if row.get(col) else None
    return rows


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, TZ)


FULL_PERIOD = pd.Timedelta(hours=12)


def _only_full_periods(df: pd.DataFrame) -> pd.DataFrame:
    """只留完整的 12 小時時段（06:00~18:00、18:00~隔天 06:00）。

    氣象署的第一個時段會隨時間被縮短（如 06:00~18:00 → 12:00~18:00），縮短後是不同主鍵的另一列，
    日期查詢不提供這些被縮短的資料；完整時段的那一列是縮短之前寫入的，不會被覆蓋。
    """
    return df[(df["forecast_time_end"] - df["forecast_time_start"]) == FULL_PERIOD]


def fetch_available_dates(sb: Client, now: datetime, probe_city: str,
                          back: int = 3, ahead: int = 7) -> list[date]:
    """日期查詢的可選日期：今天前 back 天到後 ahead 天之間，資料庫裡有完整 12 小時時段的日期（台灣日期，由小到大）。

    所有縣市在同一批寫入，所以只查一個縣市（probe_city）就能得到日期清單，筆數約 30 而不是數百。
    夜間時段（18:00～隔天 06:00）以「起點」的日期歸屬。
    """
    lo, hi = _day_start(now.date() - timedelta(days=back)), _day_start(now.date() + timedelta(days=ahead + 1))
    rows = (sb.table(TABLE).select("forecast_time_start,forecast_time_end").eq("location_name", probe_city)
            .gte("forecast_time_start", lo.isoformat()).lt("forecast_time_start", hi.isoformat())
            .limit(MAX_ROWS).execute().data)
    df = _to_df(rows)
    if df.empty:
        return []
    return sorted({s.date() for s in _only_full_periods(df)["forecast_time_start"]})


def fetch_day(sb: Client, day: date, cities: list[str]) -> pd.DataFrame:
    """指定日期（起點落在該台灣日期）、指定縣市的完整 12 小時時段，約 22 縣市 × 2 個時段。

    完整時段的主鍵（縣市、起、迄）唯一，不會有重複列，所以不需要另外去重，也不能用 _latest_batch
    （歷史列的 updated_at 不是全表最大值）。
    """
    lo = _day_start(day)
    rows = (sb.table(TABLE).select("*").in_("location_name", cities)
            .gte("forecast_time_start", lo.isoformat()).lt("forecast_time_start", (lo + timedelta(days=1)).isoformat())
            .limit(MAX_ROWS).execute().data)
    df = _to_df(rows)
    return df if df.empty else _only_full_periods(df).reset_index(drop=True)
