"""排程時槽：台灣時間 02:45 起每 3 小時。"""
from datetime import datetime

import pytest

from tw_forecast.backend.slots import current_slot
from tw_forecast.config import TZ


def at(hour, minute, day=21):
    return datetime(2026, 9, day, hour, minute, tzinfo=TZ)


@pytest.mark.parametrize("now, expected", [
    (at(2, 45), at(2, 45)),      # 剛好在時槽上
    (at(2, 46), at(2, 45)),
    (at(5, 44), at(2, 45)),      # 下一個時槽之前
    (at(5, 45), at(5, 45)),
    (at(8, 55), at(8, 45)),      # GitHub 排程延遲 10 分鐘，仍算 08:45 時槽
    (at(23, 59), at(23, 45)),
    (at(1, 0), at(23, 45, day=20)),   # 凌晨 02:45 之前屬於前一天最後一個時槽
])
def test_current_slot(now, expected):
    assert current_slot(now) == expected
