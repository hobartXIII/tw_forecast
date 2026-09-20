"""流程二：讀取 Supabase 預報資料並以 Streamlit + Folium 呈現（見 SPECIFICATION.md §8）。

執行：streamlit run streamlit_app/app.py
"""
import time

import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

from components import db
from components.charts import RAIN_ALERT, rain_chart, series_chart, temp_trend_chart
from components.format import weather_icon
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

# ---------- 篩選（地區 → 縣市連動；整頁內容跟著選擇更新） ----------
sel_left, sel_right = st.columns(2)
region = sel_left.selectbox("地區", [ALL_REGIONS, *REGIONS], key="region")
region_cities = cities_in(region)
# 換地區後，原本選的縣市若不在新地區，Streamlit 會自動回到「全部縣市」
city_choice = sel_right.selectbox("縣市", [ALL_CITIES, *region_cities], key="city")
city = None if city_choice == ALL_CITIES else city_choice
# 顯示層級：全台（依地區平均）→ 地區（依縣市）→ 單一縣市（依時段）
level = "city" if city else ("all" if region == ALL_REGIONS else "region")

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
    k1.metric(f"{city} 平均氣溫", show(crow["avg"], "°C", ".1f"), f"{weather_icon(weather)} {weather}".strip(),
              delta_color="off")
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
           + ("被選的縣市已放大並加外框，其餘縣市淡化作為對照。" if city else ""))
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
    """多系列長表與圖例順序：全台 → 每地區平均一條線；單一地區 → 每縣市一條線。"""
    key = "region" if level == "all" else "location_name"
    data = (fc.groupby([key, "forecast_time_start"], as_index=False)[column].mean()
              .rename(columns={key: "系列", column: "值"}))
    order = [n for n in (list(REGIONS) if level == "all" else CITY_ORDER) if n in set(data["系列"])]
    return data, order


tab_labels = ["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 各時段預報" if city else "📋 目前時段明細"]
tab_temp, tab_rain, tab_table = st.tabs(tab_labels)

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

with tab_rain:
    if fc is None or fc["rain_probability"].dropna().empty:
        st.info("沒有降雨機率資料（遠期時段氣象署未提供）。")
    elif level == "city":
        st.caption(f"{scope_label}｜12 小時降雨機率（紅色為 ≥ {RAIN_ALERT}%，即告警門檻）")
        st.altair_chart(rain_chart(fc, now), width="stretch")
    else:
        st.caption(f"{scope_label}｜12 小時降雨機率（紅色虛線為 {RAIN_ALERT}% 告警門檻，超過者的點放大並加紅框）")
        data, order = series_data("rain_probability")
        st.altair_chart(series_chart(data, now, "降雨機率 (%)", order, zero=True, threshold=RAIN_ALERT),
                        width="stretch")
    st.caption("氣象署僅提供近期時段的降雨機率，遠期時段無資料時不會出現在圖上。")

with tab_table:
    if city:  # 單一縣市：列出該縣市所有尚未結束的時段，與趨勢圖對照
        if fc is None:
            st.info("沒有未來預報資料（資料可能已過期），請按「立即更新」。")
            src = None
        else:
            src = fc.sort_values("forecast_time_start")
    else:
        src = cur
    if src is not None:
        table = pd.DataFrame({
            "縣市": src["location_name"],
            "地區": src["region"],
            "時段": [f"{s:%m/%d %H:%M}~{e:%H:%M}" if city else f"{s:%H:%M}~{e:%H:%M}"
                     for s, e in zip(src["forecast_time_start"], src["forecast_time_end"])],
            "天氣現象": [f"{weather_icon(w)} {w}".strip() if isinstance(w, str) else "—"
                         for w in src["weather_condition"]],
            "最低 (°C)": src["min_temp"],
            "最高 (°C)": src["max_temp"],
            "平均 (°C)": src["avg"].round(1),
            "降雨機率": src["rain_probability"],
            "舒適度": src["comfort_index"].fillna("—"),
        }).reset_index(drop=True)
        drop = ["縣市", "地區"] if city else (["地區"] if region != ALL_REGIONS else [])
        st.dataframe(
            table.drop(columns=drop), width="stretch", hide_index=True,
            column_config={
                "最低 (°C)": st.column_config.NumberColumn(format="%.0f"),
                "最高 (°C)": st.column_config.NumberColumn(format="%.0f"),
                "平均 (°C)": st.column_config.NumberColumn(format="%.1f"),
                "降雨機率": st.column_config.ProgressColumn(format="%d%%", min_value=0, max_value=100),
            })
        st.caption("點欄位標題可排序；降雨機率為空白表示氣象署該時段未提供。")
