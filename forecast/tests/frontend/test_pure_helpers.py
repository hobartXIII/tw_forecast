"""前端的小型純函式：地區對照、格式化、溫度級距、降雨色階、摘要卡片 HTML、更新門檻。"""
import math
from datetime import datetime, timedelta

import pandas as pd
import pytest

from tw_forecast.frontend import formatting, rain, regions, style, temperature, update_gate
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


# ---------- rain ----------
@pytest.mark.parametrize("prob, band", [(0, 0), (29, 0), (30, 1), (59, 1), (60, 2), (100, 2)])
def test_rain_color_bands(prob, band):
    assert rain.rain_color(prob) == rain.RAIN_BANDS[band][1]


def test_rain_alert_band_starts_at_alert_threshold():
    assert rain.RAIN_BANDS[-1][0] == rain.RAIN_ALERT
    assert rain.rain_color(None) == rain.rain_color(math.nan) == ""


# ---------- style.card ----------
def test_card_accent_delay_and_aside():
    html = style.card("最高溫", "31 °C", "☀️ 晴", accent="#e03131", index=2)
    assert 'class="glass"' in html and "--accent:#e03131" in html
    assert f"--delay:{2 * style.CARD_STAGGER_MS}ms" in html
    assert '<span class="aside">☀️ 晴</span>' in html and 'class="meter"' not in html


def test_card_without_accent_has_no_accent_variable():
    assert "--accent" not in style.card("平均氣溫", "—")


@pytest.mark.parametrize("value, width", [(70, "70%"), (0, "0%"), (130, "100%"), (-5, "0%")])
def test_card_meter_width_is_clamped(value, width):
    assert f'style="width:{width}"' in style.card("降雨機率", "70 %", meter=value)


def test_card_meter_omitted_for_missing_value():
    assert 'class="meter"' not in style.card("降雨機率", "—", meter=None)
    assert 'class="meter"' not in style.card("降雨機率", "—", meter=math.nan)


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


# ---------- update_gate：觸發後的鎖定（F5 後按鈕不可重新開放） ----------
def test_recent_dispatch_without_new_success_blocks_even_if_interval_passed():
    rows = [status(60)]  # 距上次成功 60 分鐘，本來可更新
    gate = update_gate.evaluate(rows, NOW, dispatched_at=NOW - timedelta(minutes=1))
    assert not gate.allowed and gate.message == update_gate.IN_PROGRESS_MESSAGE


def test_dispatch_lock_expires_so_a_failed_workflow_does_not_lock_forever():
    just_over = NOW - timedelta(minutes=update_gate.DISPATCH_LOCK_MINUTES, seconds=1)
    assert update_gate.evaluate([status(60)], NOW, dispatched_at=just_over).allowed


def test_new_success_after_dispatch_releases_lock_then_interval_rule_applies():
    dispatched = NOW - timedelta(minutes=2)
    rows = [status(1)]  # 觸發之後已經有新的成功紀錄
    gate = update_gate.evaluate(rows, NOW, dispatched_at=dispatched)
    assert not gate.allowed and gate.message != update_gate.IN_PROGRESS_MESSAGE and "僅 1 分鐘" in gate.message


def test_dispatch_lock_applies_when_never_succeeded():
    gate = update_gate.evaluate([{"last_success_at": None}], NOW, dispatched_at=NOW - timedelta(seconds=30))
    assert not gate.allowed and gate.message == update_gate.IN_PROGRESS_MESSAGE


def test_unreadable_status_still_reports_unknown_not_in_progress():
    gate = update_gate.evaluate(None, NOW, dispatched_at=NOW)
    assert gate.message == update_gate.UNKNOWN_MESSAGE


def test_dispatch_log_remembers_latest_time():
    log = update_gate.DispatchLog()
    assert log.last is None
    log.record(NOW)
    log.record(NOW + timedelta(minutes=1))
    assert log.last == NOW + timedelta(minutes=1)


# ---------- update_gate：間隔倒數需要的等待秒數 ----------
def test_interval_block_reports_wait_seconds_and_elapsed_minutes():
    gate = update_gate.evaluate([status(6)], NOW)
    assert not gate.allowed
    assert gate.elapsed_minutes == 6
    assert gate.wait_seconds == pytest.approx(14 * 60)


def test_wait_seconds_counts_down_to_zero_at_the_boundary():
    assert update_gate.evaluate([status(19.5)], NOW).wait_seconds == pytest.approx(30)
    assert update_gate.evaluate([status(20)], NOW).allowed  # 剛好滿間隔：放行、沒有等待時間


@pytest.mark.parametrize("gate", [
    update_gate.evaluate(None, NOW),                                                           # 讀不到狀態
    update_gate.evaluate([status(60)], NOW, dispatched_at=NOW - timedelta(minutes=1)),         # 剛觸發（鎖定）
    update_gate.evaluate([status(60)], NOW),                                                   # 放行
])
def test_only_interval_block_has_wait_seconds(gate):
    assert gate.wait_seconds is None and gate.elapsed_minutes is None
