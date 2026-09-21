"""ForecastQuery：目前時段、預報、更新狀態、日期查詢（假的資料庫）。"""
from datetime import date, datetime, timedelta

import pandas as pd

from fakes import FakeClient, forecast_rows
from tw_forecast.frontend.repository import TZ, ForecastQuery, latest_batch, only_full_periods, to_dataframe

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=TZ)
FIRST = datetime(2026, 9, 20, 6, 0, tzinfo=TZ)  # 昨天 06:00 起，共 4 天


def query(rows=None, status=None):
    return ForecastQuery(FakeClient({"weather_forecasts": rows if rows is not None else forecast_rows(FIRST),
                                     "pipeline_status": status or []}))


def test_current_returns_the_period_covering_now_for_all_cities():
    df = query().current(NOW)
    assert len(df) == 22
    assert (df["forecast_time_start"] <= NOW).all() and (df["forecast_time_end"] > NOW).all()
    assert str(df["forecast_time_start"].dt.tz) == "Asia/Taipei"


def test_current_falls_back_to_latest_started_period_when_data_is_stale():
    df = query().current(datetime(2026, 10, 30, 10, 0, tzinfo=TZ))  # 所有時段都已結束
    assert len(df) == 22 and df["forecast_time_start"].nunique() == 1
    latest_start = max(datetime.fromisoformat(r["forecast_time_start"]) for r in forecast_rows(FIRST))
    assert df["forecast_time_start"].iloc[0].to_pydatetime() == latest_start


def test_current_before_any_data_takes_earliest_upcoming_period():
    df = query().current(datetime(2026, 9, 1, 10, 0, tzinfo=TZ))
    assert df["forecast_time_start"].iloc[0].to_pydatetime() == FIRST


def test_current_is_empty_without_data():
    assert query([]).current(NOW).empty


def test_forecast_returns_unfinished_periods_sorted():
    df = query().forecast(NOW)
    assert (df["forecast_time_end"] > NOW).all()
    assert df["forecast_time_start"].is_monotonic_increasing


def test_only_latest_batch_is_kept():
    old = forecast_rows(FIRST, updated_at="2026-09-21T06:30:00+08:00")
    new = forecast_rows(FIRST, updated_at="2026-09-21T09:30:00+08:00")
    df = query(old + new).forecast(NOW)
    assert df["updated_at"].nunique() == 1 and len(df) == len(query(new).forecast(NOW))


def test_latest_batch_handles_empty_and_missing_column():
    assert latest_batch(pd.DataFrame()).empty
    assert len(latest_batch(pd.DataFrame({"x": [1]}))) == 1


def test_update_status_converts_times_and_tolerates_missing():
    rows = [{"trigger_type": "schedule", "last_success_at": "2026-09-21T01:30:00+00:00", "last_run_at": None}]
    (row,) = query(status=rows).update_status()
    assert row["last_success_at"].hour == 9 and row["last_run_at"] is None


def test_available_dates_lists_days_with_full_periods_in_window():
    dates = query().available_dates(NOW, "臺北市")
    assert dates == [date(2026, 9, 20), date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)]


def test_available_dates_ignore_shortened_periods_and_out_of_window():
    short = forecast_rows(FIRST, days=1)
    for r in short:
        r["forecast_time_start"] = (datetime.fromisoformat(r["forecast_time_start"]) + timedelta(hours=6)).isoformat()
    only_short = [r for r in short if r["location_name"] == "臺北市"][:1]  # 6 小時的縮短時段
    assert query(only_short).available_dates(NOW, "臺北市") == []
    far = forecast_rows(datetime(2026, 12, 1, 6, 0, tzinfo=TZ), days=1)
    assert query(far).available_dates(NOW, "臺北市") == []


def test_day_returns_only_that_day_and_requested_cities():
    df = query().day(date(2026, 9, 21), ["臺北市", "臺中市"])
    assert set(df["location_name"]) == {"臺北市", "臺中市"} and len(df) == 4
    assert {s.date() for s in df["forecast_time_start"]} == {date(2026, 9, 21)}
    assert query().day(date(2030, 1, 1), ["臺北市"]).empty


def test_only_full_periods_drops_shortened_rows():
    rows = forecast_rows(FIRST, days=1)[:2]
    rows[0]["forecast_time_start"] = (datetime.fromisoformat(rows[0]["forecast_time_start"]) + timedelta(hours=6)).isoformat()
    assert len(only_full_periods(to_dataframe(rows))) == 1
