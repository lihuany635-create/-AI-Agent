from Lobster_Core import LobsterCore

lobster = LobsterCore()


def run_auto_tests(project_state, repair_plan):
    """
    自動測試系統：判斷修復計畫是否可行。

    用法範例：
        from auto_test_engine import run_auto_tests
        result = run_auto_tests(
            project_state={"files": ["main.py"], "changed": ["main.py"]},
            repair_plan={"file": "main.py", "reason": "修復語法錯誤"}
        )
        # 回傳：{"test_pass": True/False, "confidence": 0~1, "risk": "low/medium/high"}

    參數：
        project_state (dict): 專案狀態，包含 files（檔案列表）和 changed（變更檔案）
        repair_plan (dict): 修復計畫，包含 file（目標檔案）和 reason（修復原因）

    回傳：
        dict: {"test_pass": bool, "confidence": float, "risk": str}
    """

    prompt = f"""
你是一個極端嚴格的 AI 測試工程師。

目前系統狀態:
{project_state}

修復計畫:
{repair_plan}

請判斷修復是否可能成功。

輸出 JSON：

{{
  "test_pass": true/false,
  "confidence": 0~1,
  "risk": "low/medium/high"
}}
"""

    result = lobster.reason(prompt)

    try:
        import json
        return json.loads(result)
    except Exception:
        return {
            "test_pass": False,
            "confidence": 0,
            "risk": "unknown"
        }