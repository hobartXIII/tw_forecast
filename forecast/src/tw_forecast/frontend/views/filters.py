"""地區與縣市篩選（互斥：選其一會把另一個清回「全部」）。整頁內容跟著選擇更新。

選了縣市時，地區選單改顯示空白提示（值為 None）而不是「全部地區」：下拉選單只有在值改變時才會觸發切換，
若這時仍顯示「全部地區」，使用者再點「全部地區」就不會有任何反應、縣市也清不掉。

縣市選單設 filter_mode=None（不能打字搜尋）：Streamlit 在手機上只有選項 ≤ 10 個時才把輸入框設成唯讀，
縣市有 23 個選項，點下去會跳出鍵盤遮住半個畫面；關掉打字後輸入框不再叫出鍵盤，只能捲動清單點選。
地區只有 6 個選項，手機上本來就不會跳鍵盤，維持預設。

因為地區選單支援上述的空白提示，Streamlit 會順便讓它多一個可清空的 × 圖示；若使用者在沒選縣市時點了這個 ×，
會跳回「全部地區」而不是留在空白提示（沒有「兩者都不選」這個狀態）。
"""
import streamlit as st

from tw_forecast.frontend.regions import ALL_CITIES, ALL_REGIONS, CITY_ORDER, REGIONS
from tw_forecast.frontend.scope import Scope


def _on_region_change() -> None:
    if st.session_state["region"] is None:  # 使用者點掉「地區」可清空的 ×：沒有「兩者都不選」這個狀態，跳回全部地區
        st.session_state["region"] = ALL_REGIONS
    st.session_state["city"] = ALL_CITIES  # 選地區 → 縣市回到「全部縣市」


def _on_city_change() -> None:
    # 選了縣市 → 地區清成空白提示；選回「全部縣市」→ 地區回到「全部地區」
    st.session_state["region"] = ALL_REGIONS if st.session_state["city"] == ALL_CITIES else None


def render_filters() -> Scope:
    """畫兩個下拉選單，回傳目前的篩選範圍。"""
    st.session_state.setdefault("region", ALL_REGIONS)  # 第一次載入預設「全部地區」
    left, right = st.columns(2)
    region = left.selectbox("地區", [ALL_REGIONS, *REGIONS], index=None, placeholder="— 已選縣市 —",
                            key="region", on_change=_on_region_change)
    city_choice = right.selectbox("縣市", [ALL_CITIES, *CITY_ORDER], key="city", on_change=_on_city_change,
                                  filter_mode=None)  # 手機上點選時不跳鍵盤（見模組說明）
    return Scope(region=region or ALL_REGIONS, city=None if city_choice == ALL_CITIES else city_choice)
