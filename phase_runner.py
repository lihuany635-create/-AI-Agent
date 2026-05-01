# phase_runner.py — 階段執行 + 自動截圖 + 立AI判斷
# 用法：在 desktop_agent.py 中呼叫 PhaseRunner，或直接 import 使用
# 依賴：pyautogui, Pillow, ollama_guard（或任何支援 vision 的本地模型）

from __future__ import annotations
import threading
import time
import datetime
import pathlib
import base64
import subprocess
import sys
from typing import Optional, Callable

# 截圖存放路徑（與原本 desktop_agent 一致）
SCREENSHOT_DIR = pathlib.Path("memory/screenshots")

# ── 核心截圖函式 ─────────────────────────────────────────────────────────────

def take_screenshot(label: str = "") -> pathlib.Path:
    """截圖並存到固定路徑，回傳檔案路徑"""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    fpath = SCREENSHOT_DIR / f"ss_{ts}{suffix}.png"

    try:
        import pyautogui
        pyautogui.screenshot(str(fpath))
    except ImportError:
        # 備案：用 subprocess 呼叫（與原本 desktop_agent 方式相同）
        result = subprocess.run(
            [sys.executable, "-c",
             f"import pyautogui; pyautogui.screenshot(r'{fpath}')"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            raise RuntimeError(f"截圖失敗：{result.stderr}")

    return fpath


# ── 立AI 讀圖判斷 ────────────────────────────────────────────────────────────

def ai_judge_screenshot(fpath: pathlib.Path, question: str = "") -> str:
    """
    讓立AI讀取截圖並判斷畫面狀態。
    優先用 ollama vision 模型（llava / moondream）；
    找不到就回傳截圖路徑讓使用者自行查看。
    """
    if not fpath.exists():
        return f"❌ 截圖檔案不存在：{fpath}"

    q = question or "請描述畫面目前的狀態，有沒有錯誤訊息或異常？"

    # ── 方案 A：透過 ollama_guard（你原本的推論介面）────────────────────────
    try:
        from ollama_guard import safe_infer_vision
        result = safe_infer_vision(image_path=str(fpath), prompt=q, timeout=60)
        return result
    except (ImportError, AttributeError):
        pass

    # ── 方案 B：直接呼叫 ollama REST API（vision 模型）──────────────────────
    try:
        import urllib.request, json
        img_b64 = base64.b64encode(fpath.read_bytes()).decode()
        payload = json.dumps({
            "model": "llava",          # 或 moondream、bakllava
            "prompt": q,
            "images": [img_b64],
            "stream": False
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        return data.get("response", "（無回應）").strip()
    except Exception as e:
        pass

    # ── 方案 C：降級，只回報截圖路徑 ─────────────────────────────────────────
    return f"📸 截圖已存至：{fpath}\n（Vision 模型未啟動，請手動查看截圖）"


# ── PhaseRunner 主類別 ────────────────────────────────────────────────────────

class PhaseRunner:
    """
    執行多個階段，每個階段跑一段時間後自動截圖，
    交給立AI判斷結果，再決定是否繼續下一階段。

    使用範例：
        runner = PhaseRunner(ui_ref=self)   # self = LobsterDesktop
        runner.add_phase("啟動伺服器", cmd="python server.py", wait=5)
        runner.add_phase("執行測試",   cmd="python test.py",   wait=10)
        runner.start()
    """

    def __init__(self, ui_ref=None, notify_fn=None):
        """
        ui_ref    : LobsterDesktop 實例（有 _log / _agent_msg_no_ask 可用）
        notify_fn : 自訂通知 callback(str)，沒有 ui_ref 時使用
        """
        self._phases = []
        self._ui = ui_ref
        self._notify = notify_fn
        self._stop_flag = False
        self._thread: Optional[threading.Thread] = None

    # ── 公開 API ──────────────────────────────────────────────────────────────

    def add_phase(
        self,
        name: str,
        cmd: Optional[str] = None,
        fn: Optional[Callable] = None,
        wait: float = 5.0,
        judge_question: str = "",
        on_pass: Optional[Callable] = None,
        on_fail: Optional[Callable] = None,
    ):
        """
        新增一個階段。
        name           : 階段名稱（顯示用）
        cmd            : 要執行的 shell 指令（與 fn 二選一）
        fn             : 要呼叫的 Python 函式（與 cmd 二選一）
        wait           : 執行後等待幾秒再截圖（讓畫面穩定）
        judge_question : 問 AI 的問題（留空用預設問題）
        on_pass        : AI 判斷「正常」時的 callback
        on_fail        : AI 判斷「有問題」時的 callback
        """
        self._phases.append({
            "name": name,
            "cmd": cmd,
            "fn": fn,
            "wait": wait,
            "judge_question": judge_question,
            "on_pass": on_pass,
            "on_fail": on_fail,
        })

    def start(self, block: bool = False):
        """在背景執行緒啟動所有階段"""
        self._stop_flag = False
        self._thread = threading.Thread(target=self._run_all, daemon=True)
        self._thread.start()
        if block:
            self._thread.join()

    def stop(self):
        """請求停止（當前階段跑完才停）"""
        self._stop_flag = True

    # ── 內部執行 ──────────────────────────────────────────────────────────────

    def _notify_msg(self, msg: str):
        """安全地把訊息送到 UI 或 print"""
        if self._ui is not None:
            try:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda m=msg: self._ui._agent_msg_no_ask(m))
                QTimer.singleShot(0, lambda m=msg: self._ui._log(
                    f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [PhaseRunner] {m}"
                ))
            except Exception:
                print(f"[PhaseRunner] {msg}")
        elif self._notify:
            self._notify(msg)
        else:
            print(f"[PhaseRunner] {msg}")

    def _run_all(self):
        total = len(self._phases)
        self._notify_msg(f"🚀 開始執行 {total} 個階段")

        for i, phase in enumerate(self._phases):
            if self._stop_flag:
                self._notify_msg("⏹ 已停止")
                break

            name = phase["name"]
            wait = phase["wait"]
            self._notify_msg(f"\n── 階段 {i+1}/{total}：{name} ──")

            # 1. 執行指令或函式
            try:
                if phase["cmd"]:
                    self._notify_msg(f"▶ 執行：{phase['cmd']}")
                    proc = subprocess.Popen(
                        phase["cmd"], shell=True,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="ignore"
                    )
                    # 非阻塞：只等 wait 秒，讓程式在背景繼續跑
                    try:
                        stdout, _ = proc.communicate(timeout=wait)
                        if stdout:
                            self._notify_msg(f"輸出：{stdout[:300]}")
                    except subprocess.TimeoutExpired:
                        # 超時代表程式仍在跑（正常），繼續往下截圖
                        pass

                elif phase["fn"]:
                    self._notify_msg(f"▶ 呼叫函式：{phase['fn'].__name__}")
                    phase["fn"]()
                    time.sleep(wait)

            except Exception as e:
                self._notify_msg(f"❌ 執行失敗：{e}")
                if phase["on_fail"]:
                    phase["on_fail"](str(e))
                continue

            # 2. 等畫面穩定
            self._notify_msg(f"⏳ 等待 {wait} 秒讓畫面穩定...")
            time.sleep(max(0, wait - (wait if phase["fn"] else 0)))

            # 3. 截圖
            try:
                label = name.replace(" ", "_").replace("/", "-")
                fpath = take_screenshot(label)
                self._notify_msg(f"📸 截圖完成：{fpath.name}")
            except Exception as e:
                self._notify_msg(f"❌ 截圖失敗：{e}")
                continue

            # 4. 立AI判斷
            self._notify_msg("🤖 立AI 判斷中...")
            verdict = ai_judge_screenshot(fpath, phase["judge_question"])
            self._notify_msg(f"📋 判斷結果：\n{verdict}")

            # 5. 根據判斷結果呼叫 callback
            is_ok = _is_verdict_ok(verdict)
            if is_ok and phase["on_pass"]:
                phase["on_pass"](verdict)
            elif not is_ok and phase["on_fail"]:
                phase["on_fail"](verdict)

        self._notify_msg("✅ 所有階段執行完畢")


# ── 簡單的「正常/異常」判斷 ──────────────────────────────────────────────────

def _is_verdict_ok(verdict: str) -> bool:
    """
    從 AI 回覆文字中判斷是否正常。
    有錯誤關鍵字 → False，否則 → True。
    """
    bad_keywords = [
        "錯誤", "error", "Error", "ERROR",
        "失敗", "fail", "Fail", "FAIL",
        "crash", "Crash", "CRASH",
        "exception", "Exception",
        "traceback", "Traceback",
        "異常", "問題", "警告", "Warning",
    ]
    low = verdict.lower()
    return not any(kw.lower() in low for kw in bad_keywords)


# ── 與 desktop_agent.py 串接的入口函式 ───────────────────────────────────────

def run_phases_from_ui(ui_ref, phases: list[dict]):
    """
    desktop_agent.py 呼叫這個函式即可啟動 PhaseRunner。

    phases 格式範例：
    [
        {"name": "啟動服務",  "cmd": "python server.py", "wait": 5},
        {"name": "跑測試",    "cmd": "python test.py",   "wait": 10},
        {"name": "檢查輸出",  "fn": some_fn,             "wait": 3,
         "judge_question": "畫面上有沒有 PASSED 字樣？"},
    ]
    """
    runner = PhaseRunner(ui_ref=ui_ref)
    for p in phases:
        runner.add_phase(**p)
    runner.start()
    return runner   # 回傳 runner 讓呼叫端可以呼叫 runner.stop()


# ── 獨立測試（不需要 PyQt6）────────────────────────────────────────────────

if __name__ == "__main__":
    def _print(msg): print(msg)

    runner = PhaseRunner(notify_fn=_print)
    runner.add_phase(
        name="測試：列出檔案",
        cmd="dir" if sys.platform == "win32" else "ls -la",
        wait=2,
        judge_question="畫面上有沒有列出任何檔案？"
    )
    runner.start(block=True)
