"""流程二：讀取 Supabase 預報資料並以 Streamlit + Folium 呈現（見 SPECIFICATION.md §8）。

執行：streamlit run streamlit_app/app.py
"""
import time

import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

from components import db
from components.charts import temp_trend_chart
from components.map_view import build_map, display_temp
from components.region_data import ALL_REGIONS, CITY_ORDER, REGIONS, cities_in, region_of

WORKFLOW_FILE = "weather_worker.yml"
COOLDOWN_SECONDS = 60

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
        return True, "已觸發更新，約 1~2 分鐘後按「重新載入資料」（更新完成前仍顯示舊資料）"
    return False, f"觸發失敗（HTTP {resp.status_code}）：{resp.text[:200]}"


def fmt_range(start: pd.Timestamp, end: pd.Timestamp) -> str:
    return f"{start:%m/%d %H:%M} ~ {end:%m/%d %H:%M}"


def add_region(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["region"] = df["location_name"].map(region_of)
    df["order"] = df["location_name"].map(lambda c: CITY_ORDER.index(c) if c in CITY_ORDER else 99)
    return df


# ---------- 標題與更新控制 ----------
head_left, head_right = st.columns([3, 2])
head_left.title("🌤️ 台灣天氣預報")
with head_right:
    btn_a, btn_b = st.columns(2)
    remaining = COOLDOWN_SECONDS - (time.monotonic() - st.session_state.get("last_dispatch", -1e9))
    if btn_a.button(f"🔄 立即更新{f'（{int(remaining)} 秒後可再按）' if remaining > 0 else ''}",
                    disabled=remaining > 0, width="stretch"):
        ok, msg = trigger_update()
        if ok:
            st.session_state["last_dispatch"] = time.monotonic()
        (st.success if ok else st.error)(msg)
    if btn_b.button("♻️ 重新載入資料", width="stretch"):
        st.rerun()

# ---------- 讀取資料庫（不快取，每次載入都重新查詢） ----------
if not secret("SUPABASE_URL") or not secret("SUPABASE_ANON_KEY"):
    st.error("尚未設定 SUPABASE_URL / SUPABASE_ANON_KEY（見 .streamlit/secrets.toml.example）")
    st.stop()
try:
    sb = db.get_client()
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

# ---------- 篩選 ----------
sel_left, sel_right = st.columns(2)
region = sel_left.selectbox("地區", [ALL_REGIONS, *REGIONS])
region_cities = cities_in(region)
city_choice = sel_right.selectbox("折線圖範圍", ["地區平均", *region_cities])

cur = current[current["location_name"].isin(region_cities)].sort_values("order")
start, end = cur["forecast_time_start"].iloc[0], cur["forecast_time_end"].iloc[0]
in_period = start <= now < end
info = st.columns(3)
info[0].metric("預報時段" if in_period else "預報時段（目前無資料，顯示最接近時段）", fmt_range(start, end))
info[1].metric("縣市數", len(cur))
info[2].metric("資料更新時間", f"{cur['updated_at'].max():%m/%d %H:%M}")
st.caption("時間皆為台灣時間 (Asia/Taipei)")

# ---------- 地圖 ----------
st.subheader("🗺️ 平均氣溫地圖")
st_folium(build_map(cur), height=520, use_container_width=True, returned_objects=[])

# ---------- 一週趨勢折線圖 ----------
st.subheader("📈 最高與最低氣溫（未來一週）")
if forecast.empty:
    st.info("沒有未來預報資料（資料可能已過期），請按「立即更新」。")
else:
    trend = forecast[forecast["location_name"].isin(region_cities)]
    if city_choice == "地區平均":
        trend = trend.groupby("forecast_time_start", as_index=False)[["min_temp", "max_temp"]].mean()
    else:
        trend = trend[trend["location_name"] == city_choice]
    trend = trend.dropna(subset=["min_temp", "max_temp"], how="all")
    if trend.empty:
        st.info("沒有可繪製的氣溫資料。")
    else:
        st.altair_chart(temp_trend_chart(trend), width="stretch")

# ---------- 明細表格 ----------
st.subheader("📋 目前時段明細")
table = pd.DataFrame({
    "縣市": cur["location_name"],
    "地區": cur["region"],
    "時段": [fmt_range(s, e) for s, e in zip(cur["forecast_time_start"], cur["forecast_time_end"])],
    "天氣現象": cur["weather_condition"],
    "最低 (°C)": cur["min_temp"],
    "最高 (°C)": cur["max_temp"],
    "平均 (°C)": display_temp(cur).round(1),
    "降雨機率 (%)": cur["rain_probability"],
    "舒適度": cur["comfort_index"],
}).reset_index(drop=True)
st.dataframe(table.fillna("—").astype(str), width="stretch", hide_index=True)
