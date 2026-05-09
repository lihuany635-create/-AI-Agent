"""
ai_memory.py — 立AI 記憶系統
每次對話後自動整理重點，下次帶進 context。
"""

import json
import pathlib
from datetime import datetime

MEMORY_DIR  = pathlib.Path(__file__).parent / "workshop_data" / "memory"
MEMORY_FILE = MEMORY_DIR / "立AI_memory.json"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

MAX_RECENT  = 20   # 最多保留幾條近期記憶
MAX_FACTS   = 30   # 最多保留幾條重要事實


def load_memory() -> dict:
    """載入記憶。"""
    if not MEMORY_FILE.exists():
        return {
            "user_preferences": [],
            "system_context":   [],
            "recent_topics":    [],
            "important_facts":  [],
            "last_updated":     "",
        }
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return load_memory.__wrapped__()


def save_memory(memory: dict):
    """儲存記憶。"""
    memory["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    MEMORY_FILE.write_text(
        json.dumps(memory, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def build_memory_prompt() -> str:
    """把記憶整理成 system prompt 的一部分。"""
    mem = load_memory()
    parts = []

    if mem.get("user_preferences"):
        parts.append("【使用者習慣】\n" + "\n".join(f"- {p}" for p in mem["user_preferences"][:5]))

    if mem.get("important_facts"):
        parts.append("【重要資訊】\n" + "\n".join(f"- {f}" for f in mem["important_facts"][:10]))

    if mem.get("recent_topics"):
        parts.append("【近期話題】\n" + "\n".join(f"- {t}" for t in mem["recent_topics"][:5]))

    if mem.get("system_context"):
        parts.append("【系統狀態】\n" + "\n".join(f"- {c}" for c in mem["system_context"][:5]))

    if not parts:
        return ""

    return "【立AI 記憶】\n" + "\n\n".join(parts)


def update_memory_from_conversation(conversation: list[dict], ollama_url: str, model: str):
    """
    根據對話內容，用 AI 整理出重點更新記憶。
    conversation: [{"role": "user"/"assistant", "content": "..."}]
    """
    if not conversation:
        return

    import requests
    mem = load_memory()

    # 把對話整理成文字
    conv_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:200]}"
        for m in conversation[-6:]  # 最近 6 條
    )

    prompt = f"""分析以下對話，整理出值得記住的重點，輸出嚴格 JSON：

對話：
{conv_text}

輸出格式（所有欄位都是字串陣列，沒有的就給空陣列）：
{{
  "new_preferences": ["使用者的習慣或偏好"],
  "new_facts": ["重要事實或資訊，如IP、路徑、設定"],
  "new_topics": ["這次討論的主題摘要（一句話）"],
  "new_context": ["系統狀態變化"]
}}

只記錄真正重要且值得下次記住的內容，不重要的不要記。"""

    try:
        r = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "只輸出 JSON，第一個字必須是 {"},
                    {"role": "user",   "content": prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 400},
            },
            timeout=30
        )
        raw = r.json().get("message", {}).get("content", "").strip()
        import re
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            return
        updates = json.loads(raw[start:end])
    except Exception:
        return

    # 更新各類記憶（去重）
    def _add_unique(lst: list, new_items: list, max_len: int) -> list:
        for item in new_items:
            if item and item not in lst:
                lst.insert(0, item)
        return lst[:max_len]

    mem["user_preferences"] = _add_unique(
        mem.get("user_preferences", []),
        updates.get("new_preferences", []), 10
    )
    mem["important_facts"] = _add_unique(
        mem.get("important_facts", []),
        updates.get("new_facts", []), MAX_FACTS
    )
    mem["recent_topics"] = _add_unique(
        mem.get("recent_topics", []),
        updates.get("new_topics", []), MAX_RECENT
    )
    mem["system_context"] = _add_unique(
        mem.get("system_context", []),
        updates.get("new_context", []), 10
    )

    save_memory(mem)


def clear_memory():
    """清除所有記憶。"""
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()


if __name__ == "__main__":
    print("📝 立AI 記憶系統")
    mem = load_memory()
    print(json.dumps(mem, ensure_ascii=False, indent=2))


# ── 對話紀錄持久化 ────────────────────────────────────────────────────────────
CONV_DIR = MEMORY_DIR / "conversations"
CONV_DIR.mkdir(parents=True, exist_ok=True)


def save_conversation(user_msg: str, ai_reply: str):
    """把一條對話存進今天的紀錄檔。"""
    today = datetime.now().strftime("%Y-%m-%d")
    conv_file = CONV_DIR / f"{today}.jsonl"
    record = {
        "time":  datetime.now().strftime("%H:%M:%S"),
        "user":  user_msg,
        "reply": ai_reply,
    }
    with open(conv_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_recent_conversations(max_turns: int = 10) -> list[dict]:
    """
    載入最近的對話紀錄，回傳 messages 格式的列表。
    跨日期也能讀取。
    """
    records = []
    # 讀取最近幾天的紀錄
    conv_files = sorted(CONV_DIR.glob("*.jsonl"), reverse=True)[:3]
    for f in reversed(conv_files):
        try:
            lines = f.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                rec = json.loads(line)
                records.append(rec)
        except Exception:
            pass

    # 只取最近 max_turns 條
    records = records[-max_turns:]

    # 轉成 messages 格式
    messages = []
    for rec in records:
        messages.append({"role": "user",      "content": rec["user"]})
        messages.append({"role": "assistant", "content": rec["reply"]})
    return messages


def get_conversation_summary() -> str:
    """取得近期對話的摘要字串，給 system prompt 用。"""
    messages = load_recent_conversations(max_turns=6)
    if not messages:
        return ""
    lines = ["【近期對話紀錄】"]
    for m in messages:
        role = "你" if m["role"] == "user" else "立AI"
        lines.append(f"{role}：{m['content'][:80]}")
    return "\n".join(lines)
