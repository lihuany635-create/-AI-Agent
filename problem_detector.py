from Lobster_Core import LobsterCore
import json
import re

lobster = LobsterCore()


def clean_json(text):
    text = re.sub(r"```json|```", "", text)
    return text.strip()


def detect_problem(project_state, error_msg):
    """
    系統級診斷引擎
    """

    files = project_state["files"]
    changed = project_state["changed"]

    prompt = f"""
你是一個資深軟體系統診斷專家。

目前專案檔案:
{files}

最近變動:
{changed}

錯誤訊息:
{error_msg}

請輸出 JSON：

{{
  "severity": "low/medium/high",
  "suspected_file": "檔名",
  "reason": "原因",
  "confidence": 0~1
}}
"""

    response = lobster.reason(prompt)

    try:
        return json.loads(clean_json(response))
    except Exception:
        return {
            "severity": "unknown",
            "suspected_file": None,
            "reason": "LLM_PARSE_FAIL",
            "confidence": 0
        }