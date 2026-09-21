"""趨勢與明細的分頁區塊：依範圍決定有哪些分頁，並交給各分頁的畫面函式。"""
import pandas as pd
import streamlit as st

from tw_forecast.frontend.repository import ForecastQuery
from tw_forecast.frontend.scope import Scope
from tw_forecast.frontend.views.date_query import render_date_tab
from tw_forecast.frontend.views.tables_view import render_next_tab, render_table_tab
from tw_forecast.frontend.views.trends import render_rain_tab, render_temperature_tab


def render_tabs(scope: Scope, cur: pd.DataFrame, fc: pd.DataFrame | None, query: ForecastQuery,
                now, period_start: pd.Timestamp) -> None:
    """輸入：範圍、目前時段資料 cur、趨勢用預報 fc（None 表示沒有）、資料庫查詢物件、現在時間、目前時段起點。

    單一縣市有 4 個分頁；全台／地區在明細右邊多一個「後續時段」分頁。
    """
    if scope.city:
        tab_temp, tab_rain, tab_table, tab_date = st.tabs(
            ["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 一週預報", "📅 日期查詢"])
        tab_next = None
    else:
        tab_temp, tab_rain, tab_table, tab_next, tab_date = st.tabs(
            ["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 目前時段明細", "🕒 後續時段", "📅 日期查詢"])

    with tab_temp:
        render_temperature_tab(scope, fc, now)
    with tab_rain:
        render_rain_tab(scope, fc, now)
    with tab_table:
        render_table_tab(scope, cur, fc)
    if tab_next is not None:
        with tab_next:
            render_next_tab(scope, fc, period_start)
    with tab_date:
        render_date_tab(scope, query, now)
