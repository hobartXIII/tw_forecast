"""查詢你的 Telegram chat_id（設定 TELEGRAM_CHAT_ID 用）。

前置：
1. 向 @BotFather 建立機器人，把 token 寫入 .env 的 TELEGRAM_BOT_TOKEN。
2. 在 Telegram 打開你的機器人，按 Start（或隨便傳一則訊息）——機器人必須先被你啟動才能傳訊息給你。

用法：
    python tools/get_telegram_chat_id.py            # 列出找到的對話
    python tools/get_telegram_chat_id.py --write    # 只有一個私訊對話時，把 TELEGRAM_CHAT_ID 寫入 .env

token 只從本機 .env 讀取，不會被印出。
"""
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("請先在 .env 設定 TELEGRAM_BOT_TOKEN")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15)
    except requests.RequestException as exc:  # 例外訊息含網址（token），只印類型
        sys.exit(f"無法連線至 Telegram（{type(exc).__name__}）")
    if resp.status_code == 401:
        sys.exit("Telegram 回應 401：token 不正確，請確認 .env 的 TELEGRAM_BOT_TOKEN")
    if resp.status_code != 200:
        sys.exit(f"Telegram 回應 {resp.status_code}")

    chats: dict[int, dict] = {}
    for update in resp.json().get("result", []):
        chat = (update.get("message") or update.get("my_chat_member") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat
    if not chats:
        sys.exit("還沒有找到對話。請在 Telegram 打開你的機器人，按 Start（或傳任何訊息），再執行一次。")

    print("找到的對話：")
    for chat_id, chat in chats.items():
        who = " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")])) or chat.get("title", "")
        print(f"  chat_id={chat_id}  類型={chat.get('type')}  名稱={who}  帳號=@{chat.get('username', '—')}")

    if "--write" in sys.argv:
        private = [i for i, c in chats.items() if c.get("type") == "private"]
        if len(private) != 1:
            sys.exit("--write 需要剛好一個私訊對話，請手動把 TELEGRAM_CHAT_ID 寫進 .env")
        if os.getenv("TELEGRAM_CHAT_ID"):
            sys.exit(".env 已有 TELEGRAM_CHAT_ID，未覆寫")
        with ENV_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\nTELEGRAM_CHAT_ID={private[0]}\n")
        print(f"已把 TELEGRAM_CHAT_ID={private[0]} 寫入 .env")


if __name__ == "__main__":
    main()
