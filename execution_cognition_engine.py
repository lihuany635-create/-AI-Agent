import json
import re
from pathlib import Path
from datetime import datetime
from Lobster_Core import LobsterCore

lobster = LobsterCore()

BASE_DIR = Path(__file__).resolve().parent
COG_DIR = BASE_DIR / "memory"
COG_FILE = COG_DIR / "cognition_log.json"


def clean_json(text):
    text = re.sub(r"```json|```", "", text)
    return text.strip()


def save_cognition(data):
    COG_DIR.mkdir(exist_ok=True)

    if COG_FILE.exists():
        history = json.loads(COG_FILE.read_text(encoding="utf-8"))
    else:
        history = []

    history.append(data)

    COG_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def analyze_trace(trace: dict):
    """
    系統意識流分析
    """

    prompt = f"""
你是一位系統級 AI 認知分析專家。

AI 行為 trace：
{trace}

請輸出 JSON：

{{
 "logic_error": "YES/NO",
 "stage": "INPUT/EVAL/FINAL",
 "severity": "LOW/MEDIUM/CRITICAL",
 "repair_hint": "..."
}}
"""

    result = lobster.reflect(prompt)

    try:
        data = json.loads(clean_json(result))
    except Exception:
        data = {
            "logic_error": "UNKNOWN",
            "stage": "UNKNOWN",
            "severity": "UNKNOWN",
            "repair_hint": "PARSE_FAIL"
        }

    data["timestamp"] = datetime.now().isoformat()
    data["trace"] = trace

    save_cognition(data)

    return data