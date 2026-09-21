"""玻璃擬態樣式（淺色／深色）：頁面開頭呼叫 inject() 一次，摘要卡片用 card() 產生 HTML。

淺色、深色的底色與文字色在 .streamlit/config.toml 的 [theme.light] / [theme.dark]；
這裡只放 config.toml 做不到的：漸層背景、半透明模糊的卡片、視窗外觀。

淺色／深色靠 CSS 的 light-dark(淺色值, 深色值)：Streamlit 會依目前主題在 .stApp 上設定 color-scheme，
所以使用者在右上角選單切換主題時立刻跟著換，不需要重跑頁面。要調整顏色或模糊程度，改下面 CSS 變數即可。
"""
import streamlit as st

CSS = """
<style>
.stApp {
  /* ---- 可調參數：light-dark(淺色, 深色) ---- */
  --glass-bg: light-dark(rgba(255,255,255,.55), rgba(255,255,255,.07));
  --glass-border: light-dark(rgba(255,255,255,.75), rgba(255,255,255,.16));
  --glass-shadow: light-dark(rgba(90,70,40,.14), rgba(0,0,0,.40));
  --glass-blur: 14px;
  /* 淺色：由左（淡米白）到右（淡天空藍）的線性漸層；深色：純色底加三個彩色光暈 */
  --bg-left: light-dark(#F7F5F0, #12141C);
  --bg-right: light-dark(#EAF3F8, #12141C);
  --glow-1: light-dark(transparent, rgba(120,90,255,.30));
  --glow-2: light-dark(transparent, rgba(0,170,200,.22));
  --glow-3: light-dark(transparent, rgba(255,110,90,.18));
  background-image:
    radial-gradient(circle at 10% 6%, var(--glow-1) 0, transparent 42%),
    radial-gradient(circle at 90% 10%, var(--glow-2) 0, transparent 40%),
    radial-gradient(circle at 72% 94%, var(--glow-3) 0, transparent 46%),
    linear-gradient(90deg, var(--bg-left), var(--bg-right)) !important;
  background-attachment: fixed !important;
}

/* 標題列按鈕：電腦版並排三顆；手機版（與 st.columns 自動堆疊的寬度相同）改顯示漢堡選單 */
.st-key-hdr_mobile { display: none; }
@media (max-width: 640px) {
  .st-key-hdr_desktop { display: none; }
  /* 只讓「☰ 選單」按鈕縮成約 1/3（col-4；想要 1/4 改成 25%）並靠右；外層容器維持整列寬度，
     因為展開的選項區寬度與定位都依外層容器（Streamlit 用 transform 定位，改 left/right 會跑出畫面） */
  .st-key-hdr_mobile { display: block; }
  .st-key-hdr_mobile [data-testid="stPopoverButton"] { display: flex !important; width: 33.333% !important; margin-left: auto; }
  .glass { margin-bottom: 12px; }  /* 摘要卡片在手機上上下堆疊，卡片之間要留間隔，否則會連在一起 */
}

/* 摘要卡片 */
.glass {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: 16px;
  padding: 14px 18px;
  min-height: 104px;
  box-shadow: 0 8px 32px var(--glass-shadow);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  backdrop-filter: blur(var(--glass-blur)) saturate(140%);
}
.glass .lbl { font-size: 14px; opacity: .7; }
.glass .val { font-size: 34px; font-weight: 600; line-height: 1.3; }
.glass .aside { font-size: 16px; font-weight: 400; opacity: .85; margin-left: 12px; line-height: 1.4; }

/* 告警設定視窗：背後的頁面模糊，視窗加圓角、細邊框與陰影（視窗底色沿用主題，避免表格難讀） */
.stDialog {
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
}
.stDialog [role="dialog"] {
  border-radius: 20px;
  border: 1px solid color-mix(in srgb, currentColor 16%, transparent);
  box-shadow: 0 16px 48px var(--glass-shadow, rgba(0,0,0,.3));
}
</style>
"""


def inject() -> None:
    """在頁面開頭呼叫一次。"""
    st.markdown(CSS, unsafe_allow_html=True)


def card(label: str, value_html: str, aside: str = "") -> str:
    """摘要卡片的 HTML。value_html 可含 colored() 產生的上色 span；aside 顯示在數值右側（如天氣圖示與文字）。"""
    aside_html = f'<span class="aside">{aside}</span>' if aside else ""
    return f'<div class="glass"><div class="lbl">{label}</div><div class="val">{value_html}{aside_html}</div></div>'
