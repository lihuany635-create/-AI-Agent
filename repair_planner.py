import json
import re
import requests
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL      = "gpt-oss:20b"


def clean_json_string(text: str):
    text = re.sub(r"```json|```", "", text)
    return text.strip()


def plan_repair(project_state):
    """AI 修復策略決策器"""
    files   = project_state.get("files", [])
    changed = project_state.get("changed", [])

    prompt = f"""你是資深 Python 系統架構師。

目前專案檔案：
{files}

最近變動檔案：
{changed}

請判斷是否需要修復。只輸出 JSON，不要其他文字：
{{
  "repair": true 或 false,
  "file": "檔名",
  "reason": "原因",
  "priority": 1到5的數字
}}"""

    try:
        r = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "你是資深 Python 架構師，只輸出 JSON，第一個字必須是 {。"},
                {"role": "user",   "content": prompt}
            ],
            "stream": False
        }, timeout=None)
        response = r.json().get("message", {}).get("content", "")
        data = json.loads(clean_json_string(response))
        return data
    except Exception:
        return {
            "repair": False,
            "file": None,
            "reason": "LLM_PARSE_FAIL",
            "priority": 0
        }