"""瀏覽器端倒數的 HTML 產生（純函式）。"""
import pytest

from tw_forecast.frontend.countdown import countdown_html, format_mmss


@pytest.mark.parametrize("seconds, text", [
    (0, "00:00"), (-5, "00:00"), (0.2, "00:01"), (59.01, "01:00"), (60, "01:00"), (822.4, "13:43"), (1200, "20:00"),
])
def test_format_mmss_rounds_up_and_never_negative(seconds, text):
    assert format_mmss(seconds) == text


def test_html_embeds_initial_time_and_remaining_milliseconds():
    html = countdown_html("還需 ", 90, " 才可更新")
    assert "還需 " in html and ">01:30<" in html and " 才可更新" in html
    assert "Date.now() + 90000;" in html


def test_html_escapes_text_so_it_cannot_inject_markup():
    html = countdown_html("<script>alert(1)</script>", 10, "<b>")
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html and "&lt;b&gt;" in html


def test_negative_seconds_start_at_zero():
    assert "Date.now() + 0;" in countdown_html("x", -3)


def test_html_supports_dark_mode_and_ticks_in_browser():
    html = countdown_html("x", 5)
    assert "prefers-color-scheme: dark" in html and "setTimeout(tick" in html
