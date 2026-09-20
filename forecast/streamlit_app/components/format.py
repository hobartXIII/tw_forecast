"""顯示用的小工具。"""
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
