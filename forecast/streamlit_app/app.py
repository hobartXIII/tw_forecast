"""流程二：讀取 Supabase 預報資料並以 Streamlit + Folium 呈現（見 SPECIFICATION.md §8）。

執行：streamlit run streamlit_app/app.py
"""
import time

import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

from components import admin_ui, db
from components.charts import RAIN_ALERT, series_chart
from components.format import is_night, weather_icon
from components.map_view import build_map, colored, display_temp, text_color
from components.region_data import ALL_REGIONS, CITY_ORDER, REGIONS, cities_in, region_of
from components.style import card, inject
from components.update_gate import MIN_INTERVAL_MINUTES, evaluate

ALL_CITIES = "全部縣市"
METRICS = {"最高溫": "max_temp", "最低溫": "min_temp", "平均溫": "avg"}

WORKFLOW_FILE = "weather_worker.yml"
REFRESH_AFTER_SECONDS = 60  # 觸發更新後，等這麼久自動重整頁面

st.set_page_config(page_title="台灣天氣預報", page_icon="🌤️", layout="wide")
inject()  # 玻璃擬態樣式（淺色／深色）


def secret(name: str) -> str | None:
    try:
        return st.secrets.get(name)
    except Exception:  # 沒有 secrets.toml 時 st.secrets 會拋例外
        return None


def trigger_update() -> tuple[bool, str]:
    """呼叫 GitHub API 觸發 workflow_dispatch，成功回傳 HTTP 204。"""
    repo, token = secret("GH_REPO"), secret("GH_DISPATCH_TOKEN")
    if not repo or not token:
        return False, "尚未設定 GH_REPO / GH_DISPATCH_TOKEN"
    try:
        resp = requests.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"ref": "main"}, timeout=15)
    except requests.RequestException as exc:
        return False, f"無法連線至 GitHub：{exc}"
    if resp.status_code == 204:
        return True, ""
    return False, f"觸發失敗（HTTP {resp.status_code}）：{resp.text[:200]}"


def fmt_range(start: pd.Timestamp, end: pd.Timestamp) -> str:
    return f"{start:%m/%d %H:%M} ~ {end:%m/%d %H:%M}"


def fmt_last(rows: list[dict] | None, trigger: str) -> str:
    """某來源（schedule / manual）最後一次成功更新的時間文字。"""
    for row in rows or []:
        if row.get("trigger_type") == trigger and row.get("last_success_at") is not None:
            return f"{row['last_success_at']:%m/%d %H:%M}"
    return "—"


def add_region(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["region"] = df["location_name"].map(region_of)
    df["order"] = df["location_name"].map(lambda c: CITY_ORDER.index(c) if c in CITY_ORDER else 99)
    return df


@st.fragment(run_every=1)
def refresh_countdown() -> None:
    """觸發更新後倒數，時間到就整頁重跑（重新查資料庫與狀態表；地區/縣市的選擇會保留）。"""
    left = st.session_state.get("refresh_at", 0) - time.time()
    if left <= 0:
        st.session_state.pop("refresh_at", None)
        st.rerun()
    st.info(f"已觸發更新，{int(left) + 1} 秒後自動重整頁面…")


# ---------- 告警設定視窗（內容在 components/admin_ui.py；一次只能開一個視窗） ----------
@st.dialog("🔒 管理者登入", width="small")
def admin_login_dialog(sb) -> None:
    admin_ui.login_view(sb)


@st.dialog("⚙️ 告警設定", width="large")  # 設定表格有 8 欄，需要寬視窗；登入只有一個密碼框，用小視窗
def admin_settings_dialog(sb) -> None:
    admin_ui.settings_view(sb)


# ---------- 標題與更新控制 ----------
head_left, head_right = st.columns([2, 3])
head_left.title("🌤️ 台灣天氣預報")

configured = bool(secret("SUPABASE_URL") and secret("SUPABASE_ANON_KEY"))
sb = None
status_rows = None  # 讀不到就維持 None：不放行手動更新
if configured:
    try:
        sb = db.get_client()
        status_rows = db.fetch_update_status(sb)
    except Exception:
        status_rows = None
gate = evaluate(status_rows, db.now_taipei())
counting = "refresh_at" in st.session_state

def header_buttons(where, suffix: str) -> tuple[bool, bool, bool]:
    """標題列三顆按鈕（立即更新、重新載入資料、告警設定）。

    電腦版與手機版各畫一組（suffix 區分 key），由 style.py 的 CSS 依視窗寬度只顯示其中一組；
    where 是放按鈕的位置（欄位、或手機版選單 popover 的內容區）。
    """
    update = where[0].button("⏳ 更新中…" if counting else "🔄 立即更新", key=f"update_{suffix}",
                             disabled=counting or not gate.allowed, width="stretch")
    reload = where[1].button("♻️ 重新載入資料", key=f"reload_{suffix}", width="stretch")
    admin = where[2].button("⚙️ 告警設定", key=f"admin_{suffix}", width="stretch", disabled=not configured)
    return update, reload, admin


with head_right:
    with st.container(key="hdr_desktop"):  # 電腦版：三顆按鈕並排
        up_d, reload_d, admin_d = header_buttons(st.columns(3), "d")
    with st.container(key="hdr_mobile"):  # 手機版：收進漢堡選單，點開才看到三個選項
        with st.popover("☰ 選單", width="stretch"):
            up_m, reload_m, admin_m = header_buttons([st, st, st], "m")
clicked, open_admin = up_d or up_m, admin_d or admin_m
if reload_d or reload_m:
    st.rerun()

# 每次執行（含按下按鈕的這一次）開頭都會重新讀取狀態表，所以這裡的 gate 就是按下當下的最新判斷；
# 通過才呼叫更新。
if clicked and gate.allowed:
    ok, msg = trigger_update()
    if ok:
        st.session_state["refresh_at"] = time.time() + REFRESH_AFTER_SECONDS
        st.session_state["pending_since"] = db.now_taipei()
        st.rerun()  # 重跑後按鈕停用並開始倒數
    else:
        st.error(msg)
elif counting:
    refresh_countdown()
elif not gate.allowed:
    st.info(gate.message)

pending = st.session_state.get("pending_since")
if pending is not None and not counting:  # 自動重整後，確認剛才觸發的更新是否已完成
    if gate.last_success is not None and gate.last_success >= pending:
        st.success("資料已更新完成")
        st.session_state.pop("pending_since")
    else:
        st.info("更新尚未完成，請稍後按「重新載入資料」")

if status_rows is not None:
    st.caption(f"最近排程更新 {fmt_last(status_rows, 'schedule')}　｜　最近手動更新 {fmt_last(status_rows, 'manual')}"
               f"　｜　手動更新需間隔 {MIN_INTERVAL_MINUTES} 分鐘")

# ---------- 開啟告警設定視窗 ----------
if toast := st.session_state.pop("admin_toast", None):  # 登出、逾時、密碼失效等提示
    st.toast(toast)
open_after_login = st.session_state.pop("admin_open_settings", False)  # 登入成功後整頁重跑，接著開設定視窗
if configured and (open_admin or open_after_login):
    if admin_ui.which_dialog(sb, refresh=open_admin) == "settings":  # 重新按按鈕時從資料庫重讀設定
        admin_settings_dialog(sb)
    else:
        admin_login_dialog(sb)

# ---------- 讀取資料庫（不快取，每次載入都重新查詢） ----------
if not configured:
    st.error("尚未設定 SUPABASE_URL / SUPABASE_ANON_KEY（見 .streamlit/secrets.toml.example）")
    st.stop()
try:
    with st.spinner("讀取預報資料中…"):
        sb = sb or db.get_client()
        now = db.now_taipei()
        current = db.fetch_current(sb, now)
        forecast = db.fetch_forecast(sb, now)
except Exception as exc:
    st.error(f"讀取資料庫失敗：{exc}")
    st.stop()
if current.empty:
    st.warning("資料庫目前沒有預報資料，請先執行流程一（GitHub Actions）。")
    st.stop()
current = add_region(current)
if not forecast.empty:  # 資料過期（排程停擺）時 forecast 可能為空
    forecast = add_region(forecast)

# ---------- 篩選（地區與縣市互斥；整頁內容跟著選擇更新） ----------
def _on_region_change() -> None:
    st.session_state["city"] = ALL_CITIES  # 選地區 → 縣市回到「全部縣市」


def _on_city_change() -> None:
    st.session_state["region"] = ALL_REGIONS  # 選縣市 → 地區回到「全部地區」


sel_left, sel_right = st.columns(2)
region = sel_left.selectbox("地區", [ALL_REGIONS, *REGIONS], key="region", on_change=_on_region_change)
city_choice = sel_right.selectbox("縣市", [ALL_CITIES, *CITY_ORDER], key="city", on_change=_on_city_change)
city = None if city_choice == ALL_CITIES else city_choice
# 顯示層級：全台（依地區平均）→ 地區（依縣市）→ 單一縣市（依時段）
level = "city" if city else ("all" if region == ALL_REGIONS else "region")
# 單一縣市時，地圖與對照範圍用該縣市所屬的地區（地區下拉已被清成「全部地區」）
home_region = region_of(city) if city else None
region_cities = cities_in(home_region) if home_region else cities_in(region)

cur = current[current["location_name"].isin(region_cities)].sort_values("order")
if cur.empty:
    st.warning("此範圍目前沒有資料。")
    st.stop()
cur = cur.assign(avg=display_temp(cur))
crow = cur[cur["location_name"] == city].iloc[0] if city else None
start, end = cur["forecast_time_start"].iloc[0], cur["forecast_time_end"].iloc[0]
in_period = start <= now < end

caption = (f"預報時段 **{fmt_range(start, end)}**　｜　資料更新 **{cur['updated_at'].max():%m/%d %H:%M}**"
           "　｜　時間皆為台灣時間")
st.caption(caption)
if not in_period:
    st.warning("目前沒有涵蓋此刻的預報時段，顯示的是最接近的時段。資料可能已過期，可按「立即更新」。")


# ---------- 重點摘要 ----------
def extreme(column: str, largest: bool) -> tuple[float | None, str]:
    """回傳 (數值, 縣市名)；欄位全為 NULL 時回傳 (None, "")。"""
    valid = cur.dropna(subset=[column])
    if valid.empty:
        return None, ""
    row = valid.loc[valid[column].idxmax() if largest else valid[column].idxmin()]
    return row[column], row["location_name"]


def show(value, unit: str, fmt: str = ".0f") -> str:
    return "—" if value is None or pd.isna(value) else f"{value:{fmt}} {unit}"


def temp_metric(col, label: str, value, fmt: str = ".0f", aside: str = "") -> None:
    """玻璃卡片，數字依溫度級距上色（st.metric 的數值無法指定顏色）；aside 顯示在數值右側。"""
    col.markdown(card(label, colored(value, show(value, "°C", fmt)), aside), unsafe_allow_html=True)


def plain_metric(col, label: str, value: str) -> None:
    """與 temp_metric 同外觀的玻璃卡片，數字不上色（降雨機率）。"""
    col.markdown(card(label, value), unsafe_allow_html=True)


def with_city(label: str, name: str) -> str:
    """多縣市摘要：標題列在指標名稱後接縣市名（「最高溫　臺中市」），數值放下一行。"""
    return f"{label}　{name}" if name else label


k1, k2, k3, k4 = st.columns(4)
if city:  # 單一縣市：直接呈現該縣市自己的數值，天氣現象（圖示與文字）放在「平均氣溫」數值右側
    weather = crow["weather_condition"] if isinstance(crow["weather_condition"], str) else "—"
    icon = weather_icon(weather, is_night(crow["forecast_time_start"], crow["forecast_time_end"]))
    temp_metric(k1, f"{city} 平均氣溫", crow["avg"], ".1f", f"{icon} {weather}".strip())
    temp_metric(k2, "最高溫", crow["max_temp"])
    temp_metric(k3, "最低溫", crow["min_temp"])
    plain_metric(k4, "降雨機率", show(crow["rain_probability"], "%"))
else:
    hot, hot_city = extreme("max_temp", True)
    cold, cold_city = extreme("min_temp", False)
    wet, wet_city = extreme("rain_probability", True)
    temp_metric(k1, "平均氣溫", cur["avg"].mean(), ".1f")
    temp_metric(k2, with_city("最高溫", hot_city), hot)
    temp_metric(k3, with_city("最低溫", cold_city), cold)
    plain_metric(k4, with_city("最高降雨機率", wet_city), show(wet, "%"))

# ---------- 地圖 ----------
st.subheader("🗺️ 平均氣溫地圖")
st.caption("滾輪縮放已關閉，請用地圖左上角的 ＋／－ 按鈕縮放，並可拖曳平移；滑鼠移到標記上可看詳細資料。"
           + (f"被選的縣市已放大並加外框，其餘{home_region or ''}縣市淡化作為對照。" if city else ""))
st_folium(build_map(cur, fit=level == "region", highlight=city), height=520,
          use_container_width=True, returned_objects=[])

# ---------- 趨勢與明細（分頁） ----------
scope_cities = [city] if city else region_cities
fc = None
if not forecast.empty:
    fc = forecast[forecast["location_name"].isin(scope_cities)]
    fc = fc.assign(avg=display_temp(fc)) if not fc.empty else None
scope_label = {"all": "全台各地區平均", "region": f"{region}各縣市", "city": city}[level]


def series_data(column: str) -> tuple[pd.DataFrame, list[str]]:
    """多系列長表與圖例順序：全台 → 每地區平均一條線；單一地區 → 每縣市一條線；單一縣市 → 一條線。"""
    key = "region" if level == "all" else "location_name"
    data = (fc.groupby([key, "forecast_time_start"], as_index=False)[column].mean()
              .rename(columns={key: "系列", column: "值"}))
    order = [n for n in (list(REGIONS) if level == "all" else CITY_ORDER) if n in set(data["系列"])]
    return data, order


def next_periods(n: int = 2) -> pd.DataFrame:
    """每個縣市「目前時段」之後的 n 個時段，依縣市（地區順序）→ 時間排序。"""
    later = (fc[fc["forecast_time_start"] > start]
             .sort_values(["order", "forecast_time_start"]).groupby("location_name", sort=False).head(n))
    return later


def make_table(src: pd.DataFrame, *, dated: bool) -> pd.DataFrame:
    """明細表格。天氣現象的圖示依每列自己的時段判斷日夜。"""
    period = [f"{s:%m/%d %H:%M}~{e:%H:%M}" if dated else f"{s:%H:%M}~{e:%H:%M}"
              for s, e in zip(src["forecast_time_start"], src["forecast_time_end"])]
    weather = [f"{weather_icon(w, is_night(s, e))} {w}".strip() if isinstance(w, str) else "—"
               for w, s, e in zip(src["weather_condition"], src["forecast_time_start"], src["forecast_time_end"])]
    columns = {"縣市": src["location_name"], "地區": src["region"]}
    columns.update({
        "時段": period, "天氣現象": weather,
        "最低 (°C)": src["min_temp"], "最高 (°C)": src["max_temp"], "平均 (°C)": src["avg"].round(1),
        "降雨機率": src["rain_probability"], "舒適度": src["comfort_index"].fillna("—"),
    })
    return pd.DataFrame(columns).reset_index(drop=True)


def show_table(table: pd.DataFrame, drop: list[str]) -> None:
    temp_columns = ["最低 (°C)", "最高 (°C)", "平均 (°C)"]
    styled = table.drop(columns=drop).style.map(
        lambda v: f"color:{text_color(v)};font-weight:700" if text_color(v) else "", subset=temp_columns)
    st.dataframe(
        styled, width="stretch", hide_index=True,
        column_config={
            "最低 (°C)": st.column_config.NumberColumn(format="%.0f"),
            "最高 (°C)": st.column_config.NumberColumn(format="%.0f"),
            "平均 (°C)": st.column_config.NumberColumn(format="%.1f"),
            "降雨機率": st.column_config.ProgressColumn(format="%d%%", min_value=0, max_value=100),
        })
    st.caption("點欄位標題可排序；降雨機率為空白表示氣象署該時段未提供；天氣圖示依時段區分日間（☀️）與夜間（🌙）。")


if city:
    tab_temp, tab_rain, tab_table, tab_date = st.tabs(
        ["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 一週預報", "📅 日期查詢"])
    tab_next = None
else:  # 全台／地區：明細右邊多一個「後續時段」分頁
    tab_temp, tab_rain, tab_table, tab_next, tab_date = st.tabs(
        ["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 目前時段明細", "🕒 後續時段", "📅 日期查詢"])

with tab_temp:
    if fc is None:
        st.info("沒有未來預報資料（資料可能已過期），請按「立即更新」。")
    else:  # 全台／地區／單一縣市都用同一種折線圖（單一縣市只有一條線）
        metric_label = st.radio("氣溫指標", list(METRICS), horizontal=True, key="metric")
        hint = "" if level == "city" else "每種顏色一條線，點圖例可強調單一系列，"
        st.caption(f"{scope_label}｜{metric_label}｜{hint}虛線為現在")
        data, order = series_data(METRICS[metric_label])
        if data["值"].dropna().empty:
            st.info("沒有可繪製的氣溫資料。")
        else:
            st.altair_chart(series_chart(data, now, f"{metric_label} (°C)", order, zero=True), width="stretch")

with tab_rain:  # 全台／地區／單一縣市都用同一種折線圖（單一縣市只有一條線）
    if fc is None or fc["rain_probability"].dropna().empty:
        st.info("沒有降雨機率資料（遠期時段氣象署未提供）。")
    else:
        st.caption(f"{scope_label}｜12 小時降雨機率（紅色虛線為 {RAIN_ALERT}% 告警門檻，超過者的點放大並加紅框）")
        data, order = series_data("rain_probability")
        st.altair_chart(series_chart(data, now, "降雨機率 (%)", order, zero=True, threshold=RAIN_ALERT,
                                     fill_zero=True), width="stretch")
    st.caption("空心點：氣象署未提供該時段的降雨機率（通常是遠期），圖上以 0 顯示，並非預報 0%；"
               "明細表格與摘要仍顯示為「—」。")

with tab_table:
    if city:  # 單一縣市：列出該縣市所有尚未結束的時段（一週預報），與趨勢圖對照
        st.caption(f"{city}｜未來一週的預報（每個時段約 12 小時）")
        if fc is None:
            st.info("沒有未來預報資料（資料可能已過期），請按「立即更新」。")
        else:
            show_table(make_table(fc.sort_values("forecast_time_start"), dated=True), ["縣市", "地區"])
    else:
        show_table(make_table(cur, dated=False), ["地區"] if region != ALL_REGIONS else [])

if tab_next is not None:
    with tab_next:
        st.caption("每個縣市「目前時段」之後的 2 個時段（依縣市、時間排序）")
        later = next_periods() if fc is not None else None
        if later is None or later.empty:
            st.info("沒有後續時段的預報資料（資料可能已過期），請按「立即更新」。")
        else:
            show_table(make_table(later, dated=True), ["地區"] if region != ALL_REGIONS else [])

with tab_date:  # 選一天，只列該天的表格（範圍跟著上方的地區／縣市）；沒有折線圖
    try:
        dates = db.fetch_available_dates(sb, now, CITY_ORDER[0])
    except Exception as exc:
        dates = []
        st.error(f"讀取可選日期失敗：{exc}")
    if not dates:
        st.info("資料庫沒有可查詢的日期。")
    else:
        weekday = "一二三四五六日"
        picked = st.selectbox(
            "日期（今天前 3 天到後 7 天內、資料庫有資料的日期）", dates, index=None, placeholder="請選擇日期",
            format_func=lambda d: f"{d:%Y-%m-%d}（週{weekday[d.weekday()]}）" + ("　今天" if d == now.date() else ""),
            key="query_date")
        if picked is not None:
            try:
                day = db.fetch_day(sb, picked, scope_cities)
            except Exception as exc:
                day = None
                st.error(f"讀取 {picked:%Y-%m-%d} 的資料失敗：{exc}")
            if day is not None and day.empty:
                st.info(f"{picked:%Y-%m-%d} 在此範圍沒有資料。")
            elif day is not None:
                st.caption(f"{scope_label}｜{picked:%Y-%m-%d} 的預報存檔（僅含完整 12 小時時段，不含被縮短的時段；預報值，非實測值；"
                           "夜間時段以起點日期歸屬）")
                day = add_region(day)
                day = day.assign(avg=display_temp(day)).sort_values(["order", "forecast_time_start"])
                drop = ["縣市", "地區"] if city else (["地區"] if region != ALL_REGIONS else [])
                show_table(make_table(day, dated=True), drop)

