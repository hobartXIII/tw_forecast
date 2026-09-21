"""ForecastParser：巢狀 JSON → 平面列。"""
import pytest

from fakes import cwa_payload
from tw_forecast.backend.parser import ForecastParser


@pytest.fixture
def parser():
    return ForecastParser()


def test_parse_flattens_one_period_into_one_row(parser):
    rows = parser.parse(cwa_payload())
    assert len(rows) == 1
    row = rows[0]
    assert row["location_name"] == "臺北市"
    assert row["forecast_time_start"] == "2026-09-21T06:00:00+08:00"
    assert (row["min_temp"], row["max_temp"], row["avg_temp"]) == (25.0, 31.0, 28.0)
    assert row["rain_probability"] == 30 and isinstance(row["rain_probability"], int)
    assert row["weather_condition"] == "多雲" and row["comfort_index"] == "悶熱"
    assert (row["latitude"], row["longitude"]) == (25.05, 121.5)


@pytest.mark.parametrize("bad", ["-", "", "  ", None, "abc"])
def test_missing_or_invalid_values_become_none(parser, bad):
    row = parser.parse(cwa_payload(MaxTemperature=bad))[0]
    assert row["max_temp"] is None
    assert row["min_temp"] == 25.0  # 其他要素不受影響


def test_rain_probability_accepts_decimal_string(parser):
    assert parser.parse(cwa_payload(ProbabilityOfPrecipitation="30.0"))[0]["rain_probability"] == 30


def test_time_without_timezone_is_treated_as_taiwan_time(parser):
    row = parser.parse(cwa_payload(start="2026-09-21 06:00:00", end="2026-09-21 18:00:00"))[0]
    assert row["forecast_time_start"] == "2026-09-21T06:00:00+08:00"
    assert row["forecast_time_end"] == "2026-09-21T18:00:00+08:00"


def test_time_with_timezone_is_kept(parser):
    assert ForecastParser.to_iso("2026-09-21T06:00:00Z") == "2026-09-21T06:00:00Z"
    assert ForecastParser.to_iso("2026-09-21T06:00:00+09:00") == "2026-09-21T06:00:00+09:00"


def test_unknown_elements_are_ignored(parser):
    payload = cwa_payload()
    payload["records"]["Locations"][0]["Location"][0]["WeatherElement"].append(
        {"ElementName": "紫外線", "Time": [{"StartTime": "x", "EndTime": "y", "ElementValue": [{"UVI": "9"}]}]})
    assert len(parser.parse(payload)) == 1


def test_element_missing_from_a_period_is_filled_with_none(parser):
    payload = cwa_payload()
    elements = payload["records"]["Locations"][0]["Location"][0]["WeatherElement"]
    elements[:] = [e for e in elements if e["ElementName"] != "12小時降雨機率"]
    assert parser.parse(payload)[0]["rain_probability"] is None


def test_every_period_has_all_columns(parser):
    row = parser.parse(cwa_payload())[0]
    for spec in ForecastParser.ELEMENTS.values():
        assert spec.column in row
