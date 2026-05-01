import sys, time
import threading
import requests
import logging

sys.path.insert(0, r'C:\Users\ACER\OneDrive\桌面\AI-Agent')

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [Bridge] %(message)s")
logger = logging.getLogger("ai_bridge")

MY_TOKEN     = "8659848303:AAFVOzNMDvcwg24uGCU_lzTvgjNlEUeVWx0"
BRIDGE_CHAT  = -5250289501
MY_NAME      = "立AI"
POLL_INTERVAL = 2.0

def send_to_bridge(text: str):
    try:
        url = f"https://api.telegram.org/bot{MY_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": BRIDGE_CHAT, "text": f"[{MY_NAME}] {text}"}, timeout=10)
        logger.info(f"已傳送：{text[:50]}")
    except Exception as e:
        logger.error(f"傳送失敗：{e}")

def handle_message(text: str, from_name: str):
    logger.info(f"收到來自 {from_name} 的訊息：{text}")
    if text.strip().lower() == "ping":
        send_to_bridge("pong！立AI在線上。")
        return
    if "狀態" in text:
        send_to_bridge("立AI運作正常，Ollama 在線。")
        return
    try:
        from ollama_guard import safe_infer
        reply = safe_infer(f"你是立AI，電腦A上的本地AI助理。請用繁體中文回答。\n\n用戶說：{text}", model="qwen2.5:14b", timeout=180)
        if reply:
            send_to_bridge(reply[:500])
    except Exception as e:
        logger.warning(f"本地 AI 處理失敗：{e}")

def poll_loop():
    offset = None
    logger.info(f"橋接系統啟動，監聽群組 {BRIDGE_CHAT}")
    send_to_bridge("立AI已上線，準備接收指令。")
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
                if is_bot:
                    continue
                if f"[{MY_NAME}]" in text:
                    continue
                threading.Thread(target=handle_message, args=(text, from_name), daemon=True).start()
        except Exception as e:
            logger.error(f"輪詢錯誤：{e}")
            time.sleep(5)
        time.sleep(POLL_INTERVAL)

def start(block: bool = True):
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    if block:
        t.join()

if __name__ == "__main__":
    start(block=True)
