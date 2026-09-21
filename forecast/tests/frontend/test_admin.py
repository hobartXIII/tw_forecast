"""告警設定的資料層：錯誤轉換（不洩漏密碼）、表格驗證與轉換、經由資料庫函式讀寫。"""
import pandas as pd
import pytest

from fakes import FakeClient
from tw_forecast.frontend import admin
from tw_forecast.frontend.admin import AdminError, AlertSettingsService, NotConfigured, WrongPassword

PASSWORD = "S3cret-Password!"


def db_city(name="臺北市", **kw):
    row = {"location_name": name, "enabled": True, "rain_enabled": True, "rain_threshold": 60,
           "min_temp_enabled": True, "min_temp_threshold": 12, "max_temp_enabled": True, "max_temp_threshold": 35}
    row.update(kw)
    return row


def rpc_data(cities=None):
    return {"cities": cities if cities is not None else [db_city("臺中市"), db_city("臺北市")],
            "slots": [{"slot": "08:45", "enabled": True}, {"slot": "14:45", "enabled": False}]}


class DbError(Exception):
    def __init__(self, message="", code="", details="", hint=""):
        super().__init__(message)
        self.message, self.code, self.details, self.hint = message, code, details, hint


# ---------- 錯誤轉換 ----------
def test_invalid_password_error():
    assert isinstance(admin.translate_error(DbError("invalid_password"), PASSWORD), WrongPassword)


@pytest.mark.parametrize("exc", [DbError(code="PGRST202"), DbError(code="42883"),
                                 DbError("Could not find the function public.x")])
def test_missing_function_error(exc):
    assert isinstance(admin.translate_error(exc, PASSWORD), NotConfigured)


def test_other_errors_mask_the_password_and_are_truncated():
    err = admin.translate_error(DbError(f"boom {PASSWORD} " + "x" * 400), PASSWORD)
    assert PASSWORD not in str(err) and "***" in str(err) and len(str(err)) <= 200


# ---------- 表格轉換 ----------
def test_to_dataframe_sorts_by_city_order_and_types_columns():
    df = admin.to_dataframe([db_city("臺中市"), db_city("臺北市"), db_city("澎湖縣")])
    assert df["縣市"].tolist() == ["臺北市", "臺中市", "澎湖縣"]
    assert df["降雨門檻 (%)"].dtype.kind == "i" and df["低溫門檻 (°C)"].dtype.kind == "f"
    assert df["啟用"].dtype == bool


def sample_df():
    return admin.to_dataframe([db_city("臺北市"), db_city("新北市")])


def test_validate_accepts_defaults():
    assert admin.validate(sample_df(), {"08:45": True}) == []


@pytest.mark.parametrize("column, value, fragment", [
    ("降雨門檻 (%)", 101, "必須介於 0 到 100"),
    ("低溫門檻 (°C)", -21, "必須介於 -20 到 50"),
    ("高溫門檻 (°C)", None, "不可空白"),
    ("降雨門檻 (%)", 60.5, "必須是整數"),
])
def test_validate_rejects_bad_thresholds(column, value, fragment):
    df = sample_df().astype({column: "object"})
    df.loc[0, column] = value
    assert any(fragment in e for e in admin.validate(df, {}))


def test_validate_rejects_duplicates_missing_columns_and_bad_slots():
    df = sample_df()
    df.loc[1, "縣市"] = "臺北市"
    assert "縣市重複" in admin.validate(df, {})
    assert admin.validate(df.drop(columns=["啟用"]), {})[0].startswith("缺少欄位")
    assert admin.validate(sample_df(), {"09:00": True}) == ["發送時段設定不合法"]


def test_build_payload_uses_native_types():
    cities, slots = admin.build_payload(sample_df(), {"08:45": True, "14:45": False})
    assert cities[0] == db_city("臺北市", min_temp_threshold=12.0, max_temp_threshold=35.0)
    assert type(cities[0]["rain_threshold"]) is int and type(cities[0]["enabled"]) is bool
    assert slots == [{"slot": "08:45", "enabled": True}, {"slot": "14:45", "enabled": False}]


def test_set_all_enabled_only_changes_enabled_column():
    df = sample_df()
    off = admin.set_all_enabled(df, False)
    assert not off["啟用"].any() and off.drop(columns="啟用").equals(df.drop(columns="啟用"))
    assert df["啟用"].all()  # 不改動原表格


# ---------- 服務（經由資料庫函式） ----------
def test_get_settings_returns_table_and_all_three_slots():
    client = FakeClient(rpc_results={"admin_get_alert_settings": rpc_data()})
    df, slots = AlertSettingsService(client).get_settings(PASSWORD)
    assert df["縣市"].tolist() == ["臺北市", "臺中市"]
    assert slots == {"08:45": True, "14:45": False, "20:45": False}  # 沒列出的時段視為關閉
    assert client.rpc_calls == [("admin_get_alert_settings", {"p_password": PASSWORD})]


def test_get_settings_wrong_password():
    client = FakeClient(rpc_results={"admin_get_alert_settings": DbError("invalid_password")})
    with pytest.raises(WrongPassword) as exc:
        AlertSettingsService(client).get_settings(PASSWORD)
    assert exc.value.__cause__ is None and PASSWORD not in str(exc.value)


def test_save_settings_validates_before_calling_database():
    client = FakeClient(rpc_results={"admin_save_alert_settings": {"ok": True}})
    df = sample_df()
    df.loc[0, "降雨門檻 (%)"] = 999
    with pytest.raises(AdminError, match="必須介於"):
        AlertSettingsService(client).save_settings(PASSWORD, df, {"08:45": True})
    assert client.rpc_calls == []


def test_save_settings_sends_payload():
    client = FakeClient(rpc_results={"admin_save_alert_settings": {"ok": True}})
    result = AlertSettingsService(client).save_settings(PASSWORD, sample_df(), {"08:45": True})
    (name, params), = client.rpc_calls
    assert result == {"ok": True} and name == "admin_save_alert_settings"
    assert params["p_password"] == PASSWORD and len(params["p_cities"]) == 2 and params["p_slots"][0]["slot"] == "08:45"


def test_many_validation_errors_are_summarised():
    df = sample_df()
    df["降雨門檻 (%)"] = 999
    df = pd.concat([df] * 4, ignore_index=True).assign(縣市=lambda d: [f"縣市{i}" for i in range(len(d))])
    with pytest.raises(AdminError, match="另有"):
        AlertSettingsService(FakeClient()).save_settings(PASSWORD, df, {})
