"""圖表資料整理與規格、地圖標記與 HTML。"""
import json
import re
from datetime import datetime

import pandas as pd
import pytest

from fakes import forecast_rows
from tw_forecast.frontend.charts import MISSING_TIP, SeriesChart
from tw_forecast.frontend.map_view import TemperatureMap, legend_html, marker_html, tooltip_html
from tw_forecast.frontend.rain import RAIN_ALERT
from tw_forecast.frontend.repository import TZ, to_dataframe
from tw_forecast.frontend.scope import add_region
from tw_forecast.frontend.temperature import display_temp

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=TZ)


def long_frame(values, city="臺北市"):
    starts = pd.date_range("2026-09-21 06:00", periods=len(values), freq="12h", tz=TZ)
    return pd.DataFrame({"系列": city, "forecast_time_start": starts, "值": values})


# ---------- SeriesChart ----------
def test_prepare_drops_missing_values_by_default():
    d = SeriesChart("氣溫", ["臺北市"]).prepare(long_frame([20.0, None, 22.0]))
    assert d["值"].tolist() == [20.0, 22.0] and d["顯示"].tolist() == ["20.0", "22.0"]
    assert d["時段"].dt.tz is None  # 去掉時區，避免瀏覽器再換算


def test_prepare_fill_zero_marks_missing_points():
    d = SeriesChart("降雨", ["臺北市"], threshold=RAIN_ALERT, fill_zero=True).prepare(long_frame([70, None]))
    assert d["值"].tolist() == [70, 0] and d["未提供"].tolist() == [False, True]
    assert d["顯示"].tolist() == ["70", MISSING_TIP]


def spec(chart):
    return json.loads(chart.to_json())


def test_temperature_chart_spec_has_curve_height_and_legend_selection():
    chart = SeriesChart("氣溫 (°C)", ["臺北市"], zero=True).build(long_frame([20.0, 22.0]), NOW)
    s = spec(chart)
    line = next(layer for layer in s["layer"] if layer["mark"]["type"] == "line")
    assert line["mark"]["interpolate"] == "monotone"
    assert s["height"] == 440
    assert s["params"][0]["bind"] == "legend"
    assert any(layer["mark"]["type"] == "rule" for layer in s["layer"])  # 「現在」虛線


def test_custom_colors_are_used():
    chart = SeriesChart("氣溫", ["最高溫", "最低溫"], colors=["#111111", "#222222"]).build(long_frame([1.0, 2.0], "最高溫"), NOW)
    assert '"#111111"' in chart.to_json() and '"#222222"' in chart.to_json()


def test_rain_chart_has_threshold_rule_fixed_domain_and_hollow_missing_points():
    s = spec(SeriesChart("降雨", ["臺北市"], zero=True, threshold=RAIN_ALERT, fill_zero=True).build(long_frame([70, None]), NOW))
    rules = [layer for layer in s["layer"] if layer["mark"]["type"] == "rule"]
    assert len(rules) == 2  # 門檻線 + 現在
    points = [layer for layer in s["layer"] if layer["mark"]["type"] == "point"]
    assert len(points) == 2 and points[1]["mark"]["filled"] is False
    line = next(layer for layer in s["layer"] if layer["mark"]["type"] == "line")
    assert line["encoding"]["y"]["scale"]["domain"] == [0, 100]


def temp_lines(highs, lows):
    return pd.concat([long_frame(highs, "最高溫"), long_frame(lows, "最低溫")])


def test_band_data_pairs_low_and_high_and_skips_missing():
    chart = SeriesChart("氣溫", ["最高溫", "最低溫"], band=("最低溫", "最高溫"))
    b = chart.band_data(chart.prepare(temp_lines([30.0, None, 28.0], [22.0, 21.0, 20.5])))
    assert b["下緣"].tolist() == [22.0, 20.5] and b["上緣"].tolist() == [30.0, 28.0]
    assert b["溫差"].tolist() == [8.0, 7.5]


def test_band_layer_is_drawn_first_with_gradient():
    s = spec(SeriesChart("氣溫", ["最高溫", "最低溫"], band=("最低溫", "最高溫")).build(
        temp_lines([30.0, 29.0], [22.0, 21.0]), NOW))
    area = s["layer"][0]
    assert area["mark"]["type"] == "area" and area["mark"]["color"]["gradient"] == "linear"
    assert area["encoding"]["y2"]["field"] == "上緣"


def test_band_skipped_when_a_series_is_missing():
    chart = SeriesChart("氣溫", ["最高溫"], band=("最低溫", "最高溫"))
    s = spec(chart.build(long_frame([30.0, 29.0], "最高溫"), NOW))
    assert not any(layer["mark"]["type"] == "area" for layer in s["layer"])


def test_charts_share_transparent_background_dashed_grid_without_frame():
    s = spec(SeriesChart("氣溫", ["臺北市"]).build(long_frame([20.0, 22.0]), NOW))
    assert s["config"]["background"] == "transparent"
    assert s["config"]["axis"]["gridDash"] == [2, 4] and s["config"]["view"]["strokeWidth"] == 0
    assert not any(layer["mark"]["type"] == "area" for layer in s["layer"])  # 沒指定 band 就不畫


def test_now_line_omitted_when_far_outside_range():
    far = datetime(2027, 1, 1, tzinfo=TZ)
    s = spec(SeriesChart("氣溫", ["臺北市"]).build(long_frame([20.0, 22.0]), far))
    assert not any(layer["mark"]["type"] == "rule" for layer in s["layer"])


# ---------- 地圖 ----------
@pytest.fixture
def cur():
    df = add_region(to_dataframe(forecast_rows(datetime(2026, 9, 21, 6, 0, tzinfo=TZ), days=1)))
    df = df[df["forecast_time_start"] == df["forecast_time_start"].min()]
    return df.assign(avg=display_temp(df))


def html_of(m):
    return re.sub(r"[0-9a-f]{32}", "ID", m.get_root().render())


def test_map_has_one_marker_per_city_legend_and_gesture_plugin(cur):
    html = html_of(TemperatureMap(cur).build())
    assert html.count("L.marker(") == 22
    assert "平均氣溫" in html and "gestureHandling" in html and "leaflet-gesture-handling.min.js" in html


def test_map_skips_rows_without_coordinates_or_temperature(cur):
    cur = cur.copy()
    cur.loc[cur.index[0], "latitude"] = None
    cur.loc[cur.index[1], ["avg_temp", "min_temp", "max_temp"]] = None
    assert html_of(TemperatureMap(cur).build()).count("L.marker(") == 20


def test_highlight_centers_on_city_and_dims_others(cur):
    html = html_of(TemperatureMap(cur, highlight="臺中市").build())
    assert html.count("opacity:0.45") == 21   # 其餘縣市淡化
    assert "0 0 0 4px #1c7ed6" in html        # 被選縣市外框
    city = cur[cur["location_name"] == "臺中市"].iloc[0]
    assert f"[{city['latitude']}, {city['longitude']}]" in html
    assert '"zoom": 9,' in html  # 被選縣市時以該縣市為中心、放大到 9


def test_marker_and_tooltip_html(cur):
    assert "background:#f59f00" in marker_html(28) and "color:#222" in marker_html(28)   # 橙黃底用深色字
    assert "color:#fff" in marker_html(35) and "28°" in marker_html(28.2)
    tip = tooltip_html(cur.iloc[0], 22.5)
    assert cur.iloc[0]["location_name"] in tip and "降雨機率" in tip
    row = cur.iloc[0].copy()
    row["rain_probability"] = None
    assert "降雨機率 —" in tooltip_html(row, 22.5)


def test_legend_lists_all_bands():
    assert legend_html().count("border-radius:50%") == 4
