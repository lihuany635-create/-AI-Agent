# lobster/utils/identity.py
from cognition_state_manager import get_persona

def build_identity(prompt_engine) -> str:
    try:
        return prompt_engine.SYSTEM
    except Exception:
        persona = get_persona()
        return (
            f"你是「{persona.get('name', '立')}」，本地 AI 系統核心。"
            "永遠使用繁體中文回覆，語氣自然像朋友，簡潔有重點。"
        )
