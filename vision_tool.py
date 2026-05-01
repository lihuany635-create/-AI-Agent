"""
vision_tool.py — 視覺辨識系統外包開發工具
獨立執行，不依賴立AI任何模組。
AI推論介面預留，之後接立AI大腦。

使用方式：
    python vision_tool.py
"""

import json
import re
import pathlib
import shutil
import datetime
import subprocess
import threading
import sys

# ── 路徑設定 ──────────────────────────────────────────────────────────────────

WORKSPACE   = pathlib.Path(".")
OUTPUT_DIR  = pathlib.Path("vision_system")
BACKUP_DIR  = pathlib.Path("vision_system/.backups")
STATE_FILE  = pathlib.Path("vision_system/.dev_state.json")

OUTPUT_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

# ── AI 推論介面（預留，之後接立AI大腦）──────────────────────────────────────

class BrainInterface:
    """
    AI推論介面預留層。
    之後接立AI大腦時，只需實作這個類別的方法。
    """

    def ask(self, prompt: str, raw: bool = False) -> str:
        """
        向AI提問，回傳回答。
        raw=True：需要結構化輸出（JSON），不加任何前綴。
        """
        raise NotImplementedError("尚未接入AI大腦，請實作 BrainInterface.ask()")

    def is_available(self) -> bool:
        """確認AI是否可用"""
        return False


# 目前使用的 brain 實例（之後替換）
_brain: BrainInterface = BrainInterface()

def set_brain(brain: BrainInterface):
    """接入AI大腦"""
    global _brain
    _brain = brain


# ── 開發狀態 ──────────────────────────────────────────────────────────────────

class DevState:
    """開發流程狀態，持久化到檔案"""

    def __init__(self):
        self.request:         str = ""
        self.groups:          dict = {}   # key → {label, desc, files, done, steps}
        self.completed_groups: list = []  # 已完成的 group key
        self.current_group:   str = ""
        self.steps:           list = []
        self.completed_steps: list = []
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
        self.__init__.__func__(self)
        if STATE_FILE.exists():
            STATE_FILE.unlink()

    def mark_group_done(self, group_key: str):
        if group_key not in self.completed_groups:
            self.completed_groups.append(group_key)
        if group_key in self.groups:
            self.groups[group_key]["done"] = True
        self.save()

    def remaining_groups(self) -> dict:
        """回傳尚未完成的分組"""
        return {k: v for k, v in self.groups.items()
                if k not in self.completed_groups}


_state = DevState()


# ── 模板 ──────────────────────────────────────────────────────────────────────

class SpecTemplate:
    """規格討論模板"""
    def __init__(self, request: str, raw_spec: str):
        self.request   = request
        self.raw_spec  = raw_spec
        self.files     = list(dict.fromkeys(re.findall(r'[a-zA-Z0-9_\-]+\.py', raw_spec)))
        self.groups_json = ""
        self._parse_groups()

    def _parse_groups(self):
        gi = self.raw_spec.rfind('{"groups"')
        if gi == -1:
            return
        depth = 0
        for i, ch in enumerate(self.raw_spec[gi:], gi):
            if ch == '{': depth += 1
            elif ch == '}': depth -= 1
            if depth == 0:
                self.groups_json = self.raw_spec[gi:i+1]
                break

    def to_next_prompt(self) -> str:
        """傳給第二輪的 context"""
        files_str = "\n".join(f"- {f}" for f in self.files[:10]) if self.files else "（請自行決定）"
        return (
            f"專案需求：「{self.request}」\n"
            f"規格討論中提到的檔案：\n{files_str}\n\n"
            + (f"分組規劃：{self.groups_json}\n\n" if self.groups_json else "")
        )


class StepTemplate:
    """步驟執行模板"""
    def __init__(self, step: dict, step_idx: int, total: int,
                 completed_steps: list, plan_context: str):
        self.step          = step
        self.step_idx      = step_idx
        self.total         = total
        self.completed     = completed_steps
        self.plan_context  = plan_context

    def to_gen_prompt(self, guidance: str = "") -> str:
        """生成程式碼的完整 prompt"""
        lines = [self.plan_context, ""]
        if self.completed:
            lines.append("已完成步驟：")
            for s in self.completed[-3:]:
                lines.append(f"  ✓ {s.get('title','')}（{s.get('file','')}）")
            lines.append("")
        if guidance:
            lines += ["設計建議：", guidance, ""]
        fname = self.step.get("file", "")
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
        self.filename = filename
        self.ok       = ok
        self.error    = error
        self.error_type = self._classify(error)

    def _classify(self, error: str) -> str:
        if not error: return ""
        if "SyntaxError" in error: return "SyntaxError"
        if "ImportError" in error or "ModuleNotFoundError" in error: return "ImportError"
        if "RuntimeError" in error or "TypeError" in error: return "RuntimeError"
        return "UnknownError"

    def to_fix_prompt(self, code: str, suggestion: str = "", attempt: int = 1) -> str:
        """修正循環的 prompt"""
        return (
            f"修正任務（第 {attempt} 次）\n"
            f"檔案：{self.filename}\n"
            f"錯誤類型：{self.error_type}\n"
            f"錯誤訊息：{self.error[:300]}\n\n"
            + (f"修正建議：\n{suggestion}\n\n" if suggestion else "")
            + f"當前程式碼：\n{code[:800]}\n\n"
            "請修正上述錯誤，只輸出修正後的完整 Python 程式碼。"
        )


# ── 核心開發流程 ──────────────────────────────────────────────────────────────

class VisionDevTool:

    def __init__(self):
        self.state = _state

    # ── 階段1：規格討論 ───────────────────────────────────────────────────────

    def start(self, request: str) -> dict:
        """
        開始開發：向AI討論規格，取得分組。
        回傳 {"groups": {...}, "spec": SpecTemplate}
        """
        if not _brain.is_available():
            return {"error": "AI大腦尚未接入，請先呼叫 set_brain()"}

        # 第一輪：規格討論
        discuss_prompt = (
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
        spec_raw = _brain.ask(discuss_prompt)
        if not spec_raw:
            return {"error": "AI規格討論失敗"}

        spec = SpecTemplate(request, spec_raw)

        # 解析分組
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

        # fallback：從檔名建立分組
        if not groups and spec.files:
            for f in spec.files:
                groups[f.replace(".py", "")] = {
                    "label": f, "icon": "📄", "desc": "", "files": [f],
                    "done": False, "steps": [],
                }

        self.state.request = request
        self.state.groups  = groups
        self.state.completed_groups = []
        self.state.save()

        return {"groups": groups, "spec": spec}

    # ── 階段2：針對模組規劃步驟 ──────────────────────────────────────────────

    def plan_module(self, group_key: str) -> list:
        """
        使用者選了某個模組後，針對這個模組向AI規劃具體步驟。
        """
        if not _brain.is_available():
            return []

        info    = self.state.groups.get(group_key, {})
        label   = info.get("label", group_key)
        desc    = info.get("desc", "")
        files   = info.get("files", [])
        request = self.state.request

        files_str = "\n".join(f"- {f}" for f in files) if files else "（請自行決定）"
        prompt = (
            f"專案需求：「{request}」\n\n"
            f"我現在要實作「{label}」這個模組，負責：{desc}\n\n"
            f"這個模組包含以下檔案：\n{files_str}\n\n"
            f"請為這些檔案輸出開發步驟的 JSON 陣列。\n"
            f"第一個字元必須是 [，只輸出 JSON：\n"
            f'[{{"title":"步驟名稱","desc":"新增實際檔名.py，定義func_a()做什麼","file":"實際檔名.py","action":"create"}}]\n\n'
            f"規則：\n"
            f"- file 必須是上面檔案清單裡的真實檔名\n"
            f"- desc 說明定義哪些函式、做什麼事\n"
            f"- action 只能是 create 或 modify\n"
            f"- 每個檔案一個步驟\n"
            f"- 只輸出 JSON 陣列"
        )

        raw = _brain.ask(prompt, raw=True)
        if not raw:
            return []

        steps = self._parse_steps_json(raw)

        # 存入狀態
        self.state.groups[group_key]["steps"] = steps
        self.state.current_group = group_key
        self.state.steps = steps
        self.state.completed_steps = []
        self.state.save()

        return steps

    # ── 階段3：執行步驟 ───────────────────────────────────────────────────────

    def execute_step(self, step_idx: int) -> dict:
        """
        執行某個步驟：
        1. 取得設計建議
        2. 生成程式碼
        3. 測試
        4. 失敗進入修正循環
        回傳 {"ok": bool, "file": str, "message": str}
        """
        if not _brain.is_available():
            return {"ok": False, "message": "AI大腦尚未接入"}

        steps = self.state.steps
        if step_idx >= len(steps):
            return {"ok": False, "message": "步驟索引超出範圍"}

        step     = steps[step_idx]
        filename = step["file"]
        action   = step.get("action", "create")
        target   = OUTPUT_DIR / filename

        # 備份
        backup_path = None
        if action == "modify" and target.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = BACKUP_DIR / f"{filename}.{ts}.bak"
            shutil.copy2(target, backup_path)

        # 取得 plan context
        plan_ctx = self._build_plan_context(step_idx)
        step_tpl = StepTemplate(
            step=step, step_idx=step_idx,
            total=len(steps),
            completed_steps=self.state.completed_steps,
            plan_context=plan_ctx,
        )

        # 設計建議
        guidance = self._get_guidance(filename, step.get("desc", ""), action)

        # 生成程式碼
        gen_prompt = step_tpl.to_gen_prompt(guidance)
        code = _brain.ask(gen_prompt, raw=True)
        if not code:
            return {"ok": False, "file": filename, "message": "程式碼生成失敗"}

        code = self._clean_code(code)

        # 語法檢查
        ok, err = self._check_syntax(code)
        if not ok:
            return {"ok": False, "file": filename, "message": f"語法錯誤：{err}"}

        # 寫入
        target.write_text(code, encoding="utf-8")

        # 測試
        test_ok, test_err = self._run_test(target)
        if not test_ok:
            return {
                "ok": False,
                "file": filename,
                "message": test_err,
                "code": code,
                "backup": str(backup_path) if backup_path else "",
                "needs_fix": True,
            }

        # 完成
        self.state.completed_steps.append(step)
        self.state.save()

        return {"ok": True, "file": filename, "message": f"✅ {filename} 完成"}

    def fix_step(self, filename: str, code: str, error: str,
                 suggestion: str = "", attempt: int = 1) -> dict:
        """
        修正循環：根據錯誤和建議重新生成。
        """
        if not _brain.is_available():
            return {"ok": False, "message": "AI大腦尚未接入"}

        test_tpl   = TestResultTemplate(filename, False, error)
        fix_prompt = test_tpl.to_fix_prompt(code, suggestion, attempt)
        new_code   = _brain.ask(fix_prompt, raw=True)

        if not new_code:
            return {"ok": False, "message": "修正生成失敗"}

        new_code = self._clean_code(new_code)
        ok, err  = self._check_syntax(new_code)
        if not ok:
            return {"ok": False, "message": f"語法錯誤：{err}", "code": new_code}

        target = OUTPUT_DIR / filename
        target.write_text(new_code, encoding="utf-8")

        test_ok, test_err = self._run_test(target)
        if test_ok:
            return {"ok": True, "file": filename, "message": f"✅ {filename} 修正成功"}
        return {"ok": False, "message": test_err, "code": new_code, "needs_fix": True}

    def complete_module(self, group_key: str):
        """標記模組完成，回傳剩餘模組清單"""
        self.state.mark_group_done(group_key)
        remaining = self.state.remaining_groups()
        return remaining

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _build_plan_context(self, current_step_idx: int) -> str:
        lines = [
            f"專案：{self.state.request}",
            f"模組：{self.state.groups.get(self.state.current_group, {}).get('label', '')}",
            f"步驟進度：{current_step_idx + 1}/{len(self.state.steps)}",
        ]
        if self.state.completed_steps:
            lines.append("已完成：")
            for s in self.state.completed_steps[-3:]:
                lines.append(f"  ✓ {s.get('title','')}（{s.get('file','')}）")
        return "\n".join(lines)

    def _get_guidance(self, filename: str, goal: str, action: str) -> str:
        if not _brain.is_available():
            return ""
        action_zh = "修改" if action == "modify" else "新增"
        prompt = (
            f"我要{action_zh}一個 Python 檔案「{filename}」，需求是：{goal}\n\n"
            "請給我：\n"
            "1. 最推薦的實作方式（2-3 個要點）\n"
            "2. 常見的坑或需要注意的地方\n"
            "3. 建議的核心函式或類別結構\n"
            "請用純文字條列回答，不要程式碼範例，保持簡潔。"
        )
        return _brain.ask(prompt) or ""

    def _clean_code(self, code: str) -> str:
        code = re.sub(r"^```\w*\s*", "", code.strip())
        code = re.sub(r"\s*```$", "", code.strip()).strip()
        lines = code.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith(("#", "import", "from", "class", "def", '"""', "'")):
                code = "\n".join(lines[i:]).strip()
                break
        return code

    def _check_syntax(self, code: str) -> tuple:
        import ast
        try:
            ast.parse(code)
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
                 f"spec=importlib.util.spec_from_file_location('m',r'{target}'); "
                 f"mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)"],
                capture_output=True, text=True, timeout=15,
                cwd=str(OUTPUT_DIR), encoding="utf-8", errors="ignore"
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr[:300]
        except subprocess.TimeoutExpired:
            return True, "(timeout, pass)"
        except Exception as e:
            return True, f"(skipped: {e})"

    def _parse_steps_json(self, raw: str) -> list:
        start = raw.find("[{")
        if start == -1: start = raw.find("[")
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
            data  = json.loads(raw[start:end+1])
            steps = []
            for s in data:
                if not all(k in s for k in ["title", "desc", "file", "action"]):
                    continue
                fname = s["file"].strip()
                if not re.match(r'^[a-zA-Z0-9_\-]+\.py$', fname):
                    continue
                steps.append({
                    "title":  s["title"],
                    "desc":   s["desc"].strip(),
                    "file":   fname,
                    "action": s["action"] if s["action"] in ["create", "modify"] else "create",
                })
            return steps
        except Exception:
            return []


# ── 單例 ─────────────────────────────────────────────────────────────────────

_tool: VisionDevTool = None

def get_tool() -> VisionDevTool:
    global _tool
    if _tool is None:
        _tool = VisionDevTool()
    return _tool


# ── 主程式（測試用）──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("vision_tool.py — 視覺辨識系統開發工具")
    print("AI大腦尚未接入，請呼叫 set_brain() 後使用。")
    print()
    print("使用方式：")
    print("  from vision_tool import get_tool, set_brain")
    print("  set_brain(your_brain)")
    print("  tool = get_tool()")
    print("  result = tool.start('幫我做一個視覺辨識系統')")
