"""告警規則：設定解析、判斷視窗、條件命中（純邏輯）。"""
from datetime import datetime

import pytest

from tw_forecast.backend import alerts
from tw_forecast.backend.alerts import AlertSettings, CityRule
from tw_forecast.config import TZ


def dt(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=TZ)


def city_row(name="臺北市", **kw):
    row = {"location_name": name, "enabled": True, "rain_enabled": True, "rain_threshold": 60,
           "min_temp_enabled": True, "min_temp_threshold": 12, "max_temp_enabled": True, "max_temp_threshold": 35}
    row.update(kw)
    return row


def forecast_row(name="臺北市", start=(21, 6), end=(21, 18), rain=10, tmin=20.0, tmax=28.0):
    return {"location_name": name, "forecast_time_start": dt(*start).isoformat(),
            "forecast_time_end": dt(*end).isoformat(), "rain_probability": rain, "min_temp": tmin, "max_temp": tmax}


# ---------- parse_settings ----------
def test_parse_valid_rows():
    settings, warnings = alerts.parse_settings(
        [city_row(rain_threshold=70)], [{"slot": "08:45", "enabled": True}, {"slot": "14:45", "enabled": False}])
    assert warnings == []
    assert settings.cities["臺北市"].rain == 70
    assert settings.slots == frozenset({"08:45"})


@pytest.mark.parametrize("patch", [
    {"enabled": 1},                    # 不是布林
    {"rain_threshold": 101},           # 超出範圍
    {"min_temp_threshold": "cold"},    # 型別錯誤
    {"max_temp_threshold": True},      # 布林不算數字
    {"location_name": ""},
])
def test_invalid_city_rows_are_skipped_with_warning(patch):
    settings, warnings = alerts.parse_settings([city_row(**patch)], [])
    assert settings.cities == {} and len(warnings) == 1


def test_missing_key_is_invalid():
    row = city_row()
    del row["rain_threshold"]
    settings, warnings = alerts.parse_settings([row], [])
    assert settings.cities == {} and warnings


def test_invalid_slot_rows_are_skipped():
    settings, warnings = alerts.parse_settings([], [{"slot": "09:00", "enabled": True}, {"slot": "08:45", "enabled": "yes"}])
    assert settings.slots == frozenset() and len(warnings) == 2


def test_none_inputs_mean_nothing_enabled():
    settings, _ = alerts.parse_settings(None, None)
    assert settings == AlertSettings()


# ---------- window_end / classify ----------
def test_window_end_is_next_enabled_slot():
    slots = frozenset({"08:45", "20:45"})
    assert alerts.window_end(dt(21, 8, 45), slots) == dt(21, 20, 45)
    assert alerts.window_end(dt(21, 20, 45), slots) == dt(22, 8, 45)


def test_window_end_with_single_slot_is_next_day():
    assert alerts.window_end(dt(21, 8, 45), frozenset({"08:45"})) == dt(22, 8, 45)


def test_window_end_without_slots_raises():
    with pytest.raises(ValueError):
        alerts.window_end(dt(21, 8, 45), frozenset())


@pytest.mark.parametrize("start, end, expected", [
    (dt(21, 6), dt(21, 18), "進行中"),       # 已開始、尚未結束
    (dt(21, 18), dt(22, 6), "即將開始"),     # 視窗內才開始
    (dt(21, 0), dt(21, 8, 45), None),        # 剛好在時槽結束 → 已過去
    (dt(22, 6), dt(22, 18), None),           # 視窗之後
])
def test_classify(start, end, expected):
    assert alerts.classify(start, end, dt(21, 8, 45), dt(21, 20, 45)) == expected


# ---------- is_hit ----------
def test_is_hit_each_condition():
    rule = CityRule(enabled=True)
    assert alerts.is_hit({"rain_probability": 60}, rule)
    assert alerts.is_hit({"min_temp": 12}, rule)
    assert alerts.is_hit({"max_temp": 35}, rule)
    assert not alerts.is_hit({"rain_probability": 59, "min_temp": 13, "max_temp": 34}, rule)


def test_is_hit_respects_switches_and_ignores_null():
    rule = CityRule(enabled=True, rain_on=False, min_on=False)
    assert not alerts.is_hit({"rain_probability": 100, "min_temp": -5, "max_temp": 30}, rule)
    assert alerts.is_hit({"max_temp": 40}, rule)
    assert not alerts.is_hit({"rain_probability": None, "min_temp": None, "max_temp": None}, CityRule(enabled=True))


# ---------- evaluate_alerts ----------
def settings_for(*rows, slots=("08:45", "14:45", "20:45")):
    return alerts.parse_settings(list(rows), [{"slot": s, "enabled": True} for s in slots])[0]


def test_evaluate_returns_only_enabled_cities_that_hit_in_window():
    settings = settings_for(city_row("臺北市"), city_row("新北市", enabled=False))
    records = [forecast_row("臺北市", rain=80), forecast_row("新北市", rain=80), forecast_row("臺中市", rain=80)]
    hits, wend = alerts.evaluate_alerts(records, settings, dt(21, 8, 45))
    assert [h["location_name"] for h in hits] == ["臺北市"]
    assert hits[0]["label"] == "進行中"
    assert wend == dt(21, 14, 45)


def test_evaluate_excludes_periods_outside_window_and_sorts_by_start():
    settings = settings_for(city_row("臺北市"))
    records = [forecast_row(start=(21, 18), end=(22, 6), rain=90),   # 視窗（08:45~14:45）之後 → 排除
               forecast_row(start=(21, 6), end=(21, 18), rain=90)]
    hits, _ = alerts.evaluate_alerts(records, settings, dt(21, 8, 45))
    assert [h["forecast_time_start"] for h in hits] == [dt(21, 6).isoformat()]


def test_evaluate_with_no_hits_returns_empty():
    hits, _ = alerts.evaluate_alerts([forecast_row(rain=0)], settings_for(city_row()), dt(21, 8, 45))
    assert hits == []
