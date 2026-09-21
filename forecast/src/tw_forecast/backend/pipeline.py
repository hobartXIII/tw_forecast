"""流程一：取得預報 → 清洗 → 寫入資料庫 → 依設定告警推播。

Pipeline 只負責「串流程」，所有外部相依（資料來源、資料庫、通知器、時鐘）都由外面注入，
因此單元測試可以完全不連網、不連資料庫。

輸入：資料來源、解析器、各 Repository、通知器；run() 收執行來源（schedule／manual）。
輸出：寫入 weather_forecasts 與 pipeline_status；符合條件時推播 Telegram；過程以 print 記錄到日誌。

執行步驟（下面 run()／_alert() 的註解用同樣的編號；每一步印出的日誌訊息見 ARCHITECTURE.md「後端步驟對照」）：
  1 啟動（cli.main）→ 2 取得 API 資料 → 3 解析 → 4 寫入預報 → 5 記錄執行狀態
  → 6 告警判斷（只有排程）→ 7 推播 Telegram
"""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from tw_forecast.backend import alerts
from tw_forecast.backend.parser import ForecastParser
from tw_forecast.backend.repository import AlertSettingsRepository, ForecastRepository, StatusRepository
from tw_forecast.backend.slots import current_slot
from tw_forecast.config import TZ


@dataclass
class Pipeline:
    """一次完整執行所需的協作物件。dry_run 時 forecasts / status / alert_settings / notifier 皆可為 None。"""
    fetch_raw: Callable[[], dict]                       # 取得 API 原始 JSON（線上 API 或離線樣本）
    parser: ForecastParser
    forecasts: ForecastRepository | None = None
    status: StatusRepository | None = None
    alert_settings: AlertSettingsRepository | None = None
    notifier: object | None = None                      # TelegramNotifier；未設定 Telegram 時為 None
    dry_run: bool = False
    now: Callable[[], datetime] = lambda: datetime.now(TZ)

    def run(self, trigger: str) -> None:
        """執行一次。trigger 為 "schedule"（排程，會推播）或 "manual"（手動／本機，只更新資料）。"""
        # [步驟 2] 取得 API 原始 JSON（CwaClient.fetch，或 --from-sample 讀樣本）→ [步驟 3] 解析成資料列
        records = self.parser.parse(self.fetch_raw())
        slot = current_slot(self.now())
        print(f"解析完成：{len(records)} 列，{len({r['location_name'] for r in records})} 個縣市")

        if self.dry_run:
            self._print_dry_run(records, slot)
            return

        # [步驟 4] 寫入預報：整批共用同一個 updated_at（新增與更新皆以本次寫入時間為準），單一交易 upsert
        stamp = self.now().isoformat()
        for record in records:
            record["updated_at"] = stamp
        self.forecasts.upsert(records)
        print(f"已 upsert {len(records)} 列至 weather_forecasts（來源：{trigger}）")
        # [步驟 5] 記錄執行狀態：寫入 pipeline_status（前端「立即更新」的間隔判斷依據）
        self.status.record(trigger, "success", stamp)

        # [步驟 6] 告警判斷：只有排程推播（手動與本機只更新資料）；資料寫入成功後才判斷。
        if trigger != "schedule":
            print(f"非排程執行（{trigger}），略過告警推播")
            return
        self._alert(records, slot)

    def record_failure(self, trigger: str, reason: str) -> None:
        """流程失敗時記錄到 pipeline_status（reason 須已遮蔽機密）。"""
        if self.status is not None:
            self.status.record(trigger, "failed", self.now().isoformat(), reason[:300])

    @staticmethod
    def _print_dry_run(records: list[dict], slot: datetime) -> None:
        wend = alerts.window_end(slot, frozenset(alerts.SEND_SLOTS))
        print(f"[dry-run] 排程時槽 {slot:%m/%d %H:%M}；若三個發送時段皆啟用，告警視窗為 "
              f"({slot:%m/%d %H:%M}, {wend:%m/%d %H:%M}]（不讀取告警設定、不寫 DB、不推播）")
        print("[dry-run] 範例列:", json.dumps(records[0], ensure_ascii=False))

    def _alert(self, records: list[dict], slot: datetime) -> None:
        """依資料庫設定判斷這個時槽要不要發、發哪些；任何一步不符合就略過並記錄原因。"""
        settings = self.alert_settings.load()
        if settings is None:  # 讀不到設定 → 不發送（fail closed）
            return
        label = f"{slot:%H:%M}"
        if label not in settings.slots:
            print(f"排程時槽 {label} 不在啟用的發送時段（{', '.join(sorted(settings.slots)) or '無'}），略過推播")
            return
        if not any(rule.enabled for rule in settings.cities.values()):
            print("尚未啟用任何縣市，不發送告警")
            return
        hits, wend = alerts.evaluate_alerts(records, settings, slot)  # 逐一套用縣市規則與判斷視窗
        scope = f"涵蓋 {slot:%m/%d %H:%M}～{wend:%m/%d %H:%M}"
        if not hits:
            print(f"無需推播（{scope}，沒有符合條件的時段）")
            return
        if self.notifier is None:
            print("未設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，略過推播")
            return
        self.notifier.notify_alerts(hits, scope)  # [步驟 7] 推播 Telegram
        print(f"已推播 {len(hits)} 筆告警（{scope}）")
