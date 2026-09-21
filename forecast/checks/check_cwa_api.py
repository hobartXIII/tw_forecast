"""驗證 CWA API 連線，並把原始回應存到 samples/ 供分析欄位結構。

用法：python checks/check_cwa_api.py [資料集代碼，預設 F-D0047-091]
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

dataset = sys.argv[1] if len(sys.argv) > 1 else "F-D0047-091"
api_key = os.getenv("WEATHER_API_KEY")
if not api_key:
    sys.exit("找不到 WEATHER_API_KEY，請先建立 .env（參考 .env.example）")

url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{dataset}"
resp = requests.get(url, params={"Authorization": api_key, "format": "JSON"}, timeout=30)
print("HTTP", resp.status_code, f"{len(resp.content) / 1024:.1f} KB")
resp.raise_for_status()

data = resp.json()
print("top-level keys:", list(data.keys()))

out = ROOT / "samples" / f"{dataset}.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("已儲存:", out)
