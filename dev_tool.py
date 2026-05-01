"""
dev_tool.py — 通用自主開發外包工具
獨立執行，不依賴立AI任何模組。
AI推論介面預留，之後接立AI大腦。

使用方式：
    from dev_tool import get_tool, set_brain, TelegramNotifier
    set_brain(your_brain)
    tool = get_tool()
    tool.set_notifier(TelegramNotifier(bot, allowed_ids))
    tool.start("幫我做一個視覺辨識系統")
"""

import json
import re
import pathlib
import logging

try:
    from agent_logger import get_logger
    logger = get_logger("dev_tool")
except ImportError:
    logger = logging.getLogger("dev_tool")
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
import time
import shutil
import datetime
import subprocess
import threading
import ast as _ast

# ── 路徑設定 ──────────────────────────────────────────────────────────────────

WORKSPACE   = pathlib.Path(".")
BACKUP_DIR  = pathlib.Path("memory/dev_backups")
STATE_FILE  = pathlib.Path("memory/dev_tool_state.json")
TEMP_DIR    = pathlib.Path("temp")       # 暫存區
PROJECTS_DIR= pathlib.Path("projects")   # 正式輸出區
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# ── 截圖判斷模組（找不到就靜默降級）────────────────────────────────────────
try:
    from phase_runner import take_screenshot, ai_judge_screenshot
    _HAS_SCREENSHOT = True
except ImportError:
    _HAS_SCREENSHOT = False

# ── AI 推論介面（預留，之後接立AI大腦）──────────────────────────────────────

class BrainInterface:
    """
    AI推論介面預留層。
    接入立AI大腦時，繼承這個 class 並實作 ask()。
    """
    def ask(self, prompt: str, raw: bool = False) -> str:
        raise NotImplementedError("請先呼叫 set_brain() 接入AI大腦")

    def is_available(self) -> bool:
        return False


_brain: BrainInterface = BrainInterface()

def set_brain(brain: BrainInterface):
    """接入AI大腦"""
    global _brain
    _brain = brain


# ── 通知介面（Telegram / 桌面 UI）────────────────────────────────────────────

class Notifier:
    """通知介面預留層"""
    def send(self, text: str, buttons: list = None):
        """
        送出通知
        buttons: [{"label": str, "callback": str}] 或 None
        """
        pass

    def send_stage(self, stage: str, detail: str = ""):
        """送出階段通知（純文字，無按鈕）"""
        pass


class TelegramNotifier(Notifier):
    """Telegram 推送實作"""

    def __init__(self, bot, allowed_ids: list):
        self.bot         = bot
        self.allowed_ids = allowed_ids

    def send(self, text: str, buttons: list = None):
        try:
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = None
            if buttons:
                kb = InlineKeyboardMarkup(row_width=1)
                for b in buttons:
                    kb.add(InlineKeyboardButton(
                        b["label"],
                        callback_data=b["callback"]
                    ))
            logger.info(f"[Notifier] 推送到 {self.allowed_ids}，按鈕數：{len(buttons) if buttons else 0}")
            for cid in self.allowed_ids:
                self.bot.send_message(cid, text, reply_markup=kb)
            logger.info("[Notifier] 推送成功")
        except Exception as e:
            logger.warning(f"[Notifier] 推送失敗：{e}")

    def send_stage(self, stage: str, detail: str = ""):
        text = f"🤖 立AI開發進度\n\n{stage}"
        if detail:
            text += f"\n{detail[:200]}"
        self.send(text)


class PrintNotifier(Notifier):
    """終端機輸出（測試用）"""
    def send(self, text: str, buttons: list = None):
        print(f"\n{text}")
        if buttons:
            for i, b in enumerate(buttons):
                print(f"  [{i+1}] {b['label']} → {b['callback']}")

    def send_stage(self, stage: str, detail: str = ""):
        print(f"[{stage}] {detail}")


# ── 開發狀態 ──────────────────────────────────────────────────────────────────

class DevState:
    """開發流程狀態，持久化到檔案"""

    def __init__(self):
        self.request:          str  = ""
        self.output_dir:       str  = ""
        self.task_name:        str  = ""     # 任務名稱（資料夾名）
        self.temp_dir:         str  = ""     # 暫存區路徑
        self.project_dir:      str  = ""     # 正式輸出路徑
        self.groups:           dict = {}
        self.completed_groups: list = []
        self.current_group:    str  = ""
        self.steps:            list = []
        self.completed_steps:  list = []
        self.active:           bool = False
        self.solo_context:     str  = ""
        self.current_step_idx: int  = 0
        self.paused:           bool = False
        self.auto_pause:       bool = True
        self.last_code:        str  = ""     # 最後一次修正的程式碼
        self.last_error:       str  = ""     # 最後一次的錯誤訊息
        self.load()

    def load(self):
        if STATE_FILE.exists():
            try:
                d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.__dict__.update(d)
            except Exception:
                pass

    def save(self):
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(self.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def reset(self):
        self.__dict__.update({
            "request": "", "output_dir": "", "groups": {},
            "completed_groups": [], "current_group": "",
            "steps": [], "completed_steps": [], "active": False,
            "task_name": "", "temp_dir": "", "project_dir": "",
            "solo_context": "", "current_step_idx": 0,
            "paused": False, "auto_pause": True,
            "last_code": "", "last_error": "",
        })
        if STATE_FILE.exists():
            STATE_FILE.unlink()

    def mark_group_done(self, group_key: str):
        if group_key not in self.completed_groups:
            self.completed_groups.append(group_key)
        if group_key in self.groups:
            self.groups[group_key]["done"] = True
        self.save()

    def remaining_groups(self) -> dict:
        return {k: v for k, v in self.groups.items()
                if k not in self.completed_groups}


# ── 模板 ──────────────────────────────────────────────────────────────────────

class SpecTemplate:
    """規格討論結果模板"""
    def __init__(self, request: str, raw_spec: str):
        self.request    = request
        self.raw_spec   = raw_spec
        self.files      = list(dict.fromkeys(re.findall(r'[a-zA-Z0-9_\-]+\.py', raw_spec)))
        self.groups_json = self._parse_groups_json()

    def _parse_groups_json(self) -> str:
        gi = self.raw_spec.rfind('{"groups"')
        if gi == -1:
            return ""
        depth = 0
        for i, ch in enumerate(self.raw_spec[gi:], gi):
            if ch == '{': depth += 1
            elif ch == '}': depth -= 1
            if depth == 0:
                return self.raw_spec[gi:i+1]
        return ""

    def context_for_step2(self) -> str:
        """傳給第二輪的 context（因為開新分頁）"""
        files_str = "\n".join(f"- {f}" for f in self.files[:10]) or "（請自行決定）"
        return (
            f"專案需求：「{self.request}」\n"
            f"規格討論中提到的檔案：\n{files_str}\n\n"
            + (f"分組規劃：{self.groups_json}\n\n" if self.groups_json else "")
        )


class StepTemplate:
    """步驟執行模板"""
    def __init__(self, step: dict, step_idx: int, total: int,
                 completed: list, plan_context: str):
        self.step         = step
        self.step_idx     = step_idx
        self.total        = total
        self.completed    = completed
        self.plan_context = plan_context

    def to_gen_prompt(self, guidance: str = "") -> str:
        lines = [self.plan_context, ""]
        if self.completed:
            lines.append("已完成步驟：")
            for s in self.completed[-3:]:
                lines.append(f"  ✓ {s.get('title','')}（{s.get('file','')}）")
            lines.append("")
        if guidance:
            lines += ["設計建議：", guidance, ""]
        fname     = self.step.get("file", "")
        action_zh = "修改" if self.step.get("action") == "modify" else "新增"
        lines += [
            f"生成任務：{action_zh} {fname}",
            f"需求：{self.step.get('desc','')}",
            "",
            "只輸出純 Python 程式碼，不要任何 markdown 標記或解釋。",
        ]
        return "\n".join(lines)


class TestResultTemplate:
    """測試結果模板"""
    def __init__(self, filename: str, ok: bool, error: str = ""):
        self.filename   = filename
        self.ok         = ok
        self.error      = error
        self.error_type = self._classify(error)

    def _classify(self, e: str) -> str:
        if not e:                                          return ""
        if "SyntaxError" in e:                            return "SyntaxError"
        if "ImportError" in e or "ModuleNotFound" in e:   return "ImportError"
        if "RuntimeError" in e or "TypeError" in e:       return "RuntimeError"
        return "UnknownError"

    def to_fix_prompt(self, code: str, suggestion: str = "", attempt: int = 1) -> str:
        return (
            f"修正任務（第 {attempt} 次）\n"
            f"檔案：{self.filename}\n"
            f"錯誤類型：{self.error_type}\n"
            f"錯誤訊息：{self.error[:300]}\n\n"
            + (f"修正建議：\n{suggestion}\n\n" if suggestion else "")
            + f"完整程式碼：\n{code}\n\n"
            "請修正上述錯誤，只輸出修正後的完整 Python 程式碼，不要任何解釋或 markdown。"
        )


# ── 核心工具 ──────────────────────────────────────────────────────────────────

class DevTool:

    def __init__(self):
        self.state    = DevState()
        self.notifier = PrintNotifier()
        self._spec:   SpecTemplate = None

    def set_notifier(self, notifier: Notifier):
        self.notifier = notifier

    # ── 階段1：規格討論 ───────────────────────────────────────────────────────

    def start(self, request: str, output_dir: str = "projects/output") -> dict:
        """開始開發：AI規格討論 → 取得分組 → 推送心智圖"""
        if not _brain.is_available():
            return {"error": "AI大腦尚未接入"}

        self.notifier.send_stage("📋 規格討論中", "正在與AI討論專案架構...")

        prompt = (
            f"我要開發一個 Python 專案：「{request}」\n\n"
            "請規劃這個專案需要哪些 Python 檔案（給出真實的英文檔名），"
            "每個檔案的職責、要定義哪些函式（列出真實函式名稱）。\n\n"
            "請自己決定最適合的分組方式，並在回答最後輸出 JSON 分類表。\n"
            "重要：JSON 裡所有內容必須是真實的，不要用佔位符。\n"
            '格式（最後一行輸出）:\n'
            '{"groups":[{"key":"capture","label":"擷取層","icon":"📸","desc":"負責畫面擷取","files":["screen_capture.py"]},{"key":"inference","label":"推論層","icon":"🧠","desc":"負責視覺辨識","files":["vision_local.py"]}]}\n\n'
            "規則：\n"
            "- key 根據功能命名（不要用 group_a）\n"
            "- label 是繁體中文（不要用分組名稱這種佔位符）\n"
            "- files 是真實的 Python 檔名清單\n"
            "- 只在回答最後輸出 JSON，前面用條列說明"
        )

        spec_raw = _brain.ask(prompt, raw=True)
        if not spec_raw:
            return {"error": "AI規格討論失敗"}

        self._spec = SpecTemplate(request, spec_raw)
        groups     = self._parse_groups(self._spec)

        # 更新狀態
        # 用需求產生任務名稱（取前20字，去掉非法字元）
        import re as _re
        task_name = _re.sub(r'[\\/:*?"<>|]', "", request[:20]).strip()
        if not task_name:
            task_name = f"task_{int(time.time())}"

        temp_path    = TEMP_DIR     / task_name
        project_path = PROJECTS_DIR / task_name
        temp_path.mkdir(parents=True, exist_ok=True)
        project_path.mkdir(parents=True, exist_ok=True)

        self.state.reset()
        self.state.request     = request
        self.state.task_name   = task_name
        self.state.temp_dir    = str(temp_path)
        self.state.project_dir = str(project_path)
        self.state.output_dir  = str(temp_path)  # 生成時先寫暫存區
        self.state.groups      = groups
        self.state.active      = True
        self.state.save()

        pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 推送心智圖第一層
        self._push_mindmap()

        return {"groups": groups, "spec": self._spec}

    # ── 階段2：針對模組規劃步驟 ──────────────────────────────────────────────

    def select_group(self, group_key: str):
        """使用者選了某個模組 → 針對這個模組規劃步驟"""
        if not _brain.is_available():
            self.notifier.send("❌ AI大腦尚未接入")
            return

        info    = self.state.groups.get(group_key, {})
        label   = info.get("label", group_key)
        desc    = info.get("desc", "")
        files   = info.get("files", [])
        request = self.state.request

        self.notifier.send_stage(f"📋 規劃 {label}", "AI正在規劃步驟...")

        files_str = "\n".join(f"- {f}" for f in files) or "（請自行決定）"
        prompt = (
            f"專案需求：「{request}」\n\n"
            f"我現在要實作「{label}」這個模組，負責：{desc}\n\n"
            f"這個模組包含以下檔案：\n{files_str}\n\n"
            "請為這些檔案輸出開發步驟的 JSON 陣列。\n"
            "第一個字元必須是 [，只輸出 JSON：\n"
            '[{"title":"步驟名稱","desc":"新增實際檔名.py，定義func_a()做什麼","file":"實際檔名.py","action":"create"}]\n\n'
            "規則：\n"
            "- file 必須是上面檔案清單裡的真實檔名\n"
            "- desc 說明定義哪些函式、做什麼事\n"
            "- action 只能是 create 或 modify\n"
            "- 每個檔案一個步驟\n"
            "- 只輸出 JSON 陣列"
        )

        raw   = _brain.ask(prompt, raw=True)
        logger.info(f"[DevTool] select_group 原始回傳前400字：{str(raw)[:400]}")
        steps = self._parse_steps_json(raw) if raw else []

        if not steps:
            self.notifier.send(f"❌ {label} 步驟規劃失敗，請重試")
            return

        self.state.groups[group_key]["steps"] = steps
        self.state.current_group  = group_key
        self.state.steps          = steps
        self.state.completed_steps = []
        self.state.save()

        # 推送步驟選擇（第二層）
        self._push_steps(group_key, steps)

    # ── 階段3：執行步驟 ───────────────────────────────────────────────────────

    def select_step(self, step_idx: int):
        """使用者選了某個步驟 → 推送確認按鈕"""
        steps = self.state.steps
        if step_idx >= len(steps):
            self.notifier.send("❌ 步驟索引超出範圍")
            return

        step = steps[step_idx]
        self.state.current_step_idx = step_idx
        self.state.save()

        self.notifier.send(
            f"▶️ 步驟 {step_idx+1}：{step['title']}\n"
            f"   📄 {step['file']}\n\n"
            f"{step.get('desc','')[:150]}\n\n"
            "確認開始製作這個步驟？",
            buttons=[
                {"label": "✅ 確認開始製作", "callback": f"dt_confirm_{step_idx}"},
                {"label": "⏸ 暫停存草稿",   "callback": "dt_save_draft"},
                {"label": "⬅️ 返回模組選擇", "callback": "dt_back_groups"},
            ]
        )

    def execute_step(self, step_idx: int):
        """確認後執行步驟：設計建議 → 生成 → 測試"""
        if not _brain.is_available():
            self.notifier.send("❌ AI大腦尚未接入")
            return

        steps = self.state.steps
        if step_idx >= len(steps):
            self.notifier.send("❌ 步驟索引超出範圍")
            return

        step       = steps[step_idx]
        filename   = step["file"]
        action     = step.get("action", "create")
        output_dir = pathlib.Path(self.state.output_dir)
        target     = output_dir / filename

        self.notifier.send_stage(f"⚙️ 製作中", f"正在生成 {filename}...")

        # 備份
        backup_path = None
        if action == "modify" and target.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = BACKUP_DIR / f"{filename}.{ts}.bak"
            shutil.copy2(target, backup_path)

        # 設計建議
        guidance = self._get_guidance(filename, step.get("desc", ""), action)

        # 生成程式碼
        plan_ctx = self._build_plan_context(step_idx)
        step_tpl = StepTemplate(
            step=step, step_idx=step_idx,
            total=len(steps),
            completed=self.state.completed_steps,
            plan_context=plan_ctx,
        )
        gen_prompt = step_tpl.to_gen_prompt(guidance)
        code = _brain.ask(gen_prompt, raw=True)

        if not code:
            self.notifier.send(f"❌ {filename} 程式碼生成失敗")
            return

        code = self._clean_code(code)
        ok, err = self._check_syntax(code)
        if not ok:
            self.notifier.send_stage("🔧 語法錯誤，自動修正中", f"{filename}：{err}")
            threading.Thread(
                target=self._enter_fix_loop,
                args=(filename, code, err, backup_path, 1),
                daemon=True,
            ).start()
            return

        # 寫入
        output_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")

        # 測試
        self.notifier.send_stage("🧪 測試中", f"正在測試 {filename}...")
        test_ok, test_err = self._run_test(target)

        if not test_ok:
            # 先推送失敗通知，讓用戶選擇修正還是退回
            done_cnt = len(self.state.completed_steps)
            self.notifier.send(
                f"❌ {filename} 測試失敗\n\n{test_err[:200]}",
                buttons=[
                    {"label": "🔧 自動修正",   "callback": f"dt_fix_1_{filename}"},
                    {"label": "⏪ 退回上一步", "callback": "dt_rollback"},
                    {"label": "⏸ 暫停存草稿", "callback": "dt_save_draft"},
                    {"label": "🛑 停止",       "callback": "dt_stop"},
                ]
            )
            return

        self._on_step_done(step, filename, code, backup_path)

    # ── 修正循環 ──────────────────────────────────────────────────────────────

    def _enter_fix_loop(self, filename: str, code: str, error: str,
                        backup_path, attempt: int = 1):
        """測試失敗進入修正循環：分析+生成一次完成，保留上一版程式碼"""
        self.notifier.send_stage("🔧 修正中", f"第 {attempt} 次嘗試修正 {filename}...")

        # 把錯誤、原始程式碼、修正說明全部放進同一個 prompt，一次給 Claude
        fix_prompt = (
            f"以下 Python 程式 {filename} 執行失敗（第 {attempt} 次修正）。\n\n"
            f"【錯誤訊息】\n{error[:500]}\n\n"
            f"【原始程式碼】\n{code}\n\n"
            f"【任務】\n"
            f"1. 先用 # 註解說明錯誤原因和修正方式（2-3 行）\n"
            f"2. 然後輸出修正後的完整 Python 程式碼\n\n"
            f"只輸出純文字，不要 markdown，不要提供下載檔案。"
        )

        new_code = _brain.ask(fix_prompt, raw=True)

        if not new_code:
            self.notifier.send(
                f"❌ {filename} 第 {attempt} 次修正生成失敗\n\n"
                f"🔴 錯誤：{error[:200]}",
                buttons=[
                    {"label": "✅ 再試一次",   "callback": f"dt_fix_{attempt+1}_{filename}"},
                    {"label": "⏪ 退回上一步", "callback": "dt_rollback"},
                    {"label": "⏸ 暫停存草稿", "callback": "dt_save_draft"},
                    {"label": "🛑 停止",       "callback": "dt_stop"},
                ]
            )
            return

        new_code = self._clean_code(new_code)
        ok, err  = self._check_syntax(new_code)
        if not ok:
            self.notifier.send(
                f"❌ {filename} 第 {attempt} 次修正語法錯誤：{err}",
                buttons=[
                    {"label": "✅ 再試一次",   "callback": f"dt_fix_{attempt+1}_{filename}"},
                    {"label": "⏪ 退回上一步", "callback": "dt_rollback"},
                    {"label": "⏸ 暫停存草稿", "callback": "dt_save_draft"},
                    {"label": "🛑 停止",       "callback": "dt_stop"},
                ]
            )
            return

        target = pathlib.Path(self.state.output_dir) / filename
        target.write_text(new_code, encoding="utf-8")

        test_ok, test_err = self._run_test(target)
        if test_ok:
            self._on_step_done(
                self.state.steps[getattr(self.state, 'current_step_idx', 0)],
                filename, new_code, backup_path
            )
        else:
            # 還是失敗，把最新版存起來，下次帶過去繼續修
            self.state.last_code  = new_code
            self.state.last_error = test_err
            self.state.save()
            self.notifier.send(
                f"⚠️ {filename} 第 {attempt} 次修正仍失敗\n\n"
                f"🔴 錯誤：{test_err[:200]}",
                buttons=[
                    {"label": "✅ 再試一次",   "callback": f"dt_fix_{attempt+1}_{filename}"},
                    {"label": "⏪ 退回上一步", "callback": "dt_rollback"},
                    {"label": "⏸ 暫停存草稿", "callback": "dt_save_draft"},
                    {"label": "🛑 停止",       "callback": "dt_stop"},
                ]
            )

    # ── 完成模組後重新推送心智圖 ──────────────────────────────────────────────

    def _on_step_done(self, step: dict, filename: str, code: str, backup_path):
        """步驟完成：記錄 → 檢查模組是否全完成 → 推送下一步"""
        self.state.completed_steps.append(step)
        self.state.save()

        steps     = self.state.steps
        done_cnt  = len(self.state.completed_steps)
        total_cnt = len(steps)

        self.notifier.send_stage("✅ 步驟完成", f"{filename} 已完成（{done_cnt}/{total_cnt}）")

        # ── 截圖 + 立AI判斷（每個步驟完成後自動執行）──────────────────────
        screenshot_verdict = ""
        if _HAS_SCREENSHOT:
            try:
                time.sleep(1.5)  # 等畫面穩定
                label = filename.replace(".", "_").replace("/", "-")
                ss_path = take_screenshot(f"step_{done_cnt}_{label}")
                question = (
                    f"剛剛完成了 {filename} 的開發，這是目前的畫面。\n"
                    f"請判斷：有沒有錯誤訊息、程式是否正常、有沒有需要注意的問題？"
                )
                verdict = ai_judge_screenshot(ss_path, question)
                screenshot_verdict = f"\n\n📸 立AI看畫面：\n{verdict[:300]}"
                logger.info(f"[截圖判斷] {filename}：{verdict[:100]}")
            except Exception as _ss_err:
                logger.warning(f"[截圖判斷] 失敗：{_ss_err}")
        # ────────────────────────────────────────────────────────────────────

        # 暫停檢查（手動暫停 or 自動暫停）
        if self.state.paused or self.state.auto_pause:
            pause_reason = "⏸ 已暫停" if self.state.paused else "⏸ 步驟完成，等待確認"
            next_info = ""
            if done_cnt < total_cnt:
                ns = self.state.steps[done_cnt]
                next_info = f"\n下一步：{ns['title']}（{ns['file']}）"
            auto_txt = "關閉每步暫停" if self.state.auto_pause else "開啟每步暫停"
            self.notifier.send(
                f"{pause_reason}\n已完成 {done_cnt}/{total_cnt} 步{next_info}",
                buttons=[
                    {"label": "▶️ 繼續下一步",    "callback": "dt_resume"},
                    {"label": f"🔔 {auto_txt}", "callback": "dt_toggle_autopause"},
                    {"label": "⏸ 暫停存草稿",     "callback": "dt_save_draft"},
                    {"label": "🛑 停止開發",       "callback": "dt_stop"},
                ]
            )
            return  # 等用戶確認才繼續

        if done_cnt >= total_cnt:
            # 整個模組完成
            group_key = self.state.current_group
            self.state.mark_group_done(group_key)
            remaining = self.state.remaining_groups()

            # 模組完成：把暫存區檔案複製到正式目錄
            self._flush_module_to_project(group_key)

            if not remaining:
                # 全部完成
                all_done = "\n".join(
                    f"  ✓ {v['label']}" for v in self.state.groups.values()
                )
                proj_path = self.state.project_dir
                self.notifier.send(
                    f"🎉 專案全部完成！\n\n"
                    f"完成的模組：\n{all_done}\n\n"
                    f"📁 檔案位置：{proj_path}"
                )
                self.state.active = False
                self.state.save()
            else:
                # 重新推送心智圖（移掉已完成的模組）
                self.notifier.send(
                    f"✅ {self.state.groups[group_key]['label']} 完成！\n"
                    f"剩餘 {len(remaining)} 個模組，請選擇繼續："
                )
                self._push_mindmap()
        else:
            # 模組內還有步驟，推送下一步
            next_idx  = done_cnt
            next_step = steps[next_idx]
            self.notifier.send(
                f"✅ 步驟 {done_cnt}/{total_cnt} 完成\n\n"
                f"下一步：{next_step['title']}（{next_step['file']}）",
                buttons=[
                    {"label": f"▶️ 繼續步驟 {done_cnt+1}", "callback": f"dt_step_{next_idx}"},
                    {"label": "⬅️ 返回模組選擇",           "callback": "dt_back_groups"},
                ]
            )

    # ── 心智圖推送 ────────────────────────────────────────────────────────────

    def _push_mindmap(self):
        """推送第一層：剩餘模組選擇按鈕"""
        remaining = self.state.remaining_groups()
        if not remaining:
            return

        lines = ["🗺 專案心智圖", "─"*28,
                 f"📌 {self.state.request[:40]}", ""]
        for info in remaining.values():
            n = len(info.get("steps", []) or info.get("files", []))
            lines.append(f"  • {info['icon']} {info['label']} — {info['desc'][:30]}")
        lines.extend(["", "👇 選擇要先開發哪個模組："])

        buttons = [
            {"label": f"{v['icon']} {v['label']}", "callback": f"dt_group_{k}"}
            for k, v in remaining.items()
        ]
        # 加入暫停控制按鈕
        auto_txt = "🔔 關閉每步暫停" if self.state.auto_pause else "🔔 開啟每步暫停"
        buttons.append({"label": auto_txt, "callback": "dt_toggle_autopause"})
        buttons.append({"label": "⏸ 暫停存草稿", "callback": "dt_save_draft"})
        self.notifier.send("\n".join(lines), buttons=buttons)

    def _push_steps(self, group_key: str, steps: list):
        """推送第二層：步驟選擇按鈕"""
        info  = self.state.groups.get(group_key, {})
        label = info.get("label", group_key)

        lines = [f"✅ {info.get('icon','')} {label}",
                 "─"*28, f"📋 規劃了 {len(steps)} 個步驟："]
        for step in steps:
            icon = "🆕" if step.get("action") == "create" else "✏️"
            lines.append(f"  • {icon} {step['title']}（{step['file']}）")
        lines.extend(["", "👇 選擇要先製作哪個步驟："])

        buttons = [
            {"label": f"{'🆕' if s.get('action')=='create' else '✏️'} {s['title']}（{s['file']}）",
             "callback": f"dt_step_{i}"}
            for i, s in enumerate(steps)
        ]
        buttons.append({"label": "⬅️ 返回模組選擇", "callback": "dt_back_groups"})
        self.notifier.send("\n".join(lines), buttons=buttons)

    # ── callback 路由（Telegram callback_data 格式：dt_xxx）─────────────────

    def handle_callback(self, callback_data: str) -> bool:
        """
        處理按鈕 callback。
        回傳 True 代表已處理，False 代表不認識。
        """
        if not callback_data.startswith("dt_"):
            return False

        data = callback_data[3:]  # 去掉 dt_ 前綴

        if data == "back_groups":
            self._push_mindmap()

        elif data.startswith("group_"):
            group_key = data[6:]
            threading.Thread(
                target=self.select_group, args=(group_key,), daemon=True
            ).start()

        elif data.startswith("step_"):
            step_idx = int(data[5:])
            self.select_step(step_idx)

        elif data.startswith("confirm_"):
            step_idx = int(data[8:])
            threading.Thread(
                target=self.execute_step, args=(step_idx,), daemon=True
            ).start()

        elif data.startswith("fix_"):
            parts    = data[4:].split("_", 1)
            attempt  = int(parts[0])
            filename = parts[1] if len(parts) > 1 else ""
            target   = pathlib.Path(self.state.output_dir) / filename
            # 優先用 state 儲存的最新版程式碼，否則從檔案讀
            code  = getattr(self.state, "last_code", None) or \
                    (target.read_text(encoding="utf-8") if target.exists() else "")
            error = getattr(self.state, "last_error", "重試") or "重試"
            threading.Thread(
                target=self._enter_fix_loop,
                args=(filename, code, error, None, attempt),
                daemon=True
            ).start()

        elif data == "rollback":
            self._rollback()

        elif data == "save_draft":
            # 儲存草稿：暫停流程，暫存區保留，不複製到正式目錄
            self.state.paused = True
            self.state.save()
            done  = len(self.state.completed_steps)
            total = len(self.state.steps)
            remaining_groups = len(self.state.remaining_groups())
            self.notifier.send(
                f"⏸ 草稿已儲存\n\n"
                f"目前進度：{done}/{total} 步驟完成\n"
                f"剩餘模組：{remaining_groups} 個\n\n"
                f"📁 暫存位置：{self.state.temp_dir}\n"
                f"（尚未寫入正式專案）\n\n"
                f"下次直接說「繼續開發」即可從這裡繼續。",
                buttons=[
                    {"label": "▶️ 繼續開發", "callback": "dt_resume"},
                    {"label": "🛑 結束",     "callback": "dt_stop"},
                ]
            )

        elif data == "pause":
            self.state.paused = True
            self.state.save()
            self.notifier.send("⏸ 已暫停，當前步驟完成後停止\n\n按「▶️ 繼續」繼續開發")

        elif data == "resume":
            self.state.paused = False
            self.state.save()
            # 繼續執行下一步
            done  = len(self.state.completed_steps)
            total = len(self.state.steps)
            if done < total:
                self.notifier.send("▶️ 繼續開發中...")
                threading.Thread(
                    target=self.execute_step, args=(done,), daemon=True
                ).start()
            else:
                self.notifier.send("✅ 所有步驟已完成")

        elif data == "toggle_autopause":
            self.state.auto_pause = not self.state.auto_pause
            self.state.save()
            status = "開啟" if self.state.auto_pause else "關閉"
            self.notifier.send(f"🔔 每步暫停已{status}")

        elif data == "stop":
            self.state.active = False
            self.state.save()
            self.notifier.send("🛑 已停止開發")

        else:
            return False

        return True

    def _rollback(self):
        """退回上一個步驟"""
        if self.state.completed_steps:
            last = self.state.completed_steps.pop()
            self.state.save()
            target = pathlib.Path(self.state.output_dir) / last["file"]
            # 找最近備份
            backups = sorted(BACKUP_DIR.glob(f"{last['file']}.*.bak"), reverse=True)
            if backups:
                shutil.copy2(backups[0], target)
                self.notifier.send(f"⏪ 已退回：{last['file']} 還原到備份版本")
            else:
                if target.exists():
                    target.unlink()
                self.notifier.send(f"⏪ 已退回：刪除 {last['file']}")
            # 找回退的步驟索引
            rolled_idx = len(self.state.completed_steps)
            rolled_step = self.state.steps[rolled_idx] if rolled_idx < len(self.state.steps) else last
            self.notifier.send(
                f"⏪ 已退回：{last['file']}\n\n"
                f"下一步：{rolled_step['title']}（{rolled_step['file']}）",
                buttons=[
                    {"label": "▶️ 重新執行這個步驟", "callback": f"dt_confirm_{rolled_idx}"},
                    {"label": "⬅️ 返回模組選擇",     "callback": "dt_back_groups"},
                ]
            )
        else:
            self.notifier.send("⏪ 沒有可以退回的步驟，返回模組選擇")
            self._push_mindmap()

    # ── 暫存區 → 正式目錄 ──────────────────────────────────────────────────

    def _flush_module_to_project(self, group_key: str):
        """
        把這個模組在暫存區的所有檔案複製到正式目錄。
        同一任務的不同模組都放在同一個 project_dir。
        """
        try:
            temp_path    = pathlib.Path(self.state.temp_dir)
            project_path = pathlib.Path(self.state.project_dir)
            project_path.mkdir(parents=True, exist_ok=True)

            # 找這個模組負責的檔案
            group_info = self.state.groups.get(group_key, {})
            group_files = group_info.get("files", [])
            # 也從 completed_steps 找
            step_files = [s["file"] for s in self.state.completed_steps
                          if s.get("_module") == group_key or not group_files]
            all_files  = list(dict.fromkeys(group_files + step_files))

            copied = []
            for fname in all_files:
                src = temp_path / fname
                dst = project_path / fname
                if src.exists():
                    shutil.copy2(src, dst)
                    copied.append(fname)

            if copied:
                logger.info(f"[DevTool] 模組 {group_key} 複製到正式目錄：{copied}")
                self.notifier.send_stage(
                    f"📁 已存入專案",
                    f"{self.state.task_name}/\n" + "\n".join(f"  + {f}" for f in copied)
                )
        except Exception as e:
            logger.warning(f"[DevTool] flush 失敗：{e}")

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _parse_groups(self, spec: SpecTemplate) -> dict:
        groups = {}
        if spec.groups_json:
            try:
                data = json.loads(spec.groups_json)
                for g in data.get("groups", []):
                    key = g.get("key", f"group_{len(groups)}")
                    groups[key] = {
                        "label": g.get("label", key),
                        "icon":  g.get("icon", "📦"),
                        "desc":  g.get("desc", ""),
                        "files": g.get("files", []),
                        "done":  False,
                        "steps": [],
                    }
            except Exception:
                pass
        if not groups and spec.files:
            for f in spec.files:
                k = f.replace(".py", "")
                groups[k] = {"label": f, "icon": "📄", "desc": "", "files": [f],
                             "done": False, "steps": []}
        return groups

    def _build_plan_context(self, current_idx: int) -> str:
        info = self.state.groups.get(self.state.current_group, {})
        lines = [
            f"專案：{self.state.request}",
            f"模組：{info.get('label', '')}",
            f"步驟進度：{current_idx+1}/{len(self.state.steps)}",
        ]
        if self.state.completed_steps:
            lines.append("已完成：")
            for s in self.state.completed_steps[-3:]:
                lines.append(f"  ✓ {s.get('title','')}（{s.get('file','')}）")
        return "\n".join(lines)

    def _get_guidance(self, filename: str, goal: str, action: str) -> str:
        # solo 模式：用知識庫經驗取代設計建議
        if self.state.solo_context:
            return self.state.solo_context
        if not _brain.is_available():
            return ""
        action_zh = "修改" if action == "modify" else "新增"
        prompt = (
            f"我要{action_zh}一個 Python 檔案「{filename}」，需求是：{goal}\n\n"
            "請給我：\n1. 最推薦的實作方式（2-3 個要點）\n"
            "2. 常見的坑\n3. 建議的核心函式結構\n"
            "用純文字條列，不要程式碼範例，保持簡潔。"
        )
        # 設計建議用 Claude（raw=True），品質更好且不依賴 Ollama
        return _brain.ask(prompt, raw=True) or ""

    def _clean_code(self, code: str) -> str:
        code = re.sub(r"^```\w*\s*", "", code.strip())
        code = re.sub(r"\s*```$", "", code.strip()).strip()
        for i, line in enumerate(code.splitlines()):
            if line.strip().startswith(("#","import","from","class","def",'"""',"'")):
                return "\n".join(code.splitlines()[i:]).strip()
        return code

    def _check_syntax(self, code: str) -> tuple:
        try:
            _ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"第 {e.lineno} 行：{e.msg}"

    def _run_test(self, target: pathlib.Path) -> tuple:
        if target.suffix.lower() != ".py":
            return True, ""
        try:
            result = subprocess.run(
                ["python", "-c",
                 f"import importlib.util; "
                 f"s=importlib.util.spec_from_file_location('m',r'{target}'); "
                 f"m=importlib.util.module_from_spec(s); s.loader.exec_module(m)"],
                capture_output=True, text=True, timeout=15,
                cwd=str(target.parent), encoding="utf-8", errors="ignore"
            )
            return (True, "") if result.returncode == 0 else (False, result.stderr[:300])
        except subprocess.TimeoutExpired:
            return True, "(timeout)"
        except Exception as e:
            return True, f"(skipped: {e})"

    def _parse_steps_json(self, raw: str) -> list:
        # 找最後一個 [{，Claude 通常把真實 JSON 放在最後
        start = raw.rfind("[{")
        if start == -1: start = raw.rfind("[")
        if start == -1: return []
        depth = 0
        end   = -1
        for i, ch in enumerate(raw[start:], start):
            if ch == "[":   depth += 1
            elif ch == "]": depth -= 1
            if depth == 0:
                end = i
                break
        if end == -1: return []
        try:
            steps = []
            for s in json.loads(raw[start:end+1]):
                if not all(k in s for k in ["title","desc","file","action"]):
                    logger.warning(f"[DevTool] 步驟缺欄位：{list(s.keys())}")
                    continue
                fname = s["file"].strip()
                # 取純檔名驗證（允許帶子資料夾路徑如 capture/screen_capture.py）
                basename = fname.split("/")[-1].split("\\")[-1]
                if not re.match(r'^[a-zA-Z0-9_\-]+\.py$', basename):
                    logger.warning(f"[DevTool] 檔名不符：{repr(fname)}")
                    continue
                steps.append({
                    "title":  s["title"],
                    "desc":   s["desc"].strip(),
                    "file":   fname,
                    "action": s["action"] if s["action"] in ["create","modify"] else "create",
                })
            logger.info(f"[DevTool] 解析到 {len(steps)} 個步驟")
            return steps
        except Exception as e:
            logger.warning(f"[DevTool] JSON 解析失敗：{e}，raw前200：{raw[start:start+200]}")
            return []


# ── 單例 ─────────────────────────────────────────────────────────────────────

_tool: DevTool = None

def get_tool() -> DevTool:
    global _tool
    if _tool is None:
        _tool = DevTool()
    return _tool


if __name__ == "__main__":
    print("dev_tool.py — 通用自主開發外包工具")
    print("AI大腦尚未接入，請呼叫 set_brain() 後使用。")
    print()
    print("接入方式：")
    print("  from dev_tool import get_tool, set_brain, BrainInterface")
    print("  class MyBrain(BrainInterface):")
    print("      def ask(self, prompt, raw=False): ...")
    print("      def is_available(self): return True")
    print("  set_brain(MyBrain())")
    print("  get_tool().start('你的專案需求')")
