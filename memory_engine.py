import json
from datetime import datetime
from pathlib import Path
from Lobster_Core import LobsterCore

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
TASK_FILE = MEMORY_DIR / "task_history.json"
SKILL_FILE = MEMORY_DIR / "skill_memory.json"

lobster = LobsterCore()


def _ensure_dir():
    MEMORY_DIR.mkdir(exist_ok=True)


def load_task_memory():
    _ensure_dir()
    if not TASK_FILE.exists():
        return []
    return json.loads(TASK_FILE.read_text(encoding="utf-8"))


def save_task_memory(memory):
    _ensure_dir()
    TASK_FILE.write_text(json.dumps(memory, indent=2), encoding="utf-8")


def record_task(project_state, decision, result):
    """
    記錄 AI 行為經驗
    """

    memory = load_task_memory()

    record = {
        "time": datetime.now().isoformat(),
        "changed_files": project_state.get("changed"),
        "decision": decision,
        "result": result
    }

    memory.append(record)
    save_task_memory(memory)


def summarize_memory():
    """
    AI 技能演化
    """

    memory = load_task_memory()

    if len(memory) < 3:
        return None

    recent = memory[-3:]

    prompt = f"""
AI 最近行為紀錄：
{recent}

請輸出 JSON：

{{
 "new_skill": "...",
 "strategy": "...",
 "efficiency_gain": 0~1
}}
"""

    result = lobster.reflect(prompt)

    try:
        skill = json.loads(result)
    except Exception:
        skill = {"new_skill": "unknown", "strategy": "unknown", "efficiency_gain": 0}

    save_skill(skill)

    return skill


def save_skill(skill):
    _ensure_dir()

    if SKILL_FILE.exists():
        skills = json.loads(SKILL_FILE.read_text(encoding="utf-8"))
    else:
        skills = []

    skills.append(skill)

    SKILL_FILE.write_text(json.dumps(skills, indent=2), encoding="utf-8")


def load_skills():
    if not SKILL_FILE.exists():
        return []
    return json.loads(SKILL_FILE.read_text(encoding="utf-8"))