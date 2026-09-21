"""地區與縣市篩選（互斥：選其一會把另一個清回「全部」）。整頁內容跟著選擇更新。"""
import streamlit as st

from tw_forecast.frontend.regions import ALL_CITIES, ALL_REGIONS, CITY_ORDER, REGIONS
from tw_forecast.frontend.scope import Scope


def _on_region_change() -> None:
    st.session_state["city"] = ALL_CITIES  # 選地區 → 縣市回到「全部縣市」


def _on_city_change() -> None:
    st.session_state["region"] = ALL_REGIONS  # 選縣市 → 地區回到「全部地區」


def render_filters() -> Scope:
    """畫兩個下拉選單，回傳目前的篩選範圍。"""
    left, right = st.columns(2)
    region = left.selectbox("地區", [ALL_REGIONS, *REGIONS], key="region", on_change=_on_region_change)
    city_choice = right.selectbox("縣市", [ALL_CITIES, *CITY_ORDER], key="city", on_change=_on_city_change)
    return Scope(region=region, city=None if city_choice == ALL_CITIES else city_choice)
