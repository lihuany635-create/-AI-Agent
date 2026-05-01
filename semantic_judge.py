from Lobster_Core import LobsterCore

lobster = LobsterCore()


def judge_semantic(project_state):
    """
    語意判斷中樞
    判斷目前專案是否存在語意錯誤
    """

    files = project_state["files"]
    changed = project_state["changed"]

    prompt = f"""
你是一個極端嚴格的軟體系統語意審查官。

目前專案檔案:
{files}

最近變動:
{changed}

請判斷系統是否語意健康。

只回答：
PASS 或 FAIL
"""

    result = lobster.judge(prompt, "")

    if "PASS" in result:
        return True
    else:
        return False