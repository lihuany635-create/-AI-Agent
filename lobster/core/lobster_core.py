# lobster/core/lobster_core.py - Lazy Loading
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
        self._os = self._reflex_memory = self._episodic = None
        self._prompt_engine = self._learning = self._editor = None
        self._detector = self._engine = self._supervisor = None
        self._trigger = self._loop = None

    @property
    def os(self):
        if self._os is None:
            from os_controller import OSController
            self._os = OSController(workspace=".")
        return self._os

    @property
    def reflex_memory(self):
        if self._reflex_memory is None:
            from reflex_memory import ReflexMemory
            self._reflex_memory = ReflexMemory()
        return self._reflex_memory

    @property
    def episodic(self):
        if self._episodic is None:
            from episodic_memory import EpisodicMemory
            self._episodic = EpisodicMemory()
        return self._episodic

    @property
    def prompt_engine(self):
        if self._prompt_engine is None:
            from prompt_engine import PromptEngine
            self._prompt_engine = PromptEngine()
        return self._prompt_engine

    @property
    def learning(self):
        if self._learning is None:
            from learning_engine import LearningEngine
            self._learning = LearningEngine()
        return self._learning

    @property
    def editor(self):
        if self._editor is None:
            from terminal_editor import TerminalEditor
            self._editor = TerminalEditor()
        return self._editor

    @property
    def detector(self):
        if self._detector is None:
            from error_detector import ErrorDetector
            self._detector = ErrorDetector()
        return self._detector

    @property
    def engine(self):
        if self._engine is None:
            from repair_engine import RepairEngine
            self._engine = RepairEngine()
        return self._engine

    @property
    def supervisor(self):
        if self._supervisor is None:
            from reasoning_supervisor import ReasoningSupervisor
            self._supervisor = ReasoningSupervisor()
        return self._supervisor

    @property
    def trigger(self):
        if self._trigger is None:
            from repair_trigger import RepairTrigger
            self._trigger = RepairTrigger(self.engine, self.supervisor)
        return self._trigger

    @property
    def loop(self):
        if self._loop is None:
            from repair_loop_controller import RepairLoopController
            self._loop = RepairLoopController(self.detector, self.trigger)
        return self._loop

    def _build_identity(self): return build_identity(self.prompt_engine)
    def _infer(self, prompt, system=""): return infer(self.model, self.url, self.prompt_engine, prompt, system)
    def _think(self, text): return think(self, text)
    def _push_to_phone(self, q, a): push_to_phone(q, a)
    def _push_dev_confirm(self, s): push_dev_confirm(s)
    def process_input(self, text, reflex, router, mode="chat"): return route(self, text, reflex, mode)
    def execute_task(self, task): return execute_task(self, task)
    def act(self, action): return act(self, action)
    def run(self, prompt): return think(self, prompt)
    def reason(self, prompt): return self._infer(prompt, self._build_identity() + "\nJSON only.")
    def reflect(self, prompt): return self._infer(prompt, self._build_identity() + "\nJSON 格式自我反思。")
    def plan(self, prompt): return self._infer(prompt, self._build_identity() + "\nJSON 格式修復計畫。")
    def judge(self, prompt, context=""): return self._infer((context+"\n\n"+prompt) if context else prompt, self._build_identity()+"\n只回答 PASS 或 FAIL。")
    def repair(self, code, prompt): return repair(self, code, prompt)


CORE = LobsterCore()

def boot():
    print("Lobster Ready, model:", CORE.model)
    if _USE_GUARD:
        start_background_monitor(interval=30)
