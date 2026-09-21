"""告警設定視窗的內容（登入視窗、設定視窗）。見 SPECIFICATION.md §8.1 第 8 點。

視窗本身（st.dialog）由 views/admin_dialogs.py 建立；這裡只放視窗裡的畫面與登入狀態管理，方便單獨測試。
- 密碼驗證在資料庫進行；密碼只存在本次連線的伺服器記憶體（st.session_state），不寫入日誌、不顯示。
- 視窗內操作元件時只會重跑視窗本身（等同 fragment）；需要「關閉視窗」時才使用整頁重跑 st.rerun()。
"""
import time

import streamlit as st
from streamlit.errors import StreamlitAPIException

from tw_forecast.frontend import admin
from tw_forecast.frontend.admin import AlertSettingsService

STATE_KEYS = ("admin_pw", "admin_df", "admin_slots", "admin_seen", "admin_ver")


def rerun_view() -> None:
    """只重跑視窗本身；若目前是整頁重跑（fragment 範圍無效）就退回整頁重跑，不會當掉。"""
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


class AdminPanel:
    """告警設定的登入狀態與兩個視窗畫面。狀態都存在 st.session_state（每個瀏覽器連線各一份）。"""

    def __init__(self, client):
        self._service = AlertSettingsService(client)

    # ---------- 登入狀態 ----------
    @staticmethod
    def logout(toast: str | None = None, defer: bool = True) -> None:
        """清除登入狀態（密碼與設定）。

        toast 的顯示時機：defer=True（預設）暫存到下一次整頁重跑再顯示——用於「接著要 st.rerun() 關閉視窗」的情況，
        因為 rerun 之前建立的 toast 會被丟掉；defer=False 則立刻顯示——用於在主流程（尚未開視窗）偵測到的情況。
        """
        for key in STATE_KEYS:
            st.session_state.pop(key, None)
        if toast:
            if defer:
                st.session_state["admin_toast"] = toast
            else:
                st.toast(toast)

    def load(self, password: str) -> None:
        """從資料庫重新讀取設定，並換一個版本號讓編輯元件回到資料庫的值。"""
        ss = st.session_state
        ss["admin_df"], ss["admin_slots"] = self._service.get_settings(password)
        ss["admin_ver"] = ss.get("admin_ver", 0) + 1

    def is_logged_in(self, defer: bool = False) -> bool:
        """已登入且沒有閒置逾時。逾時會登出並提示（defer 的意義見 logout）。"""
        ss = st.session_state
        if "admin_pw" not in ss:
            return False
        if time.time() - ss.get("admin_seen", 0) > admin.IDLE_TIMEOUT_SECONDS:
            self.logout("已因閒置超過 15 分鐘登出，請重新登入", defer=defer)
            return False
        return True

    def which_dialog(self, refresh: bool) -> str:
        """回傳要開啟的視窗：'settings'（已登入）或 'login'。

        已登入且 refresh=True 時，先從資料庫重新讀取設定（關閉視窗後未儲存的修改不保留，
        也能反映在 SQL Editor 直接改過的值）。
        """
        if not self.is_logged_in():
            return "login"
        if refresh:
            try:
                self.load(st.session_state["admin_pw"])
            except admin.WrongPassword:
                self.logout("密碼已失效，請重新登入", defer=False)  # 主流程，立刻顯示
                return "login"
            except admin.AdminError as exc:
                st.toast(str(exc))
                return "login"
        return "settings"

    # ---------- 視窗畫面 ----------
    def login_view(self) -> None:
        """登入視窗：只有密碼輸入框，看不到任何設定。成功後整頁重跑（關閉本視窗），由 app.py 接著開啟設定視窗。"""
        ss = st.session_state
        with st.form("admin_login", clear_on_submit=True, border=False):
            password = st.text_input("管理者密碼", type="password", help="輸入前請先把輸入法切成英文")
            submitted = st.form_submit_button("登入", width="stretch", type="primary")
        if not submitted:
            return
        if not password:
            st.warning("請輸入密碼")
            return
        if fails := min(ss.get("admin_fails", 0), 5):
            time.sleep(fails)  # 連續失敗越多次，等越久（資料庫端錯誤時另有 1 秒延遲）
        try:
            self.load(password)
        except admin.WrongPassword:
            ss["admin_fails"] = ss.get("admin_fails", 0) + 1
            st.error("密碼錯誤")
        except admin.AdminError as exc:
            st.error(str(exc))
        else:
            ss["admin_pw"], ss["admin_seen"], ss["admin_fails"] = password, time.time(), 0
            ss["admin_open_settings"] = True
            st.rerun()  # 整頁重跑：關閉登入視窗，app.py 會接著開啟設定視窗

    def settings_view(self) -> None:
        """設定視窗：發送時段、22 縣市可編輯表格、儲存／全部啟用／全部關閉／重新載入／登出。"""
        ss = st.session_state
        if not self.is_logged_in(defer=True):  # 閒置逾時：關閉視窗（提示暫存，整頁重跑後顯示在頁面上）
            st.rerun()
        ss["admin_seen"] = time.time()
        if notice := ss.pop("admin_notice", None):
            st.success(notice)
        df, slots, ver = ss["admin_df"], ss["admin_slots"], ss["admin_ver"]

        st.caption("勾選「啟用」的縣市才會發送告警｜設定在下一個發送時段生效｜閒置超過 15 分鐘需重新登入｜"
                   "關閉視窗會放棄未儲存的修改")
        if not df["啟用"].any():
            st.info("尚未啟用任何縣市，不會發送告警")

        with st.form("admin_edit", border=False):
            st.markdown("**發送時段**（勾選的時段才會發送；視窗為「該時段到下一個勾選時段之前」）")
            slot_cols = st.columns(len(admin.SLOTS))
            new_slots = {slot: col.checkbox(slot, value=slots[slot], key=f"admin_slot_{slot}_{ver}")
                         for slot, col in zip(admin.SLOTS, slot_cols)}
            st.markdown("**縣市設定**（每個縣市各自設定；降雨 ≥ 門檻、最低溫 ≤ 門檻、最高溫 ≥ 門檻，任一已勾選的條件符合就通知）")
            edited = st.data_editor(
                df, key=f"admin_editor_{ver}", hide_index=True, disabled=["縣市"], num_rows="fixed",
                width="stretch", height=420,
                column_config={
                    "啟用": st.column_config.CheckboxColumn(help="關閉的縣市不發送任何告警"),
                    "降雨": st.column_config.CheckboxColumn(help="啟用降雨條件"),
                    "降雨門檻 (%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=1, format="%d"),
                    "低溫": st.column_config.CheckboxColumn(help="啟用低溫條件"),
                    "低溫門檻 (°C)": st.column_config.NumberColumn(min_value=-20, max_value=50, step=0.5, format="%.1f"),
                    "高溫": st.column_config.CheckboxColumn(help="啟用高溫條件"),
                    "高溫門檻 (°C)": st.column_config.NumberColumn(min_value=-20, max_value=50, step=0.5, format="%.1f"),
                })
            col_save, col_on, col_off = st.columns(3)
            save = col_save.form_submit_button("💾 儲存", type="primary", width="stretch")
            all_on = col_on.form_submit_button("全部啟用（尚未儲存）", width="stretch")
            all_off = col_off.form_submit_button("全部關閉（尚未儲存）", width="stretch")

        if all_on or all_off:  # 只改表格內容，仍需按「儲存」才會寫入
            ss["admin_df"], ss["admin_slots"] = admin.set_all_enabled(edited, all_on), new_slots
            ss["admin_ver"] = ver + 1
            rerun_view()
        if save:
            try:
                self._service.save_settings(ss["admin_pw"], edited, new_slots)
                self.load(ss["admin_pw"])
                ss["admin_notice"] = "已儲存，設定會在下一個發送時段生效"
            except admin.WrongPassword:
                self.logout("密碼已失效，請重新登入")
                st.rerun()  # 關閉視窗
            except admin.AdminError as exc:
                st.error(f"儲存失敗：{exc}")
                return
            rerun_view()

        col_reload, col_logout = st.columns(2)
        if col_reload.button("重新載入（放棄未儲存的修改）", width="stretch"):
            try:
                self.load(ss["admin_pw"])
                ss["admin_notice"] = "已重新載入"
            except admin.AdminError as exc:
                self.logout(str(exc))
                st.rerun()
            rerun_view()
        if col_logout.button("登出", width="stretch"):
            self.logout("已登出")
            st.rerun()  # 關閉視窗
