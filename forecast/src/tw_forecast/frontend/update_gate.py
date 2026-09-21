"""手動更新的門檻判斷。

輸入：pipeline_status 的列（last_success_at 為 tz-aware 或 None）與現在時間。輸出：Gate（可否更新與提示文字）。

唯一依據是資料庫 pipeline_status 表記錄的「最後一次成功更新時間」（排程與手動取較新者），
與使用者人數、瀏覽器狀態無關；讀不到（None 或空表）一律不放行。排程不受此限制。
見 SPECIFICATION.md §8.1。
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

MIN_INTERVAL_MINUTES = 20
UNKNOWN_MESSAGE = "無法確認最後更新時間，暫不開放手動更新"


@dataclass(frozen=True)
class Gate:
    """判斷結果：allowed 為是否放行；message 為不放行時的提示；last_success 為最後一次成功更新時間。"""
    allowed: bool
    message: str = ""
    last_success: pd.Timestamp | None = None


def evaluate(rows: list[dict] | None, now: datetime, min_minutes: int = MIN_INTERVAL_MINUTES) -> Gate:
    """rows 為 pipeline_status 的列；讀取失敗傳 None。"""
    if not rows:
        return Gate(False, UNKNOWN_MESSAGE)
    times = [r["last_success_at"] for r in rows if r.get("last_success_at") is not None]
    if not times:  # 有紀錄表但從未成功更新過：沒有東西需要保護，放行
        return Gate(True)
    last = max(times)
    elapsed = now - last
    wait = timedelta(minutes=min_minutes) - elapsed
    if wait > timedelta(0):
        elapsed_min = max(int(elapsed.total_seconds() // 60), 0)
        wait_min = math.ceil(wait.total_seconds() / 60)
        return Gate(False, f"距上次更新僅 {elapsed_min} 分鐘，手動更新需間隔至少 {min_minutes} 分鐘，"
                           f"請約 {wait_min} 分鐘後再試", last)
    return Gate(True, last_success=last)
