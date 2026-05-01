# lobster/core/lobster_core.py — Lazy Loading 版
# 所有子系統只在第一次使用時才初始化，節省啟動時間和記憶體

try:
    from ollama_guard import start_background_monitor, is_online
    _USE_GUARD = True
except ImportError:
    _USE_GUARD = False

try:
    from agent_logger import get_logger
    logger = get_logger("lobster.core")
except ImportError:
    import logging
    logger = logging.getLogger("lobster.core")

from lobster.utils.identity import build_identity
from lobster.engine.infer_engine import infer, think
from lobster.router.input_router import route
from lobster.repair.repair_interface import execute_task, act, repair
from lobster.integration.push import push_to_phone, push_dev_confirm


class LobsterCore:

    def __init__(self, model="gemma4:latest"):
        self.model = model
        self.url   = "http://localhost:11434/api/generate"
        self._os            = None
        self._reflex_memory = None
        self._episodic      = None
        self._prompt_engine = None
        self._learning      = None
        self._editor        = None
        self._detector      = None
        self._engine        = None
        self._supervisor    = None
        self._trigger       = None
        self._loop          = None

    @property
    def os(self):
        if self._os is None:
            from os_controller import OSController
            self._os = OSController(workspace=".")
            logger.debug("[Lazy] OSController 初始化")
        return self._os

    @property
    def reflex_memory(self):
        if self._reflex_memory is None:
            from reflex_memory import ReflexMemory
            self._reflex_memory = ReflexMemory()
            logger.debug("[Lazy] ReflexMemory 初始化")
        return self._reflex_memory

    @property
    def episodic(self):
        if self._episodic is None:
            from episodic_memory import EpisodicMemory
            self._episodic = EpisodicMemory()
            logger.debug("[Lazy] EpisodicMemory 初始化")
        return self._episodic

    @property
    def prompt_engine(self):
        if self._prompt_engine is None:
            from prompt_engine import PromptEngine
            self._prompt_engine = PromptEngine()
            logger.debug("[Lazy] PromptEngine 初始化")
        return self._prompt_engine

    @property
    def learning(self):
        if self._learning is None:
            from learning_engine import LearningEngine
            self._learning = LearningEngine()
            logger.debug("[Lazy] LearningEngine 初始化")
        return self._learning

    @property
    def editor(self):
        if self._editor is None:
            from terminal_editor import TerminalEditor
            self._editor = TerminalEditor()
            logger.debug("[Lazy] TerminalEditor 初始化")
        return self._editor

    @property
    def detector(self):
        if self._detector is None:
            from error_detector import ErrorDetector
            self._detector = ErrorDetector()
            logger.debug("[Lazy] ErrorDetector 初始化")
        return self._detector

    @property
    def engine(self):
        if self._engine is None:
            from repair_engine import RepairEngine
            self._engine = RepairEngine()
            logger.debug("[Lazy] RepairEngine 初始化")
        return self._engine

    @property
    def supervisor(self):
        if self._supervisor is None:
            from reasoning_supervisor import ReasoningSupervisor
            self._supervisor = ReasoningSupervisor()
            logger.debug("[Lazy] ReasoningSupervisor 初始化")
        return self._supervisor

    @property
    def trigger(self):
        if self._trigger is None:
            from repair_trigger import RepairTrigger
            self._trigger = RepairTrigger(self.engine, self.supervisor)
            logger.debug("[Lazy] RepairTrigger 初始化")
        return self._trigger

    @property
    def loop(self):
        if self._loop is None:
            from repair_loop_controller import RepairLoopController
            self._loop = RepairLoopController(self.detector, self.trigger)
            logger.debug("[Lazy] RepairLoopController 初始化")
        return self._loop

    def _build_identity(self) -> str:
        return build_identity(self.prompt_engine)

    def _infer(self, prompt: str, system: str = "") -> str:
        return infer(self.model, self.url, self.prompt_engine, prompt, system)

    def _think(self, text: str) -> str:
        return think(self, text)

    def _push_to_phone(self, question: str, answer: str):
        push_to_phone(question, answer)

    def _push_dev_confirm(self, step_preview: str):
        push_dev_confirm(step_preview)

    def process_input(self, text: str, reflex, router, mode: str = "chat") -> str:
        return route(self, text, reflex, mode)

    def execute_task(self, task) -> str:
        return execute_task(self, task)

    def act(self, action: str) -> str:
        return act(self, action)

    def run(self, prompt: str) -> str:
        return think(self, prompt)

    def reason(self, prompt: str) -> str:
        return self._infer(prompt, f"{self._build_identity()}\n只輸出 JSON，不輸出任何多餘文字。")

    def reflect(self, prompt: str) -> str:
        return self._infer(prompt, f"{self._build_identity()}\n進行系統自我反思，輸出 JSON 格式分析。")

    def plan(self, prompt: str) -> str:
        return self._infer(prompt, f"{self._build_identity()}\n資深 Python 架構師，輸出 JSON 格式修復計畫。")

    def judge(self, prompt: str, context: str = "") -> str:
        full = f"{context}\n\n{prompt}" if context else prompt
        return self._infer(full, f"{self._build_identity()}\n只回答 PASS 或 FAIL，不輸出其他任何內容。")

    def repair(self, code: str, prompt: str) -> str:
        return repair(self, code, prompt)


CORE = LobsterCore()


def boot():
    print("🦞 Lobster Self-Healing Core Ready")
    print(f"   模型：{CORE.model}  端點：{CORE.url}")
    if _USE_GUARD:
        start_background_monitor(interval=30)
        print(f"   Ollama：{'在線' if is_online(force=True) else '離線（離線模式）'}")
