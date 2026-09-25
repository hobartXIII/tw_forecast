"""「氣溫趨勢」與「降雨機率」兩個分頁。全台／地區／單一縣市都用同一種折線圖（見 charts.SeriesChart）。"""
import pandas as pd
import streamlit as st

from tw_forecast.frontend import update_gate
from tw_forecast.frontend.charts import TEMP_LINE_COLORS, TEMP_LINE_COLUMNS, SeriesChart
from tw_forecast.frontend.rain import RAIN_ALERT
from tw_forecast.frontend.scope import Scope

TEMP_METRICS = {"最高溫": "max_temp", "最低溫": "min_temp", "平均溫": "avg"}  # 地區／全台的單選鈕


def render_temperature_tab(scope: Scope, fc: pd.DataFrame | None, now) -> None:
    """氣溫趨勢。單一縣市：最高／平均／最低三條線在同一張圖；地區與全台：單選鈕選一個指標，每個系列一條線。"""
    if fc is None:
        st.info(f"沒有未來預報資料（資料可能已過期），{update_gate.stale_hint()}。")
        return
    if scope.level == "city":
        st.caption(f"{scope.label}｜最高溫、平均溫、最低溫｜色帶為最低～最高溫的範圍，點圖例可強調單一線條，虛線為現在")
        data = pd.concat([scope.series_data(fc, col)[0].assign(系列=name)
                          for name, col in TEMP_LINE_COLUMNS.items()])
        if data["值"].dropna().empty:
            st.info("沒有可繪製的氣溫資料。")
        else:
            chart = SeriesChart("氣溫 (°C)", list(TEMP_LINE_COLUMNS), zero=True, colors=TEMP_LINE_COLORS,
                                band=("最低溫", "最高溫"))
            st.altair_chart(chart.build(data, now), width="stretch")
        return
    metric_label = st.radio("氣溫指標", list(TEMP_METRICS), horizontal=True, key="metric")
    st.caption(f"{scope.label}｜{metric_label}｜每種顏色一條線，點圖例可強調單一系列，虛線為現在")
    data, order = scope.series_data(fc, TEMP_METRICS[metric_label])
    if data["值"].dropna().empty:
        st.info("沒有可繪製的氣溫資料。")
    else:
        st.altair_chart(SeriesChart(f"{metric_label} (°C)", order, zero=True).build(data, now), width="stretch")


def render_rain_tab(scope: Scope, fc: pd.DataFrame | None, now) -> None:
    """降雨機率。紅色虛線為告警門檻；氣象署未提供的時段補 0 並以空心點標示。"""
    if fc is None or fc["rain_probability"].dropna().empty:
        st.info("沒有降雨機率資料（遠期時段氣象署未提供）。")
    else:
        st.caption(f"{scope.label}｜12 小時降雨機率（紅色虛線為 {RAIN_ALERT}% 告警門檻，超過者的點放大並加紅框）")
        data, order = scope.series_data(fc, "rain_probability")
        chart = SeriesChart("降雨機率 (%)", order, zero=True, threshold=RAIN_ALERT, fill_zero=True)
        st.altair_chart(chart.build(data, now), width="stretch")
    st.caption("空心點：氣象署未提供該時段的降雨機率（通常是遠期），圖上以 0 顯示，並非預報 0%；"
               "明細表格與摘要仍顯示為「—」。")
