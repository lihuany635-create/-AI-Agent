# memory_curator.py — 記憶自動學習模組
# 功能：
#   每次對話結束後，判斷這輪對話是否包含值得記住的重要資訊
#   重要的話自動存入 long_term_memory，不重要的跳過
#
# 使用方式：在 Lobster_Core._think() 回覆後呼叫
#   from memory_curator import maybe_learn
#   maybe_learn(user_input, ai_response)

import re
from typing import Optional

try:
    from long_term_memory import get_memory
    _memory = get_memory()
except Exception:
    _memory = None

try:
    from agent_logger import get_logger
    logger = get_logger("memory_curator")
except ImportError:
    import logging
    logger = logging.getLogger("memory_curator")


# ── 重要性判斷規則 ────────────────────────────────────────────────────────────

# 這些關鍵字出現在使用者輸入，代表這是重要指令或設定
USER_IMPORTANT_KEYWORDS = [
    "記住", "記下來", "不要忘記", "重要", "我叫", "我是", "我的",
    "我喜歡", "我不喜歡", "我習慣", "我的名字", "請記得",
    "設定", "偏好", "預設", "路徑", "密碼", "帳號",
]

# 這些關鍵字出現在 AI 回覆，代表這輪有實質技術內容
AI_CONTENT_KEYWORDS = [
    "修復方法", "解決方案", "步驟", "指令", "安裝", "設定",
    "錯誤原因", "因為", "原理", "方式是", "做法是",
]

# 這些代表不重要的閒聊，不存入記憶
SKIP_PATTERNS = [
    r"^(你好|嗨|哈囉|hi|hello|再見|掰|謝謝|好的|ok|好)$",
    r"^.{1,4}$",   # 超短問題
]


def _is_important(user_input: str, ai_response: str) -> tuple[bool, int, list[str]]:
    """
    判斷這輪對話是否值得存入長期記憶
    回傳：(是否重要, 重要性分數 1-10, 標籤清單)
    """
    u = user_input.strip()
    a = ai_response.strip()

    # 跳過閒聊
    for pat in SKIP_PATTERNS:
        if re.match(pat, u, re.IGNORECASE):
            return False, 0, []

    # 跳過 LLM 錯誤
    if "[LLM ERROR]" in a or len(a) < 10:
        return False, 0, []

    importance = 4  # 預設中等
    tags = []

    # 使用者明確要求記住
    if any(kw in u for kw in ["記住", "記下來", "不要忘記", "請記得"]):
        importance = 9
        tags.append("manual")
        return True, importance, tags

    # 使用者自我介紹或個人設定
    if any(kw in u for kw in ["我叫", "我是", "我的名字", "我喜歡", "我習慣", "我不喜歡"]):
        importance = 8
        tags.append("about_user")
        return True, importance, tags

    # 技術設定類
    if any(kw in u for kw in ["設定", "偏好", "預設", "路徑", "帳號"]):
        importance = 7
        tags.append("config")
        return True, importance, tags

    # AI 回覆包含技術解說
    if any(kw in a for kw in AI_CONTENT_KEYWORDS) and len(a) > 80:
        importance = 6
        tags.append("knowledge")
        return True, importance, tags

    # 使用者問的是「如何」、「為什麼」類問題，且回覆夠長
    if re.search(r"(如何|怎麼|為什麼|原因|方法|步驟)", u) and len(a) > 100:
        importance = 5
        tags.append("how_to")
        return True, importance, tags

    return False, 0, []


def maybe_learn(user_input: str, ai_response: str) -> Optional[str]:
    """
    判斷是否重要，重要則自動存入長期記憶
    回傳：存入的記憶 ID，或 None（不重要跳過）
    """
    if _memory is None:
        return None

    important, importance, tags = _is_important(user_input, ai_response)

    if not important:
        return None

    # 存入的內容：「問：... 答：...」的摘要
    u_short = user_input[:60]
    a_short = ai_response[:120]
    content = f"問：{u_short} → 答：{a_short}"

    mem_id = _memory.store(content, tags=tags, importance=importance, source="auto")
    logger.info(f"[記憶自動學習] 已儲存（重要性 {importance}）：{content[:60]}...")
    return mem_id


def learn_explicitly(content: str, tags: list = None, importance: int = 8) -> Optional[str]:
    """
    手動強制存入（給桌面 UI 的「＋新增」按鈕用）
    """
    if _memory is None:
        return None
    return _memory.store(content, tags=tags or ["manual"], importance=importance)


def forget(memory_id: str) -> bool:
    """刪除指定記憶（給桌面 UI 的刪除按鈕用）"""
    if _memory is None:
        return False
    return _memory.forget(memory_id)


def get_all(query: str = "", top_k: int = 50) -> list[dict]:
    """取得所有記憶（給桌面 UI 顯示用）"""
    if _memory is None:
        return []
    if query:
        return _memory.search(query, top_k=top_k)
    return sorted(_memory._memories, key=lambda m: m["accessed_at"], reverse=True)[:top_k]

