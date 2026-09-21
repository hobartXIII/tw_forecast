"""氣象署開放資料 API 客戶端。

輸入：API 授權碼。輸出：API 回傳的原始 JSON（dict）。
"""
import sys
import time
from typing import Callable

import requests

from tw_forecast.backend.errors import AbortRun
from tw_forecast.config import CWA_URL


class CwaClient:
    """打氣象署 F-D0047-091：失敗最多重試到 ``max_attempts`` 次；HTTP 429（超過用量）不重試、直接中止。"""

    RETRY_DELAYS = (5, 15)  # 第 1、2 次失敗後各等待幾秒

    def __init__(self, api_key: str | None, max_attempts: int = 3,
                 sleep: Callable[[float], None] = time.sleep, get=requests.get):
        """sleep 與 get 可注入，方便測試時不真的等待、不連網。"""
        self._api_key = api_key
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._get = get

    def fetch(self) -> dict:
        """打一次 API（含重試），回傳原始 JSON。缺金鑰或 429 拋 AbortRun；其餘失敗在重試用盡後拋出原例外。"""
        if not self._api_key:
            raise AbortRun("缺少環境變數 WEATHER_API_KEY")
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._request_once()
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                print(f"[第 {attempt} 次嘗試失敗] {exc}", file=sys.stderr)
                if attempt == self._max_attempts:
                    raise
                self._sleep(self.RETRY_DELAYS[attempt - 1])

    def _request_once(self) -> dict:
        resp = self._get(CWA_URL, params={"format": "JSON"},
                         headers={"Authorization": self._api_key}, timeout=30)
        if resp.status_code == 429:
            raise AbortRun("CWA API 回應 429 (超過用量限制)，中止本次執行")
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") not in (True, "true"):
            raise RuntimeError(f"CWA 回應 success != true: {data.get('result')}")
        return data
