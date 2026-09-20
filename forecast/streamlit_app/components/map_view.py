"""Folium 台灣地圖：依縣市座標與平均氣溫繪製色階標記。"""
import folium
import pandas as pd

# (顏色, 圖例文字)；規格 §8.1：<20 藍綠、20~25 綠、25~30 橙黃、>30 鮮紅
BANDS = [
    ("#17a2b8", "&lt; 20°C"),
    ("#2f9e44", "20 ~ 25°C"),
    ("#f59f00", "25 ~ 30°C"),
    ("#e03131", "&gt; 30°C"),
]


def temp_color(temp: float) -> str:
    if temp < 20:
        return BANDS[0][0]
    if temp <= 25:
        return BANDS[1][0]
    if temp <= 30:
        return BANDS[2][0]
    return BANDS[3][0]


def display_temp(df: pd.DataFrame) -> pd.Series:
    """avg_temp 為 NULL 時退回 (min_temp + max_temp) / 2。"""
    return df["avg_temp"].fillna((df["min_temp"] + df["max_temp"]) / 2)


def build_map(df: pd.DataFrame) -> folium.Map:
    """df 每縣市一列，需含 location_name、latitude、longitude 及溫度欄位。"""
    m = folium.Map(location=[23.7, 121.0], zoom_start=7, tiles="OpenStreetMap")
    temps = display_temp(df)
    for (_, row), temp in zip(df.iterrows(), temps):
        if pd.isna(row["latitude"]) or pd.isna(row["longitude"]) or pd.isna(temp):
            continue
        rain = "—" if pd.isna(row.get("rain_probability")) else f"{int(row['rain_probability'])}%"
        tip = (f"<b>{row['location_name']}</b><br>平均 {temp:.1f}°C<br>"
               f"{row.get('weather_condition') or '—'}<br>降雨機率 {rain}")
        folium.CircleMarker(
            [row["latitude"], row["longitude"]], radius=14, color="#ffffff", weight=2,
            fill=True, fill_color=temp_color(temp), fill_opacity=0.9,
            tooltip=folium.Tooltip(tip),
        ).add_to(m)
    legend = "".join(f'<div><span style="background:{c};display:inline-block;width:12px;height:12px;'
                     f'border-radius:50%;margin-right:6px"></span>{label}</div>' for c, label in BANDS)
    m.get_root().html.add_child(folium.Element(
        '<div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:#fff;padding:8px 12px;'
        'border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);font-size:12px;color:#222">'
        f'<b>平均氣溫</b>{legend}</div>'))
    return m
