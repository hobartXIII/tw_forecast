"""顯示用的小工具。"""
import pandas as pd


def weather_icon(text: str | None) -> str:
    """依「天氣現象」文字回傳對應 emoji（無法判斷時回傳空字串）。"""
    if not text or pd.isna(text):
        return ""
    for keyword, icon in (("雷", "⛈️"), ("雨", "🌧️"), ("雪", "❄️"), ("霧", "🌫️")):
        if keyword in text:
            return icon
    if text.startswith("晴"):
        return "🌤️" if "多雲" in text else "☀️"
    if "多雲" in text:
        return "⛅"
    if "陰" in text:
        return "☁️"
    return "🌡️"
