"""玻璃擬態樣式（淺色／深色）：頁面開頭呼叫 inject() 一次，摘要卡片用 card() 產生 HTML。

淺色、深色的底色與文字色在 .streamlit/config.toml 的 [theme.light] / [theme.dark]；
這裡只放 config.toml 做不到的：漸層背景、半透明模糊的卡片（依級距色發光的邊框、進度條、進場與浮起動畫）、
地圖區與分頁區的玻璃容器、藥丸狀頁籤、視窗外觀；另有一小段 JS 在捲動時收起圖表提示框（手機用）。

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
  --accent-primary: light-dark(#d9480f, #ff8a5c);  /* 與 config.toml 的 primaryColor 相同，頁籤用 */
  /* 淺色：由左（淡米白）到右（淡天空藍）的線性漸層加三個淡光暈（暖橘、天藍、淡紫）；
     深色：純色底加三個較濃的彩色光暈。玻璃卡片要背後有色彩變化才看得出模糊 */
  --bg-left: light-dark(#F7F5F0, #12141C);
  --bg-right: light-dark(#EAF3F8, #12141C);
  --glow-1: light-dark(rgba(255,160,90,.22), rgba(120,90,255,.30));
  --glow-2: light-dark(rgba(80,170,235,.20), rgba(0,170,200,.22));
  --glow-3: light-dark(rgba(160,130,255,.14), rgba(255,110,90,.18));
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

/* 地圖區與分頁區的玻璃容器（views/map_section.py、views/tabs.py 的 st.container(key=...)），與摘要卡片同一組變數 */
.st-key-glass_map, .st-key-glass_tabs {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: 20px;
  padding: 18px 22px;
  box-shadow: 0 8px 32px var(--glass-shadow);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  backdrop-filter: blur(var(--glass-blur)) saturate(140%);
}
.st-key-glass_map { margin-top: 12px; }  /* 摘要卡片的 markdown 底部是負邊距，不加會與卡片貼在一起 */
@media (max-width: 640px) {  /* 手機上內距縮小，留寬度給地圖與圖表（須寫在上面那條規則之後才蓋得過） */
  .st-key-glass_map, .st-key-glass_tabs { padding: 12px 14px; border-radius: 16px; }
  .st-key-glass_map { margin-top: 0; }  /* 手機上摘要卡片已有 12px 下邊距 */
}

/* 分頁頁籤改成藥丸狀。Streamlit 1.64 的頁籤是 React Aria 元件：頁籤有 role="tab"／aria-selected，
   原本的橘色底線是 .react-aria-SelectionIndicator、灰色基準線是 tablist 的 ::after，兩者都藏起來 */
.stTabs [role="tablist"] { gap: 6px; align-items: center; }
.stTabs [role="tablist"]::after, .stTabs .react-aria-SelectionIndicator { display: none; }
.stTabs [role="tab"] {
  height: 34px; padding: 0 14px; border-radius: 999px;
  border: 1px solid transparent;
  transition: background-color .2s ease, border-color .2s ease;
}
.stTabs [role="tab"]:hover { background: color-mix(in srgb, currentColor 7%, transparent); }
.stTabs [role="tab"][aria-selected="true"] {
  background: color-mix(in srgb, var(--accent-primary) 14%, transparent);
  border-color: color-mix(in srgb, var(--accent-primary) 40%, transparent);
}

/* 摘要卡片：發光邊框的顏色（--accent）與進場延遲（--delay）由 card() 以 inline style 帶入。
   邊框混入淡淡的級距色（溫度卡片依氣溫級距、降雨卡片依降雨色階），外圍再加一圈同色柔光；沒有 --accent 時就是一般玻璃邊框 */
.glass {
  --glow: light-dark(color-mix(in srgb, var(--accent, transparent) 40%, transparent),
                     color-mix(in srgb, var(--accent, transparent) 60%, transparent));  /* 深色底上光暈要濃一點才看得出來 */
  background: var(--glass-bg);
  border: 1px solid color-mix(in srgb, var(--accent, transparent) 45%, var(--glass-border));
  border-radius: 16px;
  padding: 14px 18px;
  min-height: 112px;
  box-shadow: 0 8px 32px var(--glass-shadow), 0 0 20px -2px var(--glow),
              inset 0 0 16px color-mix(in srgb, var(--accent, transparent) 10%, transparent);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  backdrop-filter: blur(var(--glass-blur)) saturate(140%);
}
.glass .lbl { font-size: 14px; opacity: .7; }
.glass .val { font-size: 34px; font-weight: 600; line-height: 1.3; }
.glass .aside { font-size: 16px; font-weight: 400; opacity: .85; margin-left: 12px; line-height: 1.4; }
.glass .meter {  /* 降雨機率進度條 */
  height: 6px; margin-top: 6px; border-radius: 3px; overflow: hidden;
  background: color-mix(in srgb, currentColor 12%, transparent);
}
.glass .meter > span { display: block; height: 100%; border-radius: 3px; background: var(--accent); transform-origin: left; }

/* 動態效果：卡片由下往上依序淡入、進度條由左長出、滑鼠移上去微微浮起。
   系統設定「減少動態效果」的使用者不套用。
   進場動畫只用 backwards（不用 both），動畫結束後才不會蓋掉 :hover 的 transform */
@keyframes glass-in { from { opacity: 0; transform: translateY(14px); } }
@keyframes meter-grow { from { transform: scaleX(0); } }
@media (prefers-reduced-motion: no-preference) {
  .glass {
    animation: glass-in .55s cubic-bezier(.2,.7,.2,1) backwards;
    animation-delay: var(--delay, 0ms);
    transition: transform .2s ease, box-shadow .2s ease;
  }
  .glass:hover {  /* 浮起並讓光暈更亮 */
    transform: translateY(-3px);
    box-shadow: 0 14px 40px var(--glass-shadow), 0 0 28px 2px var(--glow),
                inset 0 0 16px color-mix(in srgb, var(--accent, transparent) 14%, transparent);
  }
  .glass .meter > span { animation: meter-grow .9s cubic-bezier(.2,.7,.2,1) backwards; animation-delay: calc(var(--delay, 0ms) + .25s); }
}

/* 只放 TOOLTIP_JS 腳本的 st.html 元素高度為 0，但外層容器仍會多佔一個元素間距，整個藏起來（腳本已執行，不受影響） */
.stElementContainer:has(> [data-testid="stHtml"] > script:only-child) { display: none; }

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


# 手機上點折線圖的資料點會跳出 Vega 提示框（#vg-tooltip-element，出現時帶 visible class），
# 但手機沒有「滑鼠移開」，提示框會一直掛著。這裡在任何捲動或手指滑動時把它收起來，再點資料點仍會照常出現。
# Streamlit 捲動的是內部容器而非 window，scroll 事件不冒泡，所以用 capture 監聽；
# 每次重跑都會再執行一次，用全域旗標避免重複綁定。
TOOLTIP_JS = """
<script>
if (!window.__twHideTooltipOnScroll) {
  window.__twHideTooltipOnScroll = true;
  const hide = () => document.getElementById("vg-tooltip-element")?.classList.remove("visible");
  document.addEventListener("scroll", hide, {capture: true, passive: true});
  document.addEventListener("touchmove", hide, {capture: true, passive: true});
}
</script>
"""


def inject() -> None:
    """在頁面開頭呼叫一次：注入 CSS，以及「捲動時收起圖表提示框」的腳本。"""
    st.markdown(CSS, unsafe_allow_html=True)
    st.html(TOOLTIP_JS, unsafe_allow_javascript=True)


CARD_STAGGER_MS = 80  # 四張卡片依序淡入的間隔


def card(label: str, value_html: str, aside: str = "", *, accent: str = "", index: int = 0,
         meter: float | None = None) -> str:
    """摘要卡片的 HTML。value_html 可含 colored() 產生的上色 span；aside 顯示在數值右側（如天氣圖示與文字）。

    accent 為發光邊框與進度條的顏色（空字串為一般玻璃邊框、不發光）；index 為卡片的位置（0 起算），決定進場動畫的延遲；
    meter 為 0～100 的數值時，在數值下方畫一條進度條（降雨機率用），None 或 NaN 不畫。
    """
    aside_html = f'<span class="aside">{aside}</span>' if aside else ""
    meter_html = ""
    if meter is not None and meter == meter:  # meter == meter 排除 NaN
        width = min(max(float(meter), 0.0), 100.0)
        meter_html = f'<div class="meter"><span style="width:{width:g}%"></span></div>'
    style = f"--delay:{index * CARD_STAGGER_MS}ms" + (f";--accent:{accent}" if accent else "")
    return (f'<div class="glass" style="{style}"><div class="lbl">{label}</div>'
            f'<div class="val">{value_html}{aside_html}</div>{meter_html}</div>')
