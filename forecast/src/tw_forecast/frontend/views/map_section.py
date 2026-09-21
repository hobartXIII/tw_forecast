"""平均氣溫地圖區塊。"""
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from tw_forecast.frontend.map_view import TemperatureMap
from tw_forecast.frontend.scope import Scope

MAP_HEIGHT = 520


def render_map(cur: pd.DataFrame, scope: Scope) -> None:
    """輸入：範圍內的「目前時段」資料。單一縣市時放大並加外框，其餘縣市淡化作為對照。"""
    st.subheader("🗺️ 平均氣溫地圖")
    st.caption("手機請用兩指移動或縮放地圖（單指滑動是捲動頁面），電腦按住 Ctrl 再滾動滾輪縮放，"
               "也可用左上角的 ＋／－ 按鈕；滑鼠移到標記上可看詳細資料。"
               + (f"被選的縣市已放大並加外框，其餘{scope.home_region or ''}縣市淡化作為對照。" if scope.city else ""))
    st_folium(TemperatureMap(cur, fit=scope.level == "region", highlight=scope.city).build(),
              height=MAP_HEIGHT, use_container_width=True, returned_objects=[])
