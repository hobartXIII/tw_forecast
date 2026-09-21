"""Folium 台灣地圖：依縣市座標與平均氣溫繪製色階標記（標記內直接顯示溫度）。

輸入：每縣市一列的目前時段資料。輸出：folium.Map（由 views/map_section.py 交給 st_folium 顯示）。
"""
import folium
import pandas as pd

from tw_forecast.frontend.formatting import is_night, weather_icon
from tw_forecast.frontend.temperature import BANDS, band_index, colored, display_temp, temp_color, temp_text

# Leaflet.GestureHandling：手機單指滑動是捲頁面、雙指才操作地圖，電腦滾輪要按 Ctrl 才縮放。
# st_folium 只認元素的 default_js／default_css（不是 header），所以要登記到地圖物件上。
GESTURE_JS = "https://cdn.jsdelivr.net/npm/leaflet-gesture-handling@1.2.2/dist/leaflet-gesture-handling.min.js"
GESTURE_CSS = "https://cdn.jsdelivr.net/npm/leaflet-gesture-handling@1.2.2/dist/leaflet-gesture-handling.min.css"
GESTURE_OPTIONS = {"text": {"touch": "請用兩指移動地圖", "scroll": "按住 Ctrl 並滾動滾輪來縮放地圖",
                            "scrollMac": "按住 ⌘ 並滾動滾輪來縮放地圖"}}

# 地圖底圖（OpenStreetMap）不論主題都是淺色，圖例與提示框固定用淺色玻璃
GLASS_LIGHT = ("background:rgba(255,255,255,.72);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);"
               "border:1px solid rgba(255,255,255,.85);border-radius:12px;box-shadow:0 6px 20px rgba(60,50,30,.22);"
               "color:#222")

TAIWAN_CENTER = [23.7, 121.0]


def marker_html(temp: float, state: str = "normal") -> str:
    """標記的 HTML。state: normal 一般 / selected 被選中（放大加外框）/ dim 未被選中（淡化）。"""
    font_color = "#222" if band_index(temp) == 2 else "#fff"  # 橙黃底用深色字才看得清楚
    size = 46 if state == "selected" else 38
    ring = "0 0 0 4px #1c7ed6, 0 2px 6px rgba(0,0,0,.5)" if state == "selected" else "0 1px 4px rgba(0,0,0,.45)"
    opacity = 0.45 if state == "dim" else 1
    return (f'<div style="width:{size}px;height:{size}px;border-radius:50%;background:{temp_color(temp)};'
            f'border:2px solid #fff;box-shadow:{ring};opacity:{opacity};color:{font_color};'
            f'font:700 {14 if state == "selected" else 13}px/{size - 4}px sans-serif;text-align:center">{temp:.0f}°</div>')


def tooltip_html(row: pd.Series, temp: float) -> str:
    """滑鼠移到標記上的提示：縣市、天氣、平均／最高／最低溫（依級距上色）與降雨機率。"""
    rain = "—" if pd.isna(row.get("rain_probability")) else f"{int(row['rain_probability'])}%"
    weather = row.get("weather_condition")
    night = "forecast_time_start" in row and is_night(row["forecast_time_start"], row["forecast_time_end"])
    return (f"<b>{row['location_name']}</b><br>{weather_icon(weather, night)} {weather or '—'}<br>"
            f"平均 {colored(temp, f'{temp:.1f}°C')}<br>"
            f"最高 {colored(row['max_temp'], temp_text(row['max_temp']))} ｜ "
            f"最低 {colored(row['min_temp'], temp_text(row['min_temp']))}<br>"
            f"降雨機率 {rain}")


def legend_html() -> str:
    """左下角的平均氣溫圖例。"""
    items = "".join(f'<div><span style="background:{c};display:inline-block;width:12px;height:12px;'
                    f'border-radius:50%;margin-right:6px"></span>{label}</div>' for c, label in BANDS)
    return (f'<div style="position:fixed;bottom:24px;left:24px;z-index:9999;{GLASS_LIGHT};padding:8px 12px;'
            f'font-size:12px"><b>平均氣溫</b>{items}</div>')


class TemperatureMap:
    """依目前時段資料建立地圖。

    df 每縣市一列，需含 location_name、latitude、longitude 及溫度欄位。
    highlight 為縣市名稱時，該縣市放大加外框並置中，其餘縣市淡化但保留作為對照。
    fit=True 時把視野聚焦到目前列出的縣市（選了單一地區時使用）。
    """

    def __init__(self, df: pd.DataFrame, fit: bool = False, highlight: str | None = None):
        self.df, self.fit, self.highlight = df, fit, highlight

    def _focus(self) -> list[float] | None:
        """被選縣市的座標；沒選或查不到座標回傳 None。"""
        if self.highlight is None:
            return None
        df = self.df
        hit = df[(df["location_name"] == self.highlight) & df["latitude"].notna() & df["longitude"].notna()]
        return [float(hit["latitude"].iloc[0]), float(hit["longitude"].iloc[0])] if not hit.empty else None

    def _state(self, city: str) -> str:
        if self.highlight is None:
            return "normal"
        return "selected" if city == self.highlight else "dim"

    def build(self) -> folium.Map:
        focus = self._focus()
        m = folium.Map(location=focus or TAIWAN_CENTER, zoom_start=9 if focus else 7, tiles="OpenStreetMap",
                       zoom_control=True, gestureHandling=True, gestureHandlingOptions=GESTURE_OPTIONS)
        # 複製一份清單再附加，避免改到 folium 的類別屬性
        m.default_js = [*m.default_js, ("gesture_handling", GESTURE_JS)]
        m.default_css = [*m.default_css, ("gesture_handling_css", GESTURE_CSS)]
        points = []
        for (_, row), temp in zip(self.df.iterrows(), display_temp(self.df)):
            if pd.isna(row["latitude"]) or pd.isna(row["longitude"]) or pd.isna(temp):
                continue
            state = self._state(row["location_name"])
            half = 23 if state == "selected" else 19
            folium.Marker(
                [row["latitude"], row["longitude"]],
                icon=folium.DivIcon(html=marker_html(temp, state), icon_size=(half * 2, half * 2),
                                    icon_anchor=(half, half)),
                tooltip=folium.Tooltip(tooltip_html(row, temp), style=GLASS_LIGHT + ";padding:8px 12px"),
                z_index_offset=1000 if state == "selected" else 0,
            ).add_to(m)
            points.append([row["latitude"], row["longitude"]])
        if focus is None and self.fit and len(points) > 1:
            lats, lngs = [p[0] for p in points], [p[1] for p in points]
            m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(40, 40), max_zoom=10)
        m.get_root().html.add_child(folium.Element(legend_html()))
        return m
