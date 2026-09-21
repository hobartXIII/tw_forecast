"""告警訊息組裝與 Telegram 推播（假的 post，不連網）。"""
import pytest
import requests

from tw_forecast.backend.errors import NotifyError
from tw_forecast.backend.notifier import MAX_CHARS, TelegramNotifier, build_alert_text

TOKEN = "123456:SECRET-TOKEN-VALUE"


def row(name="臺北市", rain=70, tmin=25.0, tmax=30.0, label="進行中"):
    return {"location_name": name, "forecast_time_start": "2026-09-21T06:00:00+08:00",
            "forecast_time_end": "2026-09-21T18:00:00+08:00", "label": label,
            "rain_probability": rain, "min_temp": tmin, "max_temp": tmax}


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body if body is not None else {}

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


class RecordingPost:
    """依序回傳預先設定的回應，並記錄每次送出的 payload。"""

    def __init__(self, *responses):
        self.responses, self.payloads = list(responses), []

    def __call__(self, url, json, timeout):
        self.payloads.append(json)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


# ---------- 訊息內容 ----------
def test_text_has_title_scope_and_one_line_per_row():
    rich, plain = build_alert_text([row(), row("新北市", rain=None)], "涵蓋 09/21 08:45～14:45")
    assert plain.splitlines()[0] == "🔔 天氣告警"
    assert "共 2 筆符合條件" in plain
    assert "臺北市 09/21 06:00~18:00 進行中｜降雨 70%｜25~30°C" in plain
    assert "新北市" in plain and "降雨 —%" not in plain and "降雨 —｜" in plain
    assert rich.startswith("<b>🔔 天氣告警</b>")


def test_html_special_characters_are_escaped():
    rich, _ = build_alert_text([row("<b>&")], "範圍")
    assert "&lt;b&gt;&amp;" in rich


def test_long_lists_are_truncated_with_remainder_note():
    _, plain = build_alert_text([row(f"縣市{i}") for i in range(50)], "範圍", max_lines=10)
    assert sum(line.startswith("縣市") for line in plain.splitlines()) == 10
    assert "另有 40 筆未列出" in plain


def test_message_never_exceeds_telegram_limit():
    _, plain = build_alert_text([row("很長的縣市名稱" * 5) for _ in range(30)], "範圍")
    assert len(plain) <= MAX_CHARS + 100


# ---------- 送出 ----------
def test_send_html_success_uses_html_mode():
    post = RecordingPost(FakeResponse(200))
    TelegramNotifier(TOKEN, "42", post=post).notify_alerts([row()], "範圍")
    assert len(post.payloads) == 1
    assert post.payloads[0]["parse_mode"] == "HTML" and post.payloads[0]["chat_id"] == "42"


def test_html_rejected_falls_back_to_plain_text():
    post = RecordingPost(FakeResponse(400), FakeResponse(200))
    TelegramNotifier(TOKEN, "42", post=post).send("<b>x</b>", "x")
    assert "parse_mode" not in post.payloads[1] and post.payloads[1]["text"] == "x"


def test_error_message_never_contains_token():
    post = RecordingPost(FakeResponse(401, {"description": f"bad token {TOKEN}"}))
    with pytest.raises(NotifyError) as exc:
        TelegramNotifier(TOKEN, "42", post=post).send("a", "a")
    assert TOKEN not in str(exc.value) and "401" in str(exc.value)


def test_connection_error_message_hides_url_and_token():
    post = RecordingPost(requests.ConnectionError(f"https://api.telegram.org/bot{TOKEN}/sendMessage failed"))
    with pytest.raises(NotifyError) as exc:
        TelegramNotifier(TOKEN, "42", post=post).send("a", "a")
    assert TOKEN not in str(exc.value) and "ConnectionError" in str(exc.value)
    assert exc.value.__cause__ is None  # from None：traceback 不會帶出原例外
