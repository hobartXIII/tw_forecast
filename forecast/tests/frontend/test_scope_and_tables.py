"""篩選範圍（Scope）與明細表格整理。"""
from datetime import datetime

import pandas as pd
import pytest

from fakes import forecast_rows
from tw_forecast.frontend.regions import ALL_REGIONS, CITY_ORDER
from tw_forecast.frontend.repository import TZ, to_dataframe
from tw_forecast.frontend.scope import Scope, add_region
from tw_forecast.frontend.tables import make_table, next_periods
from tw_forecast.frontend.temperature import display_temp

FIRST = datetime(2026, 9, 21, 6, 0, tzinfo=TZ)


@pytest.fixture
def forecast():
    return add_region(to_dataframe(forecast_rows(FIRST, days=2)))


def test_add_region_and_order(forecast):
    row = forecast[forecast["location_name"] == "臺中市"].iloc[0]
    assert row["region"] == "中部地區" and row["order"] == CITY_ORDER.index("臺中市")
    assert add_region(pd.DataFrame({"location_name": ["火星市"]})).iloc[0]["order"] == 99


@pytest.mark.parametrize("scope, level, cities, label, drop", [
    (Scope(), "all", CITY_ORDER, "全台各地區平均", []),
    (Scope("離島地區"), "region", ["澎湖縣", "金門縣", "連江縣"], "離島地區各縣市", ["地區"]),
    (Scope(ALL_REGIONS, "臺中市"), "city", ["臺中市"], "臺中市", ["縣市", "地區"]),
])
def test_scope_levels(scope, level, cities, label, drop):
    assert (scope.level, scope.cities, scope.label, scope.table_drop_columns()) == (level, cities, label, drop)


def test_single_city_map_range_is_its_home_region():
    scope = Scope(ALL_REGIONS, "臺中市")
    assert scope.home_region == "中部地區"
    assert scope.region_cities == ["苗栗縣", "臺中市", "彰化縣", "南投縣", "雲林縣"]
    assert Scope().home_region is None


def test_filter_current_limits_and_sorts(forecast):
    current = forecast[forecast["forecast_time_start"] == forecast["forecast_time_start"].min()].sample(frac=1, random_state=1)
    cur = Scope("東部地區").filter_current(current)
    assert cur["location_name"].tolist() == ["宜蘭縣", "花蓮縣", "臺東縣"]


def test_filter_forecast_adds_avg_and_handles_empty(forecast):
    fc = Scope(ALL_REGIONS, "臺北市").filter_forecast(forecast)
    assert set(fc["location_name"]) == {"臺北市"} and "avg" in fc
    assert Scope().filter_forecast(forecast.iloc[0:0]) is None
    assert Scope(ALL_REGIONS, "臺北市").filter_forecast(forecast[forecast["location_name"] == "臺中市"]) is None


def test_series_data_all_averages_by_region(forecast):
    fc = Scope().filter_forecast(forecast)
    data, order = Scope().series_data(fc, "max_temp")
    assert order == ["北部地區", "中部地區", "南部地區", "東部地區", "離島地區"]
    north = data[(data["系列"] == "北部地區") & (data["forecast_time_start"] == fc["forecast_time_start"].min())]
    expected = fc[(fc["region"] == "北部地區") & (fc["forecast_time_start"] == fc["forecast_time_start"].min())]["max_temp"].mean()
    assert north["值"].iloc[0] == pytest.approx(expected)


def test_series_data_region_and_city_use_city_series(forecast):
    scope = Scope("離島地區")
    _, order = scope.series_data(scope.filter_forecast(forecast), "avg")
    assert order == ["澎湖縣", "金門縣", "連江縣"]
    scope = Scope(ALL_REGIONS, "臺北市")
    data, order = scope.series_data(scope.filter_forecast(forecast), "avg")
    assert order == ["臺北市"] and len(data) == 4


# ---------- tables ----------
def test_make_table_columns_and_formats(forecast):
    forecast = forecast.assign(avg=display_temp(forecast))
    src = forecast[forecast["location_name"] == "臺北市"].head(2)
    table = make_table(src, dated=True)
    assert list(table.columns) == ["縣市", "地區", "時段", "天氣現象", "最低 (°C)", "最高 (°C)", "平均 (°C)", "降雨機率", "舒適度"]
    assert table["時段"].iloc[0] == "09/21 06:00~18:00"
    assert make_table(src, dated=False)["時段"].iloc[0] == "06:00~18:00"
    assert table["天氣現象"].iloc[0].endswith("晴") and table["天氣現象"].iloc[0].startswith("☀️")  # 日間晴
    assert table["天氣現象"].iloc[1].startswith("☁️")  # 夜間多雲


def test_make_table_missing_values(forecast):
    forecast = forecast.assign(avg=display_temp(forecast))
    src = forecast.head(1).assign(weather_condition=None, comfort_index=None)
    table = make_table(src, dated=False)
    assert table["天氣現象"].iloc[0] == "—" and table["舒適度"].iloc[0] == "—"


def test_next_periods_takes_n_after_and_sorts_by_city_then_time(forecast):
    after = pd.Timestamp(FIRST)
    later = next_periods(forecast, after, n=2)
    assert (later["forecast_time_start"] > after).all()
    assert later.groupby("location_name").size().eq(2).all()
    assert later["location_name"].drop_duplicates().tolist() == CITY_ORDER  # 依地區順序
    first_city = later[later["location_name"] == CITY_ORDER[0]]["forecast_time_start"]
    assert first_city.is_monotonic_increasing
