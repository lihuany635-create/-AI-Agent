import json
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "bug_knowledge.json"


def load_bug_db():
    if not DB_FILE.exists():
        return []
    return json.loads(DB_FILE.read_text(encoding="utf-8"))


def save_bug_db(data):
    DB_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def learn_bug(project_state, diagnosis, repair_plan, result):
    """
    演化學習核心
    """

    db = load_bug_db()

    changed = tuple(sorted(project_state.get("changed", [])))

    for item in db:
        if tuple(item["changed"]) == changed:
            item["count"] += 1
            item["last_seen"] = datetime.now().isoformat()
            item["success_rate"] = (
                (item["success_rate"] * (item["count"] - 1) + int(result))
                / item["count"]
            )
            save_bug_db(db)
            return

    entry = {
        "changed": list(changed),
        "diagnosis": diagnosis,
        "repair_plan": repair_plan,
        "success_rate": int(result),
        "count": 1,
        "created": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat()
    }

    db.append(entry)
    save_bug_db(db)


def suggest_fix(project_state):
    """
    根據過去經驗建議策略
    """

    db = load_bug_db()
    changed = tuple(sorted(project_state.get("changed", [])))

    best = None

    for item in db:
        if tuple(item["changed"]) == changed:
            if not best or item["success_rate"] > best["success_rate"]:
                best = item

    if best:
        return {
            "repair_plan": best["repair_plan"],
            "confidence": best["success_rate"]
        }

    return None