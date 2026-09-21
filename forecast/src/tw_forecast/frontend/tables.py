"""明細表格的資料整理（純函式，不依賴 Streamlit）。"""
import pandas as pd

from tw_forecast.frontend.formatting import is_night, weather_icon


def make_table(src: pd.DataFrame, *, dated: bool) -> pd.DataFrame:
    """輸入：含 region、avg 等欄位的預報列。輸出：中文欄位的明細表格。

    天氣現象的圖示依每列自己的時段判斷日夜；dated=True 時時段文字含日期（跨日的表格用）。
    """
    period = [f"{s:%m/%d %H:%M}~{e:%H:%M}" if dated else f"{s:%H:%M}~{e:%H:%M}"
              for s, e in zip(src["forecast_time_start"], src["forecast_time_end"])]
    weather = [f"{weather_icon(w, is_night(s, e))} {w}".strip() if isinstance(w, str) else "—"
               for w, s, e in zip(src["weather_condition"], src["forecast_time_start"], src["forecast_time_end"])]
    columns = {"縣市": src["location_name"], "地區": src["region"]}
    columns.update({
        "時段": period, "天氣現象": weather,
        "最低 (°C)": src["min_temp"], "最高 (°C)": src["max_temp"], "平均 (°C)": src["avg"].round(1),
        "降雨機率": src["rain_probability"], "舒適度": src["comfort_index"].fillna("—"),
    })
    return pd.DataFrame(columns).reset_index(drop=True)


def next_periods(forecast: pd.DataFrame, after: pd.Timestamp, n: int = 2) -> pd.DataFrame:
    """每個縣市在 after 之後的 n 個時段，依縣市（地區順序）→ 時間排序。"""
    return (forecast[forecast["forecast_time_start"] > after]
            .sort_values(["order", "forecast_time_start"]).groupby("location_name", sort=False).head(n))
