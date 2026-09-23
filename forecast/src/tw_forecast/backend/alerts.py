"""告警規則：依資料庫的設定，決定「這個排程時槽要不要發、發哪些縣市的哪些時段」。

見 SPECIFICATION.md §5.1（設定表）與 §6.1（判斷邏輯）。本模組不連網路，方便單元測試。

輸入：資料庫的設定列（parse_settings）與解析後的預報列（evaluate_alerts）。
輸出：AlertSettings 與「符合條件的預報列」（每列多 label 與 reasons 欄位）。

- 設定在資料庫（alert_city_settings / alert_slot_settings）；預設所有縣市關閉 = 不發送。
- 讀不到設定或內容不合法時一律「不發送」（fail closed），不會誤發。
- 判斷視窗（W1）：從這次發送時槽到「下一個啟用的發送時槽」之前，與視窗有交集的預報時段
  （含進行中的），符合該縣市已啟用的條件才列入。
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tw_forecast.config import SEND_SLOTS


@dataclass(frozen=True)
class CityRule:
    """單一縣市的告警規則；預設值 = 資料庫預設（縣市關閉，條件全開，門檻 60 / 12 / 35）。"""
    enabled: bool = False
    rain_on: bool = True
    rain: int = 60          # 降雨機率 >= 此值
    min_on: bool = True
    min_temp: float = 12    # 最低溫 <= 此值
    max_on: bool = True
    max_temp: float = 35    # 最高溫 >= 此值


@dataclass(frozen=True)
class AlertSettings:
    """告警設定的完整快照：各縣市規則與啟用的發送時段。"""
    cities: dict = field(default_factory=dict)   # 縣市名稱 -> CityRule
    slots: frozenset = frozenset()               # 啟用的發送時段，如 {"08:45", "14:45"}


def _is_bool(v) -> bool:
    return isinstance(v, bool)


def _is_num(v, low: float, high: float) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and low <= v <= high


def parse_settings(city_rows: list[dict], slot_rows: list[dict]) -> tuple[AlertSettings, list[str]]:
    """把資料庫的列轉成 AlertSettings；不合法的列略過並回報警告（該縣市／時段視為關閉）。"""
    warnings: list[str] = []
    cities: dict[str, CityRule] = {}
    for row in city_rows or []:
        name = row.get("location_name")
        try:
            ok = (isinstance(name, str) and name
                  and all(_is_bool(row[k]) for k in ("enabled", "rain_enabled", "min_temp_enabled", "max_temp_enabled"))
                  and _is_num(row["rain_threshold"], 0, 100)
                  and _is_num(row["min_temp_threshold"], -20, 50)
                  and _is_num(row["max_temp_threshold"], -20, 50))
        except KeyError:
            ok = False
        if not ok:
            warnings.append(f"縣市設定不合法，已略過：{name!r}")
            continue
        cities[name] = CityRule(
            enabled=row["enabled"], rain_on=row["rain_enabled"], rain=int(row["rain_threshold"]),
            min_on=row["min_temp_enabled"], min_temp=float(row["min_temp_threshold"]),
            max_on=row["max_temp_enabled"], max_temp=float(row["max_temp_threshold"]))
    slots = set()
    for row in slot_rows or []:
        slot = row.get("slot")
        if slot not in SEND_SLOTS or not _is_bool(row.get("enabled")):
            warnings.append(f"發送時段設定不合法，已略過：{slot!r}")
        elif row["enabled"]:
            slots.add(slot)
    return AlertSettings(cities, frozenset(slots)), warnings


def window_end(slot: datetime, enabled_slots: frozenset) -> datetime:
    """下一個啟用的發送時槽（嚴格晚於 slot）；只啟用一個時段時為隔天的同一時間。"""
    times = sorted(enabled_slots)
    for day in (0, 1):
        for t in times:
            hour, minute = map(int, t.split(":"))
            candidate = (slot + timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > slot:
                return candidate
    raise ValueError("沒有啟用的發送時段")


def classify(start: datetime, end: datetime, slot: datetime, wend: datetime) -> str | None:
    """時段與視窗 (slot, wend] 的關係：進行中（已開始、尚未結束）／即將開始／None（不相關）。"""
    if end <= slot or start > wend:
        return None
    return "進行中" if start <= slot else "即將開始"


REASONS = ("降雨", "低溫", "高溫")  # hit_reasons 的回傳順序，也是訊息統計的順序


def hit_reasons(row: dict, rule: CityRule) -> list[str]:
    """該縣市已啟用且符合的條件，依 REASONS 順序（如 ["低溫"]、["降雨", "高溫"]）。值為 NULL 的欄位不判斷。"""
    rain, tmin, tmax = row.get("rain_probability"), row.get("min_temp"), row.get("max_temp")
    reasons = []
    if rule.rain_on and rain is not None and rain >= rule.rain:
        reasons.append("降雨")
    if rule.min_on and tmin is not None and tmin <= rule.min_temp:
        reasons.append("低溫")
    if rule.max_on and tmax is not None and tmax >= rule.max_temp:
        reasons.append("高溫")
    return reasons


def is_hit(row: dict, rule: CityRule) -> bool:
    """該縣市已啟用的條件（降雨／低溫／高溫）任一符合。"""
    return bool(hit_reasons(row, rule))


def evaluate_alerts(records: list[dict], settings: AlertSettings, slot: datetime) -> tuple[list[dict], datetime]:
    """回傳 (符合條件的列, 視窗結束時間)；依起點時間排序。

    每列多兩個欄位：label（進行中／即將開始）與 reasons（符合的條件，見 hit_reasons）。
    """
    wend = window_end(slot, settings.slots)
    alerts = []
    for row in records:
        rule = settings.cities.get(row["location_name"])
        if rule is None or not rule.enabled:
            continue
        label = classify(datetime.fromisoformat(row["forecast_time_start"]),
                         datetime.fromisoformat(row["forecast_time_end"]), slot, wend)
        if not label:
            continue
        reasons = hit_reasons(row, rule)
        if reasons:
            alerts.append({**row, "label": label, "reasons": reasons})
    alerts.sort(key=lambda r: r["forecast_time_start"])  # 穩定排序：同時段維持原本的縣市順序
    return alerts, wend
