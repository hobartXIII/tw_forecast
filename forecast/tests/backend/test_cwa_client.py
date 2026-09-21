"""CwaClient：重試、429 中止、缺金鑰（假的 get 與 sleep，不連網也不真的等待）。"""
import pytest
import requests

from tw_forecast.backend.cwa_client import CwaClient
from tw_forecast.backend.errors import AbortRun


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body if body is not None else {"success": "true", "records": {}}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


class Sequence:
    """依序回傳回應或拋出例外，並記錄呼叫次數。"""

    def __init__(self, *items):
        self.items, self.calls = list(items), 0

    def __call__(self, url, params, headers, timeout):
        self.calls += 1
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make(get, sleeps=None):
    return CwaClient("KEY", sleep=(sleeps.append if sleeps is not None else lambda s: None), get=get)


def test_success_returns_payload_and_sends_key_header():
    seen = {}

    def get(url, params, headers, timeout):
        seen.update(headers=headers, params=params)
        return FakeResponse()

    assert make(get).fetch()["success"] == "true"
    assert seen["headers"] == {"Authorization": "KEY"} and seen["params"] == {"format": "JSON"}


def test_missing_api_key_aborts_without_calling_api():
    get = Sequence()
    with pytest.raises(AbortRun, match="WEATHER_API_KEY"):
        CwaClient(None, get=get).fetch()
    assert get.calls == 0


def test_429_aborts_immediately_without_retry():
    get = Sequence(FakeResponse(429))
    with pytest.raises(AbortRun, match="429"):
        make(get).fetch()
    assert get.calls == 1


def test_retries_then_succeeds_with_backoff():
    sleeps = []
    get = Sequence(requests.ConnectionError("x"), FakeResponse(500), FakeResponse())
    assert make(get, sleeps).fetch()["success"] == "true"
    assert get.calls == 3 and sleeps == [5, 15]


def test_gives_up_after_max_attempts_and_reraises():
    get = Sequence(*[requests.ConnectionError("boom")] * 3)
    with pytest.raises(requests.ConnectionError):
        make(get).fetch()
    assert get.calls == 3


def test_success_flag_false_is_treated_as_failure():
    get = Sequence(*[FakeResponse(200, {"success": "false", "result": "nope"})] * 3)
    with pytest.raises(RuntimeError, match="success"):
        make(get).fetch()
