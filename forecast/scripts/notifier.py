"""告警推播（Telegram）。

- 訊息：標題 + 每筆一行；超過上限時最後顯示「另有 N 筆未列出」。
- 以 HTML 模式送出（標題粗體），所有動態內容都經過跳脫；若 Telegram 仍回 400（格式問題）
  會自動改用純文字重送一次。
- ⚠️ 錯誤訊息絕不可含 token：requests 的例外訊息會帶完整網址（網址裡就有 token），
  而失敗訊息會寫進 pipeline_status.last_error（前端可讀）。因此一律改寫成不含網址的訊息。
"""
import html
from datetime import datetime, timedelta, timezone

import requests

TZ = timezone(timedelta(hours=8))  # 台灣時間 (UTC+8)
MAX_LINES = 30
MAX_CHARS = 4000  # Telegram 單則訊息上限 4096 字，保留餘裕
API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class NotifyError(RuntimeError):
    """推播失敗；訊息保證不含 token 或網址。"""


def _num(value, unit: str = "") -> str:
    return "—" if value is None else f"{value:g}{unit}"


def _line(row: dict) -> str:
    start = datetime.fromisoformat(row["forecast_time_start"]).astimezone(TZ)
    return (f"{row['location_name']} {start:%m/%d %H:%M} 起｜降雨 {_num(row.get('rain_probability'), '%')}｜"
            f"{_num(row.get('min_temp'))}~{_num(row.get('max_temp'), '°C')}")


def build_alert_text(rows: list[dict], window_hours: int, title: str = "🔔 天氣告警",
                     max_lines: int = MAX_LINES) -> tuple[str, str]:
    """回傳 (HTML 版, 純文字版)。超過筆數或字數上限的部分以「另有 N 筆未列出」取代。"""
    subtitle = f"未來 {window_hours} 小時內開始的時段，共 {len(rows)} 筆符合條件"
    lines, used = [], len(title) + len(subtitle) + 40  # 40 = 「另有 N 筆」與換行的預留
    for row in rows[:max_lines]:
        line = _line(row)
        if used + len(line) + 1 > MAX_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    if len(lines) < len(rows):
        lines.append(f"另有 {len(rows) - len(lines)} 筆未列出")
    body = "\n".join(lines)
    plain = f"{title}\n{subtitle}\n\n{body}"
    rich = f"<b>{html.escape(title, quote=False)}</b>\n{html.escape(subtitle, quote=False)}\n\n" \
           f"{html.escape(body, quote=False)}"
    return rich, plain


def _post(token: str, payload: dict) -> requests.Response:
    try:
        return requests.post(API_URL.format(token=token), json=payload, timeout=15)
    except requests.RequestException as exc:
        # from None：不串接原例外，避免其訊息（含網址與 token）出現在 traceback
        raise NotifyError(f"無法連線至 Telegram（{type(exc).__name__}）") from None


def _describe(resp: requests.Response, token: str) -> str:
    try:
        text = str(resp.json().get("description", ""))
    except ValueError:
        text = ""
    return text.replace(token, "***")[:200]


def send_telegram(rich: str, plain: str, token: str, chat_id: str) -> None:
    """送出訊息；失敗拋 NotifyError（訊息不含 token）。HTML 格式被拒絕時自動改用純文字重送。"""
    resp = _post(token, {"chat_id": chat_id, "text": rich, "parse_mode": "HTML",
                         "disable_web_page_preview": True})
    if resp.status_code == 400:
        resp = _post(token, {"chat_id": chat_id, "text": plain, "disable_web_page_preview": True})
    if resp.status_code != 200:
        raise NotifyError(f"Telegram 回應 {resp.status_code}：{_describe(resp, token)}")


def notify_alerts(rows: list[dict], window_hours: int, token: str, chat_id: str, title: str = "🔔 天氣告警") -> None:
    rich, plain = build_alert_text(rows, window_hours, title=title)
    send_telegram(rich, plain, token, chat_id)
