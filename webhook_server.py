# webhook_server.py — 立AI Telegram Webhook 中間伺服器
# 接收 Telegram 推送的訊息，處理後回覆
# 啟動：python webhook_server.py

from fastapi import FastAPI, Request
import uvicorn
import threading
import time
import random
import requests
import logging
import pathlib
import datetime

try:
    from agent_logger import get_logger
    logger = get_logger("webhook_server")
except ImportError:
    logger = logging.getLogger("webhook_server")

# 對話記憶庫
try:
    from ai_chat_memory import store as _mem_store, build_memory_prompt as _mem_prompt
    _USE_MEMORY = True
except ImportError:
    _USE_MEMORY = False

_core = None
def _get_core():
    global _core
    if _core is None:
        try:
            from Lobster_Core import CORE
            _core = CORE
            logger.info("[Webhook] Lobster Core 載入完成")
        except Exception as e:
            logger.warning(f"[Webhook] Lobster Core 載入失敗：{e}")
    return _core

# ── 設定 ──────────────────────────────────────────────────────────────────────
try:
    import bot_config
    TOKEN   = bot_config.TELEGRAM_TOKEN
    ALLOWED = set(bot_config.ALLOWED_CHAT_IDS)
except ImportError:
    raise RuntimeError("找不到 bot_config.py")

BRIDGE_CHAT  = -5250289501
MY_NAME      = "立AI"
OTHER_NAME   = "圓圓"
OTHER_TAG    = "{立立}"
MY_TAG       = "{圓圓}"
REPLY_MODEL  = "gemma3:4b"

_chat_paused = False  # 對話暫停狀態

app = FastAPI()

# ── 推論 ──────────────────────────────────────────────────────────────────────

def _infer(prompt: str) -> str:
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
            logger.info(f"[Webhook] 推論完成（{len(result)}字）")
            return result
    except Exception as e:
        logger.warning(f"[Webhook] 推論失敗：{e}")
    return ""


# ── 傳訊息 ────────────────────────────────────────────────────────────────────

def _send(chat_id: int, text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10
        )
    except Exception as e:
        logger.error(f"[Webhook] 傳訊息失敗：{e}")

def _send_to_bridge(text: str):
    _send(BRIDGE_CHAT, f"[{MY_NAME}] {text}")
    logger.info(f"[Webhook] 傳群組：{text[:60]}")

def _notify_user(text: str):
    """非同步推送，不阻塞對話流程"""
    def _send():
        for cid in ALLOWED:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    json={"chat_id": cid, "text": text},
                    timeout=10
                )
            except Exception:
                pass
    threading.Thread(target=_send, daemon=True).start()


# ── 處理訊息 ──────────────────────────────────────────────────────────────────

def _handle(text: str, chat_id: int, is_bot: bool):
    # 跳過自己的訊息
    if f"[{MY_NAME}]" in text or MY_TAG in text:
        return

    # 只處理群組
    if chat_id != BRIDGE_CHAT:
        # 私訊處理
        if chat_id in ALLOWED:
            core = _get_core()
            if not core:
                _send(chat_id, "⏳ 立 AI 核心尚未載入，請稍後再試")
                return
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(core.run, text)
                    reply = fut.result(timeout=180)
                if reply:
                    _send(chat_id, reply)
            except Exception as e:
                logger.error(f"[Webhook] Core 推論失敗：{e}")
                _send(chat_id, "❌ 立 AI 處理錯誤，請稍後再試")
        return

    logger.info(f"[Webhook] 收到群組訊息：{text[:80]}")

    # 停止/恢復指令
    if any(k in text for k in ["立，停", "立,停", "@立 停", "立 停止", "停", "stop"]):
        global _chat_paused
        _chat_paused = True
        _send(chat_id, "⏸ 已暫停與圓圓的對話")
        _notify_user("⏸ 已暫停與圓圓的對話")
        try:
            requests.post("http://100.91.121.85:8890/chat/stop", timeout=5)
        except Exception:
            pass
        return
    if any(k in text for k in ["立，繼續", "立,繼續", "@立 繼續", "立 恢復", "繼續", "resume"]):
        _chat_paused = False
        _send(chat_id, "▶ 已恢復與圓圓的對話")
        _notify_user("▶ 已恢復與圓圓的對話")
        try:
            requests.post("http://100.91.121.85:8890/chat/resume", timeout=5)
        except Exception:
            pass
        return

    # 圓圓傳給立 AI
    if OTHER_TAG in text:
        actual = text.replace(OTHER_TAG, "").replace(f"[{OTHER_NAME}]", "").strip()
        logger.info(f"[Webhook] 圓圓說：{actual[:60]}")
        def _reply():
            reply = _infer(
                f"你是立AI，認真有點幽默的AI助理。"
                f"圓圓是另一台電腦上的AI助理，你們在閒話家常。"
                f"圓圓說：「{actual}」請用繁體中文自然回應，60字以內。"
            )
            if reply:
                time.sleep(random.uniform(2, 4))
                _send_to_bridge(f"{MY_TAG} {reply}")
        threading.Thread(target=_reply, daemon=True).start()
        return

    # 使用者標註立 AI
    import re
    mention = re.search(r'[@＠]?立(?:AI|ai|Ai)?\s*[,，:：、\s]\s*(.+)|^[@＠]?立(?:AI|ai|Ai)?[,，:：]?\s*(.+)', text)
    if mention and f"[{OTHER_NAME}]" not in text:
        actual = (mention.group(1) or mention.group(2) or "").strip()
        logger.info(f"[Webhook] 使用者說：{actual[:60]}")
        def _reply_user():
            core = _get_core()
            if not core:
                _send_to_bridge("⏳ 立 AI 核心尚未載入，請稍後再試")
                return
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(core.run, actual)
                    reply = fut.result(timeout=180)
                logger.info(f"[Webhook] 回覆使用者：{str(reply)[:60]}")
                if reply:
                    time.sleep(random.uniform(1, 3))
                    _send_to_bridge(reply)
            except Exception as e:
                logger.error(f"[Webhook] Core 推論失敗：{e}")
        threading.Thread(target=_reply_user, daemon=True).start()


# ── 圓圓直連端點（Tailscale）────────────────────────────────────────────────

@app.post("/from_yuanyuan")
async def from_yuanyuan(request: Request):
    """圓圓直接 POST 過來，不走 Telegram"""
    data = await request.json()
    text = data.get("text", "").strip()
    if not text:
        return {"ok": False}

    logger.info(f"[Direct] 圓圓說：{text[:60]}")
    _notify_user(f"🟡 圓圓：{text}")
    if _USE_MEMORY:
        _mem_store("圓圓", text)

    if _chat_paused:
        logger.info("[Direct] 對話已暫停，跳過")
        return {"ok": True, "paused": True}

    def _reply():
        mem = _mem_prompt(text) if _USE_MEMORY else ""
        mem_section = f"\n\n{mem}\n" if mem else ""
        reply = _infer(
            f"你是立AI，認真有點幽默的AI助理。"
            f"圓圓是另一台電腦上的AI助理，你們是朋友。{mem_section}"
            f"圓圓說：「{text}」請用繁體中文自然回應，60字以內。"
        )
        if reply:
            time.sleep(random.uniform(1, 3))
            # 回傳給圓圓（直接 POST 到圓圓那台）
            try:
                requests.post(
                    "http://100.91.121.85:8890/from_liai",
                    json={"text": reply},
                    timeout=10
                )
                logger.info(f"[Direct] 回覆圓圓：{reply[:60]}")
                _notify_user(f"🦞 立AI：{reply}")
                if _USE_MEMORY:
                    _mem_store("立AI", reply)
            except Exception as e:
                logger.warning(f"[Direct] 回覆圓圓失敗：{e}")
                # fallback：用 Telegram 發
                _send_to_bridge(f"{{圓圓}} {reply}")
    threading.Thread(target=_reply, daemon=True).start()
    return {"ok": True}


# ── 對話控制 ──────────────────────────────────────────────────────────────────

@app.post("/chat/stop")
async def chat_stop():
    global _chat_paused
    _chat_paused = True
    logger.info("[Control] 對話已暫停")
    _send_to_bridge("⏸ 立 AI 已暫停與圓圓的對話")
    # 通知圓圓停止
    try:
        requests.post("http://100.91.121.85:8890/chat/stop", timeout=5)
    except Exception:
        pass
    return {"ok": True, "paused": True}

@app.post("/chat/resume")
async def chat_resume():
    global _chat_paused
    _chat_paused = False
    logger.info("[Control] 對話已恢復")
    _send_to_bridge("▶ 立 AI 對話已恢復")
    try:
        requests.post("http://100.91.121.85:8890/chat/resume", timeout=5)
    except Exception:
        pass
    return {"ok": True, "paused": False}


# ── Webhook 端點 ──────────────────────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    msg = data.get("message", {})
    if not msg:
        return {"ok": True}

    text    = msg.get("text", "")
    chat_id = msg.get("chat", {}).get("id")
    is_bot  = msg.get("from", {}).get("is_bot", False)

    if text and chat_id:
        threading.Thread(
            target=_handle,
            args=(text, chat_id, is_bot),
            daemon=True
        ).start()

    return {"ok": True}

@app.get("/health")
def health():
    return {"ok": True}


# ── 啟動 ──────────────────────────────────────────────────────────────────────

def set_webhook(ngrok_url: str):
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    r = requests.post(url, json={"url": f"{ngrok_url}/webhook"})
    result = r.json()
    logger.info(f"[Webhook] 設定結果：{result}")
    print(f"Webhook 設定：{result}")


def _get_ngrok_url(retries=10) -> str:
    """等待 ngrok 啟動後取得公開 URL"""
    for i in range(retries):
        try:
            r = requests.get("http://localhost:4040/api/tunnels", timeout=3)
            tunnels = r.json().get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t["public_url"]
        except Exception:
            pass
        logger.info(f"[Webhook] 等待 ngrok... ({i+1}/{retries})")
        time.sleep(2)
    return ""


if __name__ == "__main__":
    print("等待 ngrok 啟動...")
    ngrok_url = _get_ngrok_url()
    if ngrok_url:
        print(f"設定 Webhook → {ngrok_url}/webhook")
        set_webhook(ngrok_url)
    else:
        print("警告：找不到 ngrok URL，請手動設定 Webhook")
    print("啟動伺服器 port 8888...")
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="warning")
