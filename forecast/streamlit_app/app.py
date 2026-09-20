"""流程二：讀取 Supabase 預報資料並以 Streamlit + Folium 呈現（見 SPECIFICATION.md §8）。

執行：streamlit run streamlit_app/app.py
"""
import time

import pandas as pd
import requests
import streamlit as st
from streamlit.errors import StreamlitAPIException
from streamlit_folium import st_folium

from components import admin, db
from components.charts import RAIN_ALERT, series_chart, temp_trend_chart
from components.format import is_night, weather_icon
from components.map_view import build_map, display_temp
from components.region_data import ALL_REGIONS, CITY_ORDER, REGIONS, cities_in, region_of
from components.update_gate import MIN_INTERVAL_MINUTES, evaluate

ALL_CITIES = "全部縣市"
METRICS = {"最高溫": "max_temp", "最低溫": "min_temp", "平均溫": "avg"}

WORKFLOW_FILE = "weather_worker.yml"
REFRESH_AFTER_SECONDS = 60  # 觸發更新後，等這麼久自動重整頁面

st.set_page_config(page_title="台灣天氣預報", page_icon="🌤️", layout="wide")


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


# ---------- 標題與更新控制 ----------
head_left, head_right = st.columns([3, 2])
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

with head_right:
    btn_a, btn_b = st.columns(2)
    clicked = btn_a.button("⏳ 更新中…" if counting else "🔄 立即更新",
                           disabled=counting or not gate.allowed, width="stretch")
    if btn_b.button("♻️ 重新載入資料", width="stretch"):
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


k1, k2, k3, k4 = st.columns(4)
if city:  # 單一縣市：直接呈現該縣市自己的數值，天氣現象放在「平均氣溫」下方
    weather = crow["weather_condition"] if isinstance(crow["weather_condition"], str) else "—"
    icon = weather_icon(weather, is_night(crow["forecast_time_start"], crow["forecast_time_end"]))
    k1.metric(f"{city} 平均氣溫", show(crow["avg"], "°C", ".1f"), f"{icon} {weather}".strip(), delta_color="off")
    k2.metric("最高溫", show(crow["max_temp"], "°C"))
    k3.metric("最低溫", show(crow["min_temp"], "°C"))
    k4.metric("降雨機率", show(crow["rain_probability"], "%"))
else:
    hot, hot_city = extreme("max_temp", True)
    cold, cold_city = extreme("min_temp", False)
    wet, wet_city = extreme("rain_probability", True)
    k1.metric("平均氣溫", show(cur["avg"].mean(), "°C", ".1f"))
    k2.metric("最高溫", show(hot, "°C"), hot_city, delta_color="off")
    k3.metric("最低溫", show(cold, "°C"), cold_city, delta_color="off")
    k4.metric("最高降雨機率", show(wet, "%"), wet_city, delta_color="off")

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
    st.dataframe(
        table.drop(columns=drop), width="stretch", hide_index=True,
        column_config={
            "最低 (°C)": st.column_config.NumberColumn(format="%.0f"),
            "最高 (°C)": st.column_config.NumberColumn(format="%.0f"),
            "平均 (°C)": st.column_config.NumberColumn(format="%.1f"),
            "降雨機率": st.column_config.ProgressColumn(format="%d%%", min_value=0, max_value=100),
        })
    st.caption("點欄位標題可排序；降雨機率為空白表示氣象署該時段未提供；天氣圖示依時段區分日間（☀️）與夜間（🌙）。")


if city:
    tab_temp, tab_rain, tab_table = st.tabs(["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 一週預報"])
    tab_next = None
else:  # 全台／地區：明細右邊多一個「後續時段」分頁
    tab_temp, tab_rain, tab_table, tab_next = st.tabs(
        ["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 目前時段明細", "🕒 後續時段"])

with tab_temp:
    if fc is None:
        st.info("沒有未來預報資料（資料可能已過期），請按「立即更新」。")
    elif level == "city":
        st.caption(f"{scope_label}｜未來一週（灰色帶為最低～最高溫範圍，虛線為現在）")
        one = fc.dropna(subset=["min_temp", "max_temp"], how="all")
        if one.empty:
            st.info("沒有可繪製的氣溫資料。")
        else:
            st.altair_chart(temp_trend_chart(one, now), width="stretch")
    else:
        metric_label = st.radio("氣溫指標", list(METRICS), horizontal=True, key="metric")
        st.caption(f"{scope_label}｜{metric_label}｜每種顏色一條線，點圖例可強調單一系列，虛線為現在")
        data, order = series_data(METRICS[metric_label])
        if data["值"].dropna().empty:
            st.info("沒有可繪製的氣溫資料。")
        else:
            st.altair_chart(series_chart(data, now, f"{metric_label} (°C)", order), width="stretch")

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


# ---------- 告警設定（管理者；密碼在資料庫驗證，登入後才讀得到設定） ----------
ADMIN_STATE_KEYS = ("admin_pw", "admin_df", "admin_slots", "admin_seen", "admin_ver")


def rerun_panel() -> None:
    """只重跑設定面板；若目前是整頁重跑（fragment 範圍無效）就退回整頁重跑，不會當掉。"""
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def admin_logout(notice: str | None = None) -> None:
    for key in ADMIN_STATE_KEYS:
        st.session_state.pop(key, None)
    if notice:
        st.session_state["admin_notice"] = notice


def admin_reload(sb, password: str, notice: str | None = None) -> None:
    """重新從資料庫讀取設定並重設編輯表格（換一個版本號，讓元件回到資料庫的值）。"""
    ss = st.session_state
    ss["admin_df"], ss["admin_slots"] = admin.get_settings(sb, password)
    ss["admin_ver"] = ss.get("admin_ver", 0) + 1
    if notice:
        ss["admin_notice"] = notice


@st.fragment
def admin_panel(sb) -> None:
    """設定面板。用 fragment 隔離：編輯設定只重跑這一塊，不會重新載入整個儀表板。"""
    ss = st.session_state
    if notice := ss.pop("admin_notice", None):
        st.info(notice)

    # 閒置超過期限：下一次操作就要求重新登入（密碼只存在本次連線的伺服器記憶體，重新整理頁面即清除）
    if "admin_pw" in ss and time.time() - ss.get("admin_seen", 0) > admin.IDLE_TIMEOUT_SECONDS:
        admin_logout()
        st.info("已因閒置超過 15 分鐘登出，請重新登入")

    if "admin_pw" not in ss:  # ---- 未登入：只有密碼輸入框，看不到任何設定 ----
        with st.form("admin_login", clear_on_submit=True):
            password = st.text_input("管理者密碼", type="password")
            submitted = st.form_submit_button("登入")
        if submitted:
            if not password:
                st.warning("請輸入密碼")
            else:
                if fails := min(ss.get("admin_fails", 0), 5):
                    time.sleep(fails)  # 連續失敗越多次，等越久（資料庫端錯誤時另有 1 秒延遲）
                try:
                    admin_reload(sb, password)
                except admin.WrongPassword:
                    ss["admin_fails"] = ss.get("admin_fails", 0) + 1
                    st.error("密碼錯誤")
                except admin.AdminError as exc:
                    st.error(str(exc))
                else:
                    ss["admin_pw"], ss["admin_seen"], ss["admin_fails"] = password, time.time(), 0
                    rerun_panel()
        return

    # ---- 已登入 ----
    ss["admin_seen"] = time.time()
    df, slots, ver = ss["admin_df"], ss["admin_slots"], ss["admin_ver"]
    st.caption("已登入｜勾選「啟用」的縣市才會發送告警｜設定在下一個發送時段生效｜"
               "閒置超過 15 分鐘，下一次操作需重新登入")
    if not df["啟用"].any():
        st.info("尚未啟用任何縣市，不會發送告警")

    with st.form("admin_edit"):
        st.markdown("**發送時段**（勾選的時段才會發送；視窗為「該時段到下一個勾選時段之前」）")
        slot_cols = st.columns(len(admin.SLOTS))
        new_slots = {slot: col.checkbox(slot, value=slots[slot], key=f"admin_slot_{slot}_{ver}")
                     for slot, col in zip(admin.SLOTS, slot_cols)}
        st.markdown("**縣市設定**（每個縣市各自設定；降雨 ≥ 門檻、最低溫 ≤ 門檻、最高溫 ≥ 門檻，任一已勾選的條件符合就通知）")
        edited = st.data_editor(
            df, key=f"admin_editor_{ver}", hide_index=True, disabled=["縣市"], num_rows="fixed",
            width="stretch", height=600,
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
        save = col_save.form_submit_button("💾 儲存", type="primary")
        all_on = col_on.form_submit_button("全部啟用（尚未儲存）")
        all_off = col_off.form_submit_button("全部關閉（尚未儲存）")

    if all_on or all_off:  # 只改表格內容，仍需按「儲存」才會寫入
        ss["admin_df"], ss["admin_slots"] = admin.set_all_enabled(edited, all_on), new_slots
        ss["admin_ver"] = ver + 1
        rerun_panel()
    if save:
        try:
            admin.save_settings(sb, ss["admin_pw"], edited, new_slots)
            admin_reload(sb, ss["admin_pw"], "已儲存，設定會在下一個發送時段生效")
        except admin.WrongPassword:
            admin_logout("密碼已失效，請重新登入")
        except admin.AdminError as exc:
            st.error(f"儲存失敗：{exc}")
            return
        rerun_panel()

    col_reload, col_logout, _ = st.columns([1, 1, 3])
    if col_reload.button("重新載入（放棄未儲存的修改）"):
        try:
            admin_reload(sb, ss["admin_pw"], "已重新載入")
        except admin.AdminError as exc:
            admin_logout(str(exc))
        rerun_panel()
    if col_logout.button("登出"):
        admin_logout("已登出")
        rerun_panel()


st.divider()
with st.expander("⚙️ 告警設定（管理者）"):
    admin_panel(sb)
