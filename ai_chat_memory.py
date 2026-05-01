# ai_chat_memory.py — 立AI 與圓圓的對話記憶庫
# 儲存對話歷史，推論時搜尋相關記憶帶入 prompt

import json
import pathlib
import datetime
import re
from typing import List, Dict

MEMORY_FILE = pathlib.Path("memory/ai_chat_history.json")
MAX_MEMORIES = 200   # 最多保留 200 條
SEARCH_TOP_K = 5     # 推論時帶入最相關的 5 條


def _load() -> List[Dict]:
    MEMORY_FILE.parent.mkdir(exist_ok=True)
    if not MEMORY_FILE.exists():
        return []
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(memories: List[Dict]):
    MEMORY_FILE.parent.mkdir(exist_ok=True)
    MEMORY_FILE.write_text(
        json.dumps(memories[-MAX_MEMORIES:], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def store(speaker: str, text: str):
    """
    儲存一條對話記錄
    speaker: "立AI" 或 "圓圓"
    """
    memories = _load()
    memories.append({
        "time":    datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "speaker": speaker,
        "text":    text[:300]
    })
    _save(memories)


def search(query: str, top_k: int = SEARCH_TOP_K) -> List[Dict]:
    """
    搜尋相關記憶（簡單關鍵字匹配）
    回傳最相關的 top_k 條
    """
    memories = _load()
    if not memories:
        return []

    query_words = set(re.findall(r'\w+', query.lower()))
    scored = []
    for m in memories:
        text_words = set(re.findall(r'\w+', m["text"].lower()))
        score = len(query_words & text_words)
        if score > 0:
            scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:top_k]]


def get_recent(n: int = 10) -> List[Dict]:
    """取得最近 n 條對話"""
    memories = _load()
    return memories[-n:]


def build_memory_prompt(query: str) -> str:
    """
    建立記憶 prompt，帶入相關記憶和最近對話
    """
    recent = get_recent(6)
    relevant = search(query, top_k=3)

    parts = []

    if recent:
        parts.append("【最近的對話記錄】")
        for m in recent:
            parts.append(f"{m['time']} {m['speaker']}：{m['text']}")

    # 相關但不在最近的記憶
    recent_texts = {m["text"] for m in recent}
    extra = [m for m in relevant if m["text"] not in recent_texts]
    if extra:
        parts.append("\n【相關的過去對話】")
        for m in extra:
            parts.append(f"{m['time']} {m['speaker']}：{m['text']}")

    return "\n".join(parts)
