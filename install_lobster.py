"""
install_lobster.py
執行此腳本會自動將所有 lobster 子模組寫入專案資料夾
用法：python install_lobster.py
"""
import pathlib

BASE = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面\AI-Agent\lobster")

FILES = {}

FILES["utils/identity.py"] = """\
# lobster/utils/identity.py
from cognition_state_manager import get_persona

def build_identity(prompt_engine) -> str:
    try:
        return prompt_engine.SYSTEM
    except Exception:
        persona = get_persona()
        return (
            f"你是「{persona.get('name', '立')}」，本地 AI 系統核心。"
            "永遠使用繁體中文回覆，語氣自然像朋友，簡潔有重點。"
        )
"""

FILES["tools/file_tool.py"] = """\
# lobster/tools/file_tool.py
import re
import pathlib

def try_read_file(text: str) -> str:
    file_match = re.search(r'([\\w\\u4e00-\\u9fff\\-_.]+\\.\\w{1,5})', text)
    if not file_match:
        return ""
    filename = file_match.group(1)
    search_paths = [
        pathlib.Path("."),
        pathlib.Path("learn_inbox"),
        pathlib.Path("memory"),
        pathlib.Path("projects"),
    ]
    target = None
    for base in search_paths:
        candidate = base / filename
        if candidate.exists():
            target = candidate
            break
    if not target:
        return ""
    try:
        ext = target.suffix.lower()
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(target))
                content = ""
                for page in reader.pages[:10]:
                    page_text = page.extract_text()
                    if page_text:
                        content += page_text + "\\n"
                return content[:3000]
            except Exception:
                return ""
        content = target.read_text(encoding="utf-8", errors="ignore")
        return content[:3000]
    except Exception:
        return ""
"""

FILES["integration/push.py"] = """\
# lobster/integration/push.py
import sys
import threading

try:
    from agent_logger import get_logger
    logger = get_logger("lobster.integration.push")
except ImportError:
    import logging
    logger = logging.getLogger("lobster.integration.push")

_PKG = r"C:\\Users\\ACER\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages"

def _ensure_pkg():
    if _PKG not in sys.path:
        sys.path.insert(0, _PKG)

def push_to_phone(question: str, answer: str):
    try:
        _ensure_pkg()
        import bot_config, telebot
        if len(answer) < 30:
            return
        def _send():
            try:
                bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN, parse_mode=None)
                q = question[:80].encode("utf-8", errors="ignore").decode("utf-8")
                a = answer[:500].encode("utf-8", errors="ignore").decode("utf-8")
                msg = "立 AI 回覆\\n\\n問：" + q + "\\n\\n答：" + a
                if len(answer) > 500:
                    msg += "\\n...（完整回覆請看電腦）"
                for cid in bot_config.ALLOWED_CHAT_IDS:
                    bot.send_message(cid, msg)
            except Exception as e:
                logger.error(f"[推送] 失敗：{e}")
        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        logger.error(f"[推送] 外層錯誤：{e}")

def push_dev_confirm(step_preview: str):
    try:
        _ensure_pkg()
        import bot_config
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        def _send():
            try:
                try:
                    import telegram_bot as _tb
                    _bot = _tb.bot
                except Exception:
                    import telebot
                    _bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN, parse_mode=None)
                msg = "🤖 立 AI 開發確認\\n\\n" + step_preview[:600]
                kb = InlineKeyboardMarkup()
                kb.row(
                    InlineKeyboardButton("✅ 確認", callback_data="dev_confirm"),
                    InlineKeyboardButton("❌ 取消", callback_data="dev_cancel"),
                )
                for cid in bot_config.ALLOWED_CHAT_IDS:
                    _bot.send_message(cid, msg, reply_markup=kb)
                logger.info("[推送] 開發確認已推送到手機（含按鈕）")
            except Exception as e:
                logger.error(f"[推送] 開發確認失敗：{e}")
        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        logger.error(f"[推送] 開發確認外層錯誤：{e}")
"""

FILES["engine/infer_engine.py"] = """\
# lobster/engine/infer_engine.py
import threading
import requests

try:
    from ollama_guard import safe_infer
    _USE_GUARD = True
except ImportError:
    _USE_GUARD = False

try:
    from agent_logger import get_logger
    logger = get_logger("lobster.engine.infer")
except ImportError:
    import logging
    logger = logging.getLogger("lobster.engine.infer")

try:
    from youtube_bridge import handle_youtube_input, extract_youtube_url
    _USE_YOUTUBE = True
except ImportError:
    _USE_YOUTUBE = False

try:
    from claude_desktop_bridge import get_bridge as get_claude_bridge
    _USE_CLAUDE_BRIDGE = True
except ImportError:
    _USE_CLAUDE_BRIDGE = False

try:
    from model_selector import get_selector
    _USE_SELECTOR = True
except ImportError:
    _USE_SELECTOR = False

from lobster.utils.identity import build_identity
from lobster.tools.file_tool import try_read_file
from lobster.integration.push import push_to_phone


def infer(model: str, url: str, prompt_engine, prompt: str, system: str = "") -> str:
    sys_prompt = system or build_identity(prompt_engine)
    if _USE_GUARD:
        return safe_infer(prompt=prompt, model=model, system=sys_prompt, timeout=180, max_retries=3)
    try:
        r = requests.post(url, json={
            "model": model, "prompt": prompt,
            "system": sys_prompt, "stream": False,
        }, timeout=180)
        r.raise_for_status()
        return r.json().get("response", "")
    except Exception as e:
        return "[LLM ERROR] " + str(e)


def think(core, text: str) -> str:
    if _USE_YOUTUBE and extract_youtube_url(text):
        def _infer_fn(prompt): return infer(core.model, core.url, core.prompt_engine, prompt)
        result = handle_youtube_input(text, _infer_fn)
        if result:
            push_to_phone(text, result)
            return result

    recent = core.episodic.search_recent(10)
    for ep in reversed(recent):
        if ep["input"].strip() == text.strip() and ep.get("response"):
            resp = ep["response"]
            if "[LLM ERROR]" not in resp and len(resp) > 5:
                logger.info(f"[think] 快取命中：{text[:30]}")
                return resp

    file_content = try_read_file(text)
    system = build_identity(core.prompt_engine)
    prompt = core.prompt_engine.build_prompt(text, core.episodic)

    if file_content:
        prompt = f"[檔案內容]（使用者問的檔案，根據這個內容回答）\\n{file_content}\\n\\n{prompt}"

    if _USE_SELECTOR:
        selected = get_selector().select(text)
        if selected != core.model:
            logger.info(f"[think] 切換模型：{core.model} → {selected}")
            core.model = selected

    logger.info(f"[think] 推論（{core.model}）：{text[:40]}")
    result = infer(core.model, core.url, core.prompt_engine, prompt, system)

    if result and "[LLM ERROR]" not in result:
        push_to_phone(text, result)

    return result
"""

FILES["repair/repair_interface.py"] = """\
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
        f"{prompt}\\n\\n原始程式碼：\\n{code}",
        f"{build_identity(core.prompt_engine)}\\n只輸出完整修復後程式碼，不輸出任何解釋或 markdown。"
    )
"""

FILES["router/input_router.py"] = """\
# lobster/router/input_router.py
import re
import threading

try:
    from agent_logger import get_logger
    logger = get_logger("lobster.router")
except ImportError:
    import logging
    logger = logging.getLogger("lobster.router")

try:
    from terminal_engine import get_terminal
    _USE_TERMINAL = True
except ImportError:
    _USE_TERMINAL = False

try:
    from dev_tool import get_tool as get_dev_tool
    _USE_DEV_TOOL = True
except ImportError:
    _USE_DEV_TOOL = False

try:
    from self_healer import get_healer
    _USE_HEALER = True
except ImportError:
    _USE_HEALER = False

try:
    from model_selector import get_selector
    _USE_SELECTOR = True
except ImportError:
    _USE_SELECTOR = False

try:
    from claude_desktop_bridge import get_bridge as get_claude_bridge
    _USE_CLAUDE_BRIDGE = True
except ImportError:
    _USE_CLAUDE_BRIDGE = False

try:
    import sys as _sys_dc
    _PKG_DC = r"C:\\Users\\ACER\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages"
    if _PKG_DC not in _sys_dc.path:
        _sys_dc.path.insert(0, _PKG_DC)
    from desktop_control import get_control
    _USE_DESKTOP = True
except Exception:
    _USE_DESKTOP = False

from lobster.integration.push import push_to_phone


def route(core, text: str, reflex, mode: str = "chat") -> str:
    logger.info(f"[router] [{mode}] 收到：{text[:60]}")

    if mode == "terminal":
        if _USE_TERMINAL:
            terminal = get_terminal()
            t = text.strip()
            if t in ["確認", "好", "執行", "yes", "ok", "是"] and terminal.has_pending():
                return terminal.confirm()
            if t in ["取消", "不", "算了", "no", "cancel"] and terminal.has_pending():
                return terminal.cancel()
            if t in ["指令歷史", "歷史"]:
                return terminal.get_history()
            result = terminal.handle(text)
            if result is not None:
                return result
            return f"無法執行指令：{text[:50]}"
        return "終端模式未載入"

    if mode == "dev":
        if _USE_DEV_TOOL:
            tool = get_dev_tool()
            t = text.strip()
            if any(kw in t for kw in ["繼續作業", "繼續上次", "繼續開發", "接著做", "繼續做", "我要繼續", "繼續專案"]):
                if tool.state.request and (tool.state.active or tool.state.remaining_groups()):
                    tool.state.active = True
                    tool.state.paused = False
                    tool.state.save()
                    done = len(tool.state.completed_groups)
                    total = len(tool.state.groups)
                    remaining = tool.state.remaining_groups()
                    threading.Thread(target=tool._push_mindmap, daemon=True).start()
                    return (
                        f"🔄 繼續上次的專案：{tool.state.request[:40]}\\n"
                        f"已完成 {done}/{total} 個模組，剩餘 {len(remaining)} 個\\n"
                        "請在手機選擇要繼續哪個模組"
                    )
                return "目前沒有進行中的專案，請輸入新的需求開始開發。"
            handled = tool.handle_callback(f"dt_input_{t}")
            if not handled:
                threading.Thread(target=tool.start, args=(t,), daemon=True).start()
                return "🤖 開始規劃，請稍候，完成後會推送到手機..."

    if mode == "desktop":
        if _USE_DESKTOP:
            result = get_control().handle(text)
            if result is not None:
                return result
        return "找不到對應的桌面指令，請嘗試：截圖、列出視窗、查看資料夾"

    if mode == "teach":
        try:
            from long_term_memory import get_memory
            get_memory().store(text, tags=["user_teach"], importance=8, source="teach_mode")
            return f"✅ 已學習：{text[:60]}"
        except Exception as e:
            return f"存入記憶庫失敗：{e}"

    if mode == "database":
        try:
            from claude_knowledge import get_knowledge
            results = get_knowledge().search(text, top_k=3)
            if results:
                lines = ["📚 找到 " + str(len(results)) + " 筆相關知識："]
                for r in results:
                    lines.append("\\n【" + r['category'] + "】" + r['content'][:150])
                return "\\n".join(lines)
            return f"知識庫中找不到「{text[:40]}」的相關資料"
        except Exception as e:
            return f"知識庫查詢失敗：{e}"

    # chat 模式
    _claude_match = (
        re.match(r"^問\\s*Claude[：:]\\s*(.+)", text, re.IGNORECASE) or
        re.match(r"^去找\\s*Claude\\s*學習[：:]\\s*(.+)", text, re.IGNORECASE) or
        re.match(r"^請問\\s*Claude[：:]\\s*(.+)", text, re.IGNORECASE)
    )
    _loop_match = re.match(r"^(去找\\s*Claude\\s*對話學習|Claude\\s*對話學習)[：:]\\s*(.+)", text, re.IGNORECASE)

    if _USE_CLAUDE_BRIDGE and _loop_match:
        question = _loop_match.group(2).strip()
        worker_ref = getattr(core, "_worker_ref", None)
        def _show_bar(show):
            if worker_ref:
                try: worker_ref.claude_bar_sig.emit(show)
                except Exception: pass
        def _notify(msg):
            if worker_ref:
                try: worker_ref.claude_reply_sig.emit(msg)
                except Exception: pass
            push_to_phone("Claude", msg)
        def _run_loop():
            try:
                _show_bar(True)
                result = get_claude_bridge().chat_loop(question, max_rounds=20, notify_fn=_notify, ui_ref=None)
                _notify("✅ 對話學習完成：" + result)
            except Exception as e:
                logger.warning(f"[router] 對話循環失敗：{e}")
            finally:
                _show_bar(False)
        threading.Thread(target=_run_loop, daemon=True).start()
        return "🔄 開始與 Claude 對話學習：" + question + "\\n隨時可以按停止按鈕結束"

    if _USE_CLAUDE_BRIDGE and _claude_match:
        question = _claude_match.group(1).strip()
        def _run_single():
            try:
                get_claude_bridge().chat_loop(question, max_rounds=20, notify_fn=push_to_phone, ui_ref=getattr(core, "_ui_ref", None))
            except Exception as e:
                logger.warning(f"[router] Claude 循環失敗：{e}")
        threading.Thread(target=_run_single, daemon=True).start()
        return "🔄 開始與 Claude 對話，隨時可按停止按鈕結束"

    if any(kw in text for kw in ["Claude知識庫", "claude知識庫", "知識庫統計", "查看知識庫"]):
        try:
            from claude_knowledge import get_knowledge
            return get_knowledge().get_stats()
        except Exception as e:
            return f"Claude 知識庫未載入：{e}"

    mem = core.reflex_memory.get(text)
    if mem:
        return mem

    r = reflex.analyze(text)
    if r:
        return r

    if _USE_HEALER:
        t = text.strip()
        if any(k in t for k in ["自我診斷", "掃描自己", "健康檢查", "自動修復自己"]):
            def _heal():
                get_healer().scan_and_heal(notify_fn=lambda msg: push_to_phone("自我診斷", msg))
            threading.Thread(target=_heal, daemon=True).start()
            return "開始自我診斷，完成後通知你。"
        if any(k in t for k in ["診斷報告", "上次診斷", "健康報告"]):
            return get_healer().get_last_report()

    if _USE_SELECTOR:
        t = text.strip()
        if any(k in t for k in ["目前模型", "用什麼模型", "哪個模型", "模型狀態"]):
            return get_selector().status()
        if "模型" in t and ("切換" in t or "換成" in t):
            _m = re.search(r"[\\w.:]{3,}", t.replace("切換模型", "").replace("切換", "").strip())
            if _m:
                result = get_selector().force_switch(_m.group(0))
                core.model = get_selector().current()
                return result

    from lobster.engine.infer_engine import think
    return think(core, text)
"""

FILES["core/lobster_core.py"] = """\
# lobster/core/lobster_core.py

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

from os_controller import OSController
from reflex_memory import ReflexMemory
from episodic_memory import EpisodicMemory
from prompt_engine import PromptEngine
from learning_engine import LearningEngine
from terminal_editor import TerminalEditor
from error_detector import ErrorDetector
from repair_engine import RepairEngine
from reasoning_supervisor import ReasoningSupervisor
from repair_trigger import RepairTrigger
from repair_loop_controller import RepairLoopController

from lobster.utils.identity import build_identity
from lobster.engine.infer_engine import infer, think
from lobster.router.input_router import route
from lobster.repair.repair_interface import execute_task, act, repair
from lobster.integration.push import push_to_phone, push_dev_confirm


class LobsterCore:

    def __init__(self, model="gemma4:latest"):
        self.model = model
        self.url   = "http://localhost:11434/api/generate"
        self.os            = OSController(workspace=".")
        self.reflex_memory = ReflexMemory()
        self.episodic      = EpisodicMemory()
        self.prompt_engine = PromptEngine()
        self.learning      = LearningEngine()
        self.editor        = TerminalEditor()
        self.detector      = ErrorDetector()
        self.engine        = RepairEngine()
        self.supervisor    = ReasoningSupervisor()
        self.trigger       = RepairTrigger(self.engine, self.supervisor)
        self.loop          = RepairLoopController(self.detector, self.trigger)

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
        return self._infer(prompt, f"{self._build_identity()}\\n只輸出 JSON，不輸出任何多餘文字。")

    def reflect(self, prompt: str) -> str:
        return self._infer(prompt, f"{self._build_identity()}\\n進行系統自我反思，輸出 JSON 格式分析。")

    def plan(self, prompt: str) -> str:
        return self._infer(prompt, f"{self._build_identity()}\\n資深 Python 架構師，輸出 JSON 格式修復計畫。")

    def judge(self, prompt: str, context: str = "") -> str:
        full = f"{context}\\n\\n{prompt}" if context else prompt
        return self._infer(full, f"{self._build_identity()}\\n只回答 PASS 或 FAIL，不輸出其他任何內容。")

    def repair(self, code: str, prompt: str) -> str:
        return repair(self, code, prompt)


CORE = LobsterCore()


def boot():
    print("🦞 Lobster Self-Healing Core Ready")
    print(f"   模型：{CORE.model}  端點：{CORE.url}")
    if _USE_GUARD:
        start_background_monitor(interval=30)
        print(f"   Ollama：{'在線' if is_online(force=True) else '離線（離線模式）'}")
"""

# 寫入所有檔案
for rel_path, content in FILES.items():
    target = BASE / rel_path
    target.write_text(content, encoding="utf-8")
    print(f"✅ 建立：{rel_path}")

print("\n🎉 所有 lobster 模組安裝完成！")
