"""驗證管理者設定功能（第 2 階段）。以前端使用的 anon 金鑰呼叫資料庫函式，模擬真實使用情況。

需要 .env：SUPABASE_URL、SUPABASE_ANON_KEY；SUPABASE_KEY（後端金鑰，只用來在測試前後比對設定有沒有被改動）。

用法：
    python scripts/check_admin_rpc.py               # 完整測試（會要你輸入管理者密碼，驗證登入成功與儲存）
    python scripts/check_admin_rpc.py --skip-login  # 只測不需要密碼的部分（錯誤密碼被擋、anon 碰不到密碼表）

測試「儲存」時只會寫入與目前完全相同的值，不會改變任何設定；最後會比對整份設定確認沒有被動過。
密碼只用 getpass 讀取，不顯示、不存檔。
"""
import getpass
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

URL, ANON, SECRET = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"), os.getenv("SUPABASE_KEY")
if not (URL and ANON):
    sys.exit("請在 .env 設定 SUPABASE_URL 與 SUPABASE_ANON_KEY")
if ANON == SECRET:
    sys.exit("SUPABASE_ANON_KEY 與 SUPABASE_KEY 相同：前端金鑰不可使用後端金鑰")

anon = create_client(URL, ANON)
admin = create_client(URL, SECRET) if SECRET else None
results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(("✅" if ok else "❌"), name, detail)


def snapshot():
    """以後端金鑰讀取整份設定（排除 updated_at），用來確認測試沒有改動任何設定。"""
    if admin is None:
        return None
    strip = lambda rows: sorted(({k: v for k, v in r.items() if k != "updated_at"} for r in rows),
                                key=lambda r: str(r.get("location_name") or r.get("slot")))
    return (strip(admin.table("alert_city_settings").select("*").execute().data),
            strip(admin.table("alert_slot_settings").select("*").execute().data))


def call(function: str, **params):
    """回傳 (成功?, 資料或錯誤訊息, 耗時秒數)。"""
    started = time.time()
    try:
        return True, anon.rpc(function, params).execute().data, time.time() - started
    except APIError as exc:
        return False, f"{exc.code}:{exc.message}", time.time() - started


def main() -> None:
    before = snapshot()
    if before is None:
        print("⚠️  沒有 SUPABASE_KEY，無法比對測試前後的設定是否被改動\n")

    ok, message, _ = call("admin_get_alert_settings", p_password="probe")
    if not ok and "PGRST202" in message:
        sys.exit("資料庫函式不存在：請先在 Supabase SQL Editor 執行 sql/init_supabase.sql")

    print("--- 不需要密碼的檢查（錯誤密碼一律被擋）")
    ok, message, took = call("admin_get_alert_settings", p_password="definitely-wrong-password")
    check("錯誤密碼讀取被拒絕", not ok and "invalid_password" in message, f"({message})")
    check("錯誤密碼延遲約 1 秒（讓連續猜測變慢）", took >= 0.9, f"(耗時 {took:.1f} 秒)")
    ok, message, _ = call("admin_get_alert_settings", p_password="")
    check("空密碼被拒絕", not ok and "invalid_password" in message)
    ok, message, _ = call("admin_get_alert_settings", p_password=None)
    check("NULL 密碼被拒絕", not ok and "invalid_password" in message)
    ok, message, _ = call("admin_get_alert_settings", p_password="' OR 1=1 --")
    check("SQL 注入字串當作密碼被拒絕", not ok and "invalid_password" in message)
    ok, message, _ = call("admin_save_alert_settings", p_password="wrong", p_cities=[], p_slots=[])
    check("錯誤密碼儲存被拒絕", not ok and "invalid_password" in message)
    ok, message, _ = call("admin_save_alert_settings", p_password="wrong",
                          p_cities=[{"location_name": "臺北市", "enabled": True, "rain_enabled": True, "rain_threshold": 0,
                                     "min_temp_enabled": True, "min_temp_threshold": 12, "max_temp_enabled": True,
                                     "max_temp_threshold": 35}], p_slots=[{"slot": "08:45", "enabled": False}])
    check("錯誤密碼帶著真實內容儲存也被拒絕（設定不會被改）", not ok and "invalid_password" in message)
    try:
        rows = anon.schema("private").table("admin_credential").select("*").execute().data
        leaked = len(rows) > 0
    except Exception:
        leaked = False  # private schema 不對 API 開放，被拒絕才是正確的
    check("anon 讀不到密碼表（private schema 不對 API 開放）", not leaked)

    if "--skip-login" not in sys.argv:
        print("\n--- 需要管理者密碼的檢查（密碼只用於本次測試，不顯示、不存檔）")
        password = getpass.getpass("管理者密碼（請先確認輸入法是英文模式）：")
        print(f"（你輸入了 {len(password)} 個字元；不會顯示密碼本身）")
        if not password.isascii() or any(ord(ch) < 32 for ch in password):
            sys.exit("❌ 偵測到中文或控制字元：" + "輸入法可能還在中文（注音）模式，被吞掉或變成中文字。請把輸入法切成英文（微軟注音可按 Shift，或 Ctrl+空白）後，手動重新輸入")
        ok, data, _ = call("admin_get_alert_settings", p_password=password)
        check("正確密碼可讀取設定", ok and len(data["cities"]) == 22 and len(data["slots"]) == 3,
              f"({len(data['cities'])} 縣市、{len(data['slots'])} 時段)" if ok else f"({data})")
        if ok:
            keep = ("location_name", "enabled", "rain_enabled", "rain_threshold", "min_temp_enabled",
                    "min_temp_threshold", "max_temp_enabled", "max_temp_threshold")
            cities = [{k: c[k] for k in keep} for c in data["cities"]]
            slots = [{"slot": s["slot"], "enabled": s["enabled"]} for s in data["slots"]]
            ok2, res, _ = call("admin_save_alert_settings", p_password=password, p_cities=cities, p_slots=slots)
            check("正確密碼儲存（寫入相同的值）成功", ok2 and res == {"cities": 22, "slots": 3}, f"({res})")

            bad = [dict(cities[0], rain_threshold=999)] + cities[1:]
            ok3, res, _ = call("admin_save_alert_settings", p_password=password, p_cities=bad, p_slots=slots)
            check("不合法的門檻（降雨 999）被資料庫拒絕", not ok3, f"({res})")

            ghost = cities + [dict(cities[0], location_name="不存在的縣市", enabled=True)]
            ok4, res, _ = call("admin_save_alert_settings", p_password=password, p_cities=ghost, p_slots=slots)
            count = len(anon.rpc("admin_get_alert_settings", {"p_password": password}).execute().data["cities"])
            check("不能新增縣市（多出來的縣市被忽略，仍為 22 列）", ok4 and res["cities"] == 22 and count == 22, f"({res})")

            ok5, res, _ = call("admin_save_alert_settings", p_password=password, p_cities="not-an-array", p_slots=slots)
            check("格式錯誤（非陣列）被拒絕", not ok5, f"({res})")

    after = snapshot()
    if before is not None:
        check("測試前後整份設定完全相同（沒有被改動）", before == after)

    print()
    print("管理者設定功能驗證通過 ✅" if all(results) else "驗證失敗 ❌，請檢查上面標示的項目")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
