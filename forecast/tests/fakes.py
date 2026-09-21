"""測試用的假物件與資料產生器：不連網、不連資料庫，也不依賴被 .gitignore 的 samples/。"""
from datetime import datetime, timedelta, timezone

from tw_forecast.frontend.regions import CITY_ORDER

TZ = timezone(timedelta(hours=8))


# ---------- 假 Supabase ----------
class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """支援 select／lte／lt／gte／gt／eq／in_／order／limit／execute 與 upsert，資料放在記憶體。"""

    def __init__(self, table):
        self._table = table
        self.rows = list(table.rows)
        self._limit = None
        self._cols = None
        self._upsert = None

    def select(self, cols="*"):
        self._cols = None if cols == "*" else cols.split(",")
        return self

    def _cmp(self, col, value, fn):
        v = datetime.fromisoformat(value)
        self.rows = [r for r in self.rows if fn(datetime.fromisoformat(r[col]), v)]
        return self

    def lte(self, col, value): return self._cmp(col, value, lambda a, b: a <= b)
    def lt(self, col, value): return self._cmp(col, value, lambda a, b: a < b)
    def gte(self, col, value): return self._cmp(col, value, lambda a, b: a >= b)
    def gt(self, col, value): return self._cmp(col, value, lambda a, b: a > b)

    def eq(self, col, value):
        self.rows = [r for r in self.rows if r[col] == value]
        return self

    def in_(self, col, values):
        self.rows = [r for r in self.rows if r[col] in values]
        return self

    def order(self, col, desc=False):
        self.rows.sort(key=lambda r: datetime.fromisoformat(r[col]), reverse=desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def upsert(self, payload, on_conflict=None):
        self._upsert = (payload, on_conflict)
        return self

    def execute(self):
        if self._upsert is not None:
            payload, on_conflict = self._upsert
            self._table.upserts.append((payload, on_conflict))
            return FakeResult(payload)
        rows = self.rows[: self._limit] if self._limit else self.rows
        if self._cols:
            rows = [{k: r[k] for k in self._cols} for r in rows]
        return FakeResult([dict(r) for r in rows])


class FakeTable:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.upserts = []  # 記錄每次 upsert 的 (資料, on_conflict)，測試用來斷言


class FakeClient:
    """table(name) 回傳查詢物件；rpc(name, params) 回傳預先設定好的結果（或拋出預先設定的例外）。"""

    def __init__(self, tables=None, rpc_results=None):
        self.tables = {name: FakeTable(rows) for name, rows in (tables or {}).items()}
        self.rpc_results = rpc_results or {}
        self.rpc_calls = []

    def table(self, name):
        return FakeQuery(self.tables.setdefault(name, FakeTable()))

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        result = self.rpc_results[name]
        if isinstance(result, Exception):
            raise result
        return _RpcCall(result)


class _RpcCall:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return FakeResult(self._data)


# ---------- 假氣象署 API 回應 ----------
def cwa_payload(city="臺北市", start="2026-09-21T06:00:00+08:00", end="2026-09-21T18:00:00+08:00", **override):
    """一個縣市、一個時段的最小 API 回應。override 可替換要素的值（如 MaxTemperature="-"）。"""
    values = {"Weather": "多雲", "MinTemperature": "25", "MaxTemperature": "31", "Temperature": "28",
              "ProbabilityOfPrecipitation": "30", "MaxComfortIndexDescription": "悶熱"}
    values.update(override)

    def element(name, key):
        return {"ElementName": name, "Time": [{"StartTime": start, "EndTime": end, "ElementValue": [{key: values[key]}]}]}

    return {"success": "true", "records": {"Locations": [{"Location": [{
        "LocationName": city, "Latitude": "25.05", "Longitude": "121.5",
        "WeatherElement": [
            element("天氣現象", "Weather"), element("最低溫度", "MinTemperature"),
            element("最高溫度", "MaxTemperature"), element("平均溫度", "Temperature"),
            element("12小時降雨機率", "ProbabilityOfPrecipitation"),
            element("最大舒適度指數", "MaxComfortIndexDescription")]}]}]}}


# ---------- 假預報資料庫列（22 縣市 × 多個 12 小時時段） ----------
def forecast_rows(first_day: datetime, days: int = 4, updated_at: str = "2026-09-21T09:30:00+08:00") -> list[dict]:
    """每個縣市、每天 06:00~18:00 與 18:00~隔天 06:00 兩個完整時段。溫度隨縣市與時段變化，方便驗證極值。"""
    rows = []
    for c, city in enumerate(CITY_ORDER):
        for d in range(days * 2):
            start = first_day + timedelta(hours=12 * d)
            rows.append({
                "location_name": city,
                "forecast_time_start": start.isoformat(), "forecast_time_end": (start + timedelta(hours=12)).isoformat(),
                "latitude": 22.0 + c * 0.15, "longitude": 120.0 + c * 0.08,
                "weather_condition": ["晴", "多雲", "陰短暫雨"][d % 3],
                "min_temp": 18.0 + c * 0.5, "max_temp": 24.0 + c * 0.5 + d, "avg_temp": 21.0 + c * 0.5,
                "rain_probability": None if d > 5 else (d * 10 + c) % 100,
                "comfort_index": "舒適", "updated_at": updated_at,
            })
    return rows
