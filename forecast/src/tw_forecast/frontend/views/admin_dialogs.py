"""告警設定的兩個視窗（st.dialog）。視窗內容在 admin_ui.AdminPanel；一次只能開一個視窗。"""
import streamlit as st

from tw_forecast.frontend.admin_ui import AdminPanel


@st.dialog("🔒 管理者登入", width="small")
def login_dialog(panel: AdminPanel) -> None:
    """登入用的小視窗：只有一個密碼框。"""
    panel.login_view()


@st.dialog("⚙️ 告警設定", width="large")  # 設定表格有 8 欄，需要寬視窗
def settings_dialog(panel: AdminPanel) -> None:
    """登入後的設定大視窗。"""
    panel.settings_view()


def open_if_requested(panel: AdminPanel, configured: bool, clicked: bool) -> None:
    """依按鈕或「登入成功後的整頁重跑」開啟對應視窗，並顯示暫存的提示（登出、逾時、密碼失效等）。"""
    if toast := st.session_state.pop("admin_toast", None):
        st.toast(toast)
    open_after_login = st.session_state.pop("admin_open_settings", False)  # 登入成功後整頁重跑，接著開設定視窗
    if configured and (clicked or open_after_login):
        if panel.which_dialog(refresh=clicked) == "settings":  # 重新按按鈕時從資料庫重讀設定
            settings_dialog(panel)
        else:
            login_dialog(panel)
