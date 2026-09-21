"""排程時槽計算（純函式，不連網）。"""
from datetime import datetime

from tw_forecast.config import SLOT_ANCHOR, SLOT_INTERVAL


def current_slot(now: datetime) -> datetime:
    """輸入：現在時間（帶時區）。輸出：最近一個已經過去的排程時槽。

    以時槽而非實際執行時間判斷「這次是哪個發送時段」，排程被 GitHub 延遲（不到一個間隔）也不受影響。
    """
    anchor = now.replace(hour=SLOT_ANCHOR[0], minute=SLOT_ANCHOR[1], second=0, microsecond=0)
    return anchor + ((now - anchor) // SLOT_INTERVAL) * SLOT_INTERVAL
