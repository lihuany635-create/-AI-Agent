from pathlib import Path
from Lobster_Core import LobsterCore
from safe_editor import safe_apply_patch

lobster = LobsterCore()


def read_file(path):
    return Path(path).read_text(encoding="utf-8")


def apply_fix(project_state, repair_plan, test_result):
    """
    系統行為層：實際執行修復
    """

    target_file = repair_plan.get("file")

    if not target_file:
        return {"success": False, "reason": "NO_TARGET_FILE"}

    try:
        original_code = read_file(target_file)

        prompt = f"""
你是一個極端嚴格的 Python 修復工程師。

修復計畫:
{repair_plan}

測試預測:
{test_result}

原始程式碼:
{original_code}

請輸出完整修復後程式碼。
"""

        fixed_code = lobster.repair(original_code, prompt)

        if not fixed_code:
            return {"success": False, "reason": "EMPTY_FIX"}

        # 安全套用
        safe_apply_patch(target_file, fixed_code)

        return {"success": True}

    except Exception as e:
        return {"success": False, "reason": str(e)}