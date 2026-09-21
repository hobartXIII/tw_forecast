"""後端 Repository：狀態記錄、告警設定讀取（假的資料庫）。"""
import pytest

from fakes import FakeClient
from tw_forecast.backend.errors import AbortRun
from tw_forecast.backend.repository import (AlertSettingsRepository, StatusRepository, create_supabase_client)


def test_status_success_sets_last_success_and_clears_error():
    client = FakeClient()
    StatusRepository(client).record("schedule", "success", "2026-09-21T08:45:00+08:00")
    (row, conflict), = client.tables["pipeline_status"].upserts
    assert conflict == "trigger_type"
    assert row == {"trigger_type": "schedule", "last_run_at": "2026-09-21T08:45:00+08:00", "last_status": "success",
                   "last_error": None, "last_success_at": "2026-09-21T08:45:00+08:00"}


def test_status_failure_keeps_previous_success_time():
    client = FakeClient()
    StatusRepository(client).record("manual", "failed", "2026-09-21T09:00:00+08:00", "boom")
    (row, _), = client.tables["pipeline_status"].upserts
    assert "last_success_at" not in row and row["last_error"] == "boom"


def test_status_write_error_only_warns(capsys):
    class Boom(FakeClient):
        def table(self, name):
            raise RuntimeError("db down")

    StatusRepository(Boom()).record("manual", "success", "t")  # 不應拋例外
    assert "無法更新 pipeline_status" in capsys.readouterr().err


def test_alert_settings_load_parses_rows():
    client = FakeClient({
        "alert_city_settings": [{"location_name": "臺北市", "enabled": True, "rain_enabled": True, "rain_threshold": 60,
                                 "min_temp_enabled": True, "min_temp_threshold": 12,
                                 "max_temp_enabled": True, "max_temp_threshold": 35}],
        "alert_slot_settings": [{"slot": "08:45", "enabled": True}]})
    settings = AlertSettingsRepository(client).load()
    assert settings.slots == frozenset({"08:45"}) and settings.cities["臺北市"].enabled


def test_alert_settings_load_returns_none_when_unreadable_and_masks_secret(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_KEY", "super-secret-key-value")

    class Boom(FakeClient):
        def table(self, name):
            raise RuntimeError("failed with super-secret-key-value")

    assert AlertSettingsRepository(Boom()).load() is None
    err = capsys.readouterr().err
    assert "super-secret-key-value" not in err and "***" in err


def test_create_client_requires_both_env_vars(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", "k")
    with pytest.raises(AbortRun, match="SUPABASE"):
        create_supabase_client()
