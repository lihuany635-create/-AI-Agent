from skill_learning_engine import SkillLearningEngine
from cognitive_intent_engine import CognitiveIntentEngine

try:
    from pc_api_client import smart_execute, is_available as _pc_available
    _HAS_PC_API = True
except ImportError:
    _HAS_PC_API = False

# 觸發 PC API 的關鍵字
_PC_KEYWORDS = [
    "截圖", "看畫面", "畫面上", "螢幕", "點擊", "點", "輸入",
    "打字", "執行", "開啟", "快捷鍵", "ctrl", "alt", "捲動",
    "滑鼠", "鍵盤", "視窗", "click", "type", "screen", "run",
]


class IntentRouter:

    def __init__(self, task_registry):
        self.tasks = task_registry
        self.skill_engine = SkillLearningEngine(task_registry)
        self.cognitive = CognitiveIntentEngine()

    def route(self, text):

        # ⭐ LOW LEVEL COMMAND
        if text.startswith("RUN_PYTHON:"):
            return {
                "action": text
            }

        # ⭐ PC API：偵測到電腦操作相關指令，交給 pc_api_client 處理
        if _HAS_PC_API and _pc_available():
            t = text.lower()
            if any(k in t for k in _PC_KEYWORDS):
                result = smart_execute(text)
                return {"action": "pc_api", "result": result}

        # ⭐ Learned skill
        learned = self.skill_engine.match(text)
        if learned is not None:
            return learned

        # ⭐ Cognitive inference
        inferred = self.cognitive.infer(text)
        if inferred:
            return self.tasks.execute(inferred)

        return None