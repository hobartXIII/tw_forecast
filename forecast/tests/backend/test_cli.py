"""CLI：執行來源判斷、機密遮蔽、失敗記錄與退出方式。"""
import pytest

from tw_forecast.backend import cli
from tw_forecast.backend.errors import AbortRun
from tw_forecast.backend.security import mask_secrets


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    """main() 會載入 forecast/.env；測試不可讀到真實金鑰，也不可被它蓋掉 monkeypatch 設定的環境變數。"""
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)


@pytest.mark.parametrize("event, expected", [("schedule", "schedule"), ("workflow_dispatch", "manual"), (None, "manual")])
def test_trigger_type(monkeypatch, event, expected):
    if event is None:
        monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    else:
        monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    assert cli.trigger_type() == expected


def test_mask_secrets_hides_long_values_only(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEFGH")
    monkeypatch.setenv("WEATHER_API_KEY", "short")  # 少於 8 字元不遮蔽（避免誤傷一般文字）
    assert mask_secrets("url=123456:ABCDEFGH short") == "url=*** short"


def test_dry_run_from_sample_runs_without_secrets(monkeypatch, tmp_path, capsys):
    from fakes import cwa_payload
    import json
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps(cwa_payload()), encoding="utf-8")
    monkeypatch.setattr(cli, "SAMPLE_PATH", sample)
    for name in ("SUPABASE_URL", "SUPABASE_KEY", "WEATHER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    cli.main(["--dry-run", "--from-sample"])
    assert "解析完成：1 列，1 個縣市" in capsys.readouterr().out


def test_missing_database_secrets_exit_with_message(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--from-sample"])
    assert "SUPABASE" in str(exc.value)


def test_abort_is_recorded_as_failure_and_exits_with_message(monkeypatch):
    recorded = []

    class FakePipeline:
        def run(self, trigger):
            raise AbortRun("CWA API 回應 429")

        def record_failure(self, trigger, reason):
            recorded.append((trigger, reason))

    monkeypatch.setattr(cli, "build_pipeline", lambda *a: FakePipeline())
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert "429" in str(exc.value)
    assert recorded == [("schedule", "CWA API 回應 429")]  # 失敗原因不加例外類型前綴


def test_unexpected_error_is_recorded_with_type_and_masked_then_reraised(monkeypatch):
    recorded = []
    monkeypatch.setenv("SUPABASE_KEY", "super-secret-key-value")

    class FakePipeline:
        def run(self, trigger):
            raise RuntimeError("leak super-secret-key-value")

        def record_failure(self, trigger, reason):
            recorded.append(reason)

    monkeypatch.setattr(cli, "build_pipeline", lambda *a: FakePipeline())
    with pytest.raises(RuntimeError):
        cli.main([])
    assert recorded == ["RuntimeError: leak ***"]
