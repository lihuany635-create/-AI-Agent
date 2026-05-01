# lobster/integration/push.py
import sys
import threading

try:
    from agent_logger import get_logger
    logger = get_logger("lobster.integration.push")
except ImportError:
    import logging
    logger = logging.getLogger("lobster.integration.push")

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"

def _ensure_pkg():
    if _PKG not in sys.path:
        sys.path.insert(0, _PKG)

def push_to_phone(question: str, answer: str):
    try:
        _ensure_pkg()
        import bot_config, telebot
        if len(answer) < 30:
            return
        def _send():
            try:
                bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN, parse_mode=None)
                q = question[:80].encode("utf-8", errors="ignore").decode("utf-8")
                a = answer[:500].encode("utf-8", errors="ignore").decode("utf-8")
                msg = "立 AI 回覆\n\n問：" + q + "\n\n答：" + a
                if len(answer) > 500:
                    msg += "\n...（完整回覆請看電腦）"
                for cid in bot_config.ALLOWED_CHAT_IDS:
                    bot.send_message(cid, msg)
            except Exception as e:
                logger.error(f"[推送] 失敗：{e}")
        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        logger.error(f"[推送] 外層錯誤：{e}")

def push_dev_confirm(step_preview: str):
    try:
        _ensure_pkg()
        import bot_config
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        def _send():
            try:
                try:
                    import telegram_bot as _tb
                    _bot = _tb.bot
                except Exception:
                    import telebot
                    _bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN, parse_mode=None)
                msg = "🤖 立 AI 開發確認\n\n" + step_preview[:600]
                kb = InlineKeyboardMarkup()
                kb.row(
                    InlineKeyboardButton("✅ 確認", callback_data="dev_confirm"),
                    InlineKeyboardButton("❌ 取消", callback_data="dev_cancel"),
                )
                for cid in bot_config.ALLOWED_CHAT_IDS:
                    _bot.send_message(cid, msg, reply_markup=kb)
                logger.info("[推送] 開發確認已推送到手機（含按鈕）")
            except Exception as e:
                logger.error(f"[推送] 開發確認失敗：{e}")
        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        logger.error(f"[推送] 開發確認外層錯誤：{e}")
