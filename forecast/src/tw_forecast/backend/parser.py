"""把氣象署的巢狀 JSON 攤平成 weather_forecasts 表的列。

輸入：API 原始 JSON。輸出：list[dict]，每列 = 一個縣市的一個 12 小時時段（含座標與各氣象要素）。
"""
import re
from dataclasses import dataclass
from typing import Callable

HAS_TZ = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def _num(v) -> float:
    return float(v)


def _int(v) -> int:
    return int(float(v))  # API 常回 "30.0" 這類字串，先轉 float 再取整


def _str(v) -> str:
    return str(v)


@dataclass(frozen=True)
class ElementSpec:
    """單一氣象要素的對應：資料表欄位、ElementValue 內的鍵名、轉型函式。"""
    column: str
    key: str
    cast: Callable


class ForecastParser:
    """ElementName（中文要素名稱）→ ElementSpec 的對照表，以及解析流程。"""

    ELEMENTS = {
        "天氣現象": ElementSpec("weather_condition", "Weather", _str),
        "最低溫度": ElementSpec("min_temp", "MinTemperature", _num),
        "最高溫度": ElementSpec("max_temp", "MaxTemperature", _num),
        "平均溫度": ElementSpec("avg_temp", "Temperature", _num),
        "12小時降雨機率": ElementSpec("rain_probability", "ProbabilityOfPrecipitation", _int),
        "最大舒適度指數": ElementSpec("comfort_index", "MaxComfortIndexDescription", _str),
    }

    @staticmethod
    def to_iso(ts: str) -> str:
        """確保時間字串帶時區；若無則視為台灣時間補上 +08:00（規格書 §3.4）。"""
        ts = ts.strip().replace(" ", "T")
        return ts if HAS_TZ.search(ts) else ts + "+08:00"

    @staticmethod
    def clean(value, cast: Callable):
        """空字串、"-"、無法轉型的值一律視為沒有資料（None → 寫入資料庫為 NULL）。"""
        if value is None or str(value).strip() in ("", "-"):
            return None
        try:
            return cast(value)
        except (TypeError, ValueError):
            return None

    def parse(self, raw: dict) -> list[dict]:
        """以 (縣市, 起, 迄) 合併各要素成一列；沒給值的要素欄位補 None。"""
        rows: dict[tuple, dict] = {}
        for locations in raw["records"]["Locations"]:
            for loc in locations["Location"]:
                lat = self.clean(loc.get("Latitude"), _num)
                lng = self.clean(loc.get("Longitude"), _num)
                for element in loc["WeatherElement"]:
                    spec = self.ELEMENTS.get(element["ElementName"])
                    if spec is None:
                        continue
                    for t in element["Time"]:
                        start, end = self.to_iso(t["StartTime"]), self.to_iso(t["EndTime"])
                        row = rows.setdefault((loc["LocationName"], start, end), {
                            "location_name": loc["LocationName"],
                            "forecast_time_start": start,
                            "forecast_time_end": end,
                            "latitude": lat,
                            "longitude": lng,
                        })
                        values = t.get("ElementValue") or [{}]
                        row[spec.column] = self.clean(values[0].get(spec.key), spec.cast)
        records = list(rows.values())
        for record in records:
            for spec in self.ELEMENTS.values():
                record.setdefault(spec.column, None)
        return records
