"""告警推播（Telegram）。

輸入：符合條件的預報列、涵蓋範圍說明、bot token 與 chat id。輸出：一則 Telegram 訊息。

- 訊息：標題 + 每筆一行；超過上限時最後顯示「另有 N 筆未列出」。
- 以 HTML 模式送出（標題粗體），所有動態內容都經過跳脫；若 Telegram 仍回 400（格式問題）
  會自動改用純文字重送一次。
- ⚠️ 錯誤訊息絕不可含 token：requests 的例外訊息會帶完整網址（網址裡就有 token），
  而失敗訊息會寫進 pipeline_status.last_error（前端可讀）。因此一律改寫成不含網址的訊息。
"""
import html
from datetime import datetime

import requests

from tw_forecast.backend.errors import NotifyError
from tw_forecast.config import TZ

__all__ = ["NotifyError", "TelegramNotifier", "build_alert_text"]

MAX_LINES = 30
MAX_CHARS = 4000  # Telegram 單則訊息上限 4096 字，保留餘裕
API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _num(value, unit: str = "") -> str:
    return "—" if value is None else f"{value:g}{unit}"


def _line(row: dict) -> str:
    """縣市 起~迄 進行中/即將開始｜降雨｜氣溫。沒有 forecast_time_end / label 的列（如舊資料）只顯示起點。"""
    start = datetime.fromisoformat(row["forecast_time_start"]).astimezone(TZ)
    period = f"{start:%m/%d %H:%M}"
    if row.get("forecast_time_end"):
        period += f"~{datetime.fromisoformat(row['forecast_time_end']).astimezone(TZ):%H:%M}"
    label = f" {row['label']}" if row.get("label") else ""
    return (f"{row['location_name']} {period}{label}｜降雨 {_num(row.get('rain_probability'), '%')}｜"
            f"{_num(row.get('min_temp'))}~{_num(row.get('max_temp'), '°C')}")


def build_alert_text(rows: list[dict], scope: str, title: str = "🔔 天氣告警",
                     max_lines: int = MAX_LINES) -> tuple[str, str]:
    """回傳 (HTML 版, 純文字版)。scope 說明涵蓋範圍（如「涵蓋 09/21 08:45～14:45」）。

    超過筆數或字數上限的部分以「另有 N 筆未列出」取代。
    """
    subtitle = f"{scope}，共 {len(rows)} 筆符合條件"
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


class TelegramNotifier:
    """把告警送到指定的 Telegram 聊天室。"""

    def __init__(self, token: str, chat_id: str, post=requests.post):
        """post 可注入，測試時不連網。"""
        self._token = token
        self._chat_id = chat_id
        self._post = post

    def notify_alerts(self, rows: list[dict], scope: str, title: str = "🔔 天氣告警") -> None:
        """組訊息並送出；失敗拋 NotifyError（訊息不含 token）。"""
        rich, plain = build_alert_text(rows, scope, title=title)
        self.send(rich, plain)

    def send(self, rich: str, plain: str) -> None:
        """送出訊息；HTML 格式被拒絕（HTTP 400）時自動改用純文字重送一次。"""
        resp = self._request({"chat_id": self._chat_id, "text": rich, "parse_mode": "HTML",
                              "disable_web_page_preview": True})
        if resp.status_code == 400:
            resp = self._request({"chat_id": self._chat_id, "text": plain, "disable_web_page_preview": True})
        if resp.status_code != 200:
            raise NotifyError(f"Telegram 回應 {resp.status_code}：{self._describe(resp)}")

    def _request(self, payload: dict) -> requests.Response:
        try:
            return self._post(API_URL.format(token=self._token), json=payload, timeout=15)
        except requests.RequestException as exc:
            # from None：不串接原例外，避免其訊息（含網址與 token）出現在 traceback
            raise NotifyError(f"無法連線至 Telegram（{type(exc).__name__}）") from None

    def _describe(self, resp: requests.Response) -> str:
        """取出 Telegram 回應的錯誤描述，並遮蔽 token、限制長度。"""
        try:
            text = str(resp.json().get("description", ""))
        except ValueError:
            text = ""
        return text.replace(self._token, "***")[:200]
