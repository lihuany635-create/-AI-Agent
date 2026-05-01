# lobster/repair/repair_interface.py

try:
    from agent_logger import get_logger
    logger = get_logger("lobster.repair")
except ImportError:
    import logging
    logger = logging.getLogger("lobster.repair")

def execute_task(core, task) -> str:
    if isinstance(task, dict) and "action" in task:
        return act(core, task["action"])
    if isinstance(task, str):
        from lobster.engine.infer_engine import think
        return think(core, task)
    return "（未知任務格式）"

def act(core, action: str) -> str:
    if action.startswith("RUN_PYTHON:"):
        file = action.split(":", 1)[1].strip()
        result = core.os.safe_run(["python", file])
        error = core.detector.detect_file_error(file)
        if error:
            return f"CRASH → AUTO REPAIR → {core.loop.run(file)}"
        return str(result)
    return f"（未知指令：{action}）"

def repair(core, code: str, prompt: str) -> str:
    from lobster.utils.identity import build_identity
    from lobster.engine.infer_engine import infer
    return infer(
        core.model, core.url, core.prompt_engine,
        f"{prompt}\n\n原始程式碼：\n{code}",
        f"{build_identity(core.prompt_engine)}\n只輸出完整修復後程式碼，不輸出任何解釋或 markdown。"
    )
