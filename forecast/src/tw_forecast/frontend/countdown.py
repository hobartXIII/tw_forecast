"""瀏覽器端倒數的 HTML（純函式，不依賴 Streamlit）。

輸入：說明文字與剩餘秒數。輸出：一段可嵌入 iframe 的 HTML，由瀏覽器的 JavaScript 每秒更新 mm:ss，
伺服器不需要每秒重跑。時間到只會把文字換成「重新整理中…」，實際的整頁重整由伺服器端的
單次計時（views/header.py）觸發。
"""
from html import escape

# 外觀仿 st.info（淺藍底）。iframe 讀不到 Streamlit 的主題，所以用瀏覽器的 prefers-color-scheme 近似淺色／深色。
_TEMPLATE = """<!doctype html>
<html lang="zh-TW"><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; background: transparent; }}
  .box {{
    box-sizing: border-box; padding: 12px 16px; border-radius: 8px;
    background: rgba(28, 131, 225, 0.10); color: #004280;
    font: 16px/1.5 "Source Sans Pro", "Source Sans", "Microsoft JhengHei", "PingFang TC", sans-serif;
  }}
  @media (prefers-color-scheme: dark) {{
    .box {{ background: rgba(61, 157, 243, 0.20); color: #c7ebff; }}
  }}
  b {{ font-variant-numeric: tabular-nums; }}
</style></head><body>
<div class="box">{prefix}<b id="t">{initial}</b>{suffix}</div>
<script>
  const end = Date.now() + {millis};
  const el = document.getElementById("t");
  function tick() {{
    const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
    const m = String(Math.floor(left / 60)).padStart(2, "0");
    const s = String(left % 60).padStart(2, "0");
    el.textContent = left > 0 ? m + ":" + s : "重新整理中…";
    if (left > 0) setTimeout(tick, 250);
  }}
  tick();
</script></body></html>"""


def format_mmss(seconds: float) -> str:
    """剩餘秒數轉 mm:ss（無條件進位到整秒；小於等於 0 顯示 00:00）。"""
    total = max(0, int(-(-seconds // 1)))
    return f"{total // 60:02d}:{total % 60:02d}"


def countdown_html(prefix: str, seconds: float, suffix: str = "") -> str:
    """prefix、suffix 是倒數數字前後的文字（會跳脫）；seconds 為剩餘秒數，於瀏覽器載入這段 HTML 時開始倒數。"""
    return _TEMPLATE.format(prefix=escape(prefix), suffix=escape(suffix), initial=format_mmss(seconds),
                            millis=int(max(0, seconds) * 1000))
