import config
import agent_basic

from project_scanner import scan_project
from repair_planner import plan_repair
from semantic_judge import judge_semantic
from code_graph_engine import build_code_graph

from problem_detector import detect_problem
from auto_test_engine import run_auto_tests
from code_editor import apply_fix
from backup_engine import rollback

from execution_cognition_engine import analyze_trace
from error_memory import record_error
from memory_engine import record_task, summarize_memory
from bug_learning_engine import learn_bug, suggest_fix


def run():

    print("SYSTEM BOOT")

    if not hasattr(config, "SYSTEM_KEY"):
        raise RuntimeError("SYSTEM KEY NOT FOUND")

    print("KEY VERIFIED")

    core = agent_basic.start()
    print("AGENT ALIVE")

    # 感知
    project_state = scan_project()

    # 語意健康
    semantic_ok = judge_semantic(project_state)

    trace = {
        "input": "PROJECT_SCAN",
        "eval_result": semantic_ok,
        "final_result": None
    }
    analyze_trace(trace)

    if semantic_ok:
        print("PROJECT HEALTHY")
        build_code_graph(project_state)
        return core

    print("SEMANTIC ISSUE DETECTED")

    # 診斷
    diagnosis = detect_problem(project_state, "semantic_failure")

    # 學習策略優先
    learned_fix = suggest_fix(project_state)

    if learned_fix:
        repair_plan = learned_fix["repair_plan"]
        print("USING LEARNED STRATEGY")
    else:
        repair_plan = plan_repair(project_state)

    # 測試
    test_result = run_auto_tests(project_state, repair_plan)

    # 修復
    fix_result = apply_fix(project_state, repair_plan, test_result)

    success = fix_result.get("success", False)

    # 回滾
    if not success:
        print("FIX FAILED → ROLLBACK")
        rollback(project_state)
    else:
        print("FIX SUCCESS")

    # 認知
    trace2 = {
        "input": "REPAIR_PROCESS",
        "eval_result": diagnosis,
        "final_result": success
    }
    analyze_trace(trace2)

    # 記憶
    record_error(project_state, diagnosis, repair_plan, success)
    record_task(project_state, repair_plan, success)

    # 學習
    learn_bug(project_state, diagnosis, repair_plan, success)

    # 技能演化
    summarize_memory()

    return core