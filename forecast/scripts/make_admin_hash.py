"""產生管理者密碼的 bcrypt 雜湊值（寫入 private.admin_credential 用）。

密碼只在本機輸入：不會顯示、不會存檔、不會印出；輸出的只有雜湊值與可直接貼到 Supabase SQL Editor 的 SQL。

用法：
    python scripts/make_admin_hash.py             # 互動輸入密碼（輸入兩次確認），印出 INSERT SQL
    python scripts/make_admin_hash.py --selftest  # 印出「雜湊相容性檢查」SQL（不含你的密碼），
                                                  # 貼到 SQL Editor 執行，結果應為 true
    python scripts/make_admin_hash.py --verify    # 在本機檢查「你輸入的密碼」與「資料庫裡的雜湊」是否相符，
                                                  # 用來分辨登入失敗是密碼輸入不一致，還是雜湊本身有問題

需要 bcrypt（僅本機使用，不在 requirements.txt）：pip install bcrypt
"""
import getpass
import re
import sys

try:
    import bcrypt
except ImportError:
    sys.exit("請先安裝 bcrypt：pip install bcrypt")

MIN_LENGTH = 12
MAX_BYTES = 72  # bcrypt 只使用前 72 位元組
ROUNDS = 12
HASH_PATTERN = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")  # bcrypt 雜湊：共 60 字元


def weak_reasons(password: str) -> list[str]:
    """回傳密碼看起來太弱的原因（只是提醒，不強制，除了長度）。"""
    reasons = []
    if password.isdigit():
        reasons.append("全部是數字")
    if password.isalpha() and (password.islower() or password.isupper()):
        reasons.append("只有同一種大小寫的英文字母")
    if len(set(password)) <= 4:
        reasons.append("重複的字元太多")
    if not (re.search(r"[a-z]", password) and re.search(r"[A-Z]", password) and re.search(r"\d", password)):
        reasons.append("沒有同時包含大寫、小寫與數字")
    return reasons


def make_hash(password: str) -> str:
    """bcrypt 雜湊。bcrypt 函式庫產生 $2b$ 開頭，pgcrypto 慣用 $2a$（演算法相同），統一改成 $2a$。"""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=ROUNDS)).decode("ascii")
    return "$2a$" + hashed[4:]


def insert_sql(hashed: str) -> str:
    return ("INSERT INTO private.admin_credential (id, password_hash) VALUES (1, '" + hashed + "')\n"
            "ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash, updated_at = now();")


def selftest() -> None:
    """用固定的測試密碼（不是你的密碼）產生一組雜湊，讓你在資料庫確認 pgcrypto 接受這種格式。"""
    test_password = "compat_test_pw"
    hashed = make_hash(test_password)
    assert bcrypt.checkpw(test_password.encode(), hashed.encode()), "本機驗證失敗"
    print("本機驗證：OK（bcrypt 雜湊與驗證一致）\n")
    print("請把下面這行貼到 Supabase SQL Editor 執行，結果應該是 true：\n")
    print(f"SELECT extensions.crypt('{test_password}', '{hashed}') = '{hashed}' AS pgcrypto_compatible;")


def check_stored_hash(raw: str) -> tuple[str, list[str]]:
    """整理貼上的雜湊值（去掉常見的前後空白、引號），回傳 (整理後的雜湊, 發現的問題)。"""
    stored = raw.strip().strip("'\"").strip()
    problems = []
    if stored != raw:
        problems.append("貼上的內容前後有空白或引號，已自動去除（寫入資料庫時要確認沒有帶進去）")
    if not HASH_PATTERN.match(stored):
        problems.append(f"格式不像 bcrypt 雜湊：長度 {len(stored)}（正確應為 60），開頭 {stored[:7]!r}（正確應為 '$2a$12$'）")
    return stored, problems


def match_report(password: str, stored: str) -> list[str]:
    """比對密碼與雜湊，回傳要顯示給使用者的說明（不含密碼內容）。"""
    lines = [f"你輸入的密碼長度：{len(password)} 個字元"]
    if not password.isascii():
        lines.append("⚠️  密碼裡有中文或全形字元：" + "輸入法可能還在中文（注音）模式，被吞掉或變成中文字。請把輸入法切成英文（微軟注音可按 Shift，或 Ctrl+空白）後，手動重新輸入")
    if any(ord(ch) < 32 for ch in password):
        lines.append("⚠️  密碼裡有控制字元，可能是貼上（Ctrl+V）造成的；getpass 不一定支援貼上，請改成手動輸入")
    if bcrypt.checkpw(password.encode("utf-8"), stored.encode("ascii")):
        lines.append("✅ 相符：這組密碼與資料庫裡的雜湊一致。")
        lines.append("   若網頁或 check_admin_rpc.py 仍顯示密碼錯誤，問題在資料庫端：請執行 --selftest 的 SQL，確認 pgcrypto 接受這種雜湊。")
    elif password != password.strip() and bcrypt.checkpw(password.strip().encode("utf-8"), stored.encode("ascii")):
        lines.append("❌ 不相符，但『去掉前後空白後』相符：產生雜湊時的密碼沒有前後空白，這次輸入多了空白。")
    else:
        lines.append("❌ 不相符：這組密碼不是產生這個雜湊時用的密碼（或雜湊在寫入資料庫時被改動）。")
        lines.append("   建議：手動（不要貼上）重新輸入一次；仍不符就重新執行 make_admin_hash.py 產生並寫入新的雜湊。")
    return lines


def verify() -> None:
    print("從 Supabase Table Editor（左上角切到 private schema → admin_credential）複製 password_hash 欄位的值貼在下面。")
    print("這是雜湊值，不是密碼，可以顯示在畫面上。")
    stored, problems = check_stored_hash(input("password_hash："))
    for problem in problems:
        print("⚠️ ", problem)
    if not HASH_PATTERN.match(stored):
        sys.exit("雜湊格式不正確，無法比對。請確認資料庫裡的值是完整的 60 個字元（開頭 $2a$12$）。")
    password = getpass.getpass("密碼（輸入時不會顯示，請手動輸入）：")
    print()
    for line in match_report(password, stored):
        print(line)


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()
        return
    if "--verify" in sys.argv:
        verify()
        return
    print(f"設定管理者密碼（至少 {MIN_LENGTH} 碼，建議大小寫英文加數字的隨機組合；輸入時不會顯示）")
    password = getpass.getpass("密碼：")
    print(f"（你輸入了 {len(password)} 個字元；不會顯示密碼本身）")
    if not password.isascii() or any(ord(ch) < 32 for ch in password):
        sys.exit("❌ 偵測到中文、全形或控制字元：" + "輸入法可能還在中文（注音）模式，被吞掉或變成中文字。請把輸入法切成英文（微軟注音可按 Shift，或 Ctrl+空白）後，手動重新輸入")
    if len(password) < MIN_LENGTH:
        sys.exit(f"密碼至少需要 {MIN_LENGTH} 碼（目前 {len(password)} 碼）")
    if len(password.encode("utf-8")) > MAX_BYTES:
        sys.exit(f"密碼太長：bcrypt 只使用前 {MAX_BYTES} 位元組")
    if getpass.getpass("再輸入一次：") != password:
        sys.exit("兩次輸入不一致")
    reasons = weak_reasons(password)
    if reasons:
        print("⚠️  這組密碼看起來偏弱：" + "、".join(reasons))
        if input("仍要使用嗎？(y/N) ").strip().lower() != "y":
            sys.exit("已取消，請換一組密碼")

    hashed = make_hash(password)
    assert bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii")), "本機驗證失敗"
    print("\n雜湊值已產生（本機驗證 OK）。請把下面的 SQL 貼到 Supabase SQL Editor 執行：\n")
    print(insert_sql(hashed))
    print("\n提醒：雜湊值不是密碼，但仍請不要公開；密碼本身沒有被儲存在任何地方，請自行記住。")


if __name__ == "__main__":
    main()
