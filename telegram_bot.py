import sys
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

# telegram_bot.py — 立 AI Telegram 機器人
# 使用輪詢模式（不需要固定 IP，行動數據可用）
# 安裝依賴：pip install pytelegrambotapi
# 使用方式：python telegram_bot.py

import threading
import time
import pathlib
import datetime

try:
    import telebot
except ImportError:
    print("請先安裝：pip install pytelegrambotapi")
    raise

try:
    from agent_logger import get_logger
    logger = get_logger("telegram_bot")
except ImportError:
    import logging
    logger = logging.getLogger("telegram_bot")

# ── 設定（從 bot_config.py 讀取）────────────────────────────────────────────
try:
    import bot_config
    TOKEN   = bot_config.TELEGRAM_TOKEN
    ALLOWED = set(bot_config.ALLOWED_CHAT_IDS)
except ImportError:
    raise RuntimeError("找不到 bot_config.py，請確認已建立設定檔")

# ── 載入 AI 核心 ──────────────────────────────────────────────────────────────
_lobster = None
_reflex  = None
_router  = None
_core_loading = False   # 防止重複載入

def _load_core() -> bool:
    """
    懶載入：第一次收到訊息才啟動 AI 核心
    之後會快取，不會每次都重新載入
    """
    global _lobster, _reflex, _router, _core_loading
    if _lobster is not None:
        return True   # 已載入，直接回傳
    if _core_loading:
        return False  # 正在載入中，避免重複
    _core_loading = True
    try:
        logger.info("首次收到訊息，正在啟動 AI 核心...")
        # 確認 Ollama 是否在線，不在線就先啟動
        _ensure_ollama()
        from Lobster_Core import LobsterCore
        from reflex_engine import ReflexEngine
        from task_capability_registry import TaskCapabilityRegistry
        from intent_router import IntentRouter
        _lobster = LobsterCore()
        _reflex  = ReflexEngine()
        _tasks   = TaskCapabilityRegistry(_lobster.os)
        _router  = IntentRouter(_tasks)
        logger.info("AI 核心載入完成")
        return True
    except Exception as e:
        logger.error(f"AI 核心載入失敗：{e}")
        return False
    finally:
        _core_loading = False

def _ensure_ollama():
    """確認 Ollama 在線，如果沒有就嘗試啟動"""
    import requests as req, subprocess, time
    try:
        r = req.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            logger.info("Ollama 已在線")
            return
    except Exception:
        pass
    # Ollama 沒在跑，嘗試啟動
    logger.info("Ollama 未啟動，正在啟動...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        # 等最多 30 秒讓 Ollama 啟動
        for _ in range(15):
            time.sleep(2)
            try:
                r = req.get("http://localhost:11434/api/tags", timeout=2)
                if r.status_code == 200:
                    logger.info("Ollama 啟動成功")
                    return
            except Exception:
                pass
        logger.warning("Ollama 啟動逾時，繼續嘗試...")
    except Exception as e:
        logger.error(f"無法啟動 Ollama：{e}")

def _ask_ai(text: str, chat_id: int = None) -> str:
    """傳送問題給 AI，回傳回覆（首次自動啟動核心）"""
    global _lobster, _reflex, _router

    # 核心尚未載入 → 自動啟動
    if _lobster is None:
        if chat_id:
            bot.send_message(chat_id, "⏳ AI 核心啟動中，請稍候（約 10～30 秒）...")
        ok = _load_core()
        if not ok:
            return "❌ AI 核心啟動失敗，請確認 Ollama 已安裝"

    if _lobster and _reflex and _router:
        try:
            return _lobster.process_input(text, _reflex, _router)
        except Exception as e:
            return f"AI 處理錯誤：{e}"
    elif _lobster:
        try:
            return _lobster.run(text)
        except Exception as e:
            return f"AI 錯誤：{e}"
    return "AI 核心尚未載入，請稍後再試"

# ── Bot 建立 ──────────────────────────────────────────────────────────────────
bot = telebot.TeleBot(TOKEN, parse_mode=None)

# 使用者目前的模式追蹤
_user_mode: dict = {}  # chat_id → mode
_DEFAULT_MODE = "chat"

def _get_mode(chat_id: int) -> str:
    return _user_mode.get(chat_id, _DEFAULT_MODE)

def _set_mode(chat_id: int, mode: str):
    _user_mode[chat_id] = mode

def _is_allowed(message) -> bool:
    """檢查是否為允許的使用者（檢查發送者 ID，支援群組訊息）"""
    if not ALLOWED:
        return True
    # 優先檢查發送者的個人 ID
    sender_id = message.from_user.id if message.from_user else None
    if sender_id and sender_id in ALLOWED:
        return True
    # 也允許群組本身（群組 ID 在白名單）
    if message.chat.id in ALLOWED:
        return True
    return False

# ── 指令處理 ──────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start", "hello"])
def cmd_start(message):
    if not _is_allowed(message):
        bot.reply_to(message, "❌ 未授權的使用者")
        return
    bot.reply_to(message,
        "🦞 立 AI 已連線！\n\n"
        "直接傳訊息給我就好，我會回答你。\n"
        "輸入 /status 查看系統狀態。"
    )
    logger.info(f"[Bot] /start from {message.chat.id}")


@bot.message_handler(commands=["help"])
def cmd_help(message):
    if not _is_allowed(message): return
    bot.reply_to(message,
        "📋 使用說明\n\n"
        "直接傳訊息 → 立 AI 回覆\n"
        "/status → 系統狀態\n"
        "/id → 你的 Chat ID"
    )


@bot.message_handler(commands=["id"])
def cmd_id(message):
    bot.reply_to(message, f"你的 Chat ID：{message.chat.id}")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not _is_allowed(message): return
    try:
        import requests as req
        r = req.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        ollama_str = f"✅ 在線  模型：{', '.join(models[:3])}"
    except Exception:
        ollama_str = "❌ 離線"
    try:
        from long_term_memory import get_memory
        mem_count = len(get_memory()._memories)
    except Exception:
        mem_count = "?"
    bot.reply_to(message,
        f"🦞 立 AI 系統狀態\n"
        f"{'─'*24}\n"
        f"🖥 Ollama：{ollama_str}\n"
        f"💾 記憶庫：{mem_count} 筆\n"
        f"🕐 {datetime.datetime.now().strftime('%H:%M:%S')}"
    )


BRIDGE_CHAT = -5250289501  # 兩台共用的群組，交給 li_ai_bridge 處理

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    # 群組訊息不由 telegram_bot 處理，交給 li_ai_bridge
    if message.chat.id == BRIDGE_CHAT:
        return

    if not _is_allowed(message):
        bot.reply_to(message, "❌ 未授權的使用者")
        return

    text = message.text.strip()
    logger.info(f"[Bot] 收到訊息：{text[:50]}")
    bot.send_chat_action(message.chat.id, "typing")

    reply = _ask_ai(text, chat_id=message.chat.id)
    if not reply:
        reply = "（沒有回應）"
    if len(reply) > 4000:
        reply = reply[:4000] + "\n...（訊息過長已截斷）"
    bot.reply_to(message, reply)

    # 更新對話上下文
    try:
        from cognition_state_manager import update_context
        update_context(text, reply)
    except Exception:
        pass

    # 寫入共享訊息檔
    try:
        import json
        msg_file = pathlib.Path("memory/mobile_messages.json")
        msg_file.parent.mkdir(exist_ok=True)
        msgs = []
        if msg_file.exists():
            try: msgs = json.loads(msg_file.read_text(encoding="utf-8"))
            except: msgs = []
        msgs.append({
            "time":  datetime.datetime.now().strftime("%H:%M:%S"),
            "user":  text,
            "reply": reply,
        })
        msgs = msgs[-50:]
        msg_file.write_text(json.dumps(msgs, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ── 推送通知函式（供其他模組呼叫）──────────────────────────────────────────

def push(message_text: str):
    """
    從任何地方主動推送訊息到手機
    用法：from telegram_bot import push; push("修復完成！")
    """
    if not ALLOWED:
        logger.warning("[Bot] 無法推送：ALLOWED_CHAT_IDS 未設定")
        return
    for chat_id in ALLOWED:
        try:
            bot.send_message(chat_id, f"🔔 {message_text}")
            logger.info(f"[Bot] 推送成功 → {chat_id}")
        except Exception as e:
            logger.error(f"[Bot] 推送失敗：{e}")


# ── 啟動 ─────────────────────────────────────────────────────────────────────

def start_bot(background: bool = False):
    """啟動 Bot（可背景執行，收到訊息才啟動 AI 核心）"""
    logger.info("Telegram Bot 啟動中...")
    print("Telegram Bot 已啟動（輕量待機模式）")
    print("   AI 核心將在收到第一則訊息時自動啟動")
    print("   在 Telegram 傳訊息給你的 Bot 即可")

    # 推送 Bot 上線通知（不啟動 AI 核心，很快）
    push("🤖 Bot 已上線，傳訊息給我就會自動啟動 AI")

    if background:
        t = threading.Thread(
            target=lambda: bot.infinity_polling(timeout=30, long_polling_timeout=20),
            daemon=True
        )
        t.start()
        return t
    else:
        bot.infinity_polling(timeout=30, long_polling_timeout=20)


if __name__ == "__main__":
    start_bot(background=False)

