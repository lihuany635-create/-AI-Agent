# test_telegram.py — Telegram 連線診斷
import sys
sys.path.insert(0, r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages")

import requests
import bot_config

TOKEN   = bot_config.TELEGRAM_TOKEN
CHAT_ID = bot_config.ALLOWED_CHAT_IDS[0]

print(f"Token：{TOKEN[:20]}...")
print(f"Chat ID：{CHAT_ID}")

# 1. 測試能否連到 Telegram API
print("\n── 測試 1：連線到 Telegram API ──")
try:
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=10)
    data = r.json()
    if data.get("ok"):
        bot = data["result"]
        print(f"✅ Bot 連線正常")
        print(f"   Bot 名稱：{bot.get('first_name')}")
        print(f"   Bot username：@{bot.get('username')}")
    else:
        print(f"❌ API 回應錯誤：{data}")
except Exception as e:
    print(f"❌ 連線失敗：{e}")

# 2. 測試發送通知
print("\n── 測試 2：發送通知到手機 ──")
try:
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": "🔔 測試通知：連線正常，claude_desktop_bridge 可以發送通知"},
        timeout=10
    )
    data = r.json()
    if data.get("ok"):
        print(f"✅ 通知發送成功，訊息 ID：{data['result']['message_id']}")
    else:
        print(f"❌ 發送失敗：{data}")
except Exception as e:
    print(f"❌ 發送失敗：{e}")

# 3. 確認 Chat ID 是否正確
print("\n── 測試 3：確認 Chat ID ──")
try:
    r = requests.get(
        f"https://api.telegram.org/bot{TOKEN}/getUpdates",
        timeout=10
    )
    updates = r.json().get("result", [])
    if updates:
        last = updates[-1]
        chat = last.get("message", {}).get("chat", {})
        print(f"最近一則訊息的 Chat ID：{chat.get('id')}")
        print(f"設定的 Chat ID：{CHAT_ID}")
        print(f"{'✅ 相符' if chat.get('id') == CHAT_ID else '❌ 不相符！'}")
    else:
        print("沒有收到任何更新（可能 Bot 還沒收過訊息）")
except Exception as e:
    print(f"❌ 失敗：{e}")
