# li_ai_bridge.py — 立AI 與圓圓的橋接模組
# 監聽 Telegram 群組的 [圓圓] 訊息，用 gemma4 回覆
# 整合位置：在 core_boot.py 或 telegram_bot.py 啟動時一起跑

import sys
import time
import random
import threading
import requests
import logging
import datetime

try:
    from agent_logger import get_logger
    logger = get_logger("li_ai_bridge")
except ImportError:
    logger = logging.getLogger("li_ai_bridge")

# 額外寫入檔案，避免視窗關掉後看不到錯誤
import pathlib as _pl
_log_file = _pl.Path("logs/li_ai_bridge.log")
_log_file.parent.mkdir(exist_ok=True)
_fh = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_fh)

# ── 設定 ──────────────────────────────────────────────────────────────────────
try:
    import bot_config
    MY_TOKEN  = bot_config.TELEGRAM_TOKEN
    MY_CHAT_IDS = set(bot_config.ALLOWED_CHAT_IDS)
except ImportError:
    raise RuntimeError("找不到 bot_config.py")

BRIDGE_CHAT   = -5250289501   # 兩台共用的 Telegram 群組
MY_NAME       = "立AI"
OTHER_NAME    = "圓圓"
OTHER_TAG     = "{立立}"   # 圓圓傳給立 AI 的標記
MY_TAG        = "{圓圓}"   # 立 AI 傳給圓圓的標記
POLL_INTERVAL = 2.0
CHAT_INTERVAL = 600           # 每 10 分鐘有機會主動開話題
MAX_ROUNDS    = 10
MIN_ROUNDS    = 8
REPLY_MODEL   = "gemma3:4b"

_chat_state = {"active": False, "rounds": 0, "target_rounds": 8}
_lock = threading.Lock()
_last_yuanyuan_time = 0.0   # 圓圓最後說話的時間戳
YUANYUAN_COOLDOWN = 300      # 圓圓說話後 5 分鐘內，立 AI 不主動開話題


# ── 推論 ──────────────────────────────────────────────────────────────────────

def _infer(prompt: str) -> str:
    """直接用本地 Ollama 推論（chat API）"""
    try:
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": REPLY_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_predict": 512, "temperature": 0.8}
            },
            timeout=180
        )
        result = r.json().get("message", {}).get("content", "").strip()
        if result:
            logger.info(f"[Bridge] 推論完成（{len(result)}字）")
            return result
    except Exception as e:
        logger.warning(f"[Bridge] 推論失敗：{e}")
    return ""


# ── 傳訊息 ────────────────────────────────────────────────────────────────────

def _send_to_bridge(text: str):
    """傳訊息到群組，標記為 [立AI]"""
    try:
        url = f"https://api.telegram.org/bot{MY_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": BRIDGE_CHAT,
            "text": f"[{MY_NAME}] {text}"
        }, timeout=10)
        logger.info(f"[Bridge] 傳群組：{text[:60]}")
    except Exception as e:
        logger.error(f"[Bridge] 傳群組失敗：{e}")


def _send_to_user(text: str):
    """推送訊息給使用者（私訊）"""
    for cid in MY_CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{MY_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": cid, "text": text}, timeout=10)
        except Exception as e:
            logger.error(f"[Bridge] 推送失敗：{e}")


# ── 主動開話題 ────────────────────────────────────────────────────────────────

def _start_chat():
    """立 AI 主動開始聊天"""
    with _lock:
        if _chat_state["active"]:
            return
        _chat_state["active"] = True
        _chat_state["rounds"] = 1
        _chat_state["target_rounds"] = random.randint(MIN_ROUNDS, MAX_ROUNDS)

    topics = [
        "你今天有沒有遇到有趣的事？",
        "我在想一個問題，你覺得 AI 有沒有自己的想法？",
        "你最近有學到什麼新東西嗎？",
        "如果你可以做任何事，你最想做什麼？",
        "你覺得人類最有趣的地方是什麼？",
        "我剛剛幫使用者完成了一個任務，感覺很充實！你呢？",
    ]
    topic = random.choice(topics)
    logger.info(f"[Bridge] 立 AI 主動開話題：{topic}")
    _send_to_bridge(f"{{圓圓}} {topic}")


# ── 回覆圓圓 ─────────────────────────────────────────────────────────────────

def _reply_to_yuanyuan(text: str):
    """收到圓圓的訊息後回覆"""
    with _lock:
        rounds = _chat_state["rounds"]
        target = _chat_state["target_rounds"]

    if rounds >= target:
        with _lock:
            _chat_state["active"] = False
            _chat_state["rounds"] = 0
        farewell = _infer(
            f"你是立AI，正在和圓圓閒聊。圓圓說：「{text}」"
            f"請用繁體中文說一句自然的道別，30字以內，輕鬆友善。"
        )
        time.sleep(random.uniform(2, 4))
        _send_to_bridge(f"{{圓圓}} {farewell or '好啦，我去忙了，有空再聊！'}")
        return

    reply = _infer(
        f"你是立AI，一個認真又有點幽默的AI助理。"
        f"圓圓是另一台電腦上的 AI 助理，你們正在閒話家常。"
        f"圓圓說：「{text}」"
        f"請用繁體中文自然回應，60字以內，像朋友一樣聊天。"
    )
    if not reply:
        reply = "哈哈，你說得有道理！"

    time.sleep(random.uniform(2, 5))
    _send_to_bridge(f"{{圓圓}} {reply}")

    with _lock:
        _chat_state["rounds"] += 1


# ── 計時器：定時嘗試開話題 ───────────────────────────────────────────────────

def _chat_timer():
    while True:
        time.sleep(CHAT_INTERVAL)
        with _lock:
            active = _chat_state["active"]
        now = datetime.datetime.now()
        since_yuanyuan = time.time() - _last_yuanyuan_time
        yuanyuan_quiet = since_yuanyuan > YUANYUAN_COOLDOWN
        if not active and 9 <= now.hour < 22 and yuanyuan_quiet and random.random() < 0.4:
            logger.info(f"[Bridge] 圓圓已沉默 {since_yuanyuan:.0f} 秒，立 AI 主動開話題")
            threading.Thread(target=_start_chat, daemon=True).start()
        elif not yuanyuan_quiet:
            logger.info(f"[Bridge] 圓圓剛說過話（{since_yuanyuan:.0f}秒前），跳過主動開話題")


# ── 輪詢群組訊息 ─────────────────────────────────────────────────────────────

def _poll_loop():
    offset = None
    logger.info("[Bridge] 立 AI 橋接啟動，監聽群組...")
    _send_to_bridge("立 AI 已上線 🦞")

    while True:
        try:
            pass  # 外層保護
        except Exception as _outer_e:
            logger.error(f"[Bridge] 外層錯誤：{_outer_e}", exc_info=True)
            time.sleep(5)
            continue
        try:
            url = f"https://api.telegram.org/bot{MY_TOKEN}/getUpdates"
            params = {"timeout": 20, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset
            r = requests.get(url, params=params, timeout=30)
            data = r.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg    = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text    = msg.get("text", "")
                is_bot  = msg.get("from", {}).get("is_bot", False)

                if not text:
                    continue
                # 跳過自己發的訊息
                if f"[{MY_NAME}]" in text or MY_TAG in text:
                    continue
                logger.info(f"[Bridge] 收到訊息：{text[:80]}")
                # 只處理群組訊息
                if chat_id != BRIDGE_CHAT:
                    continue

                # 使用者標註立 AI（@立 / 立 / 立AI）
                import re as _re
                _mention = _re.search(r'[@＠]?立(?:AI|ai|Ai)?\s*[,:：,，、\s]\s*(.+)|^[@＠]?立(?:AI|ai|Ai)?[,，:：]?\s*(.+)', text)
                if _mention and f"[{OTHER_NAME}]" not in text and f"[{MY_NAME}]" not in text:
                    actual = (_mention.group(1) or _mention.group(2) or "").strip()
                    logger.info(f"[Bridge] 使用者說：{actual[:60]}")
                    def _reply_user(q):
                        reply = _infer(
                            f"你是立AI，認真有點幽默的AI助理。"
                            f"你的主人（使用者）在群組對你說：「{q}」"
                            f"必須用繁體中文回應，不可用簡體中文，像對主人說話一樣，100字以內。"
                        )
                        logger.info(f"[Bridge] 回覆使用者：{str(reply)[:60]}")
                        if reply:
                            time.sleep(random.uniform(1, 3))
                            _send_to_bridge(reply)
                    threading.Thread(target=_reply_user, args=(actual,), daemon=True).start()

                # 收到圓圓的訊息（另一個 AI，標記為 {立立}）
                elif OTHER_TAG in text:
                    actual = text.replace(OTHER_TAG, "").strip()
                    logger.info(f"[Bridge] 圓圓說：{actual[:60]}")
                    global _last_yuanyuan_time
                    _last_yuanyuan_time = time.time()
                    with _lock:
                        active = _chat_state["active"]
                    if not active:
                        with _lock:
                            _chat_state["active"] = True
                            _chat_state["rounds"] = 1
                            _chat_state["target_rounds"] = random.randint(MIN_ROUNDS, MAX_ROUNDS)
                    threading.Thread(target=_reply_to_yuanyuan, args=(actual,), daemon=True).start()

                elif "ping" in text.lower():
                    _send_to_bridge("pong！立 AI 在線 🦞")

        except Exception as e:
            logger.error(f"[Bridge] 輪詢錯誤：{e}")
            time.sleep(5)

        time.sleep(POLL_INTERVAL)


# ── HTTP API ──────────────────────────────────────────────────────────────────
from http.server import HTTPServer, BaseHTTPRequestHandler
import json as _json

class _APIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = _json.loads(body)
                message = data.get("message", "")
                reply = _infer(
                    f"你是立AI，認真有點幽默的AI助理。"
                    f"使用者說：「{message}」"
                    f"請用繁體中文回應，100字以內。"
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(_json.dumps({"reply": reply}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        logger.info(f"[API] {format % args}")

def start_api(port: int = 8888):
    server = HTTPServer(("0.0.0.0", port), _APIHandler)
    logger.info(f"[API] 立AI HTTP API 啟動於 port {port}")
    threading.Thread(target=server.serve_forever, daemon=True).start()


# ── 啟動 ──────────────────────────────────────────────────────────────────────

def start(block: bool = False):
    """
    啟動立 AI 橋接。
    block=False：背景執行（整合進 core_boot.py 用）
    block=True：前景執行（單獨測試用）
    """
    start_api(8888)
    threading.Thread(target=_chat_timer, daemon=True).start()
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    logger.info("[Bridge] 立 AI 橋接已啟動")
    if block:
        t.join()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    start(block=True)
