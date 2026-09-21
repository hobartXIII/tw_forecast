"""氣溫級距與顏色：地圖標記、圖例、表格與摘要卡片共用同一套級距。"""
import pandas as pd

# (顏色, 圖例文字)；規格 §8.1：<20 藍綠、20~25 綠、25~30 橙黃、>30 鮮紅
BANDS = [
    ("#17a2b8", "&lt; 20°C"),
    ("#2f9e44", "20 ~ 25°C"),
    ("#f59f00", "25 ~ 30°C"),
    ("#e03131", "&gt; 30°C"),
]

# 文字用的級距色：中等明度，在淺色與深色主題的底色上對比都約 3:1 以上（標記底色用上面的 BANDS，較亮）
TEXT_COLORS = ["#0b8ba0", "#2b8a3e", "#cc6a00", "#e03131"]


def band_index(temp: float) -> int:
    """溫度所屬級距：0（<20）、1（20~25）、2（25~30）、3（>30）；邊界值歸入較低級距。"""
    if temp < 20:
        return 0
    if temp <= 25:
        return 1
    if temp <= 30:
        return 2
    return 3


def temp_color(temp: float) -> str:
    """標記底色（較亮）。"""
    return BANDS[band_index(temp)][0]


def text_color(value) -> str:
    """文字用的級距色；NULL 回傳空字串（沿用預設文字色）。"""
    return "" if pd.isna(value) else TEXT_COLORS[band_index(value)]


def colored(value, text: str) -> str:
    """把 text 依 value 的溫度級距包成有色的 <span>（HTML）；NULL 不上色。"""
    color = text_color(value)
    return f'<span style="color:{color};font-weight:700">{text}</span>' if color else text


def temp_text(value, unit: str = "°C") -> str:
    """整數溫度；NULL 顯示「—」。"""
    return "—" if pd.isna(value) else f"{value:.0f}{unit}"


def display_temp(df: pd.DataFrame) -> pd.Series:
    """平均溫；avg_temp 為 NULL 時退回 (min_temp + max_temp) / 2。"""
    return df["avg_temp"].fillna((df["min_temp"] + df["max_temp"]) / 2)
