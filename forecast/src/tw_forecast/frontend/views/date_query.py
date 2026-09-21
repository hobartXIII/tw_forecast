"""「日期查詢」分頁：選一天，只列該天的表格（範圍跟著上方的地區／縣市）；沒有折線圖。"""
import streamlit as st

from tw_forecast.frontend.regions import CITY_ORDER
from tw_forecast.frontend.repository import ForecastQuery
from tw_forecast.frontend.scope import Scope, add_region
from tw_forecast.frontend.tables import make_table
from tw_forecast.frontend.temperature import display_temp
from tw_forecast.frontend.views.tables_view import show_table

WEEKDAYS = "一二三四五六日"


def render_date_tab(scope: Scope, query: ForecastQuery, now) -> None:
    """輸入：資料庫查詢物件與現在時間。可選日期是今天前 3 天到後 7 天內、資料庫有完整時段的日期。"""
    try:
        dates = query.available_dates(now, CITY_ORDER[0])
    except Exception as exc:
        dates = []
        st.error(f"讀取可選日期失敗：{exc}")
    if not dates:
        st.info("資料庫沒有可查詢的日期。")
        return
    picked = st.selectbox(
        "日期（今天前 3 天到後 7 天內、資料庫有資料的日期）", dates, index=None, placeholder="請選擇日期",
        format_func=lambda d: f"{d:%Y-%m-%d}（週{WEEKDAYS[d.weekday()]}）" + ("　今天" if d == now.date() else ""),
        key="query_date")
    if picked is None:
        return
    try:
        day = query.day(picked, scope.cities)
    except Exception as exc:
        st.error(f"讀取 {picked:%Y-%m-%d} 的資料失敗：{exc}")
        return
    if day.empty:
        st.info(f"{picked:%Y-%m-%d} 在此範圍沒有資料。")
        return
    st.caption(f"{scope.label}｜{picked:%Y-%m-%d} 的預報存檔（僅含完整 12 小時時段，不含被縮短的時段；預報值，非實測值；"
               "夜間時段以起點日期歸屬）")
    day = add_region(day)
    day = day.assign(avg=display_temp(day)).sort_values(["order", "forecast_time_start"])
    show_table(make_table(day, dated=True), scope.table_drop_columns())
