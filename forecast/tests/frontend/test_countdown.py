"""瀏覽器端倒數的 HTML 產生（純函式）。"""
import pytest

from tw_forecast.frontend.countdown import format_mmss, interval_countdown_html


@pytest.mark.parametrize("seconds, text", [
    (0, "00:00"), (-5, "00:00"), (0.2, "00:01"), (59.01, "01:00"), (60, "01:00"), (822.4, "13:43"), (1200, "20:00"),
])
def test_format_mmss_rounds_up_and_never_negative(seconds, text):
    assert format_mmss(seconds) == text


def test_html_embeds_initial_elapsed_and_remaining_time():
    # 20 分鐘間隔，還剩 90 秒（=1:30）→ 已過 18 分鐘。
    html = interval_countdown_html(20, 90)
    assert ">18<" in html and ">01:30<" in html and "需間隔 20 分鐘" in html
    assert "const total = 1200;" in html and "Date.now() + 90000;" in html


def test_elapsed_and_remaining_derive_from_the_same_clock_so_they_stay_in_sync():
    """兩個數字都用同一個 total/left 算出來，不會有其中一個沒跟著動的情況。"""
    html = interval_countdown_html(20, 90)
    assert "total - left" in html  # 已過分鐘數是從剩餘秒數推導，而不是寫死的常數


def test_negative_seconds_start_at_zero():
    html = interval_countdown_html(20, -3)
    assert "Date.now() + 0;" in html and ">20<" in html  # 已到門檻：已過分鐘數等於間隔本身


def test_html_supports_dark_mode_and_ticks_in_browser():
    html = interval_countdown_html(20, 5)
    assert "prefers-color-scheme: dark" in html and "setTimeout(tick" in html
