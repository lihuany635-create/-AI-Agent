"""
task_scheduler.py - 多模組協作任務排程系統
功能：
  - 將複雜任務拆解成多個步驟，依序執行
  - 每個步驟指定由哪個模組負責
  - 步驟失敗時自動重試或呼叫 repair_engine
  - 支援任務狀態查詢、暫停、取消
使用方式：
    from task_scheduler import TaskScheduler, Task, Step
    scheduler = TaskScheduler()
    task = Task("修復專案", steps=[
        Step("scan",   "project_scanner",  "掃描所有 .py 檔案"),
        Step("detect", "error_detector",   "偵測語法錯誤"),
        Step("repair", "repair_engine",    "自動修復錯誤"),
        Step("test",   "auto_test_engine", "執行測試驗證"),
    ])
    scheduler.submit(task)
    scheduler.run_all()
"""

import threading
import time
import uuid
import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

try:
    from agent_logger import get_logger
    logger = get_logger("task_scheduler")
except ImportError:
    import logging
    logger = logging.getLogger("task_scheduler")

# ── 資料結構 ────────────────────────────────────────────────────────────────

class TaskStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    CANCELLED = "cancelled"
    PAUSED    = "paused"

@dataclass
class Step:
    name:    str            # 步驟名稱（如 "scan"）
    module:  str            # 負責的模組名稱（如 "error_detector"）
    payload: str = ""       # 傳給模組的指令或資料
    max_retries: int = 2    # 失敗最多重試幾次
    # 執行後填入
    status:  TaskStatus = TaskStatus.PENDING
    result:  str = ""
    error:   str = ""
    retries: int = 0
    started_at:  str = ""
    finished_at: str = ""

@dataclass
class Task:
    name:  str
    steps: list[Step] = field(default_factory=list)
    # 自動填入
    id:          str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status:      TaskStatus = TaskStatus.PENDING
    created_at:  str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds"))
    started_at:  str = ""
    finished_at: str = ""
    priority:    int = 5  # 1(高) ~ 10(低)

    def progress(self) -> str:
        done  = sum(1 for s in self.steps if s.status == TaskStatus.DONE)
        total = len(self.steps)
        pct   = int(done / total * 100) if total else 0
        bar   = "█" * (pct // 10) + "░" * (10 - pct // 10)
        return f"{bar} {done}/{total} ({pct}%)"

# ── 模組執行器 ──────────────────────────────────────────────────────────────

class ModuleRunner:
    """嘗試呼叫對應模組執行步驟，找不到模組就用 Lobster_Core 代勞"""

    _registry: dict[str, Callable] = {}

    @classmethod
    def register(cls, module_name: str, fn: Callable):
        cls._registry[module_name] = fn

    @classmethod
    def run(cls, step: Step, context: dict = None) -> str:
        """
        context 是任務共享狀態，各步驟可以讀取前步驟的結果。
        """
        ctx = context or {}
        if step.module in cls._registry:
            return cls._registry[step.module](step.payload, ctx)
        return cls._try_dynamic(step, ctx)

    @classmethod
    def _try_dynamic(cls, step: Step, ctx: dict) -> str:

        # ── repair_planner：需要 project_state ─────────────────────────────
        if step.module == "repair_planner":
            try:
                from repair_planner import plan_repair
                project_state = ctx.get("project_state", {
                    "files": [], "changed": []
                })
                result = plan_repair(project_state)
                # 驗證 file 欄位是否真的存在於磁碟
                import pathlib as _pl
                suggested_file = result.get("file", "")
                if suggested_file and _pl.Path(suggested_file).exists():
                    ctx["repair_plan"] = result
                    logger.info(f"  規劃建議修復：{suggested_file}")
                else:
                    # 模型回傳的不是真實路徑，忽略規劃結果，保留 error_detector 的結果
                    logger.warning(f"  repair_planner 回傳無效路徑 '{suggested_file}'，"
                                   f"改用 error_detector 的結果")
                    ctx["repair_plan"] = {"repair": False, "file": None,
                                          "reason": "規劃路徑無效，改用偵測結果"}
                return str(result)
            except Exception as e:
                raise RuntimeError(f"repair_planner 失敗：{e}")

        # ── bug_learning_engine：需要 project_state + diagnosis + result ───
        if step.module == "bug_learning_engine":
            try:
                from bug_learning_engine import learn_bug
                learn_bug(
                    project_state = ctx.get("project_state", {"changed": []}),
                    diagnosis     = str(ctx.get("error_info", {})),
                    repair_plan   = str(ctx.get("repair_plan", {})),
                    result        = ctx.get("repair_success", False),
                )
                return "已學習此次修復經驗"
            except Exception as e:
                return f"bug_learning_engine 記錄失敗（不影響修復）：{e}"

        # ── error_detector：回傳結果存進 ctx ───────────────────────────────
        if step.module == "error_detector":
            try:
                from error_detector import ErrorDetector
                target = step.payload.replace("偵測錯誤：", "").strip()
                det = ErrorDetector()
                import pathlib
                py_files = list(pathlib.Path(target).rglob("*.py")) if pathlib.Path(target).is_dir() else [pathlib.Path(target)]
                for f in py_files[:20]:  # 最多掃 20 個
                    err = det.detect_file_error(str(f))
                    if err:
                        ctx["error_info"] = err
                        ctx["error_file"] = str(f)
                        return f"發現錯誤：{f.name} → {err.get('type')} line {err.get('line')}"
                return "未發現錯誤"
            except Exception as e:
                raise RuntimeError(f"error_detector 失敗：{e}")

        # ── repair_engine：優先用 Step 3 規劃的目標，其次用 Step 2 偵測結果 ──
        if step.module == "repair_engine":
            try:
                from repair_engine import RepairEngine
                from reasoning_supervisor import ReasoningSupervisor

                # 優先採用 repair_planner 的規劃結果
                plan = ctx.get("repair_plan", {})
                if isinstance(plan, dict) and plan.get("repair") and plan.get("file"):
                    file_path = plan["file"]
                    logger.info(f"  使用規劃目標：{file_path}（原因：{plan.get('reason','')}）")
                else:
                    file_path = ctx.get("error_file", "")

                if not file_path:
                    return "沒有需要修復的檔案"

                error_info = ctx.get("error_info", {})
                supervisor = ReasoningSupervisor()
                engine     = RepairEngine()
                result     = engine.repair(file_path, error_info, supervisor)
                ctx["repair_success"] = result.get("status") == "FIXED"
                ctx["repair_result"]  = result
                return f"修復結果：{result.get('status')}（備份：{result.get('backup','')}）"
            except Exception as e:
                raise RuntimeError(f"repair_engine 失敗：{e}")

        # ── project_scanner：建立 project_state ───────────────────────────
        if step.module == "project_scanner":
            try:
                import pathlib
                target = step.payload.replace("掃描目標：", "").strip() or "."
                p = pathlib.Path(target)
                files = [str(f) for f in p.rglob("*.py") if ".git" not in str(f)][:50]
                project_state = {"files": files, "changed": files[-5:] if files else []}
                ctx["project_state"] = project_state
                return f"掃描完成：{len(files)} 個 .py 檔案"
            except Exception as e:
                raise RuntimeError(f"project_scanner 失敗：{e}")

        # ── repair_validator：從 ctx 取得修復前後程式碼 ───────────────────
        if step.module == "repair_validator":
            try:
                from repair_validator import RepairValidator
                repair_result = ctx.get("repair_result", {})
                error_file    = ctx.get("error_file", "")
                backup_path   = repair_result.get("backup", "")

                if not error_file or not backup_path:
                    return "略過驗證（無修復記錄）"

                import pathlib as _pl
                before_code = _pl.Path(backup_path).read_text(encoding="utf-8") \
                              if _pl.Path(backup_path).exists() else ""
                after_code  = _pl.Path(error_file).read_text(encoding="utf-8") \
                              if _pl.Path(error_file).exists() else ""

                if not before_code or not after_code:
                    return "略過驗證（檔案不存在）"

                val = RepairValidator().validate(before_code, after_code)
                ctx["validation_result"] = val
                return f"驗證{'通過' if val.get('valid') else '失敗'}：{val}"
            except Exception as e:
                return f"repair_validator 略過：{e}"

        # ── 其他模組：動態 import ──────────────────────────────────────────
        module_map = {
            "auto_test_engine": ("auto_test_engine",  "AutoTestEngine",  "run"),
            "memory_engine":    ("memory_engine",     "MemoryEngine",    "store"),
            "problem_detector": ("problem_detector",  "ProblemDetector", "detect"),
            "code_editor":      ("code_editor",       "CodeEditor",      "edit"),
            "repair_validator": ("repair_validator", "RepairValidator", "validate"),
        }
        if step.module in module_map:
            mod_name, class_name, method = module_map[step.module]
            try:
                import importlib
                mod = importlib.import_module(mod_name)
                cls_obj = getattr(mod, class_name)()
                return str(getattr(cls_obj, method)(step.payload))
            except Exception as e:
                raise RuntimeError(f"模組 {step.module} 執行失敗：{e}")

        raise RuntimeError(f"未知模組：{step.module}，不允許自動切換模型")

# ── 排程器 ──────────────────────────────────────────────────────────────────

class TaskScheduler:
    def __init__(self):
        self._queue:   list[Task] = []
        self._history: list[Task] = []
        self._lock = threading.Lock()
        self._running = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # 預設不暫停
        logger.info("TaskScheduler 啟動")

    # ── 任務管理 ──────────────────────────────────────────────────────────

    def submit(self, task: Task) -> str:
        """加入任務佇列，回傳任務 ID"""
        with self._lock:
            self._queue.append(task)
            self._queue.sort(key=lambda t: t.priority)
        logger.info(f"任務已提交：[{task.id}] {task.name}（{len(task.steps)} 個步驟）")
        return task.id

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            for t in self._queue:
                if t.id == task_id and t.status == TaskStatus.PENDING:
                    t.status = TaskStatus.CANCELLED
                    self._queue.remove(t)
                    self._history.append(t)
                    logger.info(f"任務已取消：{task_id}")
                    return True
        return False

    def pause(self):
        self._pause_event.clear()
        logger.info("排程器已暫停")

    def resume(self):
        self._pause_event.set()
        logger.info("排程器已繼續")

    def status(self, task_id: str) -> Optional[Task]:
        all_tasks = self._queue + self._history
        return next((t for t in all_tasks if t.id == task_id), None)

    def list_tasks(self) -> list[dict]:
        all_tasks = self._queue + self._history
        return [{"id": t.id, "name": t.name, "status": t.status.value, "progress": t.progress()} for t in all_tasks]

    # ── 執行 ──────────────────────────────────────────────────────────────

    def run_all(self, block: bool = True):
        """執行佇列中所有任務"""
        if block:
            self._run_loop()
        else:
            t = threading.Thread(target=self._run_loop, daemon=True)
            t.start()

    def _run_loop(self):
        self._running = True
        while self._running:
            self._pause_event.wait()  # 暫停點
            with self._lock:
                pending = [t for t in self._queue if t.status == TaskStatus.PENDING]
            if not pending:
                time.sleep(0.5)
                continue
            task = pending[0]
            self._execute_task(task)

    def _execute_task(self, task: Task):
        now = lambda: datetime.datetime.now().isoformat(timespec="seconds")
        task.status = TaskStatus.RUNNING
        task.started_at = now()
        logger.info(f"開始執行任務：[{task.id}] {task.name}")

        # 任務共享狀態：各步驟可讀取前步驟的結果
        context: dict = {}

        for step in task.steps:
            if task.status == TaskStatus.CANCELLED:
                break

            self._pause_event.wait()
            step.status = TaskStatus.RUNNING
            step.started_at = now()
            logger.info(f"  步驟 [{step.name}] 由 {step.module} 執行中...")

            success = False
            for attempt in range(step.max_retries + 1):
                try:
                    step.result = ModuleRunner.run(step, context)
                    step.status = TaskStatus.DONE
                    step.finished_at = now()
                    logger.info(f"  步驟 [{step.name}] 完成：{step.result[:60]}")
                    success = True
                    break
                except Exception as e:
                    step.retries = attempt + 1
                    step.error = str(e)
                    logger.warning(f"  步驟 [{step.name}] 第 {attempt+1} 次失敗：{e}")
                    if attempt < step.max_retries:
                        time.sleep(1)

            if not success:
                # bug_learning_engine 失敗不中止任務
                if step.module == "bug_learning_engine":
                    step.status = TaskStatus.DONE
                    step.result = "（學習步驟略過）"
                    continue

                step.status = TaskStatus.FAILED
                step.finished_at = now()
                task.status = TaskStatus.FAILED
                task.finished_at = now()
                logger.error(f"任務 [{task.id}] 在步驟 [{step.name}] 失敗，中止")
                with self._lock:
                    if task in self._queue:
                        self._queue.remove(task)
                    self._history.append(task)
                return

        if task.status != TaskStatus.FAILED and task.status != TaskStatus.CANCELLED:
            task.status = TaskStatus.DONE
        task.finished_at = now()
        logger.info(f"任務完成：[{task.id}] {task.name}")
        with self._lock:
            if task in self._queue:
                self._queue.remove(task)
            self._history.append(task)


# ── 快捷函式：建立常用任務 ─────────────────────────────────────────────────

def create_auto_repair_task(target_file: str = ".") -> Task:
    """建立「自動掃描並修復專案」任務"""
    return Task(
        name=f"自動修復：{target_file}",
        priority=3,
        steps=[
            Step("scan",    "project_scanner",  f"掃描目標：{target_file}"),
            Step("detect",  "error_detector",   f"偵測錯誤：{target_file}"),
            Step("plan",    "repair_planner",   "規劃修復策略"),
            Step("repair",  "repair_engine",    "執行修復"),
            Step("validate","repair_validator", "驗證修復結果"),
            Step("learn",   "bug_learning_engine", "學習此次修復經驗"),
        ]
    )

def create_code_review_task(file_path: str) -> Task:
    """建立「程式碼審查」任務"""
    return Task(
        name=f"程式碼審查：{file_path}",
        priority=5,
        steps=[
            Step("scan",    "project_scanner", f"分析：{file_path}"),
            Step("graph",   "code_graph_engine", f"建立依賴圖：{file_path}"),
            Step("problem", "problem_detector",  f"找出問題：{file_path}"),
            Step("suggest", "reasoning_supervisor", "給出改善建議"),
        ]
    )


# ── 使用範例 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    scheduler = TaskScheduler()

    # 建立一個修復任務
    task = create_auto_repair_task(".")
    task_id = scheduler.submit(task)
    print(f"任務 ID：{task_id}")
    print("任務清單：", scheduler.list_tasks())

    # 直接執行（會嘗試呼叫各模組）
    scheduler.run_all(block=True)

    # 查看結果
    finished = scheduler.status(task_id)
    if finished:
        print(f"\n結果：{finished.status.value}")
        for s in finished.steps:
            icon = "✓" if s.status == TaskStatus.DONE else "✗"
            print(f"  {icon} [{s.name}] {s.result[:60] or s.error[:60]}")
