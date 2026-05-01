# youtube_bridge.py — YouTube AI 整合橋接
# 偵測輸入是否含 YouTube 連結，若是則抓字幕並用 AI 摘要
# 使用方式：在 Lobster_Core 或任何地方 import 此模組

import re

try:
    from agent_logger import get_logger
    logger = get_logger("youtube_bridge")
except ImportError:
    import logging
    logger = logging.getLogger("youtube_bridge")

try:
    from youtube_handler import get_transcript, get_video_info
    _HAS_HANDLER = True
except ImportError:
    _HAS_HANDLER = False
    logger.warning("[YouTubeBridge] youtube_handler 未載入")


# YouTube 連結偵測 pattern
_YT_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=[\w\-]+|youtu\.be/[\w\-]+)"
)


def extract_youtube_url(text: str) -> str | None:
    """從文字中擷取 YouTube URL，找不到回傳 None"""
    m = _YT_PATTERN.search(text)
    if not m:
        return None
    url = m.group(0)
    if not url.startswith("http"):
        url = "https://" + url
    return url


def handle_youtube_input(text: str, infer_fn) -> str | None:
    """
    主入口：
    - 偵測 text 含 YouTube 連結 → 抓字幕 → 用 infer_fn 摘要 → 回傳摘要
    - 不含連結 → 回傳 None（讓呼叫方繼續正常流程）

    infer_fn: callable(prompt: str) -> str，傳入 Lobster_Core 或 ollama_guard 的推論函式
    """
    if not _HAS_HANDLER:
        return None

    url = extract_youtube_url(text)
    if not url:
        return None

    logger.info(f"[YouTubeBridge] 偵測到 YouTube 連結：{url}")

    # 取影片資訊
    info     = get_video_info(url)
    title    = info.get("title", "")
    duration = info.get("duration", "")
    info_str = f"《{title}》（{duration}）\n" if title else ""

    # 抓字幕
    transcript = get_transcript(url)
    if not transcript:
        return f"⚠️ 無法取得這部影片的字幕（可能沒有開放字幕）\n{info_str}"

    # 截斷字幕避免 prompt 太長（qwen2 限制）
    max_chars  = 800
    transcript_short = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")

    # 用 AI 摘要
    prompt = (
        f"以下是 YouTube 影片的字幕內容：\n\n"
        f"{info_str}"
        f"字幕：\n{transcript_short}\n\n"
        f"請用繁體中文摘要這部影片的主要內容，3-5句話。"
    )

    try:
        summary = infer_fn(prompt)
        if not summary:
            summary = "（AI 摘要失敗）"
    except Exception as e:
        summary = f"（摘要錯誤：{e}）"

    return f"🎬 {info_str}[YouTube字幕摘要]\n{summary}"


if __name__ == "__main__":
    # 測試（不需要 AI，只測字幕抓取）
    test_url = input("輸入 YouTube URL：").strip()
    url = extract_youtube_url(test_url)
    print(f"擷取到的 URL：{url}")
