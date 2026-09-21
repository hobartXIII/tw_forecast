"""前端的小型純函式：地區對照、格式化、溫度級距、更新門檻。"""
import math
from datetime import datetime, timedelta

import pandas as pd
import pytest

from tw_forecast.frontend import formatting, regions, temperature, update_gate
from tw_forecast.frontend.repository import TZ


def ts(hour, day=21):
    return pd.Timestamp(datetime(2026, 9, day, hour, 0, tzinfo=TZ))


# ---------- regions ----------
def test_every_city_belongs_to_exactly_one_region():
    assert len(regions.CITY_ORDER) == 22 == len(set(regions.CITY_ORDER))
    assert set(regions.CITY_ORDER) == set(regions.CITY_TO_REGION)


def test_region_of_normalizes_taiwan_character():
    assert regions.region_of("台北市") == regions.region_of("臺北市") == "北部地區"
    assert regions.region_of("不存在") is None


def test_cities_in():
    assert regions.cities_in(regions.ALL_REGIONS) == regions.CITY_ORDER
    assert regions.cities_in("離島地區") == ["澎湖縣", "金門縣", "連江縣"]


# ---------- formatting ----------
@pytest.mark.parametrize("start, end, night", [(6, 18, False), (18, 30, True), (0, 6, True), (12, 18, False)])
def test_is_night_uses_midpoint(start, end, night):
    s = pd.Timestamp(datetime(2026, 9, 21, 0, 0, tzinfo=TZ)) + pd.Timedelta(hours=start)
    e = pd.Timestamp(datetime(2026, 9, 21, 0, 0, tzinfo=TZ)) + pd.Timedelta(hours=end)
    assert formatting.is_night(s, e) is night


@pytest.mark.parametrize("text, night, icon", [
    ("晴", False, "☀️"), ("晴", True, "🌙"), ("晴時多雲", False, "🌤️"), ("晴時多雲", True, "🌙☁️"),
    ("多雲", False, "⛅"), ("多雲", True, "☁️"), ("陰", False, "☁️"),
    ("短暫陣雨", True, "🌧️"), ("雷陣雨", False, "⛈️"), ("有霧", False, "🌫️"), ("未知", False, "🌡️"),
    (None, False, ""), ("", False, ""), (float("nan"), False, ""),
])
def test_weather_icon(text, night, icon):
    assert formatting.weather_icon(text, night) == icon


def test_format_helpers():
    assert formatting.format_range(ts(6), ts(18, 22)) == "09/21 06:00 ~ 09/22 18:00"
    rows = [{"trigger_type": "schedule", "last_success_at": ts(9)}, {"trigger_type": "manual", "last_success_at": None}]
    assert formatting.format_last_update(rows, "schedule") == "09/21 09:00"
    assert formatting.format_last_update(rows, "manual") == "—"
    assert formatting.format_last_update(None, "schedule") == "—"
    assert formatting.format_value(23.456, "°C", ".1f") == "23.5 °C"
    assert formatting.format_value(None, "%") == formatting.format_value(math.nan, "%") == "—"


# ---------- temperature ----------
@pytest.mark.parametrize("temp, band", [(19.9, 0), (20, 1), (25, 1), (25.1, 2), (30, 2), (30.1, 3)])
def test_band_boundaries(temp, band):
    assert temperature.band_index(temp) == band
    assert temperature.temp_color(temp) == temperature.BANDS[band][0]
    assert temperature.text_color(temp) == temperature.TEXT_COLORS[band]


def test_null_temperature_is_not_colored():
    assert temperature.text_color(float("nan")) == "" and temperature.text_color(None) == ""
    assert temperature.colored(None, "—") == "—"
    assert "color:#e03131" in temperature.colored(35, "35°C")
    assert temperature.temp_text(float("nan")) == "—" and temperature.temp_text(23.6) == "24°C"


def test_display_temp_falls_back_to_midpoint():
    df = pd.DataFrame({"avg_temp": [20.0, None], "min_temp": [10.0, 10.0], "max_temp": [30.0, 20.0]})
    assert temperature.display_temp(df).tolist() == [20.0, 15.0]


# ---------- update_gate ----------
NOW = datetime(2026, 9, 21, 10, 0, tzinfo=TZ)


def status(minutes_ago):
    return {"last_success_at": pd.Timestamp(NOW - timedelta(minutes=minutes_ago))}


def test_unknown_status_blocks():
    for rows in (None, []):
        gate = update_gate.evaluate(rows, NOW)
        assert not gate.allowed and gate.message == update_gate.UNKNOWN_MESSAGE


def test_never_succeeded_allows():
    assert update_gate.evaluate([{"last_success_at": None}], NOW).allowed


def test_too_soon_blocks_with_wait_minutes():
    gate = update_gate.evaluate([status(5)], NOW)
    assert not gate.allowed and "僅 5 分鐘" in gate.message and "約 15 分鐘" in gate.message


def test_interval_boundary_allows_and_uses_newest_of_sources():
    assert update_gate.evaluate([status(20)], NOW).allowed
    gate = update_gate.evaluate([status(90), status(3)], NOW)
    assert not gate.allowed  # 取較新的一筆
    assert update_gate.evaluate([status(90), status(30)], NOW).allowed
