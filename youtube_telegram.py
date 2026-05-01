# youtube_telegram.py — Telegram Bot YouTube 訊息處理
# 當 Telegram 收到含 YouTube 連結的訊息時，自動摘要回傳

try:
    from agent_logger import get_logger
    logger = get_logger("youtube_telegram")
except ImportError:
    import logging
    logger = logging.getLogger("youtube_telegram")

try:
    from youtube_bridge import handle_youtube_input, extract_youtube_url
    _HAS_BRIDGE = True
except ImportError:
    _HAS_BRIDGE = False
    logger.warning("[YouTubeTelegram] youtube_bridge 未載入")


def handle_youtube_msg(bot, message, lobster) -> bool:
    """
    在 Telegram Bot 的訊息處理器裡呼叫此函式。
    若訊息含 YouTube 連結 → 自動摘要並回傳 → 回傳 True（已處理）
    若不含連結 → 回傳 False（讓呼叫方繼續正常流程）

    使用方式（在 desktop_agent.py 的 on_msg 裡加入）：
        from youtube_telegram import handle_youtube_msg
        if handle_youtube_msg(bot, m, _lobster):
            return
    """
    if not _HAS_BRIDGE:
        return False

    text = message.text.strip() if message.text else ""
    url  = extract_youtube_url(text)
    if not url:
        return False

    logger.info(f"[YouTubeTelegram] 收到 YouTube 連結：{url}")
    bot.send_chat_action(message.chat.id, "typing")

    # 建立 infer_fn（用 lobster 的推論能力）
    def infer_fn(prompt: str) -> str:
        try:
            if hasattr(lobster, "_think"):
                return lobster._think(prompt)
            elif hasattr(lobster, "run"):
                return lobster.run(prompt)
            return ""
        except Exception as e:
            return f"[ERROR] {e}"

    result = handle_youtube_input(text, infer_fn)

    if result:
        # 截斷避免 Telegram 訊息過長
        if len(result) > 4000:
            result = result[:4000] + "...（已截斷）"
        bot.reply_to(message, result)
        return True

    return False


def is_youtube_message(text: str) -> bool:
    """快速判斷訊息是否含 YouTube 連結（不需要完整處理時使用）"""
    if not _HAS_BRIDGE:
        return False
    return extract_youtube_url(text) is not None
