"""明細表格相關分頁：一週預報／目前時段明細、後續時段。表格內容由 tables.py 整理，這裡只負責顯示。"""
import pandas as pd
import streamlit as st

from tw_forecast.frontend import update_gate
from tw_forecast.frontend.scope import Scope
from tw_forecast.frontend.tables import make_table, next_periods
from tw_forecast.frontend.temperature import text_color

TEMP_COLUMNS = ["最低 (°C)", "最高 (°C)", "平均 (°C)"]


def show_table(table: pd.DataFrame, drop: list[str]) -> None:
    """顯示明細表格：溫度欄依級距上色，降雨機率以進度條呈現。drop 為要隱藏的欄位。"""
    styled = table.drop(columns=drop).style.map(
        lambda v: f"color:{text_color(v)};font-weight:700" if text_color(v) else "", subset=TEMP_COLUMNS)
    st.dataframe(
        styled, width="stretch", hide_index=True,
        column_config={
            "最低 (°C)": st.column_config.NumberColumn(format="%.0f"),
            "最高 (°C)": st.column_config.NumberColumn(format="%.0f"),
            "平均 (°C)": st.column_config.NumberColumn(format="%.1f"),
            "降雨機率": st.column_config.ProgressColumn(format="%d%%", min_value=0, max_value=100),
        })
    st.caption("點欄位標題可排序；降雨機率為空白表示氣象署該時段未提供；天氣圖示依時段區分日間（☀️）與夜間（🌙）。")


def render_table_tab(scope: Scope, cur: pd.DataFrame, fc: pd.DataFrame | None) -> None:
    """單一縣市：列出該縣市所有尚未結束的時段（一週預報），與趨勢圖對照；其他範圍：目前時段的各縣市明細。"""
    if scope.city:
        st.caption(f"{scope.city}｜未來一週的預報（每個時段約 12 小時）")
        if fc is None:
            st.info(f"沒有未來預報資料（資料可能已過期），{update_gate.stale_hint()}。")
        else:
            show_table(make_table(fc.sort_values("forecast_time_start"), dated=True), scope.table_drop_columns())
    else:
        show_table(make_table(cur, dated=False), scope.table_drop_columns())


def render_next_tab(scope: Scope, fc: pd.DataFrame | None, after: pd.Timestamp) -> None:
    """每個縣市「目前時段」之後的 2 個時段（僅全台／地區有這個分頁）。"""
    st.caption("每個縣市「目前時段」之後的 2 個時段（依縣市、時間排序）")
    later = next_periods(fc, after) if fc is not None else None
    if later is None or later.empty:
        st.info(f"沒有後續時段的預報資料（資料可能已過期），{update_gate.stale_hint()}。")
    else:
        show_table(make_table(later, dated=True), scope.table_drop_columns())
