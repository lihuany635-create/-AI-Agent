# cognition_state_manager.py — 升級版
# 修復：MAX_HISTORY 從 8 提高到 16，上下文記得更久
# 新增：get_recent_summary() 供 prompt_engine 使用

import json
from pathlib import Path

BASE_DIR     = Path(__file__).resolve().parent
STATE_FILE   = BASE_DIR / "memory" / "runtime_state.json"
PERSONA_FILE = BASE_DIR / "persona_state.json"

MAX_HISTORY = 16   # 原本是 8，提高到 16 讓 AI 記得更多對話


def get_persona():
    if PERSONA_FILE.exists():
        return json.loads(PERSONA_FILE.read_text(encoding="utf-8"))
    return {}


def _safe_state(mem):
    if not isinstance(mem, dict):
        mem = {}
    if "history" not in mem:
        mem["history"] = []
    return mem


def load_memory():
    if STATE_FILE.exists():
        try:
            mem = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            mem = {}
    else:
        mem = {}
    return _safe_state(mem)


def save_memory(mem):
    mem = _safe_state(mem)
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(mem, indent=2, ensure_ascii=False), encoding="utf-8")


def update_context(user: str, ai: str):
    """儲存一輪對話到記憶"""
    # 過濾掉 LLM 錯誤，不存入歷史（避免污染上下文）
    if "[LLM ERROR]" in ai:
        return
    mem = load_memory()
    mem["history"].append({"user": user, "ai": ai})
    mem["history"] = mem["history"][-MAX_HISTORY:]
    save_memory(mem)


def get_current_context() -> str:
    """取得格式化的對話歷史（供 prompt_engine 使用）"""
    mem  = load_memory()
    hist = mem.get("history", [])
    if not hist:
        return ""
    lines = []
    for h in hist:
        lines.append(f"使用者：{h['user']}")
        lines.append(f"立：{h['ai']}")
    return "\n".join(lines)


def get_recent_summary(n: int = 3) -> str:
    """取得最近 n 輪的簡短摘要"""
    mem  = load_memory()
    hist = mem.get("history", [])[-n:]
    if not hist:
        return ""
    parts = []
    for h in hist:
        parts.append(f"Q: {h['user'][:40]} → A: {h['ai'][:60]}")
    return " | ".join(parts)


def clear_context():
    """清除對話歷史（debug 用）"""
    mem = load_memory()
    mem["history"] = []
    save_memory(mem)
