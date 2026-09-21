"""重點摘要：四張玻璃卡片（平均氣溫、最高溫、最低溫、降雨機率）。

輸入：範圍內的「目前時段」資料（含 avg 欄位）與篩選範圍。輸出：畫面。
單一縣市顯示該縣市自己的數值；其他範圍顯示平均與極值（並標出是哪個縣市）。
"""
import pandas as pd
import streamlit as st

from tw_forecast.frontend.formatting import format_value, is_night, weather_icon
from tw_forecast.frontend.scope import Scope
from tw_forecast.frontend.style import card
from tw_forecast.frontend.temperature import colored


def _extreme(cur: pd.DataFrame, column: str, largest: bool) -> tuple[float | None, str]:
    """回傳 (數值, 縣市名)；欄位全為 NULL 時回傳 (None, "")。"""
    valid = cur.dropna(subset=[column])
    if valid.empty:
        return None, ""
    row = valid.loc[valid[column].idxmax() if largest else valid[column].idxmin()]
    return row[column], row["location_name"]


def _temp_card(col, label: str, value, fmt: str = ".0f", aside: str = "") -> None:
    """玻璃卡片，數字依溫度級距上色（st.metric 的數值無法指定顏色）；aside 顯示在數值右側。"""
    col.markdown(card(label, colored(value, format_value(value, "°C", fmt)), aside), unsafe_allow_html=True)


def _plain_card(col, label: str, value: str) -> None:
    """與 _temp_card 同外觀的玻璃卡片，數字不上色（降雨機率）。"""
    col.markdown(card(label, value), unsafe_allow_html=True)


def _with_city(label: str, name: str) -> str:
    """多縣市摘要：標題列在指標名稱後接縣市名（「最高溫　臺中市」），數值放下一行。"""
    return f"{label}　{name}" if name else label


def render_summary(cur: pd.DataFrame, scope: Scope) -> None:
    k1, k2, k3, k4 = st.columns(4)
    if scope.city:  # 單一縣市：直接呈現該縣市自己的數值，天氣現象（圖示與文字）放在「平均氣溫」數值右側
        crow = cur[cur["location_name"] == scope.city].iloc[0]
        weather = crow["weather_condition"] if isinstance(crow["weather_condition"], str) else "—"
        icon = weather_icon(weather, is_night(crow["forecast_time_start"], crow["forecast_time_end"]))
        _temp_card(k1, f"{scope.city} 平均氣溫", crow["avg"], ".1f", f"{icon} {weather}".strip())
        _temp_card(k2, "最高溫", crow["max_temp"])
        _temp_card(k3, "最低溫", crow["min_temp"])
        _plain_card(k4, "降雨機率", format_value(crow["rain_probability"], "%"))
    else:
        hot, hot_city = _extreme(cur, "max_temp", True)
        cold, cold_city = _extreme(cur, "min_temp", False)
        wet, wet_city = _extreme(cur, "rain_probability", True)
        _temp_card(k1, "平均氣溫", cur["avg"].mean(), ".1f")
        _temp_card(k2, _with_city("最高溫", hot_city), hot)
        _temp_card(k3, _with_city("最低溫", cold_city), cold)
        _plain_card(k4, _with_city("最高降雨機率", wet_city), format_value(wet, "%"))
