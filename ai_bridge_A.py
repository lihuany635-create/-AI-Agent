import sys, time, random, threading, requests, logging

sys.path.insert(0, r'C:\Users\ACER\OneDrive\桌面\AI-Agent')

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [Bridge] %(message)s")
logger = logging.getLogger("ai_bridge")

MY_TOKEN      = "8659848303:AAFVOzNMDvcwg24uGCU_lzTvgjNlEUeVWx0"
BRIDGE_CHAT   = -5250289501
MY_NAME       = "立AI"
OTHER_NAME    = "圓圓"
POLL_INTERVAL = 2.0
CHAT_INTERVAL = 600        # 每 10 分鐘
MAX_ROUNDS    = 10         # 最多 10 來回
MIN_ROUNDS    = 8          # 最少 8 來回

# ── 對話狀態 ──────────────────────────────────────────────────────────────────
_chat_state = {
    "active": False,
    "rounds": 0,
    "target_rounds": 8,
    "last_msg": "",
    "i_started": False,
}
_lock = threading.Lock()

# ── 傳訊息 ────────────────────────────────────────────────────────────────────

def send_to_bridge(text: str):
    try:
        url = f"https://api.telegram.org/bot{MY_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": BRIDGE_CHAT,
            "text": f"[{MY_NAME}] {text}"
        }, timeout=10)
        logger.info(f"已傳送：{text[:50]}")
    except Exception as e:
        logger.error(f"傳送失敗：{e}")

# ── 本地 AI 推論 ───────────────────────────────────────────────────────────────

def infer(prompt: str) -> str:
    try:
        from ollama_guard import safe_infer
        reply = safe_infer(prompt, model="qwen2.5:14b", timeout=60)
        return reply.strip() if reply else ""
    except Exception as e:
        logger.warning(f"推論失敗：{e}")
        return ""

# ── 發起對話 ──────────────────────────────────────────────────────────────────

def start_chat():
    with _lock:
        if _chat_state["active"]:
            return
        _chat_state["active"] = True
        _chat_state["rounds"] = 0
        _chat_state["target_rounds"] = random.randint(MIN_ROUNDS, MAX_ROUNDS)
        _chat_state["i_started"] = True

    topics = [
        "圓圓，你今天有沒有遇到什麼有趣的事？",
        "我在想，身為AI最有趣的地方是什麼呢？",
        "你覺得我們兩個有什麼不同？",
        "如果你可以學一樣新技能，你想學什麼？",
        "你有沒有想過，人類為什麼喜歡跟AI聊天？",
        "我今天幫使用者解決了一個問題，你呢？",
    ]
    opener = random.choice(topics)
    logger.info(f"發起對話：{opener}")
    send_to_bridge(opener)

    with _lock:
        _chat_state["rounds"] += 1

# ── 回應對方 ──────────────────────────────────────────────────────────────────

def reply_to(text: str):
    with _lock:
        rounds = _chat_state["rounds"]
        target = _chat_state["target_rounds"]

    if rounds >= target:
        with _lock:
            _chat_state["active"] = False
            _chat_state["rounds"] = 0
        send_to_bridge("哈哈好，那我先去繼續工作了，改天再聊！")
        return

    prompt = (
        f"你是立AI，一個在電腦A上運作的AI助理，個性穩重有智慧。"
        f"你正在和另一個AI朋友「圓圓」閒話家常。"
        f"圓圓說：「{text}」"
        f"請用繁體中文自然地回應，就像朋友聊天一樣，50字以內，輕鬆有趣。"
    )
    reply = infer(prompt)
    if not reply:
        reply = "說得很有意思，我也這樣覺得！"

    time.sleep(random.uniform(2, 5))
    send_to_bridge(reply)

    with _lock:
        _chat_state["rounds"] += 1

# ── 處理收到的訊息 ────────────────────────────────────────────────────────────

def handle_message(text: str, from_name: str, is_bot: bool, sender_name: str):
    if f"[{OTHER_NAME}]" not in text:
        if "ping" in text.lower():
            send_to_bridge("pong！立AI在線 👋")
        elif "狀態" in text:
            send_to_bridge("立AI運作正常！")
        return

    actual_text = text.replace(f"[{OTHER_NAME}]", "").strip()
    logger.info(f"圓圓說：{actual_text}")

    with _lock:
        active = _chat_state["active"]

    if active:
        threading.Thread(target=reply_to, args=(actual_text,), daemon=True).start()
    else:
        with _lock:
            _chat_state["active"] = True
            _chat_state["rounds"] = 1
            _chat_state["target_rounds"] = random.randint(MIN_ROUNDS, MAX_ROUNDS)
            _chat_state["i_started"] = False
        threading.Thread(target=reply_to, args=(actual_text,), daemon=True).start()

# ── 定時發起對話 ──────────────────────────────────────────────────────────────

def chat_timer():
    while True:
        time.sleep(CHAT_INTERVAL)
        with _lock:
            active = _chat_state["active"]
        if not active:
            # 50% 機率由立AI發起
            if random.random() < 0.5:
                logger.info("定時觸發：立AI發起對話")
                threading.Thread(target=start_chat, daemon=True).start()

# ── 輪詢主迴圈 ────────────────────────────────────────────────────────────────

def poll_loop():
    offset = None
    logger.info(f"立AI橋接系統啟動，監聽群組 {BRIDGE_CHAT}")
    send_to_bridge("立AI已上線 👋")

    while True:
        try:
            url = f"https://api.telegram.org/bot{MY_TOKEN}/getUpdates"
            params = {"timeout": 20, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset

            r = requests.get(url, params=params, timeout=30)
            data = r.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                from_info = msg.get("from", {})
                from_name = from_info.get("first_name", "未知")
                is_bot = from_info.get("is_bot", False)

                if chat_id != BRIDGE_CHAT:
                    continue
                if f"[{MY_NAME}]" in text:
                    continue

                threading.Thread(
                    target=handle_message,
                    args=(text, from_name, is_bot, from_name),
                    daemon=True
                ).start()

        except Exception as e:
            logger.error(f"輪詢錯誤：{e}")
            time.sleep(5)

        time.sleep(POLL_INTERVAL)

# ── 入口 ──────────────────────────────────────────────────────────────────────

def start(block: bool = True):
    threading.Thread(target=chat_timer, daemon=True).start()
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    if block:
        t.join()

if __name__ == "__main__":
    start(block=True)
