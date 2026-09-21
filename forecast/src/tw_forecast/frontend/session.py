"""Streamlit 連線與機密：讀取 secrets、建立（並快取）Supabase 連線。

secrets 由 Streamlit Community Cloud 的 Secrets 設定，本機則是 .streamlit/secrets.toml（不會被 commit）。
連線物件用 st.cache_resource 重用；查詢結果不快取（見 repository.py）。
"""
import streamlit as st
from supabase import Client, create_client

from tw_forecast.frontend.repository import now_taipei  # noqa: F401  重新匯出，views 統一從 session 取現在時間


def secret(name: str) -> str | None:
    """讀取 st.secrets 的值；沒有 secrets 檔或沒有這個鍵一律回傳 None。"""
    try:
        return st.secrets.get(name)
    except Exception:  # 沒有 secrets.toml 時 st.secrets 會拋例外
        return None


def is_configured() -> bool:
    """資料庫連線所需的兩個 secrets 是否都已設定。"""
    return bool(secret("SUPABASE_URL") and secret("SUPABASE_ANON_KEY"))


@st.cache_resource
def get_client() -> Client:
    """建立 Supabase 連線（anon key，權限由 RLS 控制；不可放 service_role）。"""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])
