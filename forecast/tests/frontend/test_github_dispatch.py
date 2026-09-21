"""WorkflowDispatcher：觸發後端 workflow（假的 post，不連網）。"""
import pytest
import requests

from tw_forecast.frontend.github_dispatch import WorkflowDispatcher


class Response:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


def dispatcher(post, repo="owner/repo", token="ghp_token"):
    return WorkflowDispatcher(repo, token, post=post)


def test_success_on_204_and_200_sends_expected_request():
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return Response(204)

    assert dispatcher(post).trigger() == (True, "")
    assert seen["url"] == "https://api.github.com/repos/owner/repo/actions/workflows/weather_worker.yml/dispatches"
    assert seen["headers"]["Authorization"] == "Bearer ghp_token" and seen["json"] == {"ref": "main"}
    assert dispatcher(lambda *a, **k: Response(200)).trigger() == (True, "")


@pytest.mark.parametrize("repo, token", [(None, "t"), ("r", None), ("", "")])
def test_missing_configuration_does_not_call_api(repo, token):
    def post(*a, **k):
        raise AssertionError("不應該呼叫 API")

    ok, message = dispatcher(post, repo, token).trigger()
    assert not ok and "GH_REPO" in message


def test_http_error_reports_status_and_truncates_body():
    ok, message = dispatcher(lambda *a, **k: Response(403, "x" * 500)).trigger()
    assert not ok and "HTTP 403" in message and len(message) < 260


def test_connection_error_is_reported():
    def post(*a, **k):
        raise requests.ConnectionError("dns")

    ok, message = dispatcher(post).trigger()
    assert not ok and "無法連線至 GitHub" in message
