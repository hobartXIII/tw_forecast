"""瀏覽器端倒數的 HTML（純函式，不依賴 Streamlit）。

輸入：需間隔的分鐘數與還要等待的秒數。輸出：一段可嵌入 iframe 的 HTML；「距上次更新僅 X 分鐘」與
「還需 mm:ss」兩個數字都由瀏覽器的 JavaScript 從同一個剩餘秒數推導、每 250ms 一起更新，兩者保證同步，
伺服器不需要每秒重跑。時間到只會把倒數文字換成「重新整理中…」，實際的整頁重整由伺服器端的單次計時
（views/header.py）觸發。
"""

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
<div class="box">距上次更新僅 <b id="e">{initial_elapsed}</b> 分鐘，需間隔 {min_interval} 分鐘，還需 <b id="t">{initial_left}</b> 才可更新</div>
<script>
  const total = {total};
  const end = Date.now() + {millis};
  const e = document.getElementById("e");
  const t = document.getElementById("t");
  function tick() {{
    const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
    e.textContent = Math.max(0, Math.floor((total - left) / 60));
    const m = String(Math.floor(left / 60)).padStart(2, "0");
    const s = String(left % 60).padStart(2, "0");
    t.textContent = left > 0 ? m + ":" + s : "重新整理中…";
    if (left > 0) setTimeout(tick, 250);
  }}
  tick();
</script></body></html>"""


def format_mmss(seconds: float) -> str:
    """剩餘秒數轉 mm:ss（無條件進位到整秒；小於等於 0 顯示 00:00）。"""
    total = max(0, int(-(-seconds // 1)))
    return f"{total // 60:02d}:{total % 60:02d}"


def interval_countdown_html(min_interval_minutes: int, wait_seconds: float) -> str:
    """手動更新的間隔倒數：min_interval_minutes 為需間隔的分鐘數，wait_seconds 為目前還要等的秒數
    （於瀏覽器載入這段 HTML 時開始倒數）。兩個數字都由同一個剩餘秒數推導，內容只有數字與寫死的文字
    （不含使用者輸入），可安全嵌入 iframe。"""
    total = min_interval_minutes * 60
    clamped_wait = max(0.0, wait_seconds)
    initial_elapsed = max(0, int((total - clamped_wait) // 60))
    return _TEMPLATE.format(min_interval=min_interval_minutes, initial_elapsed=initial_elapsed,
                            initial_left=format_mmss(wait_seconds), total=int(total),
                            millis=int(clamped_wait * 1000))
