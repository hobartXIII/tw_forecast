"""手動更新的門檻判斷。

輸入：pipeline_status 的列（last_success_at 為 tz-aware 或 None）、現在時間、最近一次觸發時間。
輸出：Gate（可否更新與提示文字）。

依據是資料庫 pipeline_status 表記錄的「最後一次成功更新時間」（排程與手動取較新者），與使用者人數、
瀏覽器狀態無關；讀不到（None 或空表）一律不放行。排程不受此限制。

另外，觸發後到資料庫出現新的成功紀錄之間有空窗（workflow 排隊與執行約 30～60 秒），這段時間資料庫看起來
仍可更新，重新整理頁面就會讓按鈕重新開放。因此伺服器記憶體會記住「最近一次觸發時間」（DispatchLog，
所有連線共用）：觸發後、資料庫尚無更新的成功紀錄、且未超過 DISPATCH_LOCK_MINUTES 時，一律不放行。
見 SPECIFICATION.md §8.1。
"""
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

MANUAL_UPDATE_ENABLED = False  # 「立即更新」只在 Vercel 版提供；Streamlit 版關閉（按鈕不顯示、不觸發 workflow）
MIN_INTERVAL_MINUTES = 20
DISPATCH_LOCK_MINUTES = 5  # 觸發後最多鎖這麼久；workflow 失敗時不會一直鎖住
UNKNOWN_MESSAGE = "無法確認最後更新時間，暫不開放手動更新"
IN_PROGRESS_MESSAGE = "已觸發更新，正在等待完成，請稍後按「重新載入資料」"


def stale_hint() -> str:
    """資料過期時的引導文字：有「立即更新」就請使用者按，沒有就請等排程。"""
    return "請按「立即更新」" if MANUAL_UPDATE_ENABLED else "請等待下次排程更新（每 3 小時一次）"


class DispatchLog:
    """記住最近一次觸發更新的時間（伺服器記憶體，所有連線共用；app 重啟後清空）。"""

    def __init__(self):
        self._at: datetime | None = None
        self._lock = threading.Lock()

    def record(self, at: datetime) -> None:
        with self._lock:
            self._at = at

    @property
    def last(self) -> datetime | None:
        with self._lock:
            return self._at


@dataclass(frozen=True)
class Gate:
    """判斷結果：allowed 為是否放行；message 為不放行時的提示；last_success 為最後一次成功更新時間。

    只有「距上次成功更新不滿間隔」這種情況才有 wait_seconds（還要等幾秒才可再更新）與 elapsed_minutes
    （已過幾分鐘），畫面用它們做倒數；其他情況為 None。
    """
    allowed: bool
    message: str = ""
    last_success: pd.Timestamp | None = None
    wait_seconds: float | None = None
    elapsed_minutes: int | None = None


def evaluate(rows: list[dict] | None, now: datetime, min_minutes: int = MIN_INTERVAL_MINUTES,
             dispatched_at: datetime | None = None) -> Gate:
    """rows 為 pipeline_status 的列；讀取失敗傳 None。dispatched_at 為最近一次觸發更新的時間（沒有則 None）。"""
    if not rows:
        return Gate(False, UNKNOWN_MESSAGE)
    times = [r["last_success_at"] for r in rows if r.get("last_success_at") is not None]
    last = max(times) if times else None
    just_dispatched = (dispatched_at is not None
                       and now - dispatched_at < timedelta(minutes=DISPATCH_LOCK_MINUTES)
                       and (last is None or last < dispatched_at))
    if just_dispatched:
        return Gate(False, IN_PROGRESS_MESSAGE, last)  # 剛觸發、資料庫還沒出現新的成功紀錄
    if last is None:  # 有紀錄表但從未成功更新過：沒有東西需要保護，放行
        return Gate(True)
    elapsed = now - last
    wait = timedelta(minutes=min_minutes) - elapsed
    if wait > timedelta(0):
        elapsed_min = max(int(elapsed.total_seconds() // 60), 0)
        wait_min = math.ceil(wait.total_seconds() / 60)
        return Gate(False, f"距上次更新僅 {elapsed_min} 分鐘，手動更新需間隔至少 {min_minutes} 分鐘，"
                           f"請約 {wait_min} 分鐘後再試", last,
                    wait_seconds=wait.total_seconds(), elapsed_minutes=elapsed_min)
    return Gate(True, last_success=last)
