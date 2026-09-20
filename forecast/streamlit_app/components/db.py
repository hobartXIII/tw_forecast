"""Supabase 唯讀查詢（使用 anon key，權限由 RLS 控制）。

查詢結果一律不快取（見 SPECIFICATION.md §8.1）；只重用連線物件。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from supabase import Client, create_client

TABLE = "weather_forecasts"
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
