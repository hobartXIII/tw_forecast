"""Folium 台灣地圖：依縣市座標與平均氣溫繪製色階標記（標記內直接顯示溫度）。"""
import folium
import pandas as pd

from .format import is_night, weather_icon

# (顏色, 圖例文字)；規格 §8.1：<20 藍綠、20~25 綠、25~30 橙黃、>30 鮮紅
BANDS = [
    ("#17a2b8", "&lt; 20°C"),
    ("#2f9e44", "20 ~ 25°C"),
    ("#f59f00", "25 ~ 30°C"),
    ("#e03131", "&gt; 30°C"),
]


def _band(temp: float) -> int:
    if temp < 20:
        return 0
    if temp <= 25:
        return 1
    if temp <= 30:
        return 2
    return 3


def temp_color(temp: float) -> str:
    return BANDS[_band(temp)][0]


def _temp_text(value, unit: str = "°C") -> str:
    """整數溫度；NULL 顯示「—」。"""
    return "—" if pd.isna(value) else f"{value:.0f}{unit}"


def display_temp(df: pd.DataFrame) -> pd.Series:
    """avg_temp 為 NULL 時退回 (min_temp + max_temp) / 2。"""
    return df["avg_temp"].fillna((df["min_temp"] + df["max_temp"]) / 2)


def _marker_html(temp: float, state: str = "normal") -> str:
    """state: normal 一般 / selected 被選中（放大加外框）/ dim 未被選中（淡化）。"""
    text_color = "#222" if _band(temp) == 2 else "#fff"  # 橙黃底用深色字才看得清楚
    size = 46 if state == "selected" else 38
    ring = "0 0 0 4px #1c7ed6, 0 2px 6px rgba(0,0,0,.5)" if state == "selected" else "0 1px 4px rgba(0,0,0,.45)"
    opacity = 0.45 if state == "dim" else 1
    return (f'<div style="width:{size}px;height:{size}px;border-radius:50%;background:{temp_color(temp)};'
            f'border:2px solid #fff;box-shadow:{ring};opacity:{opacity};color:{text_color};'
            f'font:700 {14 if state == "selected" else 13}px/{size - 4}px sans-serif;text-align:center">{temp:.0f}°</div>')


def build_map(df: pd.DataFrame, fit: bool = False, highlight: str | None = None) -> folium.Map:
    """df 每縣市一列，需含 location_name、latitude、longitude 及溫度欄位。

    highlight 為縣市名稱時，該縣市放大加外框並置中，其餘縣市淡化但保留作為對照。

    - 滾輪縮放已關閉（避免捲動頁面時誤觸），保留左上角 +/- 按鈕手動縮放。
    - fit=True 時把視野聚焦到目前列出的縣市（選了單一地區時使用）。
    """
    focus = None
    if highlight is not None:
        hit = df[(df["location_name"] == highlight) & df["latitude"].notna() & df["longitude"].notna()]
        if not hit.empty:
            focus = [float(hit["latitude"].iloc[0]), float(hit["longitude"].iloc[0])]
    m = folium.Map(location=focus or [23.7, 121.0], zoom_start=9 if focus else 7, tiles="OpenStreetMap",
                   scrollWheelZoom=False, zoom_control=True)
    temps = display_temp(df)
    points = []
    for (_, row), temp in zip(df.iterrows(), temps):
        if pd.isna(row["latitude"]) or pd.isna(row["longitude"]) or pd.isna(temp):
            continue
        rain = "—" if pd.isna(row.get("rain_probability")) else f"{int(row['rain_probability'])}%"
        weather = row.get("weather_condition")
        night = "forecast_time_start" in row and is_night(row["forecast_time_start"], row["forecast_time_end"])
        tip = (f"<b>{row['location_name']}</b><br>{weather_icon(weather, night)} {weather or '—'}<br>"
               f"平均 {temp:.1f}°C<br>最高 {_temp_text(row['max_temp'])} ｜ 最低 {_temp_text(row['min_temp'])}<br>"
               f"降雨機率 {rain}")
        state = "normal" if highlight is None else ("selected" if row["location_name"] == highlight else "dim")
        half = 23 if state == "selected" else 19
        folium.Marker(
            [row["latitude"], row["longitude"]],
            icon=folium.DivIcon(html=_marker_html(temp, state), icon_size=(half * 2, half * 2), icon_anchor=(half, half)),
            tooltip=folium.Tooltip(tip),
            z_index_offset=1000 if state == "selected" else 0,
        ).add_to(m)
        points.append([row["latitude"], row["longitude"]])
    if focus is None and fit and len(points) > 1:
        lats, lngs = [p[0] for p in points], [p[1] for p in points]
        m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(40, 40), max_zoom=10)
    legend = "".join(f'<div><span style="background:{c};display:inline-block;width:12px;height:12px;'
                     f'border-radius:50%;margin-right:6px"></span>{label}</div>' for c, label in BANDS)
    m.get_root().html.add_child(folium.Element(
        '<div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:#fff;padding:8px 12px;'
        'border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);font-size:12px;color:#222">'
        f'<b>平均氣溫</b>{legend}</div>'))
    return m
