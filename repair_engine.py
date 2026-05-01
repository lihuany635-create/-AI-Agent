from syntax_classifier import SyntaxClassifier
from syntax_rewriter import SyntaxRewriter
import ast
import re
from pathlib import Path
import importlib.util
import requests

from repair_validator import RepairValidator


class RepairEngine:

    def __init__(self):
        self.validator = RepairValidator()
        self.syntax_classifier = SyntaxClassifier()
        self.syntax_rewriter = SyntaxRewriter()

    # ================= ENTRY =================

    def repair(self, file_path, error_info, supervisor):
        """修復入口：先備份，修復失敗自動還原。"""
        fp = Path(file_path)
        before_code = fp.read_text(encoding='utf-8')

        # ── 備份原始碼 ────────────────────────────────────────────────────────
        import datetime, shutil
        backup_dir = fp.parent / ".repair_backup"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{fp.stem}_{ts}{fp.suffix}"
        shutil.copy2(fp, backup_path)

        def _restore():
            fp.write_text(before_code, encoding='utf-8')

        # ⭐ Phase 1 啟發式（只改出錯行）
        if self._heuristic_repair(file_path, error_info):
            after_code = fp.read_text(encoding='utf-8')
            try:
                val = self.validator.validate(before_code, after_code)
                if val["valid"]:
                    return {"status": "FIXED", "backup": str(backup_path)}
            except Exception:
                pass
            _restore()

        # ⭐ Phase 2 LLM
        if self._repair_llm(file_path, error_info)["status"] == "FIXED":
            after_code = fp.read_text(encoding='utf-8')
            try:
                val = self.validator.validate(before_code, after_code)
                if val["valid"]:
                    return {"status": "FIXED", "backup": str(backup_path)}
            except Exception:
                pass
            _restore()

        _restore()
        return {"status": "FAILED", "backup": str(backup_path)}

    # ================= HEURISTIC PACK =================

    def _heuristic_repair(self, file_path, error_info):

        print("HEURISTIC CALLED:", error_info)

        err_msg = str(error_info)

        # ⭐ Syntax dispatch
        if error_info and error_info.get("type") == "SYNTAX_ERROR":

            print("SYNTAX ERROR DETECTED")

            syntax_type = self.syntax_classifier.classify(
                error_info.get("message", "")
            )

            print("SYNTAX TYPE:", syntax_type)

            if syntax_type == "MISSING_COLON":
                line_no = error_info.get("line")
                print("FIXING COLON AT:", line_no)
                return self.syntax_rewriter.fix_missing_colon(file_path, line_no)

        # ---- existing heuristics ----

        if "division by zero" in err_msg:
            return self._fix_zero_division(file_path, error_info)

        if "has no attribute" in err_msg:
            return self._fix_attribute_error(file_path, error_info)

        if "unsupported operand" in err_msg:
            return self._fix_type_error(file_path, error_info)

        if "not defined" in err_msg:
            return self._fix_name_error(file_path, error_info)

        if "No module named" in err_msg:
            return self._fix_import_error(file_path, error_info)

        return False

    def _fix_line(self, file_path: str, line_no: int, transform) -> bool:
        """只修改出錯的那一行，不動其他行。"""
        if not line_no:
            return False
        lines = Path(file_path).read_text(encoding='utf-8').splitlines(keepends=True)
        if line_no < 1 or line_no > len(lines):
            return False
        original = lines[line_no - 1]
        fixed = transform(original)
        if fixed is None or fixed == original:
            return False
        lines[line_no - 1] = fixed
        Path(file_path).write_text("".join(lines), encoding='utf-8')
        return True

    def _fix_zero_division(self, file_path, error_info=None):
        line_no = (error_info or {}).get("line")
        if line_no:
            return self._fix_line(file_path, line_no,
                lambda l: re.sub(r"/ *0(?![.\d])", "/ 1", l))
        # fallback：只改第一個出現的位置
        lines = Path(file_path).read_text(encoding='utf-8').splitlines(keepends=True)
        for i, line in enumerate(lines):
            new = re.sub(r"/ *0(?![.\d])", "/ 1", line)
            if new != line:
                lines[i] = new
                Path(file_path).write_text("".join(lines), encoding='utf-8')
                return True
        return False

    def _fix_attribute_error(self, file_path, error_info=None):
        line_no = (error_info or {}).get("line")
        # 不做全域替換，改成送 LLM 修比較安全
        return False  # 讓 Phase 2 LLM 處理

    def _fix_type_error(self, file_path, error_info=None):
        line_no = (error_info or {}).get("line")
        if line_no:
            return self._fix_line(file_path, line_no,
                lambda l: re.sub(r'"(\d+)" *\+ *(\d+)', r'int("\1") + \2', l))
        return False

    def _fix_name_error(self, file_path, error_info=None):
        # 只在出錯行上方加宣告，不動整個檔案
        line_no = (error_info or {}).get("line")
        msg = str((error_info or {}).get("message", ""))
        m = re.search(r"name '(\w+)' is not defined", msg)
        if not m:
            return False
        var = m.group(1)
        lines = Path(file_path).read_text(encoding='utf-8').splitlines(keepends=True)
        insert_at = max(0, (line_no or 1) - 1)
        indent = len(lines[insert_at]) - len(lines[insert_at].lstrip()) if lines else 0
        lines.insert(insert_at, " " * indent + f"{var} = None  # auto-patched\n")
        Path(file_path).write_text("".join(lines), encoding='utf-8')
        return True

    def _fix_import_error(self, file_path, error_info=None):
        msg = str((error_info or {}).get("message", ""))
        m = re.search(r"No module named '([\w.]+)'", msg)
        if not m:
            return False
        mod = m.group(1)
        lines = Path(file_path).read_text(encoding='utf-8').splitlines(keepends=True)
        # 找到出問題的 import 行，加 try/except 包住
        for i, line in enumerate(lines):
            if f"import {mod}" in line or f"from {mod}" in line:
                stripped = line.rstrip()
                indent = len(stripped) - len(stripped.lstrip())
                ind = " " * indent
                lines[i] = (f"{ind}try:\n{ind}    {stripped.lstrip()}\n"
                            f"{ind}except ImportError:\n{ind}    {mod.replace('.','_')} = None\n")
                Path(file_path).write_text("".join(lines), encoding='utf-8')
                return True
        return False

    # ================= LLM =================

    def _repair_llm(self, file_path, error_info):

        code = Path(file_path).read_text()

        prompt = f"""
修復此程式錯誤：

{code}

錯誤：
{error_info}
"""

        try:
            r = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "gpt-oss:20b",
                    "messages": [
                        {"role": "system", "content": "你是資深 Python 工程師，只輸出修復後的完整程式碼，不要說明。"},
                        {"role": "user",   "content": prompt}
                    ],
                    "stream": False
                },
                timeout=None
            )
            fixed_code = r.json()["message"]["content"].strip()
            # 移除可能的 markdown fences
            if fixed_code.startswith("```"):
                lines = fixed_code.split("\n")
                fixed_code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            Path(file_path).write_text(fixed_code)
            return {"status": "FIXED"}

        except:
            return {"status": "SKIPPED"}