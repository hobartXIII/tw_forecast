"""驗證 RLS：用前端的公開金鑰 (anon / publishable) 確認「可讀、不可寫」。

需要 .env：SUPABASE_URL、SUPABASE_ANON_KEY (公開金鑰)、SUPABASE_KEY (後端金鑰，用於驗證與還原)。
寫入測試使用不存在於預報中的假資料 (縣市 "__rls_test__")；若 RLS 失效導致寫入成功，
會用後端金鑰 SUPABASE_KEY 刪除該測試列並回報失敗。

用法：python scripts/check_rls.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

URL = os.getenv("SUPABASE_URL")
ANON = os.getenv("SUPABASE_ANON_KEY")
SECRET = os.getenv("SUPABASE_KEY")
TABLE = "weather_forecasts"
TEST_ROW = {"location_name": "__rls_test__",
            "forecast_time_start": "2000-01-01T00:00:00+00:00",
            "forecast_time_end": "2000-01-01T06:00:00+00:00"}

if not (URL and ANON):
    sys.exit("請在 .env 補上 SUPABASE_ANON_KEY (Supabase 的 publishable / anon 公開金鑰)")
if ANON == SECRET:
    sys.exit("SUPABASE_ANON_KEY 與 SUPABASE_KEY 相同：前端金鑰不可使用後端 secret key")

anon = create_client(URL, ANON)
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("✅" if ok else "❌"), name, detail)


# 1. 讀取應成功
try:
    r = anon.table(TABLE).select("*", count="exact").limit(1).execute()
    check("anon 可讀取", r.count is not None and r.count > 0, f"(總列數 {r.count})")
except Exception as exc:
    check("anon 可讀取", False, f"({exc})")

# 2. 新增應被拒絕
try:
    anon.table(TABLE).insert(TEST_ROW).execute()
    check("anon 新增被拒絕", False, "(新增竟然成功！)")
    create_client(URL, SECRET).table(TABLE).delete().eq("location_name", "__rls_test__").execute()
except Exception as exc:
    check("anon 新增被拒絕", True, f"({getattr(exc, 'code', type(exc).__name__)})")

# 3. 更新 / 刪除：只針對一列專用測試資料，避免 RLS 失效時波及真實預報。
#    RLS 下不可見的列，操作會影響 0 列而非報錯，因此改用後端金鑰檢查該測試列是否被動過。
admin = create_client(URL, SECRET)
admin.table(TABLE).upsert({**TEST_ROW, "weather_condition": "original"},
                          on_conflict="location_name,forecast_time_start,forecast_time_end").execute()
match = {"location_name": TEST_ROW["location_name"], "forecast_time_start": TEST_ROW["forecast_time_start"]}


def test_row():
    q = admin.table(TABLE).select("weather_condition")
    for k, v in match.items():
        q = q.eq(k, v)
    return q.execute().data


try:
    q = anon.table(TABLE).update({"weather_condition": "hacked"})
    for k, v in match.items():
        q = q.eq(k, v)
    q.execute()
except Exception:
    pass
rows = test_row()
check("anon 更新被拒絕", bool(rows) and rows[0]["weather_condition"] == "original")

try:
    q = anon.table(TABLE).delete()
    for k, v in match.items():
        q = q.eq(k, v)
    q.execute()
except Exception:
    pass
check("anon 刪除被拒絕", len(test_row()) == 1)

admin.table(TABLE).delete().eq("location_name", TEST_ROW["location_name"]).execute()  # 清除測試列

# 4. pipeline_status（手動更新門檻用）：anon 可讀、不可改、不可刪。
#    以 schedule 那一列做測試；若 RLS 失效導致被改動，會用後端金鑰還原。
STATUS = "pipeline_status"
try:
    r = anon.table(STATUS).select("*").execute()
    check("anon 可讀取 pipeline_status", len(r.data) > 0, f"(共 {len(r.data)} 列)")
except Exception as exc:
    check("anon 可讀取 pipeline_status", False, f"({exc}) 請先在 Supabase 執行 sql/init_supabase.sql")
else:
    def status_row():
        return admin.table(STATUS).select("*").eq("trigger_type", "schedule").execute().data

    before = status_row()
    try:
        anon.table(STATUS).update({"last_error": "hacked"}).eq("trigger_type", "schedule").execute()
    except Exception:
        pass
    after = status_row()
    check("anon 更新 pipeline_status 被拒絕", after == before)
    if after != before and before:
        admin.table(STATUS).upsert(before[0], on_conflict="trigger_type").execute()  # 還原

    try:
        anon.table(STATUS).delete().eq("trigger_type", "schedule").execute()
    except Exception:
        pass
    deleted = not status_row() and bool(before)
    check("anon 刪除 pipeline_status 被拒絕", not deleted)
    if deleted:
        admin.table(STATUS).upsert(before[0], on_conflict="trigger_type").execute()  # 還原

print()
print("RLS 驗證通過 ✅" if all(results) else "RLS 驗證失敗 ❌，請檢查 sql/init_supabase.sql 的 policy")
sys.exit(0 if all(results) else 1)
