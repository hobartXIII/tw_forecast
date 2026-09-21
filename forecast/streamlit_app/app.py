"""流程二：讀取 Supabase 預報資料並以 Streamlit + Folium 呈現（見 SPECIFICATION.md §8）。

執行：streamlit run streamlit_app/app.py

這裡只負責「串接」：依序呼叫 src/tw_forecast/frontend/ 底下各區塊。
輸入：使用者在頁面上的選擇（地區、縣市、日期、按鈕）與 Supabase 的預報資料；輸出：整個儀表板頁面。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # 讓 `import tw_forecast` 找得到 src/

import streamlit as st  # noqa: E402

from tw_forecast.frontend import session, style, update_gate  # noqa: E402
from tw_forecast.frontend.admin_ui import AdminPanel  # noqa: E402
from tw_forecast.frontend.formatting import format_range  # noqa: E402
from tw_forecast.frontend.github_dispatch import WorkflowDispatcher  # noqa: E402
from tw_forecast.frontend.repository import ForecastQuery  # noqa: E402
from tw_forecast.frontend.scope import add_region  # noqa: E402
from tw_forecast.frontend.temperature import display_temp  # noqa: E402
from tw_forecast.frontend.views import admin_dialogs  # noqa: E402
from tw_forecast.frontend.views.filters import render_filters  # noqa: E402
from tw_forecast.frontend.views.header import Header  # noqa: E402
from tw_forecast.frontend.views.map_section import render_map  # noqa: E402
from tw_forecast.frontend.views.summary import render_summary  # noqa: E402
from tw_forecast.frontend.views.tabs import render_tabs  # noqa: E402

st.set_page_config(page_title="台灣天氣預報", page_icon="🌤️", layout="wide")
style.inject()  # 玻璃擬態樣式（淺色／深色）


def main() -> None:
    # ---------- 標題與更新控制 ----------
    head_left, head_right = st.columns([2, 3])
    head_left.title("🌤️ 台灣天氣預報")

    configured = session.is_configured()
    sb = None
    status_rows = None  # 讀不到就維持 None：不放行手動更新
    if configured:
        try:
            sb = session.get_client()
            status_rows = ForecastQuery(sb).update_status()
        except Exception:
            status_rows = None
    log = session.dispatch_log()
    gate = update_gate.evaluate(status_rows, session.now_taipei(), dispatched_at=log.last)
    dispatcher = WorkflowDispatcher(session.secret("GH_REPO"), session.secret("GH_DISPATCH_TOKEN"))
    header = Header(gate, configured, dispatcher, log)
    with head_right:
        actions = header.render_controls()
    header.handle(actions, status_rows)

    # ---------- 告警設定視窗 ----------
    admin_dialogs.open_if_requested(AdminPanel(sb), configured, actions.admin)

    # ---------- 讀取資料庫（不快取，每次載入都重新查詢） ----------
    if not configured:
        st.error("尚未設定 SUPABASE_URL / SUPABASE_ANON_KEY（見 .streamlit/secrets.toml.example）")
        st.stop()
    try:
        with st.spinner("讀取預報資料中…"):
            sb = sb or session.get_client()
            query = ForecastQuery(sb)
            now = session.now_taipei()
            current = query.current(now)
            forecast = query.forecast(now)
    except Exception as exc:
        st.error(f"讀取資料庫失敗：{exc}")
        st.stop()
    if current.empty:
        st.warning("資料庫目前沒有預報資料，請先執行流程一（GitHub Actions）。")
        st.stop()
    current = add_region(current)
    if not forecast.empty:  # 資料過期（排程停擺）時 forecast 可能為空
        forecast = add_region(forecast)

    # ---------- 篩選（地區與縣市互斥）與目前時段 ----------
    scope = render_filters()
    cur = scope.filter_current(current)
    if cur.empty:
        st.warning("此範圍目前沒有資料。")
        st.stop()
    cur = cur.assign(avg=display_temp(cur))
    start, end = cur["forecast_time_start"].iloc[0], cur["forecast_time_end"].iloc[0]

    st.caption(f"預報時段 **{format_range(start, end)}**　｜　資料更新 **{cur['updated_at'].max():%m/%d %H:%M}**"
               "　｜　時間皆為台灣時間")
    if not start <= now < end:
        st.warning("目前沒有涵蓋此刻的預報時段，顯示的是最接近的時段。資料可能已過期，可按「立即更新」。")

    # ---------- 重點摘要、地圖、趨勢與明細 ----------
    render_summary(cur, scope)
    render_map(cur, scope)
    render_tabs(scope, cur, scope.filter_forecast(forecast), query, now, start)


main()
