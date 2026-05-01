# autonomous_dev.py — 自主開發系統
# 您說需求，立自己規劃、寫程式、測試、完成通知
# 使用方式：直接在對話框說「幫我做一個 xxx 程式」

import json
import pathlib
import datetime
import subprocess
import ast
import threading
from typing import Optional

try:
    from agent_logger import get_logger
    logger = get_logger("autonomous_dev")
except ImportError:
    import logging
    logger = logging.getLogger("autonomous_dev")

try:
    from screenshot_copy_strategy import smart_copy_after_model_selected
    _USE_SCREENSHOT = True
except ImportError:
    _USE_SCREENSHOT = False
    logger.warning("[AutoDev] screenshot_copy_strategy 未找到，截圖功能停用")

try:
    from ollama_guard import safe_infer
    _USE_GUARD = True
except ImportError:
    _USE_GUARD = False

try:
    from pc_api_client import (
        is_available as _pc_available,
        run_command as _pc_run,
        open_file as _pc_open,
    )
    import requests as _pc_requests
    _USE_PC_API = True
except ImportError:
    _USE_PC_API = False

try:
    from pc_api_client import is_available as _pc_available, run_command as _pc_run, notify as _pc_notify
    _USE_PC_API = True
except ImportError:
    _USE_PC_API = False

OUTPUT_DIR  = pathlib.Path("projects")
REPORT_FILE = pathlib.Path("memory/autonomous_dev_history.json")
OUTPUT_DIR.mkdir(exist_ok=True)


class AutonomousDev:
    """
    自主開發引擎
    輸入需求 → 自動規劃 → 自動生成所有檔案 → 自動測試 → 完成通知
    """

    # 模型優先順序：主模型失敗時依序嘗試備用
    FALLBACK_MODELS = [
        "gemma4",
        "deepseek-r1:1.5b",
        "llama3.2:latest",
        "qwen2:7b-instruct-q4_0",
    ]

    def __init__(self, model: str = "gemma4"):
        self.model        = model
        self._status      = "idle"
        self._log         = []
        self._fail_counts = {}  # 各模型失敗次數

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def build(self, requirement: str, on_progress=None) -> str:
        """
        完整自主開發流程
        on_progress: 進度回呼函式，用於更新 UI
        """
        self._status = "running"
        self._log    = []
        start_time   = datetime.datetime.now()

        def progress(msg: str):
            self._log.append(msg)
            logger.info(f"[AutoDev] {msg}")
            if on_progress:
                on_progress(msg)

        try:
            # 0. 預熱 Ollama
            progress("⏳ 確認 Ollama 狀態...")
            self._warmup()

            # 1. 規劃架構
            progress("📋 分析需求，規劃架構...")
            plan = self._plan(requirement)
            if not plan:
                return "❌ 無法規劃架構，請換個描述方式"

            project_name = plan.get("project_name", "my_project")
            files        = plan.get("files", [])
            description  = plan.get("description", requirement)

            # ★ 截圖判斷：選定模型後，判斷側欄狀態決定複製方式
            copied_content = ""
            if _USE_SCREENSHOT:
                progress("📸 截圖判斷複製方式...")
                try:
                    copied_content = smart_copy_after_model_selected()
                    progress(f"✅ 複製完成（{len(copied_content)} 字元）")
                except Exception as e:
                    progress(f"⚠️ 截圖判斷失敗，跳過：{e}")

            # 若有複製到 Claude 的回應，補充進需求描述一起規劃
            if copied_content:
                enriched_requirement = (
                    f"{requirement}\n\n"
                    f"# Claude 提供的設計方向與程式碼參考：\n{copied_content[:3000]}"
                )
            else:
                enriched_requirement = requirement

            progress(f"📁 專案名稱：{project_name}")
            progress(f"📄 計畫建立 {len(files)} 個檔案：{', '.join(f['name'] for f in files)}")

            # 建立專案資料夾
            project_dir = OUTPUT_DIR / project_name
            project_dir.mkdir(exist_ok=True)

            # 2. 逐一生成每個檔案
            success_files = []
            failed_files  = []

            for i, file_info in enumerate(files, 1):
                fname   = file_info["name"]
                purpose = file_info.get("purpose", "")
                deps    = file_info.get("depends_on", [])

                progress(f"⚙️  [{i}/{len(files)}] 生成 {fname}...")

                # 讀取已完成的依賴檔案內容（讓 AI 知道上下文）
                context_code = ""
                for dep in deps:
                    dep_path = project_dir / dep
                    if dep_path.exists():
                        context_code += f"\n# === {dep} ===\n"
                        context_code += dep_path.read_text(encoding="utf-8")[:800]

                # 生成程式碼（附上 Claude 回應的設計參考）
                code = self._generate_file(
                    requirement=enriched_requirement,
                    project_name=project_name,
                    filename=fname,
                    purpose=purpose,
                    all_files=files,
                    context_code=context_code,
                    claude_reference=copied_content[:2000] if copied_content else "",
                )

                if not code:
                    progress(f"  ⚠️ {fname} 生成失敗，跳過")
                    failed_files.append(fname)
                    continue

                # 語法檢查（Python 檔案）
                if fname.endswith(".py"):
                    try:
                        ast.parse(code)
                    except SyntaxError as e:
                        progress(f"  ⚠️ {fname} 語法錯誤（{e}），嘗試修復...")
                        code = self._fix_syntax(code, str(e))
                        try:
                            ast.parse(code)
                        except SyntaxError:
                            progress(f"  ❌ {fname} 修復失敗，跳過")
                            failed_files.append(fname)
                            continue

                # 寫入檔案（優先走 PC API，否則直接寫）
                file_path = str(project_dir / fname)
                if _USE_PC_API and _pc_available():
                    import requests as _req
                    _req.post("http://localhost:8899/file/write",
                              json={"path": file_path, "content": code}, timeout=10)
                    progress(f"  ✅ {fname} 完成（{len(code.splitlines())} 行，PC API）")
                else:
                    (project_dir / fname).write_text(code, encoding="utf-8")
                    progress(f"  ✅ {fname} 完成（{len(code.splitlines())} 行）")
                success_files.append(fname)

            # 3. 執行測試
            progress("🧪 執行測試...")
            test_result = self._test_project(project_dir, files)
            progress(f"  {test_result}")

            # 4. 生成 README
            progress("📝 生成說明文件...")
            readme = self._generate_readme(requirement, project_name, success_files)
            (project_dir / "README.md").write_text(readme, encoding="utf-8")

            # 5. 完成
            elapsed = int((datetime.datetime.now() - start_time).total_seconds())
            self._status = "done"

            # 記錄歷史
            self._record(requirement, project_name, success_files, failed_files, elapsed)

            # 推送完成通知
            self._notify(project_name, success_files, failed_files)

            summary = (
                f"✅ 專案完成！\n\n"
                f"📁 位置：projects/{project_name}/\n"
                f"📄 成功：{len(success_files)} 個檔案\n"
            )
            if failed_files:
                summary += f"⚠️ 失敗：{len(failed_files)} 個（{', '.join(failed_files)}）\n"
            summary += f"⏱ 耗時：{elapsed} 秒\n\n"
            summary += f"啟動方式：\n```\npython projects/{project_name}/main.py\n```"

            return summary

        except Exception as e:
            self._status = "error"
            logger.error(f"[AutoDev] 錯誤：{e}")
            return f"❌ 開發過程發生錯誤：{e}"

    # ── 規劃 ──────────────────────────────────────────────────────────────────

    def _warmup(self):
        """預熱 Ollama 確保模型已載入"""
        try:
            import requests
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.model, "prompt": "hi", "stream": False},
                timeout=30
            )
            logger.info(f"[AutoDev] Ollama 預熱完成")
        except Exception as e:
            logger.warning(f"[AutoDev] 預熱失敗：{e}")

    def _plan(self, requirement: str) -> Optional[dict]:
        """讓 AI 規劃專案架構"""
        prompt = (
            f"你是一個 Python 軟體架構師。\n"
            f"需求：{requirement}\n\n"
            f"請規劃這個專案的檔案架構，輸出 JSON：\n"
            f'{{"project_name": "專案名稱（英文）", '
            f'"description": "簡短描述", '
            f'"files": [{{"name": "main.py", "purpose": "主程式入口", "depends_on": []}}, '
            f'{{"name": "database.py", "purpose": "資料庫操作", "depends_on": []}}]}}\n\n'
            f"規則：\n"
            f"1. 只輸出 JSON，不要其他文字\n"
            f"2. 檔案數量 3～8 個\n"
            f"3. 依賴關係要正確（被依賴的排前面）\n"
            f"4. 一定要有 main.py 作為入口"
        )
        # 規劃用 gemma4
        plan_model = "gemma4"
        orig = self.model
        self.model = plan_model
        result = self._infer(prompt, timeout=120)
        self.model = orig
        try:
            import re
            result = re.sub(r"```json|```", "", result).strip()
            # 找 JSON 區塊
            start = result.find("{")
            end   = result.rfind("}") + 1
            if start != -1 and end > start:
                result = result[start:end]
            return json.loads(result)
        except Exception as e:
            logger.error(f"[AutoDev] 規劃解析失敗：{e}\n原始：{result[:200]}")
            return None

    # ── 生成單一檔案 ──────────────────────────────────────────────────────────

    def _generate_file(
        self, requirement: str, project_name: str,
        filename: str, purpose: str, all_files: list, context_code: str,
        claude_reference: str = ""
    ) -> str:
        """生成單一檔案的程式碼"""
        all_files_str = ", ".join(f["name"] for f in all_files)
        prompt = (
            f"你是一個 Python 工程師，正在開發「{project_name}」。\n"
            f"整體需求：{requirement}\n"
            f"整個專案包含：{all_files_str}\n"
            f"現在要寫：{filename}（{purpose}）\n\n"
        )
        if claude_reference:
            prompt += f"Claude 提供的設計方向與程式碼參考（請依此實作）：\n{claude_reference}\n\n"
        if context_code:
            prompt += f"已完成的相關程式碼（參考用）：\n{context_code}\n\n"

        prompt += (
            f"請輸出 {filename} 的完整程式碼。\n"
            f"規則：\n"
            f"1. 只輸出純 Python 程式碼，不要 markdown\n"
            f"2. 使用繁體中文寫註解\n"
            f"3. 語法必須正確\n"
            f"4. 要能實際執行\n"
            f"5. UI 使用 PyQt6 或 tkinter\n"
            f"6. 資料庫使用 sqlite3（Python 內建）"
        )
        system = (
            "你是專業 Python 工程師。"
            "只輸出純 Python 程式碼，不要任何 markdown 或解釋。"
        )
        result = self._infer(prompt, system, timeout=120)
        import re
        result = re.sub(r"^```python\s*", "", result.strip())
        result = re.sub(r"\s*```$", "", result.strip())
        result = result.strip()
        # 清除全形標點（中文逗號、句號等會造成語法錯誤）
        result = result.replace("，", ",").replace("。", ".").replace("：", ":").replace("；", ";")
        result = result.replace("（", "(").replace("）", ")").replace("「", '"').replace("」", '"')
        return result

    # ── 修復語法 ──────────────────────────────────────────────────────────────

    def _fix_syntax(self, code: str, error: str) -> str:
        """嘗試修復語法錯誤"""
        prompt = (
            f"以下 Python 程式碼有語法錯誤：{error}\n\n"
            f"```python\n{code[:2000]}\n```\n\n"
            f"請輸出修復後的完整程式碼，只輸出程式碼不要其他文字。"
        )
        result = self._infer(prompt, timeout=120)
        import re
        result = re.sub(r"^```python\s*", "", result.strip())
        result = re.sub(r"\s*```$", "", result.strip())
        result = result.strip()
        result = result.replace("\uff0c", ",").replace("\u3002", ".").replace("\uff1a", ":").replace("\uff1b", ";")
        result = result.replace("\uff08", "(").replace("\uff09", ")")
        return result

    # ── 測試 ──────────────────────────────────────────────────────────────────

    def _test_project(self, project_dir: pathlib.Path, files: list) -> str:
        """嘗試 import 測試每個 Python 檔案（優先走 PC API）"""
        results = []
        for f in files:
            if not f["name"].endswith(".py") or f["name"] == "main.py":
                continue
            fpath = project_dir / f["name"]
            if not fpath.exists():
                continue
            try:
                cmd = (
                    f"python -c \"import importlib.util; "
                    f"spec=importlib.util.spec_from_file_location('m',r'{fpath}'); "
                    f"mod=importlib.util.module_from_spec(spec); "
                    f"spec.loader.exec_module(mod)\""
                )
                if _USE_PC_API and _pc_available():
                    result = _pc_run(cmd, wait=True)
                    ok = result.get("returncode", 1) == 0
                    err = result.get("stderr", "")[:60]
                else:
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True,
                        timeout=10, cwd=str(project_dir)
                    )
                    ok  = result.returncode == 0
                    err = result.stderr[:60]

                if ok:
                    results.append(f"✅ {f['name']}")
                else:
                    results.append(f"⚠️ {f['name']}: {err}")
            except Exception as e:
                results.append(f"⚠️ {f['name']}: {e}")
        return " | ".join(results) if results else "✅ 基本語法檢查通過"

    # ── README 生成 ───────────────────────────────────────────────────────────

    def _generate_readme(self, requirement: str, project_name: str, files: list) -> str:
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        files_str = "\n".join(f"- `{f}`" for f in files)
        return (
            f"# {project_name}\n\n"
            f"由立 AI 自主開發 · {now}\n\n"
            f"## 需求\n{requirement}\n\n"
            f"## 檔案結構\n{files_str}\n- `README.md`\n\n"
            f"## 啟動方式\n```bash\npython main.py\n```\n\n"
            f"## 依賴套件\n```bash\npip install PyQt6\n```\n"
        )

    # ── 通知 ──────────────────────────────────────────────────────────────────

    def _notify(self, project_name: str, success: list, failed: list):
        """推送完成通知（PC API 桌面通知 + Telegram）"""
        msg = (
            f"立 AI 完成自主開發！\n"
            f"專案：{project_name}\n"
            f"成功：{len(success)} 個檔案\n"
            f"位置：projects/{project_name}/"
        )
        # PC API 桌面通知
        if _USE_PC_API and _pc_available():
            try:
                import requests as _req
                _req.post("http://localhost:8899/notify",
                          json={"title": "立 AI 開發完成", "message": f"專案：{project_name} 成功 {len(success)} 個檔案", "duration": 8},
                          timeout=5)
            except Exception:
                pass
        # Telegram 通知
        try:
            import bot_config, telebot
            bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN, parse_mode=None)
            for cid in bot_config.ALLOWED_CHAT_IDS:
                try:
                    bot.send_message(cid, msg)
                except Exception:
                    pass
        except Exception:
            pass

    # ── 歷史記錄 ──────────────────────────────────────────────────────────────

    def _record(self, requirement, project_name, success, failed, elapsed):
        REPORT_FILE.parent.mkdir(exist_ok=True)
        history = []
        if REPORT_FILE.exists():
            try:
                history = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        history.append({
            "time":         datetime.datetime.now().isoformat(timespec="seconds"),
            "requirement":  requirement[:100],
            "project_name": project_name,
            "success":      success,
            "failed":       failed,
            "elapsed":      elapsed,
        })
        REPORT_FILE.write_text(
            json.dumps(history[-50:], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ── 底層推論 ──────────────────────────────────────────────────────────────

    def _infer(self, prompt: str, system: str = "", timeout: int = 180) -> str:
        if _USE_GUARD:
            return safe_infer(prompt=prompt, system=system,
                              model=self.model, timeout=timeout)
        try:
            import requests
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.model, "prompt": prompt,
                      "system": system, "stream": False},
                timeout=timeout
            )
            return r.json().get("response", "")
        except Exception as e:
            return f"[ERROR] {e}"

    def get_status(self) -> str:
        return self._status

    def get_log(self) -> list:
        return self._log


# ── 模組層級單例 ──────────────────────────────────────────────────────────────
_auto_dev: Optional[AutonomousDev] = None

def get_auto_dev() -> AutonomousDev:
    global _auto_dev
    if _auto_dev is None:
        _auto_dev = AutonomousDev()
    return _auto_dev