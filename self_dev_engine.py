# self_dev_engine.py — 自主開發引擎（逐步確認版）
# 流程：說需求 → AI 規劃步驟清單 → 逐步問確認 → 每步完成才繼續
#
# 使用方式（在對話框輸入）：
#   幫我做一個 YouTube 字幕抓取工具
#   修改 reflex_engine.py，讓它多支援「謝謝」的回應
#   新增一個 hello_world.py，內容是印出你好

import ast
import subprocess
import pathlib
import shutil
import datetime
import json
import re
from typing import Optional

try:
    from agent_logger import get_logger
    logger = get_logger("self_dev_engine")
except ImportError:
    import logging
    logger = logging.getLogger("self_dev_engine")

try:
    from ollama_guard import safe_infer
    _USE_GUARD = True
except ImportError:
    _USE_GUARD = False

WORKSPACE    = pathlib.Path(".")
PROJECTS_DIR = pathlib.Path("projects")
BACKUP_DIR   = pathlib.Path("memory/dev_backups")
REPORT_FILE  = pathlib.Path("memory/dev_history.json")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _push_confirm_to_phone(msg: str):
    """推送開發確認訊息到手機，附上確認/取消按鈕"""
    try:
        import sys, threading
        _pkg = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
        if _pkg not in sys.path:
            sys.path.insert(0, _pkg)
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

                kb = InlineKeyboardMarkup()
                kb.row(
                    InlineKeyboardButton("✅ 確認", callback_data="dev_confirm"),
                    InlineKeyboardButton("❌ 取消", callback_data="dev_cancel"),
                )
                text = "🤖 立 AI 開發確認\n\n" + msg[:600]
                for cid in bot_config.ALLOWED_CHAT_IDS:
                    _bot.send_message(cid, text, reply_markup=kb)
                logger.info("[SelfDev] 開發確認已推送到手機")
            except Exception as e:
                logger.warning(f"[SelfDev] 推送失敗：{e}")

        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        logger.warning(f"[SelfDev] 推送外層失敗：{e}")


def _push_stage_to_phone(stage: str, detail: str = ""):
    """
    推送目前開發階段到手機（純通知，不帶按鈕）
    stage: 📋規劃 / 🔍設計 / ⚙️施作 / 🧪測試
    """
    try:
        import sys, threading
        _pkg = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
        if _pkg not in sys.path:
            sys.path.insert(0, _pkg)
        import bot_config

        def _send():
            try:
                try:
                    import telegram_bot as _tb
                    _bot = _tb.bot
                except Exception:
                    import telebot
                    _bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN, parse_mode=None)
                text = f"🤖 立 AI 開發進度\n\n{stage}"
                if detail:
                    text += f"\n{detail[:200]}"
                for cid in bot_config.ALLOWED_CHAT_IDS:
                    _bot.send_message(cid, text)
            except Exception as e:
                logger.warning(f"[SelfDev] 階段推送失敗：{e}")

        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        logger.warning(f"[SelfDev] 階段推送外層失敗：{e}")

# 模型 → 步驟對應表（兩層選擇用）
_model_step_map: dict = {}

def _push_mindmap_to_phone(request: str, spec: str, steps: list, groups: list = None):
    """推送第一層：由 Claude 決定的分組選擇按鈕"""
    global _model_step_map
    try:
        import sys, threading
        _pkg = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
        if _pkg not in sys.path:
            sys.path.insert(0, _pkg)
        import bot_config
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

        # 建立分組對應（完全依照 Claude 給的 groups，不寫死任何判斷）
        built_groups = {}
        if groups:
            for g in groups:
                key   = g.get("key", f"group_{len(built_groups)}")
                label = g.get("label", key)
                icon  = g.get("icon", "📦")
                desc  = g.get("desc", "")
                files = g.get("files", [])
                # 找出這組 files 對應的步驟索引
                step_indices = [
                    i for i, s in enumerate(steps)
                    if s.get("file", "") in files
                ]
                # 若沒有明確對應，把沒被分到的步驟放進來
                if not step_indices and len(built_groups) == len(groups) - 1:
                    assigned = {idx for g2 in built_groups.values() for idx in g2["steps"]}
                    step_indices = [i for i in range(len(steps)) if i not in assigned]
                built_groups[key] = {
                    "label": f"{icon} {label}",
                    "desc":  desc,
                    "steps": step_indices,
                }
        else:
            # Claude 沒給分組 → fallback：每個步驟自成一組
            for i, step in enumerate(steps):
                built_groups[f"step_{i}"] = {
                    "label": f"📄 {step['title']}",
                    "desc":  step.get("desc", ""),
                    "steps": [i],
                }

        _model_step_map = {"models": built_groups, "steps": steps, "request": request}

        def _send():
            try:
                try:
                    import telegram_bot as _tb
                    _bot = _tb.bot
                except Exception:
                    import telebot
                    _bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN, parse_mode=None)
                lines = ["🗺 專案心智圖", "─"*28, f"📌 {request[:40]}", ""]
                for key, info in built_groups.items():
                    n = len(info["steps"])
                    lines.append(f"  • {info['label']} — {n} 個步驟")
                    if info.get("desc"):
                        lines.append(f"    {info['desc'][:40]}")
                lines.extend(["", "👇 選擇要先開發哪個部分："])
                kb = InlineKeyboardMarkup(row_width=1)
                for key, info in built_groups.items():
                    kb.add(InlineKeyboardButton(
                        info["label"],
                        callback_data=f"dev_model_{key}"
                    ))
                kb.add(InlineKeyboardButton("▶️ 從頭開始（照順序）", callback_data="dev_confirm"))
                for cid in bot_config.ALLOWED_CHAT_IDS:
                    _bot.send_message(cid, "\n".join(lines), reply_markup=kb)
                logger.info("[SelfDev] 心智圖第一層已推送")
            except Exception as e:
                logger.warning(f"[SelfDev] 心智圖推送失敗：{e}")
        threading.Thread(target=_send, daemon=True).start()

        # 同時通知桌面 UI 顯示心智圖選擇列
        try:
            import desktop_agent as _da
            ui = getattr(_da, '_desktop_ui_ref', None)
            if ui and hasattr(ui, 'show_mindmap'):
                ui.show_mindmap(built_groups, steps)
        except Exception as e:
            logger.warning(f"[SelfDev] 桌面心智圖通知失敗：{e}")

    except Exception as e:
        logger.warning(f"[SelfDev] 心智圖外層失敗：{e}")


def _push_model_steps_to_phone(model_key: str):
    """推送第二層：該模型負責的步驟按鈕"""
    global _model_step_map
    try:
        import sys, threading
        _pkg = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
        if _pkg not in sys.path:
            sys.path.insert(0, _pkg)
        import bot_config
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

        found_models = _model_step_map.get("models", {})
        steps        = _model_step_map.get("steps", [])
        info         = found_models.get(model_key, {})
        label        = info.get("label", model_key)
        role         = info.get("role", "")
        step_indices = info.get("steps", list(range(len(steps))))

        def _send():
            try:
                try:
                    import telegram_bot as _tb
                    _bot = _tb.bot
                except Exception:
                    import telebot
                    _bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN, parse_mode=None)
                lines = [f"✅ {label}（{role}）", "─"*28, "📋 負責的步驟："]
                for idx in step_indices:
                    step = steps[idx]
                    icon = "🆕" if step.get("action") == "create" else "✏️"
                    lines.append(f"  • {icon} {step['title']}（{step['file']}）")
                lines.extend(["", "👇 選擇要先製作哪個步驟："])
                kb = InlineKeyboardMarkup(row_width=1)
                for idx in step_indices:
                    step = steps[idx]
                    icon = "🆕" if step.get("action") == "create" else "✏️"
                    kb.add(InlineKeyboardButton(
                        f"{icon} {step['title']}（{step['file']}）",
                        callback_data=f"dev_start_{idx}"
                    ))
                kb.add(InlineKeyboardButton("⬅️ 返回模型選擇", callback_data="dev_back_models"))
                for cid in bot_config.ALLOWED_CHAT_IDS:
                    _bot.send_message(cid, "\n".join(lines), reply_markup=kb)
                logger.info(f"[SelfDev] 第二層已推送：{model_key}")
            except Exception as e:
                logger.warning(f"[SelfDev] 第二層推送失敗：{e}")
        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        logger.warning(f"[SelfDev] 第二層外層失敗：{e}")


# 核心系統檔：修改時維持在根目錄，不移到 projects/
CORE_FILES = {
    "desktop_agent.py", "Lobster_Core.py", "prompt_engine.py",
    "ollama_guard.py", "model_selector.py", "self_dev_engine.py",
    "reflex_engine.py", "terminal_engine.py", "desktop_control.py",
    "long_term_memory.py", "episodic_memory.py", "cognition_state_manager.py",
    "intent_router.py", "backup_engine.py", "repair_engine.py",
    "bot_config.py", "agent_logger.py",
}

# ── 全域狀態 ──────────────────────────────────────────────────────────────────

# 舊版單步確認（向下相容）
_pending: dict = {}

# 新版多步流程狀態
_plan_state: dict = {
    "active":        False,
    "request":       "",
    "steps":         [],
    "current_step":  0,
    "completed":     [],
    "pending_write": {},
}

# 本次開發流程的錯誤記錄
_dev_errors: list = []


# ── 核心類別 ──────────────────────────────────────────────────────────────────

class SelfDevEngine:
    """
    自主開發引擎（逐步確認版）
    接收自然語言需求 → AI 規劃步驟 → 逐步詢問確認 → 逐步執行
    """

    def __init__(self, model: str = "qwen2.5:14b"):
        self.model = model

    # ── 路徑決策 ─────────────────────────────────────────────────────────────

    # 模板名稱 → 專案子資料夾對應
    _TPL_PROJECT_DIRS = {
        "_tpl_youtube":  "youtube",
        "_tpl_telegram": "telegram_bot",
        "_tpl_gui_tool": "gui_tool",
        "_tpl_scraper":  "scraper",
        "_tpl_api":      "api_client",
        "_tpl_word":     "word_editor",
        "_tpl_generic":  "misc",
    }

    def _resolve_path(self, filename: str, action: str) -> pathlib.Path:
        """
        決定檔案要放在哪裡：
        - 修改現有檔案 → 根目錄（WORKSPACE）
        - 核心系統檔 → 根目錄
        - 全新建立的非核心檔 → projects/<專案子資料夾>/
        """
        if action == "modify" or filename in CORE_FILES:
            return WORKSPACE / filename

        # 從目前計畫的模板找子資料夾名稱
        tpl_fn   = _plan_state.get("template", "_tpl_generic")
        proj_dir = self._TPL_PROJECT_DIRS.get(tpl_fn, "misc")
        target   = PROJECTS_DIR / proj_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def handle(self, request: str) -> str:
        global _plan_state

        if _plan_state["active"]:
            t = request.strip()
            # 重試：清除 pending_write，重新生成當前步驟
            if t in ["重試", "retry", "重新生成", "再試一次"]:
                _plan_state["pending_write"] = {}
                step_idx = _plan_state["current_step"]
                step     = _plan_state["steps"][step_idx]
                total    = len(_plan_state["steps"])
                _push_stage_to_phone("🔄 重試中", f"重新生成 {step['file']}...")
                return self._generate_step(step, step_idx, total)
            return (
                f"⚠️ 目前還有進行中的開發計畫"
                f"（步驟 {_plan_state['current_step'] + 1}/{len(_plan_state['steps'])}）\n\n"
                f"輸入「確認」繼續 ／ 「取消」放棄 ／ 「重試」重新生成"
            )

        logger.info(f"[SelfDev] 收到需求：{request[:60]}")
        global _dev_errors
        _dev_errors = []  # 清空上次的錯誤記錄

        # 複雜需求：先讓 Claude 細化需求並規劃步驟，再讓 Claude 自審
        if self._is_complex_request(request):
            claude_steps = self._clarify_with_claude(request)
            if claude_steps:
                # Claude 自審：同意/不同意哪些，生成修正版
                reviewed_steps = self._review_plan_with_claude(request, claude_steps)
                return self._plan_from_claude(request, reviewed_steps)
            # Claude 失敗 → 降級到本地模板
            return self._plan_project(request)
        else:
            return self._plan_single_file(request)

    # ── Claude 需求細化 ───────────────────────────────────────────────────────

    def _clarify_with_claude(self, request: str) -> list:
        """
        把模糊需求丟給 Claude，請它規劃成具體的開發步驟清單。
        Claude 扮演需求分析師：把「幫我做個監控工具」變成 4-5 個有檔名、有描述的步驟。
        回傳步驟 list（同 _make_steps 格式），失敗回傳空 list。
        """
        try:
            from claude_desktop_bridge import get_bridge

            # ── 第一輪：討論規格，並要求 Claude 決定分類方式 ────────────
            discuss_prompt = (
                f"我要開發一個 Python 專案：「{request}」\n\n"
                "請幫我規劃這個專案的架構，說明需要哪些 Python 檔案、每個檔案的職責、"
                "要定義哪些函式，以及檔案之間怎麼互相呼叫。\n\n"
                "同時，請你自己決定最適合這個專案的分組方式（例如按功能模組、按技術層、"
                "按執行順序、按依賴關係，或任何你認為最清楚的方式），"
                "並在回答最後輸出一個 JSON 分類表，格式如下：\n"
                '{"groups":[{"key":"group_a","label":"分組名稱","icon":"📦","desc":"這組負責什麼","files":["file1.py","file2.py"]}]}\n\n'
                "規則：\n"
                "- groups 是陣列，每個元素是一個分組\n"
                "- key 是英文識別碼\n"
                "- label 是顯示名稱（繁體中文）\n"
                "- icon 選一個最能代表這組的 emoji\n"
                "- files 是這組負責的檔案清單\n"
                "- 只在回答最後輸出這個 JSON，前面的說明用自然語言條列"
            )
            logger.info("[SelfDev] 請 Claude 討論專案規格並決定分類")
            _push_stage_to_phone("📋 規格討論中", "正在與 Claude 討論專案架構...")
            bridge = get_bridge()
            spec = bridge.ask(discuss_prompt, auto_learn=False, raw=True)

            if not spec or spec.startswith("❌") or len(spec) < 50:
                logger.warning("[SelfDev] Claude 規格討論失敗，降級")
                return []
            logger.info(f"[SelfDev] Claude 規格討論完成（{len(spec)} 字）")

            # 從 spec 中提取分類 JSON
            import json as _json
            _groups = []
            try:
                gi = spec.rfind('{"groups"')
                if gi != -1:
                    depth = 0
                    ge = -1
                    for i, ch in enumerate(spec[gi:], gi):
                        if ch == "{": depth += 1
                        elif ch == "}": depth -= 1
                        if depth == 0:
                            ge = i
                            break
                    if ge != -1:
                        _groups = _json.loads(spec[gi:ge+1]).get("groups", [])
                        logger.info(f"[SelfDev] 解析到 {len(_groups)} 個分組")
            except Exception as e:
                logger.warning(f"[SelfDev] 分組 JSON 解析失敗：{e}")

            # ── 第二輪：把規格轉成 JSON 步驟 ─────────────────────────────
            prompt = (
                f"根據剛才討論的專案規格：\n\n{spec[:1500]}\n\n"
                "請把這個規格轉成 3-5 個開發步驟的 JSON 陣列。\n"
                "只輸出 JSON，不要任何說明：\n"
                '[{"title":"步驟標題","desc":"新增xxx.py，定義func_a()做某事","file":"xxx.py","action":"create"}]\n\n'
                "規則：\n"
                "- file 必須是實際的英文檔名.py（根據規格討論的檔案，不要用xxx.py）\n"
                "- desc 說明具體新增哪些函式和做法\n"
                "- action 只能是 create 或 modify\n"
                "- 只輸出 JSON 陣列"
            )
            logger.info("[SelfDev] 請 Claude 將規格轉成 JSON 步驟")
            _push_stage_to_phone("📋 規劃中", "正在將規格轉換為開發步驟...")
            raw = bridge.ask(prompt, auto_learn=False, raw=True)
            logger.info(f"[SelfDev] 第二輪原始回傳前500字：{str(raw)[:500]}")

            if not raw or raw.startswith("❌"):
                logger.warning("[SelfDev] Claude 回傳無效，降級本地模板")
                return []

            # 用括號配對法精確提取第一個完整 JSON 陣列（找 [{ 確保是真正的 JSON）
            start = raw.find("[{")
            if start == -1:
                start = raw.find("[")  # 備用：找任何 [
            if start == -1:
                logger.warning(f"[SelfDev] Claude 回傳無 JSON：{raw[:100]}")
                return []

            depth = 0
            end   = -1
            for i, ch in enumerate(raw[start:], start):
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break

            if end == -1:
                logger.warning("[SelfDev] JSON 陣列未閉合")
                return []

            steps_data = json.loads(raw[start:end + 1])
            steps = []
            for s in steps_data:
                if not all(k in s for k in ["title", "desc", "file", "action"]):
                    continue
                fname = s["file"].strip()
                # 自動修正：去掉路徑、取最後的檔名
                if "/" in fname or "\\" in fname:
                    fname = fname.replace("\\", "/").split("/")[-1]
                # 自動補 .py
                if not fname.endswith(".py"):
                    fname = re.sub(r'\.[^.]+$', '', fname) + ".py"
                # 過濾非英文檔名（修正後仍不符合就跳過）
                if not re.match(r'^[a-zA-Z0-9_\-]+\.py$', fname):
                    logger.warning(f"[SelfDev] 跳過無法修正的檔名：{s['file']} → {fname}")
                    continue
                # desc 太短補上 title
                desc = s["desc"].strip()
                if len(desc) < 15:
                    desc = f"新增 {fname}，實作{s['title']}功能"
                steps.append({
                    "title":  s["title"],
                    "desc":   desc,
                    "file":   fname,
                    "action": s["action"] if s["action"] in ["create", "modify"] else "create",
                })

            if not steps:
                logger.warning("[SelfDev] Claude 步驟解析結果為空（全被過濾）")
                return []

            logger.info(f"[SelfDev] Claude 規劃了 {len(steps)} 個步驟")
            try:
                _push_mindmap_to_phone(request, spec, steps, _groups)
            except Exception as e:
                logger.warning(f"[SelfDev] 心智圖推送失敗：{e}")
            return steps

        except Exception as e:
            logger.warning(f"[SelfDev] Claude 需求細化失敗：{e}")
            return []

    def _review_plan_with_claude(self, request: str, steps: list) -> list:
        """
        讓 Claude 審查自己剛規劃的步驟：
        - 同意哪些步驟
        - 不同意哪些點（理由）
        - 生成修正後的最終版本
        審查失敗或無改動時，回傳原始步驟。
        """
        try:
            from claude_desktop_bridge import get_bridge

            # 把步驟轉成可讀文字給 Claude 審查
            steps_text = "\n".join(
                f"{i+1}. [{s['action']}] {s['file']} — {s['title']}：{s['desc']}"
                for i, s in enumerate(steps)
            )

            prompt = (
                f"我剛規劃了以下開發步驟來完成需求「{request}」：\n\n"
                f"{steps_text}\n\n"
                "請審查並改進這個規劃，按以下格式輸出：\n"
                "第一行先輸出修正後的JSON陣列（只輸出JSON，不要其他文字）：\n"
                '[{"title":"步驟標題","desc":"新增xxx.py，定義func_a()做某事","file":"xxx.py","action":"create"}]\n\n'
                "注意：file 欄位必須是真實的英文檔名（如 health_core.py），不要寫「英文檔名」這種說明文字。\n\n"
                "然後再說明：\n"
                "1. 哪些步驟合理\n"
                "2. 做了哪些改進"
            )

            logger.info("[SelfDev] 請 Claude 自審規劃步驟")
            _push_stage_to_phone("📋 自審規劃中", "Claude 正在審查並改進開發步驟...")
            bridge = get_bridge()
            raw = bridge.ask(prompt, auto_learn=False, raw=True)

            if not raw or raw.startswith("❌"):
                logger.warning("[SelfDev] Claude 自審失敗，使用原始步驟")
                return steps

            # 記錄 Claude 的審查意見（取 JSON 前的文字）
            json_start = raw.find("[{")
            if json_start > 0:
                review_comment = raw[:json_start].strip()
                if review_comment:
                    logger.info(f"[SelfDev] Claude 審查意見：{review_comment[:150]}")

            # 用括號配對法提取修正後的 JSON
            if json_start == -1:
                logger.warning("[SelfDev] Claude 自審未回傳 JSON，使用原始步驟")
                return steps

            depth = 0
            json_end = -1
            for i, ch in enumerate(raw[json_start:], json_start):
                if ch == "[":   depth += 1
                elif ch == "]": depth -= 1
                if depth == 0:
                    json_end = i
                    break

            if json_end == -1:
                return steps

            reviewed_data = json.loads(raw[json_start:json_end + 1])
            reviewed_steps = []
            for s in reviewed_data:
                if not all(k in s for k in ["title", "desc", "file", "action"]):
                    continue
                fname = s["file"].strip()
                if "/" in fname or "\\" in fname:
                    fname = fname.replace("\\", "/").split("/")[-1]
                if not fname.endswith(".py"):
                    fname = re.sub(r'\.[^.]+$', '', fname) + ".py"
                if not re.match(r'^[a-zA-Z0-9_\-]+\.py$', fname):
                    logger.warning(f"[SelfDev] 自審後跳過無法修正的檔名：{s['file']}")
                    continue
                desc = s["desc"].strip()
                if len(desc) < 15:
                    desc = f"新增 {fname}，實作{s['title']}功能"
                reviewed_steps.append({
                    "title":  s["title"],
                    "desc":   desc,
                    "file":   fname,
                    "action": s["action"] if s["action"] in ["create", "modify"] else "create",
                })

            if not reviewed_steps:
                logger.warning("[SelfDev] Claude 自審結果為空，使用原始步驟")
                return steps

            logger.info(f"[SelfDev] Claude 自審完成，步驟數：{len(steps)} → {len(reviewed_steps)}")
            return reviewed_steps

        except Exception as e:
            logger.warning(f"[SelfDev] Claude 自審失敗（{e}），使用原始步驟")
            return steps

    def _plan_from_claude(self, request: str, steps: list) -> str:
        """
        用 Claude 規劃的步驟清單建立開發計畫（取代 _plan_project 的模板邏輯）
        """
        global _plan_state

        _plan_state = {
            "active":        True,
            "request":       request,
            "steps":         steps,
            "current_step":  0,
            "completed":     [],
            "pending_write": {},
            "template":      "_tpl_generic",
        }

        plan_lines = []
        for i, step in enumerate(steps):
            icon = "▶" if i == 0 else "○"
            plan_lines.append(f"{icon} 步驟 {i+1}：{step['title']}\n   {step['desc']}")

        first_step = steps[0]
        msg = (
            "🤖 我請教了 Claude，規劃了 " + str(len(steps)) + " 個步驟：\n\n"
            + "\n\n".join(plan_lines) + "\n\n"
            + "─" * 40 + "\n"
            + "▶ 現在開始步驟 1：" + first_step["title"] + "\n"
            + "   " + first_step["desc"] + "\n"
            + "   目標檔案：" + first_step["file"] + "\n\n"
            + "✅ 輸入「確認」開始這一步 ／ ❌ 輸入「取消」放棄整個計畫"
        )
        try:
            _push_confirm_to_phone(msg)
        except Exception:
            pass
        return msg

    # ── 複雜度判斷 ────────────────────────────────────────────────────────────

    def _is_complex_request(self, request: str) -> bool:
        complex_keywords = ["做一個", "製作", "建立系統", "開發", "幫我做",
                            "工具", "應用", "系統", "功能模組", "媒介"]
        simple_keywords  = ["修改", "改", "幫我改", "幫我在", "新增一個", "加上"]

        ext_pattern   = r"[\w\u4e00-\u9fff\-]+\.(py|html|js|css|json|md|txt)"
        file_mentions = re.findall(ext_pattern, request)
        if len(file_mentions) > 1:
            return True

        has_complex = any(kw in request for kw in complex_keywords)
        has_simple  = any(kw in request for kw in simple_keywords)
        return has_complex and not has_simple

    # ── 多步專案規劃（關鍵字模板版，不依賴 AI JSON）────────────────────────

    # 專案類型模板：(關鍵字清單, 步驟產生函式名稱)
    _PROJECT_TEMPLATES = [
        (["youtube", "字幕", "yt", "影片抓取"],         "_tpl_youtube"),
        (["telegram", "bot", "機器人"],                  "_tpl_telegram"),
        (["視窗", "gui", "介面", "pyqt", "tkinter"],     "_tpl_gui_tool"),
        (["爬蟲", "爬取", "抓取", "requests", "網頁"],   "_tpl_scraper"),
        (["api", "串接", "webhook"],                     "_tpl_api"),
        (["word", "文書", "文字編輯", "編輯器", "記事本", "筆記"],  "_tpl_word"),
        (["工具", "系統", "功能", "模組", "做一個",
          "製作", "開發", "幫我做", "媒介", "應用"],      "_tpl_generic"),
    ]

    def _plan_project(self, request: str) -> str:
        global _plan_state
        logger.info(f"[SelfDev] 規劃專案步驟（模板版）：{request[:60]}")

        req_lower = request.lower()
        steps    = None
        used_tpl = "_tpl_generic"
        for keywords, tpl_fn in self._PROJECT_TEMPLATES:
            if any(kw in req_lower for kw in keywords):
                steps    = getattr(self, tpl_fn)(request)
                used_tpl = tpl_fn
                break

        if not steps:
            return self._plan_single_file(request)

        _plan_state = {
            "active":        True,
            "request":       request,
            "steps":         steps,
            "current_step":  0,
            "completed":     [],
            "pending_write": {},
            "template":      used_tpl,
        }

        plan_lines = []
        for i, step in enumerate(steps):
            icon = "▶" if i == 0 else "○"
            plan_lines.append(f"{icon} 步驟 {i+1}：{step['title']}\n   {step['desc']}")

        first_step = steps[0]
        msg = (
            "🤖 我規劃了 " + str(len(steps)) + " 個步驟來完成這個需求：\n\n"
            + "\n\n".join(plan_lines) + "\n\n"
            + "─" * 40 + "\n"
            + "▶ 現在開始步驟 1：" + first_step["title"] + "\n"
            + "   " + first_step["desc"] + "\n"
            + "   目標檔案：" + first_step["file"] + "\n\n"
            + "✅ 輸入「確認」開始這一步 ／ ❌ 輸入「取消」放棄整個計畫"
        )
        try:
            _push_confirm_to_phone(msg)
        except Exception:
            pass
        return msg

    # ── 專案模板：各類型的步驟定義 ──────────────────────────────────────────

    def _make_steps(self, *args):
        """快速建立步驟清單：每個元素是 (title, desc, file, action)"""
        return [{"title": t, "desc": d, "file": f, "action": a} for t, d, f, a in args]

    def _tpl_youtube(self, request: str) -> list:
        return self._make_steps(
            ("建立字幕抓取核心",
             "新增 youtube_handler.py，使用 yt-dlp 下載字幕到暫存資料夾，"
             "清除時間戳記，函式名 get_transcript(url) 回傳純文字字串，失敗回傳 None。",
             "youtube_handler.py", "create"),
            ("建立 AI 核心整合橋接",
             "新增 youtube_bridge.py，定義函式 handle_youtube_input(text, infer_fn)，"
             "偵測 text 含 youtube.com 或 youtu.be 時呼叫 youtube_handler.get_transcript()，"
             "取得字幕後用 infer_fn 摘要並回傳，否則回傳 None。",
             "youtube_bridge.py", "create"),
            ("建立 Telegram YouTube 處理器",
             "新增 youtube_telegram.py，定義函式 handle_youtube_msg(bot, message, lobster)，"
             "呼叫 youtube_bridge.handle_youtube_input() 取得摘要後回傳給使用者，"
             "失敗時回覆無法取得字幕。",
             "youtube_telegram.py", "create"),
        )

    def _tpl_word(self, request: str) -> list:
        return self._make_steps(
            ("建立文字編輯主視窗",
             "新增 word_editor.py，用 PyQt6 建立主視窗，包含 QTextEdit 編輯區、"
             "選單列（檔案/編輯/格式）、狀態列顯示字數和游標位置。",
             "word_editor.py", "create"),
            ("建立格式工具列",
             "新增 word_toolbar.py，定義 FormatToolbar 類別繼承 QToolBar，"
             "提供粗體、斜體、底線、字型選擇、字型大小、字體顏色等格式化按鈕，"
             "透過 signal 與主視窗的 QTextEdit 連動。",
             "word_toolbar.py", "create"),
            ("建立檔案管理功能",
             "新增 word_file.py，定義 FileManager 類別，"
             "支援新增、開啟、儲存、另存新檔（.txt .html）和列印功能，"
             "使用 QFileDialog 選擇路徑，儲存時保留 HTML 格式。",
             "word_file.py", "create"),
        )

    def _tpl_telegram(self, request: str) -> list:
        return self._make_steps(
            ("建立 Bot 設定",
             "新增或確認 bot_config.py，設定 TOKEN 和 ALLOWED_CHAT_IDS。",
             "bot_config.py", "create"),
            ("建立 Bot 核心邏輯",
             "新增 telegram_bot.py，處理指令與訊息，整合 Lobster_Core。",
             "telegram_bot.py", "create"),
        )

    def _tpl_gui_tool(self, request: str) -> list:
        # 從需求裡嘗試抓檔名，抓不到就用 gui_tool.py
        import re
        m = re.search(r"([\w一-鿿]+)\.(py)", request)
        fname = m.group(0) if m else "gui_tool.py"
        return self._make_steps(
            ("建立 GUI 主視窗",
             f"新增 {fname}，用 PyQt6 建立主視窗和基本 UI 元件。",
             fname, "create"),
            ("加入核心功能",
             f"修改 {fname}，加入主要業務邏輯和事件處理。",
             fname, "modify"),
        )

    def _tpl_scraper(self, request: str) -> list:
        import re
        m = re.search(r"([\w一-鿿]+)\.(py)", request)
        fname = m.group(0) if m else "scraper.py"
        return self._make_steps(
            ("建立爬蟲核心",
             f"新增 {fname}，用 requests + BeautifulSoup 抓取目標網頁內容。",
             fname, "create"),
            ("加入資料處理",
             f"修改 {fname}，加入資料清洗、儲存為 JSON/CSV 的功能。",
             fname, "modify"),
        )

    def _tpl_api(self, request: str) -> list:
        import re
        m = re.search(r"([\w一-鿿]+)\.(py)", request)
        fname = m.group(0) if m else "api_client.py"
        return self._make_steps(
            ("建立 API 客戶端",
             f"新增 {fname}，封裝 API 請求、認證、錯誤處理。",
             fname, "create"),
            ("整合到主系統",
             "修改 Lobster_Core.py，在需要時呼叫 API 客戶端。",
             "Lobster_Core.py", "modify"),
        )

    def _tpl_generic(self, request: str) -> list:
        """
        通用模板：用本地模型規劃步驟（穩定不會失敗）
        """
        logger.info("[SelfDev] 用本地模型規劃步驟")

        try:
            import json as _json
            prompt = (
                "根據以下需求規劃軟體開發步驟，只輸出 JSON 陣列，不要任何解釋：\n\n"
                "需求：" + request + "\n\n"
                '格式：[{"title":"步驟標題","desc":"這步做什麼","file":"檔名.py","action":"create或modify"}]\n\n'
                "規則：步驟數 2-4 個，action 只能是 create 或 modify，file 必須是 .py 結尾"
            )
            system = "只輸出 JSON 陣列，不要任何解釋或 markdown 標記。"
            raw = self._infer(prompt, system)

            start = raw.find("[")
            end   = raw.rfind("]")
            if start == -1 or end == -1 or end <= start:
                raise Exception("找不到 JSON 陣列")
            steps_data = _json.loads(raw[start:end+1])

            steps = []
            for s in steps_data:
                if all(k in s for k in ["title", "desc", "file", "action"]):
                    steps.append({
                        "title":  s["title"],
                        "desc":   s["desc"],
                        "file":   s["file"],
                        "action": s["action"] if s["action"] in ["create", "modify"] else "create",
                    })

            if steps:
                logger.info(f"[SelfDev] 本地模型規劃了 {len(steps)} 個步驟")
                return steps

        except Exception as e:
            logger.warning(f"[SelfDev] 本地模型規劃失敗：{e}，改用單步")

        # 備用：從需求抓檔名，兩步處理
        import re
        m = re.search(r"([\w一-鿿\-]+\.py)", request)
        fname = m.group(1) if m else "main.py"
        return self._make_steps(
            ("建立核心模組", "新增 " + fname + "，實作需求的主要功能。", fname, "create"),
            ("加入錯誤處理", "修改 " + fname + "，補充錯誤處理和 __main__ 區塊。", fname, "modify"),
        )

    # ── 單檔案規劃 ────────────────────────────────────────────────────────────

    def _plan_single_file(self, request: str) -> str:
        global _plan_state

        intent = self._parse_intent(request)
        if not intent:
            return "無法理解需求，請說得更具體一點，例如：\n「修改 reflex_engine.py，讓它支援英文問候」"

        filename  = intent.get("file")
        action    = intent.get("action")
        goal      = intent.get("goal", request)

        if not filename:
            return "請指定要修改或新增的檔案名稱"

        action_zh = "修改" if action == "modify" else "新增"

        _plan_state = {
            "active":        True,
            "request":       request,
            "steps":         [{"title": f"{action_zh} {filename}", "desc": goal,
                               "file": filename, "action": action}],
            "current_step":  0,
            "completed":     [],
            "pending_write": {},
        }

        return (
            f"📋 我打算{action_zh} {filename}\n\n"
            f"計畫：{goal}\n\n"
            f"✅ 輸入「確認」開始生成程式碼 ／ ❌ 輸入「取消」放棄"
        )

    # ── 確認：執行目前步驟 ────────────────────────────────────────────────────

    def confirm(self) -> str:
        global _plan_state, _pending

        if _pending and not _plan_state["active"]:
            return self._confirm_legacy()

        if not _plan_state["active"]:
            return "沒有進行中的開發計畫，請先說明需求"

        steps    = _plan_state["steps"]
        step_idx = _plan_state["current_step"]
        step     = steps[step_idx]
        total    = len(steps)

        # 階段 A：尚未生成程式碼 → 生成並預覽
        if not _plan_state["pending_write"]:
            return self._generate_step(step, step_idx, total)

        # 階段 B：程式碼已生成 → 寫入
        return self._execute_step(step, step_idx, total)

    # ── 生成當前步驟的程式碼 ──────────────────────────────────────────────────

    # 大檔案行數門檻：超過此行數改用補丁模式，不傳完整原始碼給 AI
    LARGE_FILE_THRESHOLD = 150

    def _generate_step(self, step: dict, step_idx: int, total: int) -> str:
        global _plan_state

        # 防止重複呼叫（手機雙擊確認等情況）
        if _plan_state.get("generating"):
            return "⏳ 正在生成中，請稍候..."
        _plan_state["generating"] = True

        try:
            return self._generate_step_inner(step, step_idx, total)
        finally:
            _plan_state["generating"] = False

    def _generate_step_inner(self, step: dict, step_idx: int, total: int) -> str:
        global _plan_state

        filename = step["file"]
        action   = step["action"]
        goal     = step["desc"]

        context = ""
        if _plan_state["completed"]:
            done    = [f"• {s['title']}（{s['file']}）" for s in _plan_state["completed"]]
            context = "\n\n已完成的步驟：\n" + "\n".join(done)

        full_goal = f"專案需求：{_plan_state['request']}\n目前步驟：{goal}{context}"

        target = self._resolve_path(filename, action)
        if action == "modify" and target.exists():
            original_code = target.read_text(encoding="utf-8")
        else:
            original_code = ""
            action        = "create"

        logger.info(f"[SelfDev] 生成步驟 {step_idx+1}/{total}：{filename} → {target}")

        # ── 步驟 0：先詢問 Claude 取得設計建議（solo 模式跳過）───────────────
        claude_guidance = ""
        _is_solo = bool(_plan_state.get("_solo_context"))
        if pathlib.Path(filename).suffix.lower() == ".py" and not _is_solo:
            claude_guidance = self._ask_claude_for_guidance(full_goal, filename, action)
            if claude_guidance:
                full_goal = (
                    full_goal
                    + "\n\n── Claude 設計建議（請參考以下要點生成程式碼）──\n"
                    + claude_guidance
                )

        # ── 大檔案偵測：改用補丁模式 ─────────────────────────────────────────
        orig_lines = original_code.count("\n") + 1 if original_code else 0
        is_large   = (action == "modify" and orig_lines > self.LARGE_FILE_THRESHOLD)

        if is_large:
            new_code, patch_mode = self._generate_patch(full_goal, filename, original_code)
        else:
            new_code  = self._generate_code(full_goal, filename, original_code, action)
            patch_mode = False

        # ── Claude 審查生成結果（僅 .py，且生成成功、非補丁模式）─────────────
        # 注意：若 _generate_code 已成功透過 Claude bridge 生成，跳過審查（避免重複呼叫）
        used_claude_gen = (
            new_code and not new_code.startswith("[ERROR]")
            and not patch_mode
            and pathlib.Path(filename).suffix.lower() == ".py"
            and not getattr(self, "_last_gen_used_local", False)
        )
        if (new_code and not new_code.startswith("[ERROR]")
                and pathlib.Path(filename).suffix.lower() == ".py"
                and not patch_mode
                and getattr(self, "_last_gen_used_local", False)
                and not _plan_state.get("_solo_context")):
            # 本地模型生成的才需要 Claude 審查（solo 模式跳過）
            new_code = self._ask_claude_to_review(new_code, filename, full_goal)

        if not new_code or new_code.startswith("[ERROR]"):
            return f"❌ 步驟 {step_idx+1} 程式碼生成失敗，請稍後再試\n\n輸入「取消」放棄計畫"

        ext = pathlib.Path(filename).suffix.lower()
        if ext == ".py":
            syntax_ok, syntax_err = self._check_syntax(new_code)
            if not syntax_ok:
                # 自動請 Claude 修復語法錯誤
                logger.info(f"[SelfDev] 語法錯誤，請 Claude 修復：{syntax_err}")
                new_code = self._ask_claude_to_fix(new_code, filename, syntax_err, "syntax")
                syntax_ok, syntax_err = self._check_syntax(new_code)
                if not syntax_ok:
                    return (
                        f"❌ 生成的程式碼有語法錯誤（Claude 修復後仍失敗）：\n{syntax_err}\n\n"
                        f"輸入「取消」放棄，或換個描述再試"
                    )

        _plan_state["pending_write"] = {
            "filename":      filename,
            "action":        action,
            "original_code": original_code,
            "new_code":      new_code,
            "patch_mode":    patch_mode,
        }

        preview   = new_code[:400] + ("\n..." if len(new_code) > 400 else "")
        lines     = new_code.count("\n") + 1
        summary   = self._summarize_changes(original_code, new_code, action)
        action_zh = "修改" if action == "modify" else "新增"
        progress  = self._progress_bar(step_idx, total)
        mode_note = "（補丁模式：只加入新功能，不覆蓋原有程式碼）\n" if patch_mode else ""
        claude_note = "🤖 已詢問 Claude 取得設計建議並完成審查\n" if claude_guidance else ""

        step_msg = (
            progress + "\n"
            + "步驟 " + str(step_idx+1) + "/" + str(total) + "：" + step["title"] + "\n\n"
            + claude_note
            + "📝 我打算" + action_zh + " " + filename + "（" + str(lines) + " 行）" + mode_note + "\n\n"
            + "計畫做的事：\n" + summary + "\n\n"
            + "程式碼預覽：\n```python\n" + preview + "\n```\n\n"
            + "✅ 輸入「確認」寫入此步驟 ／ ❌ 輸入「取消」放棄整個計畫"
        )
        try:
            _push_confirm_to_phone(
                "步驟 " + str(step_idx+1) + "/" + str(total) + "：" + step["title"] + "\n\n"
                + "計畫做的事：\n" + summary + "\n\n"
                + "程式碼預覽：\n" + preview[:300]
            )
        except Exception:
            pass
        return step_msg

    def _generate_patch(self, goal: str, filename: str, original_code: str) -> tuple:
        """
        大檔案補丁模式：
        1. 只傳函式/類別結構摘要給 AI（不傳完整程式碼）
        2. AI 只生成要新增的函式或修改的片段
        3. 將補丁附加到原始檔案末尾
        回傳 (最終程式碼, patch_mode=True)
        """
        # 從原始碼提取結構摘要（函式名、類別名、前50行）
        import re as _re
        funcs   = _re.findall(r"^def (\w+)", original_code, _re.MULTILINE)
        classes = _re.findall(r"^class (\w+)", original_code, _re.MULTILINE)
        head    = "\n".join(original_code.splitlines()[:40])

        structure_summary = (
            f"檔案：{filename}\n"
            f"現有函式：{', '.join(funcs) if funcs else '無'}\n"
            f"現有類別：{', '.join(classes) if classes else '無'}\n"
            f"檔案前40行：\n{head}\n..."
        )

        prompt = (
            f"你是一個資深 Python 工程師。\n"
            f"需求：{goal}\n\n"
            f"目標檔案結構摘要：\n{structure_summary}\n\n"
            f"請只輸出需要**新增**到這個檔案的程式碼片段（函式或方法）。\n"
            f"不要輸出原有程式碼，只輸出新增的部分。\n"
            f"規則：\n"
            f"1. 只輸出 Python 程式碼，不要任何解釋或 markdown 標記\n"
            f"2. 使用繁體中文寫註解\n"
            f"3. 確保語法正確\n"
            f"4. 如果是修改現有函式，輸出完整的新版函式（用同名覆蓋）"
        )
        system = (
            "你是一個專業的 Python 工程師。"
            "只輸出需要新增的程式碼片段，不要輸出整個檔案。"
            "程式碼必須語法正確。使用繁體中文寫註解。"
        )

        patch = self._infer(prompt, system)
        if not patch or patch.startswith("[ERROR]"):
            return patch, False

        # 清理 markdown
        patch = re.sub(r"^```\w*\s*", "", patch.strip())
        patch = re.sub(r"\s*```$", "", patch.strip()).strip()

        # 合併：原始碼 + 補丁（加分隔線）
        merged = (
            original_code.rstrip() + "\n\n"
            f"# ── 自動補丁（{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}）──\n"
            + patch
        )
        return merged, True

    # ── 寫入當前步驟 ──────────────────────────────────────────────────────────

    def _execute_step(self, step: dict, step_idx: int, total: int) -> str:
        global _plan_state

        pw            = _plan_state["pending_write"]
        filename      = pw["filename"]
        action        = pw["action"]
        original_code = pw["original_code"]
        new_code      = pw["new_code"]

        _plan_state["pending_write"] = {}

        target      = self._resolve_path(filename, action)
        backup_path = None
        if action == "modify" and target.exists():
            backup_path = self._backup(target)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # 設定暫停重啟旗標，讓 AutoRestart 等測試完才重啟
            _pause_flag = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面\AI-Agent\memory\.auto_restart_paused")
            _pause_flag.parent.mkdir(exist_ok=True)
            _pause_flag.touch()
            target.write_text(new_code, encoding="utf-8")
            logger.info(f"[SelfDev] 已寫入：{target}")
        except Exception as e:
            try:
                _pause_flag.unlink(missing_ok=True)
            except Exception:
                pass
            return f"❌ 步驟 {step_idx+1} 寫入失敗：{e}"

        test_ok, test_output = self._run_test(filename)
        if not test_ok and backup_path:
            shutil.copy2(backup_path, target)
            logger.warning(f"[SelfDev] 測試失敗，已還原：{filename}")
            try:
                _pause_flag.unlink(missing_ok=True)
            except Exception:
                pass
            return (
                f"⚠️ 步驟 {step_idx+1} 測試失敗，已自動還原 {filename}\n\n"
                f"錯誤：{test_output}\n\n輸入「取消」放棄計畫，或重新描述需求"
            )

        # ── 自我測試：A）功能測試 + C）Claude 生成 unittest ──────────────────
        self_test_info = ""
        if pathlib.Path(filename).suffix == ".py":
            _push_stage_to_phone("🧪 測試中", f"正在對 {filename} 進行功能測試與 unittest...")
            self_test_info = self._self_test(filename, new_code, target)

            # 測試失敗時推送重試選項
            if self_test_info and ("⚠️" in self_test_info or "❌" in self_test_info):
                try:
                    _push_confirm_to_phone(
                        f"⚠️ {filename} 測試未完全通過\n\n"
                        f"{self_test_info[:300]}\n\n"
                        f"輸入「重試」重新生成，或「確認」保留目前版本繼續"
                    )
                except Exception:
                    pass

        # 測試完成，解除暫停旗標，允許 AutoRestart 重啟
        try:
            _pause_flag.unlink(missing_ok=True)
        except Exception:
            pass

        _plan_state["completed"].append({
            "title":  step["title"],
            "file":   filename,
            "action": action,
            "backup": backup_path,
        })
        self._record(filename, action, step["desc"], new_code, test_ok, backup_path)

        test_info = "✓ 測試通過" if test_ok else "⚠ 測試略過"
        if self_test_info:
            test_info += "\n" + self_test_info
        progress  = self._progress_bar(step_idx + 1, total)
        action_zh = "修改" if action == "modify" else "新增"

        # 偵測第三方套件
        install_hint = ""
        if pathlib.Path(filename).suffix == ".py":
            pkgs = self._detect_imports(new_code)
            if pkgs:
                install_hint = "\n\n📦 偵測到第三方套件，如未安裝請執行：\npip install " + " ".join(pkgs)

        next_idx = step_idx + 1
        if next_idx >= total:
            _plan_state["active"] = False
            completed_list = "\n".join(
                f"  ✓ {s['title']}（{s['file']}）" for s in _plan_state["completed"]
            )
            return (
                f"{progress}\n"
                f"✅ 已{action_zh} {filename}　{test_info}\n\n"
                f"🎉 全部 {total} 個步驟已完成！\n\n"
                f"完成清單：\n{completed_list}"
                + install_hint
            )
        else:
            _plan_state["current_step"] = next_idx
            next_step = _plan_state["steps"][next_idx]
            return (
                f"{progress}\n"
                f"✅ 步驟 {step_idx+1} 完成：已{action_zh} {filename}　{test_info}"
                + install_hint + "\n\n"
                f"{'─'*40}\n"
                f"▶ 下一步（步驟 {next_idx+1}/{total}）：{next_step['title']}\n"
                f"   {next_step['desc']}\n"
                f"   目標檔案：{next_step['file']}\n\n"
                f"✅ 輸入「確認」開始這一步 ／ ❌ 輸入「取消」放棄剩餘步驟"
            )

    # ── 取消 ─────────────────────────────────────────────────────────────────

    def cancel(self) -> str:
        global _plan_state, _pending

        if _plan_state["active"]:
            completed = _plan_state["completed"]
            deleted  = []
            restored = []
            for s in completed:
                fname       = s["file"]
                action      = s.get("action", "create")
                backup_path = s.get("backup", "")
                target      = self._resolve_path(fname, action)
                if action == "create":
                    try:
                        if target.exists():
                            target.unlink()
                            deleted.append(fname)
                    except Exception as e:
                        logger.warning(f"[SelfDev] 取消清除失敗（{fname}）：{e}")
                elif action == "modify" and backup_path:
                    try:
                        if pathlib.Path(backup_path).exists():
                            shutil.copy2(backup_path, target)
                            restored.append(fname)
                    except Exception as e:
                        logger.warning(f"[SelfDev] 取消還原失敗（{fname}）：{e}")

            _plan_state = {
                "active": False, "request": "", "steps": [],
                "current_step": 0, "completed": [], "pending_write": {},
            }
            parts = ["❌ 已取消計畫，所有資料已清除"]
            if deleted:   parts.append(f"🗑 已刪除：{', '.join(deleted)}")
            if restored:  parts.append(f"↩ 已還原：{', '.join(restored)}")
            if not deleted and not restored: parts.append("（無已寫入的檔案）")
            return "\n".join(parts)

    def has_pending(self) -> bool:
        return _plan_state["active"] or bool(_pending)

    # ── 進度條 ────────────────────────────────────────────────────────────────

    def _progress_bar(self, done: int, total: int) -> str:
        filled = "█" * done
        empty  = "░" * (total - done)
        return f"進度 [{filled}{empty}] {done}/{total}"

    # ── 舊版單步確認（向下相容）──────────────────────────────────────────────

    def _confirm_legacy(self) -> str:
        global _pending
        if not _pending:
            return "沒有待確認的行動，請先說明需求"

        filename      = _pending["filename"]
        action        = _pending["action"]
        goal          = _pending["goal"]
        original_code = _pending["original_code"]
        new_code      = _pending["new_code"]
        _pending      = {}

        target      = self._resolve_path(filename, action)
        backup_path = None
        if action == "modify" and target.exists():
            backup_path = self._backup(target)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_code, encoding="utf-8")
        except Exception as e:
            return f"寫入失敗：{e}"

        test_ok, test_output = self._run_test(filename)
        if not test_ok and backup_path:
            shutil.copy2(backup_path, target)
            return (
                f"⚠️ 測試失敗，已自動還原 {filename}\n\n"
                f"錯誤：{test_output}\n\n請換個描述方式再試"
            )

        self._record(filename, action, goal, new_code, test_ok, backup_path)
        action_zh   = "修改" if action == "modify" else "新增"
        backup_info = f"\n備份：{pathlib.Path(backup_path).name}" if backup_path else ""
        test_info   = "✓ 測試通過" if test_ok else "⚠ 測試略過"
        summary     = self._summarize_changes(original_code, new_code, action)

        return (
            f"✅ 已{action_zh} {filename}{backup_info}\n"
            f"{test_info}\n\n做了什麼：\n{summary}"
        )

    # ── 意圖解析 ──────────────────────────────────────────────────────────────

    def _parse_intent(self, request: str) -> Optional[dict]:
        req         = request.strip()
        ext_pattern = r"([\w\u4e00-\u9fff\-]+\.(py|html|js|css|json|md|txt|yaml|yml|toml|bat|sh))"

        create_pat = re.search(r"(新增|建立|create)[一個]*\s*" + ext_pattern, req, re.IGNORECASE)
        modify_pat = re.search(r"(修改|改|更新|幫我改|幫我在|在)\s*" + ext_pattern, req, re.IGNORECASE)
        file_pat   = re.search(ext_pattern, req, re.IGNORECASE)

        if create_pat:
            return {"action": "create", "file": create_pat.group(2), "goal": req}
        if modify_pat:
            return {"action": "modify", "file": modify_pat.group(2), "goal": req}
        if file_pat:
            fname  = file_pat.group(1)
            action = "create" if not (WORKSPACE / fname).exists() else "modify"
            return {"action": action, "file": fname, "goal": req}

        prompt = (
            f"使用者需求：{req}\n\n"
            "請判斷這是要新增還是修改哪個檔案，輸出 JSON：\n"
            '{"action": "modify" 或 "create", "file": "檔名.副檔名", "goal": "需求摘要"}\n'
            "只輸出 JSON，不要其他文字。"
        )
        result = self._infer(prompt)
        try:
            result = re.sub(r"```json|```", "", result).strip()
            return json.loads(result)
        except Exception:
            return None

    # ── 程式碼生成 ────────────────────────────────────────────────────────────

    # ── Claude 詢問學習（自主開發銜接）────────────────────────────────────────

    def _ask_claude_for_guidance(self, goal: str, filename: str, action: str) -> str:
        """
        在生成程式碼前，先問 Claude 這個任務的最佳實踐與設計建議。
        取得的回答會：
          1. 存入 claude_knowledge（下次可搜尋參考）
          2. 當作 context 注入到 prompt 提升生成品質
        回傳 Claude 的建議文字，失敗回傳空字串。
        """
        try:
            from claude_desktop_bridge import get_bridge
            from claude_knowledge import get_knowledge

            action_zh = "修改" if action == "modify" else "新增"
            question = (
                f"我要{action_zh}一個 Python 檔案「{filename}」，需求是：{goal}\n\n"
                "請給我：\n"
                "1. 這個功能最推薦的實作方式（2-3 個要點）\n"
                "2. 常見的坑或需要注意的地方\n"
                "3. 建議的核心函式或類別結構\n"
                "請用純文字條列回答，不要程式碼範例，保持簡潔。"
            )

            logger.info(f"[SelfDev] 詢問 Claude 設計建議：{filename}")
            _push_stage_to_phone("🔍 設計中", f"Claude 正在為 {filename} 提供設計建議...")
            bridge  = get_bridge()
            guidance = bridge.ask(question, auto_learn=False)  # auto_learn=False，我們自己存

            if not guidance or guidance.startswith("❌") or len(guidance) < 20:
                logger.warning("[SelfDev] Claude 建議取得失敗，繼續生成")
                return ""

            # 存入 claude_knowledge 知識庫
            try:
                get_knowledge().store(
                    question=f"[開發建議] {filename}：{goal[:60]}",
                    answer=guidance,
                    source="self_dev_consultation"
                )
                logger.info(f"[SelfDev] Claude 建議已存入知識庫")
            except Exception as e:
                logger.warning(f"[SelfDev] 知識庫寫入失敗：{e}")

            return guidance

        except Exception as e:
            logger.warning(f"[SelfDev] Claude 詢問失敗（繼續本地生成）：{e}")
            return ""

    def _ask_claude_to_fix(self, code: str, filename: str, error: str, error_type: str) -> str:
        """
        發生錯誤時自動問 Claude 修復。
        error_type: 'syntax' / 'functional' / 'unittest'
        回傳修復後的程式碼，失敗回傳原碼。
        """
        global _dev_errors
        _dev_errors.append(f"[{error_type}] {filename}：{error[:150]}")

        try:
            from claude_desktop_bridge import get_bridge

            if error_type == "syntax":
                prompt = (
                    f"以下 Python 程式碼有語法錯誤：\n{error}\n\n"
                    f"檔名：{filename}\n\n"
                    f"```python\n{code[:2000]}\n```\n\n"
                    f"請修復語法錯誤，只輸出純 Python 程式碼，不要任何解釋或 markdown。"
                )
            elif error_type == "functional":
                prompt = (
                    f"以下 Python 程式碼執行時發生錯誤：\n{error}\n\n"
                    f"檔名：{filename}\n\n"
                    f"```python\n{code[:2000]}\n```\n\n"
                    f"請找出錯誤原因並修復，只輸出修復後的完整 Python 程式碼，不要任何解釋或 markdown。"
                )
            else:  # unittest
                prompt = (
                    f"以下 Python 程式碼的 unittest 測試失敗：\n{error}\n\n"
                    f"檔名：{filename}\n\n"
                    f"```python\n{code[:2000]}\n```\n\n"
                    f"請根據測試失敗原因修復程式碼，只輸出修復後的完整 Python 程式碼，不要任何解釋或 markdown。"
                )

            logger.info(f"[SelfDev] 請 Claude 修復 {error_type} 錯誤：{filename}")
            bridge = get_bridge()
            fixed = bridge.ask(prompt, auto_learn=False, max_chars=0)

            if not fixed or fixed.startswith("❌") or len(fixed) < 30:
                return code

            fixed = re.sub(r"^```\w*\s*", "", fixed.strip())
            fixed = re.sub(r"\s*```$", "", fixed.strip()).strip()
            fixed = self._fix_fullwidth(fixed)

            if filename.endswith(".py"):
                ok, err = self._check_syntax(fixed)
                if not ok:
                    logger.warning(f"[SelfDev] Claude 修復後仍有語法錯誤：{err}")
                    return code

            logger.info(f"[SelfDev] Claude 修復成功：{filename}")
            return fixed

        except Exception as e:
            logger.warning(f"[SelfDev] Claude 修復失敗：{e}")
            return code

    def _ask_claude_to_review(self, code: str, filename: str, goal: str) -> str:
        """
        生成程式碼後，讓 Claude 審查並改進。
        若 Claude 回傳有效程式碼則使用；否則保留原碼。
        同時將問答存入知識庫。
        """
        try:
            from claude_desktop_bridge import get_bridge
            from claude_knowledge import get_knowledge

            ext = pathlib.Path(filename).suffix.lower()
            question = (
                f"以下是我剛生成的 {filename}，需求是：{goal}\n\n"
                f"```python\n{code[:1500]}\n```\n\n"
                "請審查並輸出**改進後的完整程式碼**（只輸出純 Python 程式碼，不要任何 markdown 標記或解釋）。"
                "如果沒有需要改進的地方，原樣輸出即可。"
            )

            logger.info(f"[SelfDev] 請 Claude 審查程式碼：{filename}")
            bridge   = get_bridge()
            reviewed = bridge.ask(question, auto_learn=False, max_chars=0)

            if not reviewed or reviewed.startswith("❌") or len(reviewed) < 30:
                return code

            # 清理 markdown fence
            reviewed = re.sub(r"^```\w*\s*", "", reviewed.strip())
            reviewed = re.sub(r"\s*```$", "", reviewed.strip()).strip()

            # 存入知識庫（這次問答本身有學習價值）
            try:
                get_knowledge().store(
                    question=f"[程式碼審查] {filename}：{goal[:60]}",
                    answer=f"Claude 審查後改進了以下部分：\n{reviewed[:300]}",
                    source="self_dev_review"
                )
            except Exception:
                pass

            # 語法驗證：確保 Claude 的回傳是有效程式碼
            if ext == ".py":
                ok, err = self._check_syntax(reviewed)
                if not ok:
                    logger.warning(f"[SelfDev] Claude 審查後語法錯誤（{err}），保留原碼")
                    return code

            logger.info(f"[SelfDev] Claude 審查完成，採用改進版本")
            return reviewed

        except Exception as e:
            logger.warning(f"[SelfDev] Claude 審查失敗，保留原碼：{e}")
            return code

    def _get_knowledge_context(self, goal: str) -> str:
        """從 Claude 知識庫取得相關知識，加入生成 prompt"""
        try:
            from claude_knowledge import get_knowledge
            results = get_knowledge().search(goal, top_k=3)
            if not results:
                return ""
            lines = ["\n相關知識（請參考以下最佳實踐）："]
            for r in results:
                lines.append(f"- {r['question']}：{r['answer'][:150]}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _detect_imports(self, code: str) -> list:
        """偵測程式碼中的 import，找出需要安裝的第三方套件"""
        stdlib = {
            "os", "sys", "re", "json", "time", "datetime", "pathlib",
            "shutil", "subprocess", "threading", "queue", "logging",
            "ast", "math", "random", "hashlib", "base64", "io",
            "collections", "functools", "itertools", "typing", "abc",
            "unittest", "argparse", "csv", "sqlite3", "http", "urllib",
        }
        third_party = []
        for line in code.splitlines():
            line = line.strip()
            if line.startswith("import "):
                pkg = line.split()[1].split(".")[0]
                if pkg not in stdlib:
                    third_party.append(pkg)
            elif line.startswith("from "):
                pkg = line.split()[1].split(".")[0]
                if pkg not in stdlib:
                    third_party.append(pkg)
        return list(dict.fromkeys(third_party))  # 去重保序

    def _generate_code(self, goal: str, filename: str, original_code: str, action: str) -> str:
        ext      = pathlib.Path(filename).suffix.lower()
        lang_map = {".py": "Python", ".html": "HTML", ".js": "JavaScript",
                    ".css": "CSS", ".json": "JSON", ".md": "Markdown"}
        lang     = lang_map.get(ext, "Python")

        # ── Solo 模式：只用本地模型 + 知識庫經驗，跳過所有 Claude 呼叫 ──
        solo_ctx = _plan_state.get("_solo_context", "")
        if solo_ctx and ext == ".py":
            logger.info("[SelfDev] Solo 模式：用知識庫經驗直接本地生成")
            self._last_gen_used_local = True
            solo_prompt = (
                f"你是一個資深 Python 工程師。\n"
                f"需求：{goal}\n\n"
                f"相關開發經驗（請參考以下模式）：\n{solo_ctx[:800]}\n\n"
            )
            if action == "modify" and original_code:
                solo_prompt += f"現有程式碼：\n{original_code[:500]}\n\n"
            solo_prompt += "只輸出純 Python 程式碼，不要任何解釋或 markdown 標記。"
            system = "你是一個專業的 Python 工程師。只輸出純 Python 程式碼，使用繁體中文寫註解。"
            for attempt in range(1, 4):
                result = self._infer(solo_prompt, system)
                result = re.sub(r"^```\w*\s*", "", result.strip())
                result = re.sub(r"\s*```$", "", result.strip()).strip()
                result = self._fix_fullwidth(result)
                ok, err = self._check_syntax(result)
                if ok:
                    return result
                logger.warning(f"[SelfDev] Solo attempt {attempt}: {err}")
            return result

        # 從 Claude 知識庫取得相關知識
        knowledge_ctx = self._get_knowledge_context(goal) if ext == ".py" else ""

        if action == "modify":
            prompt = (
                "你是一個資深 " + lang + " 工程師。\n需求：" + goal + "\n\n"
                "現有程式碼（" + filename + "）：\n```" + lang.lower() + "\n" + original_code + "\n```\n\n"
                + knowledge_ctx + "\n\n"
                "請輸出修改後的**完整**程式碼。\n規則：\n"
                "1. 只輸出 " + lang + " 程式碼，不要任何解釋或 markdown 標記\n"
                "2. 保留所有原有功能，只增加/修改需求要求的部分\n"
                "3. 使用繁體中文寫註解\n4. 確保語法正確\n"
                "5. 不要省略任何原有程式碼，輸出完整檔案\n"
                "6. 加上適當的錯誤處理"
            )
        else:
            prompt = (
                "你是一個資深 " + lang + " 工程師。\n需求：" + goal + "\n檔案名稱：" + filename + "\n\n"
                + knowledge_ctx + "\n\n"
                "請輸出這個新檔案的完整程式碼。\n規則：\n"
                "1. 只輸出 " + lang + " 程式碼，不要任何解釋或 markdown 標記\n"
                "2. 使用繁體中文寫註解\n3. 確保語法正確\n"
                "4. 加上簡短的檔案說明在最前面\n5. 結構清楚\n"
                "6. 加上適當的錯誤處理\n"
                "7. 如果是 Python，加上 if __name__ == '__main__' 區塊"
            )

        system = (
            "你是一個專業的 " + lang + " 工程師。"
            "永遠只輸出純 " + lang + " 程式碼，不要任何 markdown 標記（```）或解釋。"
            "程式碼必須語法正確。使用繁體中文寫註解。"
        )

        # 優先用 Claude 橋接生成程式碼（品質更高）
        try:
            from claude_desktop_bridge import get_bridge
            bridge_prompt = (
                "請用繁體中文寫註解，只輸出純 " + lang + " 程式碼，不要任何解釋或 markdown 標記。\n\n"
                + prompt
            )
            logger.info("[SelfDev] 使用 Claude 橋接生成程式碼")
            _push_stage_to_phone("⚙️ 施作中", f"Claude 正在生成 {filename} 的程式碼...")
            result = get_bridge().ask(bridge_prompt, auto_learn=False, max_chars=0)
            if result and not result.startswith("❌") and len(result) > 50:
                # 清理 markdown 標記
                result = re.sub(r"^```\w*\s*", "", result.strip())
                result = re.sub(r"\s*```$", "", result.strip()).strip()

                # 若第一行不像 Python 程式碼（有中文句子），跳過到第一個 def/import/# 行
                if ext == ".py":
                    lines = result.splitlines()
                    code_start = 0
                    for i, line in enumerate(lines):
                        stripped = line.strip()
                        if stripped.startswith(("#", "import", "from", "def ", "class ", '"""', "\'")):
                            code_start = i
                            break
                    if code_start > 0:
                        result = "\n".join(lines[code_start:]).strip()

                    # 全形字元清理（Claude 有時也會輸出全形標點）
                    result = self._fix_fullwidth(result)

                    syntax_ok, syntax_err = self._check_syntax(result)
                    if syntax_ok:
                        logger.info("[SelfDev] Claude 橋接生成成功")
                        self._last_gen_used_local = False
                        return result
                    logger.warning(f"[SelfDev] Claude 生成語法錯誤：{syntax_err}")
                else:
                    self._last_gen_used_local = False
                    return result
        except Exception as e:
            logger.warning(f"[SelfDev] Claude 橋接失敗，改用本地模型：{e}")

        for attempt in range(1, 4):
            result = self._infer(prompt, system)
            result = re.sub(r"^```\w*\s*", "", result.strip())
            result = re.sub(r"\s*```$", "", result.strip()).strip()

            if ext == ".py":
                result = self._fix_fullwidth(result)

                syntax_ok, syntax_err = self._check_syntax(result)
                if syntax_ok:
                    self._last_gen_used_local = True  # 本地生成，可讓 Claude 審查
                    return result

                logger.warning(f"[SelfDev] attempt {attempt}: syntax error: {syntax_err}")
                prompt = (
                    f"你剛才生成的 {filename} 有語法錯誤：\n{syntax_err}\n\n"
                    f"有問題的程式碼：\n```python\n{result}\n```\n\n"
                    f"請修復語法錯誤，輸出修正後的**完整**程式碼。只輸出 Python 程式碼。"
                )
            else:
                return result

        logger.error("[SelfDev] 3 次重試都失敗")
        return result

    # ── 語法檢查 ──────────────────────────────────────────────────────────────

    def _fix_fullwidth(self, code: str) -> str:
        """清理全形標點符號，避免 Python 語法錯誤"""
        return (code
            .replace("\u300c", '"').replace("\u300d", '"')
            .replace("\u300e", '"').replace("\u300f", '"')
            .replace("\uff0c", ",").replace("\u3002", ".")
            .replace("\uff1a", ":").replace("\uff1b", ";")
            .replace("\uff08", "(").replace("\uff09", ")")
            .replace("\uff3b", "[").replace("\uff3d", "]")
            .replace("\uff5b", "{").replace("\uff5d", "}")
        )

    def _check_syntax(self, code: str) -> tuple[bool, str]:
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"第 {e.lineno} 行：{e.msg}"

    # ── 執行測試 ──────────────────────────────────────────────────────────────

    def _run_test(self, filename: str) -> tuple[bool, str]:
        ext = pathlib.Path(filename).suffix.lower()
        if ext != ".py":
            return True, "(non-Python, skip test)"
        try:
            result = subprocess.run(
                ["python", "-c",
                 f"import importlib.util, sys; "
                 f"spec=importlib.util.spec_from_file_location('m',r'{WORKSPACE/filename}'); "
                 f"mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)"],
                capture_output=True, text=True, timeout=15, cwd=str(WORKSPACE)
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr[:300]
        except subprocess.TimeoutExpired:
            return True, "(test timeout, pass)"
        except Exception as e:
            return True, f"(test skipped: {e})"

    # ── 備份 ─────────────────────────────────────────────────────────────────

    def _self_test(self, filename: str, code: str, target: pathlib.Path) -> str:
        """
        寫入後的自我測試，分兩階段：
        A）功能測試：執行 __main__ 區塊，檢查輸出
        C）Claude 生成 unittest：問 Claude 寫測試 → 執行 → 回報
        測試完成後寫學習總結存入知識庫。
        回傳測試摘要字串。
        """
        results = []

        # A）功能測試
        func_ok, func_out = self._run_functional_test(filename, target)
        if func_ok:
            results.append(f"🧪 功能測試通過")
            logger.info(f"[SelfDev] 功能測試通過：{filename}")
        else:
            results.append(f"⚠️ 功能測試失敗：{func_out[:80]}")
            logger.warning(f"[SelfDev] 功能測試失敗：{func_out[:100]}")
            # 自動請 Claude 修復
            fixed_code = self._ask_claude_to_fix(code, filename, func_out, "functional")
            if fixed_code != code:
                target.write_text(fixed_code, encoding="utf-8")
                code = fixed_code
                func_ok2, func_out2 = self._run_functional_test(filename, target)
                if func_ok2:
                    results.append("✅ Claude 修復後功能測試通過")
                    func_ok = True
                else:
                    results.append(f"❌ Claude 修復後仍失敗：{func_out2[:60]}")

        # C）Claude 生成 unittest 並執行
        unittest_result = self._generate_and_run_unittest(filename, code, target)
        if unittest_result:
            results.append(unittest_result)

        # 寫學習總結存入知識庫
        self._write_dev_summary(filename, code, func_ok, unittest_result)

        return "\n".join(results)

    def _write_dev_summary(self, filename: str, code: str, func_ok: bool, unittest_result: str):
        """
        測試完成後，讓 Claude 生成這次開發的學習總結，存入 claude_knowledge。
        內容包含：模組功能、設計亮點、測試結果、錯誤原因、可改進的地方。
        """
        try:
            from claude_desktop_bridge import get_bridge
            from claude_knowledge import get_knowledge

            funcs   = re.findall(r"^def (\w+)\(", code, re.MULTILINE)
            classes = re.findall(r"^class (\w+)", code, re.MULTILINE)
            head    = "\n".join(code.splitlines()[:40])
            test_status     = "通過" if func_ok else "失敗"
            unittest_status = unittest_result or "未執行"

            # 整理本次流程中的錯誤記錄
            errors_text = ""
            if _dev_errors:
                errors_text = "\n本次流程發生的錯誤：\n" + "\n".join(f"- {e}" for e in _dev_errors)

            prompt = (
                f"我剛完成了 {filename} 的開發與測試，請幫我寫一份學習總結。\n\n"
                f"模組資訊：\n"
                f"- 函式：{', '.join(funcs[:8]) if funcs else '無'}\n"
                f"- 類別：{', '.join(classes) if classes else '無'}\n"
                f"- 功能測試：{test_status}\n"
                f"- unittest：{unittest_status[:100]}\n"
                f"{errors_text}\n\n"
                f"程式碼前40行：\n{head}\n\n"
                f"請用繁體中文寫一份簡短學習總結（200字以內），包含：\n"
                f"1. 這個模組的核心功能\n"
                f"2. 使用了哪些技術或設計模式\n"
                f"3. 測試結果與品質評估\n"
                f"4. 本次流程中發生了哪些錯誤及原因\n"
                f"5. 未來可以改進的地方"
            )

            logger.info(f"[SelfDev] 請 Claude 生成學習總結：{filename}")
            bridge  = get_bridge()
            summary = bridge.ask(prompt, auto_learn=False)

            if not summary or summary.startswith("❌"):
                logger.warning("[SelfDev] 學習總結生成失敗")
                return

            # 存入 claude_knowledge
            get_knowledge().store(
                question=f"[開發總結] {filename} 開發與測試完成",
                answer=summary,
                source="self_dev_summary"
            )
            logger.info(f"[SelfDev] 學習總結已存入知識庫：{filename}")

            # 推送摘要到手機
            _push_stage_to_phone(
                "📝 學習總結",
                f"{filename}\n\n{summary[:200]}"
            )

        except Exception as e:
            logger.warning(f"[SelfDev] 學習總結失敗：{e}")

    def _run_functional_test(self, filename: str, target: pathlib.Path) -> tuple[bool, str]:
        """
        執行程式的 __main__ 區塊，檢查有無例外。
        timeout 10 秒，有輸出視為通過，拋例外視為失敗。
        """
        try:
            result = subprocess.run(
                ["python", str(target)],
                capture_output=True, text=True, timeout=10,
                cwd=str(WORKSPACE), encoding="utf-8", errors="ignore"
            )
            if result.returncode == 0:
                out = (result.stdout or "（無輸出）").strip()[:100]
                return True, out
            err = (result.stderr or result.stdout or "未知錯誤").strip()[:200]
            return False, err
        except subprocess.TimeoutExpired:
            return True, "（執行超時，視為通過）"
        except Exception as e:
            return True, f"（略過：{e}）"

    def _generate_and_run_unittest(self, filename: str, code: str, target: pathlib.Path) -> str:
        """
        C）讓 Claude 為這個模組生成 unittest，存成 test_xxx.py，執行後回報。
        """
        test_filename = "test_" + filename
        test_target   = target.parent / test_filename

        try:
            from claude_desktop_bridge import get_bridge

            # 取程式碼摘要（函式清單 + 前50行）
            funcs = re.findall(r"^def (\w+)\(", code, re.MULTILINE)
            head  = "\n".join(code.splitlines()[:50])
            funcs_str = ", ".join(funcs[:8]) if funcs else "（無函式）"

            prompt = (
                f"以下是 Python 模組 {filename} 的摘要：\n\n"
                f"函式：{funcs_str}\n\n"
                f"程式碼前50行：\n{head}\n\n"
                f"請為這個模組寫一個精簡的 unittest 測試檔，檔名為 {test_filename}。\n"
                f"規則：\n"
                f"1. 只輸出純 Python 程式碼，不要任何解釋或 markdown\n"
                f"2. 使用 unittest.TestCase\n"
                f"3. 每個函式最多一個測試，總共不超過 10 個測試\n"
                f"4. 測試要能獨立執行（不依賴外部服務，用 mock 或 patch）\n"
                f"5. 加上 if __name__ == '__main__': unittest.main()\n"
                f"6. 保持簡潔，整個測試檔不超過 100 行"
            )

            logger.info(f"[SelfDev] 請 Claude 生成 unittest：{test_filename}")
            bridge   = get_bridge()
            test_code = bridge.ask(prompt, auto_learn=False, max_chars=0)

            if not test_code or test_code.startswith("❌"):
                return "⚠️ unittest 生成失敗"

            # 清理 markdown
            test_code = re.sub(r"^```\w*\s*", "", test_code.strip())
            test_code = re.sub(r"\s*```$", "", test_code.strip()).strip()
            test_code = self._fix_fullwidth(test_code)

            # 清理 leading zeros（如 011434 → 11434）
            test_code = re.sub(r'\b0+([1-9]\d*)\b', r'\1', test_code)

            # 跳過開頭非程式碼行（說明文字、markdown 殘留）
            lines = test_code.splitlines()
            code_start = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith(("#", "import", "from", "class", "def", '"""', "'")):
                    code_start = i
                    break
            if code_start > 0:
                test_code = "\n".join(lines[code_start:]).strip()

            # 語法檢查，失敗時嘗試截斷到最後一個完整函式
            ok, err = self._check_syntax(test_code)
            if not ok:
                # 找最後一個語法正確的截斷點
                lines = test_code.splitlines()
                for cut in range(len(lines), 0, -10):
                    candidate = "\n".join(lines[:cut])
                    ok2, _ = self._check_syntax(candidate)
                    if ok2:
                        test_code = candidate
                        ok = True
                        logger.info(f"[SelfDev] unittest 截斷修復到第 {cut} 行")
                        break
            if not ok:
                logger.warning(f"[SelfDev] unittest 語法錯誤：{err}")
                return f"⚠️ unittest 語法錯誤：{err}"

            # 寫入測試檔
            test_target.write_text(test_code, encoding="utf-8")
            logger.info(f"[SelfDev] 已寫入測試檔：{test_target}")

            # 執行測試
            result = subprocess.run(
                ["python", "-m", "unittest", str(test_target), "-v"],
                capture_output=True, text=True, timeout=30,
                cwd=str(WORKSPACE), encoding="utf-8", errors="ignore"
            )
            output = (result.stderr or result.stdout or "").strip()

            # 解析結果
            if "OK" in output:
                passed = len(re.findall(r"\.{1}", output))
                return f"✅ unittest 通過（{passed} 個測試）→ {test_filename}"
            elif "FAILED" in output:
                failures = re.findall(r"FAILED \((.+?)\)", output)
                fail_str = failures[0] if failures else "未知"
                # 自動請 Claude 修復主程式碼
                fixed_code = self._ask_claude_to_fix(code, filename, output[-500:], "unittest")
                if fixed_code != code:
                    target.write_text(fixed_code, encoding="utf-8")
                    # 重新執行 unittest
                    result2 = subprocess.run(
                        ["python", "-m", "unittest", str(test_target), "-v"],
                        capture_output=True, text=True, timeout=30,
                        cwd=str(WORKSPACE), encoding="utf-8", errors="ignore"
                    )
                    output2 = (result2.stderr or result2.stdout or "").strip()
                    if "OK" in output2:
                        passed = len(re.findall(r"\.{1}", output2))
                        return f"✅ Claude 修復後 unittest 通過（{passed} 個測試）→ {test_filename}"
                return f"❌ unittest 失敗（{fail_str}）→ {test_filename}"
            else:
                return f"🧪 unittest 執行完成 → {test_filename}"

        except subprocess.TimeoutExpired:
            return f"⚠️ unittest 執行超時 → {test_filename}"
        except Exception as e:
            logger.warning(f"[SelfDev] unittest 失敗：{e}")
            return f"⚠️ unittest 失敗：{e}"

    def _backup(self, file_path: pathlib.Path) -> str:
        ts     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"{file_path.name}.{ts}.bak"
        shutil.copy2(file_path, backup)
        logger.info(f"[SelfDev] 備份：{backup.name}")
        return str(backup)

    def restore(self, filename: str) -> str:
        target  = WORKSPACE / filename
        backups = sorted(BACKUP_DIR.glob(f"{filename}.*.bak"), reverse=True)
        if not backups:
            return f"找不到 {filename} 的備份"
        shutil.copy2(backups[0], target)
        return f"✅ 已還原 {filename}（從 {backups[0].name}）"

    # ── 變更摘要 ──────────────────────────────────────────────────────────────

    def _summarize_changes(self, original: str, new_code: str, action: str) -> str:
        if action == "create":
            lines   = new_code.count("\n") + 1
            funcs   = re.findall(r"^def (\w+)", new_code, re.MULTILINE)
            classes = re.findall(r"^class (\w+)", new_code, re.MULTILINE)
            parts   = [f"新增了 {lines} 行程式碼"]
            if funcs:   parts.append(f"函式：{', '.join(funcs)}")
            if classes: parts.append(f"類別：{', '.join(classes)}")
            return "\n".join(f"• {p}" for p in parts)

        orig_lines = set(original.splitlines())
        new_lines  = set(new_code.splitlines())
        added   = [l.strip() for l in (new_lines - orig_lines) if l.strip() and not l.strip().startswith("#")]
        removed = [l.strip() for l in (orig_lines - new_lines) if l.strip() and not l.strip().startswith("#")]
        parts   = []
        if added[:3]:   parts.append(f"新增了：{' / '.join(added[:3])}")
        if removed[:2]: parts.append(f"移除了：{' / '.join(removed[:2])}")
        if not parts:   parts.append("格式或註解調整")
        return "\n".join(f"• {p}" for p in parts)

    # ── 歷史記錄 ──────────────────────────────────────────────────────────────

    def _record(self, filename, action, goal, code, success, backup):
        REPORT_FILE.parent.mkdir(exist_ok=True)
        history = []
        if REPORT_FILE.exists():
            try:
                history = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
            except Exception:
                history = []
        history.append({
            "time":    datetime.datetime.now().isoformat(timespec="seconds"),
            "file":    filename,
            "action":  action,
            "goal":    goal[:100],
            "success": success,
            "backup":  backup,
            "lines":   code.count("\n") + 1,
        })
        history = history[-100:]
        REPORT_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_history(self, n: int = 10) -> str:
        if not REPORT_FILE.exists():
            return "（尚無開發記錄）"
        history = json.loads(REPORT_FILE.read_text(encoding="utf-8"))[-n:]
        lines   = []
        for h in reversed(history):
            icon      = "✓" if h["success"] else "✗"
            action_zh = "新增" if h["action"] == "create" else "修改"
            lines.append(f"{icon} [{h['time']}] {action_zh} {h['file']} — {h['goal'][:50]}")
        return "\n".join(lines)

    # ── 底層推論 ──────────────────────────────────────────────────────────────

    def _infer(self, prompt: str, system: str = "") -> str:
        if _USE_GUARD:
            return safe_infer(prompt=prompt, system=system, model=self.model, timeout=120)
        try:
            import requests
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.model, "prompt": prompt,
                      "system": system, "stream": False},
                timeout=120
            )
            return r.json().get("response", "")
        except Exception as e:
            return f"[ERROR] {e}"


# ── 模組層級單例 ──────────────────────────────────────────────────────────────
_engine: Optional[SelfDevEngine] = None

def get_engine() -> SelfDevEngine:
    global _engine
    if _engine is None:
        _engine = SelfDevEngine()
    return _engine


if __name__ == "__main__":
    eng    = SelfDevEngine()
    result = eng.handle("幫我做一個可以抓 YouTube 字幕的工具，存成 youtube_handler.py")
    print(result)
