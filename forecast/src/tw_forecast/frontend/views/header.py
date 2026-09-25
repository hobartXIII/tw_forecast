"""標題列的更新控制：立即更新、重新載入資料、告警設定三顆按鈕，以及更新流程的提示訊息。

輸入：更新門檻判斷（Gate）、pipeline_status 的列、GitHub 觸發器。輸出：畫面元件，以及使用者按了哪些按鈕。
update_gate.MANUAL_UPDATE_ENABLED 為 False 時（Streamlit 版目前的設定，立即更新只在 Vercel 版提供），
不畫「立即更新」按鈕（只剩兩顆），也不觸發 workflow、不顯示倒數與更新提示。
"""
import time
from dataclasses import dataclass
from datetime import timedelta

import streamlit as st

from tw_forecast.frontend import session, update_gate
from tw_forecast.frontend.countdown import interval_countdown_html
from tw_forecast.frontend.formatting import format_last_update
from tw_forecast.frontend.github_dispatch import WorkflowDispatcher
from tw_forecast.frontend.update_gate import MIN_INTERVAL_MINUTES, DispatchLog, Gate

REFRESH_AFTER_SECONDS = 60  # 觸發更新後，等這麼久自動重整頁面
COUNTDOWN_HEIGHT = 72       # 間隔倒數的 iframe 高度（手機上文字折成兩行剛好；st.iframe 的自動高度會量成 150px，不可用）


@st.fragment(run_every=1)
def refresh_countdown() -> None:
    """觸發更新後倒數，時間到就整頁重跑（重新查資料庫與狀態表；地區/縣市的選擇會保留）。"""
    left = st.session_state.get("refresh_at", 0) - time.time()
    if left <= 0:
        st.session_state.pop("refresh_at", None)
        st.rerun()
    st.info(f"已觸發更新，{int(left) + 1} 秒後自動重整頁面…")


def _interval_countdown(until: float) -> None:
    """間隔倒數：兩個數字都由瀏覽器每秒更新、彼此同步（見 countdown.py）；這個 fragment 只在 until 之後
    被觸發一次，到時整頁重跑，重新讀取資料庫，按鈕就會變成可按。"""
    left = until - time.time()
    if left <= 0:
        st.rerun()
    st.iframe(interval_countdown_html(MIN_INTERVAL_MINUTES, left), height=COUNTDOWN_HEIGHT)


def show_interval_countdown(gate: Gate) -> None:
    """gate 為「距上次成功更新不滿間隔」時顯示倒數。剩餘時間只在這一次腳本執行時取一次，之後由瀏覽器倒數；
    伺服器端只設定一個在剩餘時間後才觸發的計時（不是每秒更新）。"""
    until = time.time() + gate.wait_seconds
    run_after = timedelta(seconds=max(gate.wait_seconds + 1, 2))  # 多 1 秒，確保觸發時資料庫的時間已過門檻
    st.fragment(run_every=run_after)(_interval_countdown)(until)


@dataclass(frozen=True)
class HeaderActions:
    """使用者這次按了哪些按鈕（電腦版與手機版的同一顆按鈕合併）。"""
    update: bool
    reload: bool
    admin: bool


class Header:
    """標題列的按鈕與更新流程。"""

    def __init__(self, gate: Gate, configured: bool, dispatcher: WorkflowDispatcher, dispatch_log: DispatchLog):
        self.gate = gate
        self.configured = configured
        self.dispatcher = dispatcher
        self.dispatch_log = dispatch_log
        self.counting = "refresh_at" in st.session_state  # 已觸發更新、正在倒數

    def _buttons(self, where, suffix: str) -> tuple[bool, bool, bool]:
        """三顆按鈕（關閉立即更新時兩顆）。電腦版與手機版各畫一組（suffix 區分 key），由 style.py 的 CSS
        依視窗寬度只顯示其中一組；where 是放按鈕的位置（欄位、或手機版選單 popover 的內容區）。"""
        update = False
        if update_gate.MANUAL_UPDATE_ENABLED:
            update = where[0].button("⏳ 更新中…" if self.counting else "🔄 立即更新", key=f"update_{suffix}",
                                     disabled=self.counting or not self.gate.allowed, width="stretch")
            where = where[1:]
        reload = where[0].button("♻️ 重新載入資料", key=f"reload_{suffix}", width="stretch")
        admin = where[1].button("⚙️ 告警設定", key=f"admin_{suffix}", width="stretch",
                                disabled=not self.configured)
        return update, reload, admin

    def render_controls(self) -> HeaderActions:
        """畫按鈕（呼叫端要在放置按鈕的欄位 with 區塊內呼叫）：電腦版並排，手機版收進漢堡選單。"""
        count = 3 if update_gate.MANUAL_UPDATE_ENABLED else 2
        with st.container(key="hdr_desktop"):
            up_d, reload_d, admin_d = self._buttons(st.columns(count), "d")
        with st.container(key="hdr_mobile"):
            with st.popover("☰ 選單", width="stretch"):
                up_m, reload_m, admin_m = self._buttons([st] * count, "m")
        return HeaderActions(up_d or up_m, reload_d or reload_m, admin_d or admin_m)

    def handle(self, actions: HeaderActions, status_rows: list[dict] | None) -> None:
        """依按鈕與門檻顯示對應的訊息或觸發更新。

        每次執行（含按下按鈕的這一次）開頭都會重新讀取狀態表，所以 gate 就是按下當下的最新判斷；通過才呼叫更新。
        """
        if actions.reload:
            st.rerun()
        if update_gate.MANUAL_UPDATE_ENABLED:
            self._handle_update(actions)
        if status_rows is not None:
            interval = (f"　｜　手動更新需間隔 {MIN_INTERVAL_MINUTES} 分鐘"
                        if update_gate.MANUAL_UPDATE_ENABLED else "")
            st.caption(f"最近排程更新 {format_last_update(status_rows, 'schedule')}　｜　"
                       f"最近手動更新 {format_last_update(status_rows, 'manual')}{interval}")

    def _handle_update(self, actions: HeaderActions) -> None:
        """立即更新：觸發 workflow、倒數與更新結果的提示。"""
        if actions.update and self.gate.allowed:
            ok, msg = self.dispatcher.trigger()
            if ok:
                self.dispatch_log.record(session.now_taipei())  # 所有連線共用：F5 後按鈕仍維持停用
                st.session_state["refresh_at"] = time.time() + REFRESH_AFTER_SECONDS
                st.session_state["pending_since"] = session.now_taipei()
                st.rerun()  # 重跑後按鈕停用並開始倒數
            else:
                st.error(msg)
        elif self.counting:
            refresh_countdown()
        elif self.gate.wait_seconds is not None:  # 距上次更新不滿間隔：倒數，時間到自動重整
            show_interval_countdown(self.gate)
        elif not self.gate.allowed:
            st.info(self.gate.message)

        pending = st.session_state.get("pending_since")
        if pending is not None and not self.counting:  # 自動重整後，確認剛才觸發的更新是否已完成
            if self.gate.last_success is not None and self.gate.last_success >= pending:
                st.success("資料已更新完成")
                st.session_state.pop("pending_since")
            else:
                st.info("更新尚未完成，請稍後按「重新載入資料」")
