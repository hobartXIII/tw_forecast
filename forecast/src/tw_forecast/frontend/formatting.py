"""顯示用的小工具：日夜判斷、天氣圖示、時間文字。"""
import pandas as pd


def is_night(start, end) -> bool:
    """依時段中點判斷日夜：中點在 06:00～18:00 為日間，其餘為夜間。

    氣象署時段以 06 時與 18 時為日夜分界；第一個時段可能被截短（如 00:00–06:00、12:00–18:00），
    用中點判斷仍然正確。start / end 為 tz-aware（Asia/Taipei）。
    """
    mid = start + (end - start) / 2
    return not (6 <= mid.hour < 18)


def weather_icon(text: str | None, night: bool = False) -> str:
    """依「天氣現象」文字與日夜回傳對應 emoji（無法判斷時回傳空字串）。

    有太陽的圖示夜間不可出現，晴改月亮、其餘改雲；雨／雷／雪／霧沒有太陽，日夜相同。
    """
    if not text or pd.isna(text):
        return ""
    for keyword, icon in (("雷", "⛈️"), ("雨", "🌧️"), ("雪", "❄️"), ("霧", "🌫️")):
        if keyword in text:
            return icon
    if text.startswith("晴"):
        if "多雲" in text:  # 晴時多雲
            return "🌙☁️" if night else "🌤️"
        return "🌙" if night else "☀️"
    if "陰" in text:  # 陰、陰時多雲、多雲時陰 … 以陰天為主
        return "☁️"
    if "多雲" in text:  # 多雲、多雲時晴
        return "☁️" if night else "⛅"
    return "🌡️"


def format_range(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """預報時段文字，如「09/21 18:00 ~ 09/22 06:00」。"""
    return f"{start:%m/%d %H:%M} ~ {end:%m/%d %H:%M}"


def format_last_update(rows: list[dict] | None, trigger: str) -> str:
    """某來源（schedule / manual）最後一次成功更新的時間文字；沒有紀錄回傳「—」。"""
    for row in rows or []:
        if row.get("trigger_type") == trigger and row.get("last_success_at") is not None:
            return f"{row['last_success_at']:%m/%d %H:%M}"
    return "—"


def format_value(value, unit: str, fmt: str = ".0f") -> str:
    """數值加單位；None 或 NaN 顯示「—」。"""
    return "—" if value is None or pd.isna(value) else f"{value:{fmt}} {unit}"
