import json
from datetime import datetime
from pathlib import Path

ERROR_PATH = Path("memory/error_memory.json")


def load_error_memory():
    if not ERROR_PATH.exists():
        return []
    return json.loads(ERROR_PATH.read_text(encoding="utf-8"))


def save_error_memory(memory):
    ERROR_PATH.parent.mkdir(exist_ok=True)
    ERROR_PATH.write_text(
        json.dumps(memory, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def record_error(project_state, diagnosis, repair_plan, result):
    """
    記錄完整錯誤經驗
    """

    memory = load_error_memory()

    record = {
        "time": datetime.now().isoformat(),
        "changed_files": project_state.get("changed"),
        "diagnosis": diagnosis,
        "repair_plan": repair_plan,
        "result": result
    }

    memory.append(record)
    save_error_memory(memory)


def find_similar_error(project_state):
    """
    找類似錯誤（基礎版）
    """

    memory = load_error_memory()
    changed = set(project_state.get("changed", []))

    for m in reversed(memory):
        past = set(m.get("changed_files", []))
        if changed & past:
            return m

    return None