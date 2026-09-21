"""Pipeline：串流程與各種分支（全部相依都以假物件注入）。"""
from datetime import datetime

import pytest

from fakes import FakeClient, cwa_payload
from tw_forecast.backend.parser import ForecastParser
from tw_forecast.backend.pipeline import Pipeline
from tw_forecast.backend.repository import AlertSettingsRepository, ForecastRepository, StatusRepository
from tw_forecast.config import TZ

# 2026-09-21 08:50：時槽 08:45（發送時段之一）；預報時段 06:00~18:00 進行中
NOW = datetime(2026, 9, 21, 8, 50, tzinfo=TZ)


class RecordingNotifier:
    def __init__(self):
        self.calls = []

    def notify_alerts(self, rows, scope):
        self.calls.append((rows, scope))


def city_setting(**kw):
    row = {"location_name": "臺北市", "enabled": True, "rain_enabled": True, "rain_threshold": 20,
           "min_temp_enabled": False, "min_temp_threshold": 12, "max_temp_enabled": False, "max_temp_threshold": 35}
    row.update(kw)
    return row


def build(client=None, dry_run=False, notifier=None, now=NOW, payload=None):
    client = client or FakeClient({"alert_city_settings": [city_setting()],
                                   "alert_slot_settings": [{"slot": "08:45", "enabled": True}]})
    return client, Pipeline(
        fetch_raw=lambda: payload or cwa_payload(), parser=ForecastParser(), dry_run=dry_run,
        forecasts=ForecastRepository(client), status=StatusRepository(client),
        alert_settings=AlertSettingsRepository(client), notifier=notifier, now=lambda: now)


def upserts(client, table):
    """該表收到的 upsert 記錄；從未被寫入的表回傳空清單。"""
    return client.tables[table].upserts if table in client.tables else []


def test_manual_run_writes_forecasts_and_status_but_does_not_notify(capsys):
    notifier = RecordingNotifier()
    client, pipe = build(notifier=notifier)
    pipe.run("manual")
    (records, conflict), = upserts(client, "weather_forecasts")
    assert len(records) == 1 and conflict == "location_name,forecast_time_start,forecast_time_end"
    assert records[0]["updated_at"] == NOW.isoformat()
    (status, _), = upserts(client, "pipeline_status")
    assert status["trigger_type"] == "manual" and status["last_success_at"] == NOW.isoformat()
    assert notifier.calls == []
    assert "非排程執行" in capsys.readouterr().out


def test_schedule_run_notifies_when_conditions_match():
    notifier = RecordingNotifier()
    _, pipe = build(notifier=notifier)
    pipe.run("schedule")
    (rows, scope), = notifier.calls
    assert rows[0]["location_name"] == "臺北市" and rows[0]["label"] == "進行中"
    assert scope == "涵蓋 09/21 08:45～09/22 08:45"


def test_schedule_outside_enabled_slot_does_not_notify(capsys):
    notifier = RecordingNotifier()
    _, pipe = build(notifier=notifier, now=datetime(2026, 9, 21, 5, 50, tzinfo=TZ))  # 時槽 05:45，未啟用
    pipe.run("schedule")
    assert notifier.calls == [] and "不在啟用的發送時段" in capsys.readouterr().out


def test_no_city_enabled_does_not_notify(capsys):
    client = FakeClient({"alert_city_settings": [city_setting(enabled=False)],
                         "alert_slot_settings": [{"slot": "08:45", "enabled": True}]})
    notifier = RecordingNotifier()
    _, pipe = build(client, notifier=notifier)
    pipe.run("schedule")
    assert notifier.calls == [] and "尚未啟用任何縣市" in capsys.readouterr().out


def test_no_matching_period_does_not_notify(capsys):
    client = FakeClient({"alert_city_settings": [city_setting(rain_threshold=100)],
                         "alert_slot_settings": [{"slot": "08:45", "enabled": True}]})
    notifier = RecordingNotifier()
    _, pipe = build(client, notifier=notifier)
    pipe.run("schedule")
    assert notifier.calls == [] and "無需推播" in capsys.readouterr().out


def test_missing_telegram_config_is_skipped(capsys):
    _, pipe = build(notifier=None)
    pipe.run("schedule")
    assert "略過推播" in capsys.readouterr().out


def test_unreadable_alert_settings_fail_closed():
    class Boom(FakeClient):
        def table(self, name):
            if name.startswith("alert_"):
                raise RuntimeError("table missing")
            return super().table(name)

    notifier = RecordingNotifier()
    _, pipe = build(Boom(), notifier=notifier)
    pipe.run("schedule")
    assert notifier.calls == []


def test_dry_run_touches_nothing(capsys):
    client = FakeClient()
    _, pipe = build(client, dry_run=True)
    pipe.forecasts = pipe.status = pipe.alert_settings = None
    pipe.run("schedule")
    assert client.tables == {} and "[dry-run]" in capsys.readouterr().out


def test_record_failure_writes_failed_status_without_success_time():
    client, pipe = build()
    pipe.record_failure("schedule", "x" * 500)
    (row, _), = upserts(client, "pipeline_status")
    assert row["last_status"] == "failed" and "last_success_at" not in row
    assert len(row["last_error"]) == 300


def test_record_failure_without_status_repository_is_noop():
    _, pipe = build()
    pipe.status = None
    pipe.record_failure("manual", "boom")  # 不應拋例外


@pytest.mark.parametrize("trigger", ["schedule", "manual"])
def test_forecast_write_failure_propagates_and_skips_status(trigger):
    class Boom(FakeClient):
        def table(self, name):
            if name == "weather_forecasts":
                raise RuntimeError("db down")
            return super().table(name)

    client, pipe = build(Boom())
    with pytest.raises(RuntimeError):
        pipe.run(trigger)
    assert upserts(client, "pipeline_status") == []  # 資料沒寫成功就不能標成功
