"""流程二：讀取 Supabase 預報資料並以 Streamlit + Folium 呈現（見 SPECIFICATION.md §8）。

執行：streamlit run streamlit_app/app.py

這裡只負責「串接」：依序呼叫 src/tw_forecast/frontend/ 底下各區塊。
輸入：使用者在頁面上的選擇（地區、縣市、日期、按鈕）與 Supabase 的預報資料；輸出：整個儀表板頁面。

頁面由上而下分成 A～H 幾個區塊，下面 main() 的註解用同樣的代號標出各區塊由哪一行畫出來；
完整的畫面示意圖與「區塊 ↔ 檔案」對照表見 ARCHITECTURE.md 的「頁面區塊對照」。
Streamlit 沒有事件處理：每次載入或操作，main() 都會從頭整段重跑一次（像一份會重複執行的模板）。
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
    # ---------- [A] 標題、[B] 三顆按鈕、[C] 更新提示 ----------
    head_left, head_right = st.columns([2, 3])
    head_left.title("🌤️ 台灣天氣預報")  # [A] 標題（畫面左上）

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
    with head_right:  # [B] 立即更新／重新載入資料／告警設定 三顆按鈕（畫面右上）
        actions = header.render_controls()
    header.handle(actions, status_rows)  # [C] 更新提示、倒數、「最近排程更新…」小字

    # ---------- [彈出] 告警設定視窗（按了 [B] 的「告警設定」才會出現） ----------
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

    # ---------- [D] 地區／縣市篩選（互斥）與目前時段 ----------
    scope = render_filters()  # [D] 兩個下拉選單
    cur = scope.filter_current(current)
    if cur.empty:
        st.warning("此範圍目前沒有資料。")
        st.stop()
    cur = cur.assign(avg=display_temp(cur))
    start, end = cur["forecast_time_start"].iloc[0], cur["forecast_time_end"].iloc[0]

    # [E] 預報時段與資料更新時間；目前時間不在該時段內時顯示過期警示
    st.caption(f"預報時段 **{format_range(start, end)}**　｜　資料更新 **{cur['updated_at'].max():%m/%d %H:%M}**"
               "　｜　時間皆為台灣時間")
    if not start <= now < end:
        st.warning("目前沒有涵蓋此刻的預報時段，顯示的是最接近的時段。資料可能已過期，可按「立即更新」。")

    # ---------- [F] 摘要卡片、[G] 地圖、[H] 分頁 ----------
    render_summary(cur, scope)  # [F] 四張摘要卡片
    render_map(cur, scope)  # [G] 地圖
    render_tabs(scope, cur, scope.filter_forecast(forecast), query, now, start)  # [H] 氣溫趨勢／降雨機率／明細／後續時段／日期查詢


main()
