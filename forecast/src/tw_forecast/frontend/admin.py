"""管理者設定面板的資料層（SPECIFICATION.md §8.1）。

輸入：管理者密碼、可編輯的設定表格（DataFrame）與發送時段。輸出：資料庫函式的回傳值、驗證結果。

- 密碼只在呼叫時當作函式參數送給資料庫驗證；本模組不儲存密碼、不寫入日誌，錯誤訊息一律遮蔽密碼。
- 所有讀寫都經過資料庫函式（admin_get_alert_settings / admin_save_alert_settings），
  前端的 anon 金鑰無法直接讀寫設定表。
- 表格轉換與驗證是純函式，不需要資料庫；AlertSettingsService 負責呼叫資料庫。
"""
import pandas as pd

from tw_forecast.config import SEND_SLOTS
from tw_forecast.frontend.regions import CITY_ORDER

SLOTS = SEND_SLOTS                           # 可選的發送時段（與資料庫 CHECK 一致）
IDLE_TIMEOUT_SECONDS = 15 * 60               # 閒置多久自動登出

# 表格欄位（顯示名稱）→ 資料庫欄位
COLUMNS = {
    "縣市": "location_name",
    "啟用": "enabled",
    "降雨": "rain_enabled", "降雨門檻 (%)": "rain_threshold",
    "低溫": "min_temp_enabled", "低溫門檻 (°C)": "min_temp_threshold",
    "高溫": "max_temp_enabled", "高溫門檻 (°C)": "max_temp_threshold",
}
BOOL_COLUMNS = ["啟用", "降雨", "低溫", "高溫"]
LIMITS = {"降雨門檻 (%)": (0, 100), "低溫門檻 (°C)": (-20, 50), "高溫門檻 (°C)": (-20, 50)}  # 與資料庫 CHECK 一致


class AdminError(Exception):
    """設定面板的錯誤；訊息保證不含密碼。"""


class WrongPassword(AdminError):
    """密碼錯誤（或已失效）。"""


class NotConfigured(AdminError):
    """資料庫函式不存在（尚未執行 sql/init_supabase.sql）。"""


def translate_error(exc: Exception, password: str | None) -> AdminError:
    """把資料庫（PostgREST）的例外轉成不含密碼的 AdminError。"""
    code = str(getattr(exc, "code", "") or "")
    text = " ".join(str(getattr(exc, attr, "") or "") for attr in ("message", "details", "hint")).strip() or str(exc)
    if "invalid_password" in text:
        return WrongPassword("密碼錯誤")
    if code in ("PGRST202", "42883") or "Could not find the function" in text:
        return NotConfigured("設定功能尚未啟用：資料庫函式不存在，請先在 Supabase 執行 sql/init_supabase.sql")
    if password:
        text = text.replace(password, "***")
    return AdminError(text[:200])


def to_dataframe(rows: list[dict]) -> pd.DataFrame:
    """資料庫列 → 表格；依縣市順序（北→中→南→東→離島）排序，欄位改為中文並轉成正確型別。"""
    inverse = {db: shown for shown, db in COLUMNS.items()}
    df = pd.DataFrame(rows or [], columns=list(inverse)).rename(columns=inverse)
    order = {name: i for i, name in enumerate(CITY_ORDER)}
    df = df.assign(_o=df["縣市"].map(lambda n: order.get(n, 999))).sort_values(["_o", "縣市"]).drop(columns="_o")
    for column in BOOL_COLUMNS:
        df[column] = df[column].astype(bool)
    df["降雨門檻 (%)"] = df["降雨門檻 (%)"].astype(int)
    for column in ("低溫門檻 (°C)", "高溫門檻 (°C)"):
        df[column] = df[column].astype(float)
    return df.reset_index(drop=True)


def validate(df: pd.DataFrame, slots: dict[str, bool]) -> list[str]:
    """儲存前檢查（資料庫另有 CHECK 把關）。回傳錯誤訊息清單，空清單代表通過。"""
    errors = []
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        return [f"缺少欄位：{', '.join(missing)}"]
    if df["縣市"].duplicated().any():
        errors.append("縣市重複")
    for _, row in df.iterrows():
        name = row["縣市"]
        for column in BOOL_COLUMNS:
            if pd.isna(row[column]):
                errors.append(f"{name}：「{column}」必須勾選或不勾選")
        for column, (low, high) in LIMITS.items():
            value = row[column]
            if pd.isna(value):
                errors.append(f"{name}：「{column}」不可空白")
            elif not (low <= float(value) <= high):
                errors.append(f"{name}：「{column}」必須介於 {low} 到 {high}")
            elif column == "降雨門檻 (%)" and float(value) != int(float(value)):
                errors.append(f"{name}：「{column}」必須是整數")
    if set(slots) - set(SLOTS) or not all(v in (True, False) for v in slots.values()):
        errors.append("發送時段設定不合法")
    return errors


def build_payload(df: pd.DataFrame, slots: dict[str, bool]) -> tuple[list[dict], list[dict]]:
    """表格 → 資料庫函式的參數（使用 Python 原生型別，確保可轉成 JSON）。"""
    cities = []
    for _, row in df.iterrows():
        item = {COLUMNS[c]: bool(row[c]) for c in BOOL_COLUMNS}
        item["location_name"] = str(row["縣市"])
        item["rain_threshold"] = int(row["降雨門檻 (%)"])
        item["min_temp_threshold"] = float(row["低溫門檻 (°C)"])
        item["max_temp_threshold"] = float(row["高溫門檻 (°C)"])
        cities.append(item)
    return cities, [{"slot": slot, "enabled": bool(enabled)} for slot, enabled in slots.items()]


def set_all_enabled(df: pd.DataFrame, enabled: bool) -> pd.DataFrame:
    """「全部啟用／全部關閉」：只改「啟用」欄，其他設定不動。"""
    return df.assign(**{"啟用": enabled})


class AlertSettingsService:
    """經由資料庫函式讀寫告警設定（密碼在資料庫驗證）。"""

    def __init__(self, client):
        self._sb = client

    def _rpc(self, function: str, params: dict):
        try:
            return self._sb.rpc(function, params).execute().data
        except Exception as exc:  # 用 from None 切斷原例外，避免其內容出現在 traceback
            raise translate_error(exc, params.get("p_password")) from None

    def get_settings(self, password: str) -> tuple[pd.DataFrame, dict[str, bool]]:
        """讀取告警設定。密碼錯誤拋 WrongPassword。回傳 (縣市表格, {發送時段: 是否啟用})。"""
        data = self._rpc("admin_get_alert_settings", {"p_password": password})
        slots = {row["slot"]: bool(row["enabled"]) for row in data["slots"]}
        return to_dataframe(data["cities"]), {slot: slots.get(slot, False) for slot in SLOTS}

    def save_settings(self, password: str, df: pd.DataFrame, slots: dict[str, bool]) -> dict:
        """儲存告警設定。驗證不過拋 AdminError；密碼錯誤拋 WrongPassword。"""
        errors = validate(df, slots)
        if errors:
            raise AdminError("；".join(errors[:5]) + (f"（另有 {len(errors) - 5} 項）" if len(errors) > 5 else ""))
        cities, slot_rows = build_payload(df, slots)
        return self._rpc("admin_save_alert_settings",
                         {"p_password": password, "p_cities": cities, "p_slots": slot_rows})
