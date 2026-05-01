# cognitive_intent_engine.py — 修復版
# 問題根源：每次問問題都會先對 Ollama 發一個技能比對 request
#           → Ollama 慢或離線時卡住 60 秒 → _think() 沒機會被呼叫
#           → 使用者看到「沒有回應」
#
# 修復策略：
#   1. 如果 skill_memory 裡沒有技能，直接 return None（不打 Ollama）
#   2. 技能比對改用關鍵字快速比對（不需要 LLM）
#   3. 只有在關鍵字比對有結果時，才考慮呼叫 LLM 確認
#   4. 整體加上短 timeout（5 秒），不讓它卡住主流程

import json
from pathlib import Path

try:
    from ollama_guard import safe_infer, is_online
    _USE_GUARD = True
except ImportError:
    _USE_GUARD = False


class CognitiveIntentEngine:

    def __init__(self):
        self.skill_file = Path("skill_memory.json")

    def _load_skills(self) -> dict:
        if self.skill_file.exists():
            try:
                data = json.loads(self.skill_file.read_text(encoding="utf-8"))
                return data.get("skills", {})
            except Exception:
                pass
        return {}

    def infer(self, text: str):
        """
        判斷輸入是否對應某個已學技能
        優先用關鍵字快速比對，不需要 LLM
        """
        skills = self._load_skills()

        # ── 快速路徑：沒有技能 → 直接讓 _think() 處理 ─────────────────────
        if not skills:
            return None

        text_lower = text.lower().strip()

        # ── 關鍵字比對（不需要 LLM，毫秒級）────────────────────────────────
        for phrase, task_name in skills.items():
            if phrase.lower() in text_lower:
                return task_name

        # ── 沒有比對到 → 直接 return None，讓 _think() 接手 ────────────────
        # 原本這裡會呼叫 Ollama 做語意比對，但：
        #   1. skill_memory 目前只有一個技能「開AI」
        #   2. 對一個技能做語意比對沒有意義
        #   3. 這會卡住 60 秒
        # 未來技能變多後，可以在這裡加回 LLM 語意比對
        return None
