# auto_restart.py — 監控 AI-Agent 資料夾，檔案變更時自動重啟立 AI
# 使用：python auto_restart.py
# 依賴：pip install watchdog

import sys
import time
import subprocess
import pathlib
import threading

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("請先安裝：pip install watchdog")
    sys.exit(1)

# ── 設定 ─────────────────────────────────────────────────────────────────────
WATCH_DIR    = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面\AI-Agent")
MAIN_SCRIPT  = WATCH_DIR / "desktop_agent.py"
PYTHON_CMD   = "python"  # 用 python 啟動（watchdog 裝在 Python 3.11）

# 暫停重啟旗標檔：self_dev_engine 測試期間寫入此檔，AutoRestart 看到就等待
PAUSE_FLAG   = WATCH_DIR / "memory" / ".auto_restart_paused"

# 忽略的檔案和資料夾（變更這些不重啟）
IGNORE_PATHS = {
    "memory", "logs", "learn_inbox", "__pycache__",
    "memory\\screenshots", "memory\\backups", "memory\\dev_backups",
    "runtime_state.json", "mobile_queue.json", "mobile_messages.json",
    "projects",  # 專案輸出資料夾，變更不重啟（避免開發中途被打斷）
    ".git",
}

# 核心系統檔：只有這些檔案變更才觸發重啟
CORE_FILES = {
    "desktop_agent.py", "Lobster_Core.py", "prompt_engine.py",
    "ollama_guard.py", "model_selector.py", "self_dev_engine.py",
    "reflex_engine.py", "terminal_engine.py", "desktop_control.py",
    "long_term_memory.py", "episodic_memory.py", "cognition_state_manager.py",
    "intent_router.py", "telegram_bot.py", "bot_config.py",
    "agent_logger.py", "claude_desktop_bridge.py", "claude_knowledge.py",
    "Lobster_Core.py", "auto_restart.py",
    "dev_tool.py", "dev_brain.py",
}

# 重啟延遲（秒）：避免連續多個檔案變更觸發多次重啟
RESTART_DELAY = 3.0

# ── 全域狀態 ─────────────────────────────────────────────────────────────────
_process     = None
_restart_timer = None
_lock        = threading.Lock()


def _should_ignore(path: str) -> bool:
    """判斷這個路徑的變更是否要忽略"""
    p = pathlib.Path(path)

    # 忽略特定資料夾
    for part in p.parts:
        if part in IGNORE_PATHS:
            return True

    # 忽略特定檔名
    if p.name in IGNORE_PATHS:
        return True

    # 只監控 .py 和 .bat 檔
    if p.suffix not in [".py", ".bat"]:
        return True

    # 忽略 __pycache__
    if "__pycache__" in str(path):
        return True

    # 所有 .py 變更都重啟（除了已忽略的路徑）
    return False


def start_agent():
    """啟動立 AI"""
    global _process
    # 清掉殘留的暫停旗標（上次異常結束可能留下）
    try:
        if PAUSE_FLAG.exists():
            PAUSE_FLAG.unlink()
            print("[AutoRestart] 清除殘留暫停旗標")
    except Exception:
        pass
    print(f"[AutoRestart] 啟動立 AI...")
    try:
        _process = subprocess.Popen(
            [PYTHON_CMD, str(MAIN_SCRIPT)],
            cwd=str(WATCH_DIR),
        )
        print(f"[AutoRestart] 立 AI 已啟動（PID: {_process.pid}）")
    except Exception as e:
        print(f"[AutoRestart] 啟動失敗：{e}")


def stop_agent():
    """停止立 AI"""
    global _process
    if _process and _process.poll() is None:
        print(f"[AutoRestart] 停止立 AI（PID: {_process.pid}）...")
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
        print("[AutoRestart] 立 AI 已停止")
    _process = None


def schedule_restart(reason: str):
    """延遲重啟（避免短時間多次觸發）"""
    global _restart_timer

    with _lock:
        # 取消舊的計時器
        if _restart_timer and _restart_timer.is_alive():
            _restart_timer.cancel()

        print(f"[AutoRestart] 偵測到變更：{reason}，{RESTART_DELAY:.0f} 秒後重啟...")

        def _do_restart():
            # 若測試旗標存在，等待最多 300 秒
            wait_start = time.time()
            last_modified = PAUSE_FLAG.stat().st_mtime if PAUSE_FLAG.exists() else 0
            while PAUSE_FLAG.exists():
                elapsed = time.time() - wait_start
                if elapsed > 300:
                    print("[AutoRestart] 等待測試超時（300秒），強制重啟並清除旗標")
                    try:
                        PAUSE_FLAG.unlink(missing_ok=True)
                    except Exception:
                        pass
                    break
                # 旗標存在超過 60 秒沒有更新，視為殘留直接清除
                try:
                    mtime = PAUSE_FLAG.stat().st_mtime
                    if time.time() - mtime > 60:
                        print("[AutoRestart] 暫停旗標疑似殘留（60秒未更新），清除並重啟")
                        PAUSE_FLAG.unlink(missing_ok=True)
                        break
                except Exception:
                    break
                print(f"[AutoRestart] 測試進行中，等待...（{elapsed:.0f}s）")
                time.sleep(3)
            stop_agent()
            time.sleep(1.0)
            start_agent()

        _restart_timer = threading.Timer(RESTART_DELAY, _do_restart)
        _restart_timer.daemon = True
        _restart_timer.start()


class AgentRestartHandler(FileSystemEventHandler):
    """檔案系統事件處理器"""

    def on_modified(self, event):
        if event.is_directory:
            return
        if _should_ignore(event.src_path):
            return
        schedule_restart(f"修改 {pathlib.Path(event.src_path).name}")

    def on_created(self, event):
        if event.is_directory:
            return
        if _should_ignore(event.src_path):
            return
        schedule_restart(f"新增 {pathlib.Path(event.src_path).name}")

    def on_deleted(self, event):
        if event.is_directory:
            return
        if _should_ignore(event.src_path):
            return
        schedule_restart(f"刪除 {pathlib.Path(event.src_path).name}")


def main():
    print(f"[AutoRestart] 監控資料夾：{WATCH_DIR}")
    print(f"[AutoRestart] 重啟延遲：{RESTART_DELAY} 秒")
    print("[AutoRestart] 按 Ctrl+C 停止\n")

    # 先啟動立 AI
    start_agent()

    # 開始監控
    handler  = AgentRestartHandler()
    observer = Observer()
    observer.schedule(handler, str(WATCH_DIR), recursive=True)
    observer.start()

    try:
        while True:
            # 如果立 AI 意外崩潰，自動重啟
            if _process and _process.poll() is not None:
                print("[AutoRestart] 立 AI 意外結束，自動重啟...")
                time.sleep(2.0)
                start_agent()
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[AutoRestart] 停止中...")
        observer.stop()
        stop_agent()

    observer.join()
    print("[AutoRestart] 已停止")


if __name__ == "__main__":
    main()

# 自動啟動 AI Bridge
import subprocess, pathlib
_bp = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面\AI-Agent\ai_bridge.py")
if _bp.exists():
    subprocess.Popen(["python", str(_bp)], creationflags=8)
    print("AI Bridge 已啟動")
