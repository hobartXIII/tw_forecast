"""流程一：CWA F-D0047-091 一週預報 → 清洗 → Upsert 至 Supabase → 告警推播。

用法：
    python scripts/fetch_and_store.py                       # 正式執行 (打 API、寫 DB、推播)
    python scripts/fetch_and_store.py --dry-run             # 打 API 但不寫 DB、不推播
    python scripts/fetch_and_store.py --dry-run --from-sample   # 讀 samples/ 離線測試
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATASET = "F-D0047-091"
CWA_URL = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{DATASET}"
SAMPLE_PATH = ROOT / "samples" / f"{DATASET}.json"
TZ = timezone(timedelta(hours=8))  # 台灣時間 (UTC+8)，不依賴系統時區

# 告警門檻與範圍 (SPECIFICATION.md §6.1)
ALERT_RAIN = 60
ALERT_MIN_TEMP = 12
ALERT_MAX_TEMP = 35
ALERT_WINDOW_HOURS = 6  # 與 cron 間隔一致：時段起點落在 (現在, 現在+6h] 才告警，每時段只通知一次

# ElementName -> (資料表欄位, ElementValue 鍵名, 轉型函式)
def _num(v): return float(v)
def _int(v): return int(float(v))
def _str(v): return str(v)

ELEMENTS = {
    "天氣現象": ("weather_condition", "Weather", _str),
    "最低溫度": ("min_temp", "MinTemperature", _num),
    "最高溫度": ("max_temp", "MaxTemperature", _num),
    "平均溫度": ("avg_temp", "Temperature", _num),
    "12小時降雨機率": ("rain_probability", "ProbabilityOfPrecipitation", _int),
    "最大舒適度指數": ("comfort_index", "MaxComfortIndexDescription", _str),
}
HAS_TZ = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def fetch_cwa(max_attempts: int = 3) -> dict:
    """打 CWA API（只打一次，失敗最多重試到 max_attempts 次；429 不重試）。"""
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        sys.exit("缺少環境變數 WEATHER_API_KEY")
    delays = [5, 15]
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(CWA_URL, params={"format": "JSON"},
                                headers={"Authorization": api_key}, timeout=30)
            if resp.status_code == 429:
                sys.exit("CWA API 回應 429 (超過用量限制)，中止本次執行")
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") not in (True, "true"):
                raise RuntimeError(f"CWA 回應 success != true: {data.get('result')}")
            return data
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            print(f"[第 {attempt} 次嘗試失敗] {exc}", file=sys.stderr)
            if attempt == max_attempts:
                raise
            time.sleep(delays[attempt - 1])


def _iso(ts: str) -> str:
    """確保時間字串帶時區；若無則視為台灣時間補上 +08:00 (SPECIFICATION.md §3.4)。"""
    ts = ts.strip().replace(" ", "T")
    return ts if HAS_TZ.search(ts) else ts + "+08:00"


def _clean(value, cast):
    if value is None or str(value).strip() in ("", "-"):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def parse(raw: dict) -> list[dict]:
    """把巢狀 JSON 攤平成 weather_forecasts 的列，以 (縣市, 起, 迄) 合併各要素。"""
    rows: dict[tuple, dict] = {}
    for locations in raw["records"]["Locations"]:
        for loc in locations["Location"]:
            lat = _clean(loc.get("Latitude"), _num)
            lng = _clean(loc.get("Longitude"), _num)
            for element in loc["WeatherElement"]:
                spec = ELEMENTS.get(element["ElementName"])
                if spec is None:
                    continue
                column, key, cast = spec
                for t in element["Time"]:
                    start, end = _iso(t["StartTime"]), _iso(t["EndTime"])
                    row = rows.setdefault((loc["LocationName"], start, end), {
                        "location_name": loc["LocationName"],
                        "forecast_time_start": start,
                        "forecast_time_end": end,
                        "latitude": lat,
                        "longitude": lng,
                    })
                    values = t.get("ElementValue") or [{}]
                    row[column] = _clean(values[0].get(key), cast)
    records = list(rows.values())
    for r in records:  # 該時段 API 沒給值（如 "-"）的欄位補 None，寫入資料庫為 NULL
        for column, _, _ in ELEMENTS.values():
            r.setdefault(column, None)
    return records


def is_alert(row: dict, now: datetime) -> bool:
    """即將開始的時段 (起點在 (now, now+6h])，且符合降雨/低溫/高溫任一條件。"""
    start = datetime.fromisoformat(row["forecast_time_start"])
    if not (now < start <= now + timedelta(hours=ALERT_WINDOW_HOURS)):
        return False
    rain, tmin, tmax = row.get("rain_probability"), row.get("min_temp"), row.get("max_temp")
    return ((rain is not None and rain >= ALERT_RAIN)
            or (tmin is not None and tmin <= ALERT_MIN_TEMP)
            or (tmax is not None and tmax >= ALERT_MAX_TEMP))


def build_card(rows: list[dict]) -> dict:
    lines = []
    for r in rows:
        start = datetime.fromisoformat(r["forecast_time_start"]).astimezone(TZ)
        lines.append(f"{r['location_name']} {start:%m/%d %H:%M} 起｜降雨 {r.get('rain_probability')}%｜"
                     f"{r.get('min_temp')}~{r.get('max_temp')}°C")
    return {"cardsV2": [{"cardId": "weather-alert", "card": {
        "header": {"title": "🔔 天氣告警", "subtitle": f"未來 {ALERT_WINDOW_HOURS} 小時內開始的時段，{len(rows)} 筆符合條件"},
        "sections": [{"widgets": [{"textParagraph": {"text": "<br>".join(lines[:30])}}]}],
    }}]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="不寫入資料庫、不推播")
    parser.add_argument("--from-sample", action="store_true", help="讀 samples/ 而非呼叫 API")
    args = parser.parse_args()

    raw = (json.loads(SAMPLE_PATH.read_text(encoding="utf-8")) if args.from_sample else fetch_cwa())
    records = parse(raw)
    now = datetime.now(TZ)
    print(f"解析完成：{len(records)} 列，{len({r['location_name'] for r in records})} 個縣市")

    alerts = [r for r in records if is_alert(r, now)]

    if args.dry_run:
        print(f"[dry-run] 符合告警 {len(alerts)} 筆（不寫 DB、不推播）")
        for r in alerts[:5]:
            print("  ", r["location_name"], r["forecast_time_start"], r.get("rain_probability"),
                  r.get("min_temp"), r.get("max_temp"))
        print("[dry-run] 範例列:", json.dumps(records[0], ensure_ascii=False))
        return

    from supabase import create_client
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not url or not key:
        sys.exit("缺少 SUPABASE_URL / SUPABASE_KEY")
    sb = create_client(url, key)

    # 整批共用同一個 updated_at（新增與更新皆以本次寫入時間為準）
    stamp = datetime.now(TZ).isoformat()
    for r in records:
        r["updated_at"] = stamp

    # 單次 upsert = 單一交易，前端不會讀到寫一半的批次
    sb.table("weather_forecasts").upsert(
        records, on_conflict="location_name,forecast_time_start,forecast_time_end").execute()
    print(f"已 upsert {len(records)} 列至 weather_forecasts")

    # 告警：資料寫入成功後才推播；去重靠 is_alert 的 6 小時起點視窗（見 SPECIFICATION.md §6.1）
    if not alerts:
        print("無需推播")
        return
    webhook = os.getenv("GOOGLE_CHAT_WEBHOOK")
    if not webhook:
        print("未設定 GOOGLE_CHAT_WEBHOOK，略過推播")
        return
    requests.post(webhook, json=build_card(alerts), timeout=15).raise_for_status()
    print(f"已推播 {len(alerts)} 筆告警")


if __name__ == "__main__":
    main()
