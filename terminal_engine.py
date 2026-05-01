# terminal_engine.py — 終端執行引擎
# 功能：讓 AI 直接在電腦上執行指令
# 安全：危險指令先確認，執行結果顯示在對話框

import subprocess
import os
import sys
import re
import pathlib
import datetime
import platform
from typing import Optional

try:
    from agent_logger import get_logger
    logger = get_logger("terminal_engine")
except ImportError:
    import logging
    logger = logging.getLogger("terminal_engine")

# ── 危險指令清單（執行前需確認）────────────────────────────────────────────────
DANGEROUS_PATTERNS = [
    # 刪除類
    r"\brm\b", r"\bdel\b", r"\brmdir\b", r"\brd\b",
    r"format\s+[a-z]:", r"diskpart",
    # 系統修改
    r"\bregedit\b", r"\bnetsh\b", r"shutdown", r"restart",
    r"taskkill", r"sc\s+(stop|delete|create)",
    # 權限提升
    r"runas", r"sudo", r"chmod\s+777",
    # 網路危險
    r"curl.*\|\s*(bash|python|sh)", r"wget.*\|\s*(bash|python|sh)",
    # 大量寫入
    r">\s*[a-z]:\\", r"dd\s+if=",
]

# ── 允許直接執行的安全指令前綴 ───────────────────────────────────────────────
SAFE_PREFIXES = [
    "dir", "ls", "pwd", "cd", "echo", "type", "cat",
    "python", "py", "pip", "git", "ipconfig", "ping",
    "systeminfo", "tasklist", "where", "which",
    "mkdir", "md", "cls", "clear", "date", "time",
    "notepad", "code", "explorer", "start",
    "python -c", "py -c",
]

# 待確認的指令（暫存）
_pending_cmd: dict = {}


class TerminalEngine:

    def __init__(self):
        self.cwd = str(pathlib.Path.cwd())  # 目前工作目錄
        self.history = []                    # 指令歷史

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def handle(self, request: str) -> str:
        """
        判斷請求是否為終端指令並執行
        回傳結果字串
        """
        global _pending_cmd

        cmd = self._extract_command(request)
        if not cmd:
            return None  # 不是終端指令，交給 AI 處理

        logger.info(f"[Terminal] 指令：{cmd}")

        # 連續指令支援（用 && 分隔）
        if "&&" in cmd:
            cmds = [c.strip() for c in cmd.split("&&") if c.strip()]
            results = []
            for c in cmds:
                if self._is_dangerous(c):
                    results.append(f"[WARNING] {c} -- skipped (dangerous)")
                    continue
                r = self._execute(c)
                results.append(r)
            return "\n".join(results)

        # 危險性檢查
        if self._is_dangerous(cmd):
            _pending_cmd = {"cmd": cmd, "cwd": self.cwd}
            return (
                f"[WARNING] this command may be dangerous:\n\n"
                f"```\n{cmd}\n```\n\n"
                f"cwd: {self.cwd}\n\n"
                f"type 'confirm' to execute / 'cancel' to abort"
            )

        return self._execute(cmd)

    def confirm(self) -> str:
        """使用者確認後執行危險指令"""
        global _pending_cmd
        if not _pending_cmd:
            return "沒有待確認的指令"
        cmd = _pending_cmd.get("cmd", "")
        cwd = _pending_cmd.get("cwd", self.cwd)
        _pending_cmd = {}
        return self._execute(cmd, cwd=cwd)

    def cancel(self) -> str:
        """取消待確認指令"""
        global _pending_cmd
        if not _pending_cmd:
            return "沒有待確認的指令"
        cmd = _pending_cmd.get("cmd", "")
        _pending_cmd = {}
        return f"cancelled: {cmd}"

    def has_pending(self) -> bool:
        return bool(_pending_cmd)

    # ── 指令萃取 ──────────────────────────────────────────────────────────────

    def _extract_command(self, request: str) -> Optional[str]:
        """
        從使用者輸入判斷是否為終端指令
        支援：
          - 直接輸入指令：dir, python xxx.py, git status
          - 自然語言：執行 dir、幫我跑 python test.py、開啟記事本
          - > 前綴：> dir /w
        """
        req = request.strip()

        # > 前綴強制執行
        if req.startswith(">"):
            return req[1:].strip()

        # 自然語言觸發詞
        nl_triggers = [
            (r"^(執行|跑|運行|run)\s+(.+)$", 2),
            (r"^幫我(執行|跑|運行)\s+(.+)$", 2),
            (r"^(開啟|打開|open)\s+(.+)$", 2),
            (r"^查看?(系統|CPU|記憶體|磁碟|硬碟).*$", 0),
            (r"^(列出|顯示).*檔案.*$", 0),
        ]
        for pat, group in nl_triggers:
            m = re.match(pat, req, re.IGNORECASE)
            if m:
                if group == 0:
                    return self._nl_to_cmd(req)
                return m.group(group)

        # 直接是指令（以已知指令開頭）
        first_word = req.split()[0].lower() if req.split() else ""
        known_cmds = [
            "dir", "ls", "cd", "pwd", "echo", "type", "cat", "mkdir", "md",
            "python", "py", "pip", "git", "ipconfig", "ping", "systeminfo",
            "tasklist", "taskkill", "notepad", "explorer", "start", "code",
            "where", "which", "cls", "clear", "curl", "wget", "rm", "del",
            "copy", "move", "rename", "attrib", "netstat", "whoami",
        ]
        if first_word in known_cmds:
            return req

        return None

    def _nl_to_cmd(self, text: str) -> str:
        """自然語言轉指令"""
        t = text.lower()
        if "cpu" in t or "處理器" in t:
            return "wmic cpu get name,numberofcores,maxclockspeed"
        if "記憶體" in t or "ram" in t:
            return "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize"
        if "磁碟" in t or "硬碟" in t or "disk" in t:
            return "wmic logicaldisk get caption,size,freespace"
        if "列出" in t or "檔案" in t:
            return "dir"
        if "系統" in t:
            return "systeminfo | findstr /C:\"OS\" /C:\"Memory\""
        return "systeminfo"

    # ── 危險性判斷 ────────────────────────────────────────────────────────────

    def _is_dangerous(self, cmd: str) -> bool:
        cmd_lower = cmd.lower()
        for pat in DANGEROUS_PATTERNS:
            if re.search(pat, cmd_lower):
                return True
        return False

    # ── 執行指令 ──────────────────────────────────────────────────────────────

    def _execute(self, cmd: str, cwd: str = None) -> str:
        """實際執行指令並回傳結果"""
        cwd = cwd or self.cwd

        # 特殊處理：cd 切換目錄
        cd_match = re.match(r"^cd\s+(.+)$", cmd.strip(), re.IGNORECASE)
        if cd_match:
            return self._change_dir(cd_match.group(1).strip())

        # 特殊處理：開啟應用程式
        if cmd.lower().startswith(("notepad", "explorer", "start ", "code ")):
            return self._open_app(cmd)

        # 特殊處理：系統資訊
        if cmd.lower() in ["sysinfo", "系統資訊"]:
            return self._system_info()

        # 長時間執行的程式用背景模式（不等待結束）
        background_patterns = [
            "telegram_bot", "desktop_agent", "core_boot",
            "web_dashboard", "start ", "notepad", "explorer",
            "code ", "chrome", "firefox"
        ]
        is_background = any(p in cmd.lower() for p in background_patterns)

        if is_background:
            try:
                subprocess.Popen(cmd, shell=True, cwd=cwd)
                return f"已在背景啟動：{cmd}"
            except Exception as e:
                return f"啟動失敗：{e}"

        # 一般指令執行
        try:
            # 設定環境變數讓子程序用 UTF-8
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            result = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                timeout=120,
                env=env,
            )

            # 嘗試多種編碼解碼
            def _decode(b):
                if not b:
                    return ""
                for enc in ["utf-8", "cp950", "big5", "gbk", "latin-1"]:
                    try:
                        return b.decode(enc)
                    except (UnicodeDecodeError, LookupError):
                        continue
                return b.decode("utf-8", errors="replace")

            output = _decode(result.stdout)
            error = _decode(result.stderr)

            # 記錄歷史
            self.history.append({
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
                "cmd":  cmd,
                "code": result.returncode,
            })
            self.history = self.history[-50:]

            # 組合回應
            if result.returncode == 0:
                out = output.strip()
                if not out:
                    out = "(done)"
                # 限制長度
                if len(out) > 2000:
                    out = out[:2000] + "\n...(truncated)"
                return f"```\n{out}\n```"
            else:
                err = (error or output).strip()[:800]
                return f"failed (code {result.returncode}):\n```\n{err}\n```"

        except subprocess.TimeoutExpired:
            return "timeout (120s)"
        except Exception as e:
            return f"error: {e}"

    def _change_dir(self, path: str) -> str:
        """切換工作目錄"""
        try:
            new_path = pathlib.Path(self.cwd) / path
            new_path = new_path.resolve()
            if not new_path.exists():
                return f"path not found: {new_path}"
            self.cwd = str(new_path)
            return f"cd {self.cwd}"
        except Exception as e:
            return f"cd failed: {e}"

    def _open_app(self, cmd: str) -> str:
        """開啟應用程式"""
        try:
            subprocess.Popen(cmd, shell=True)
            return f"opened: {cmd}"
        except Exception as e:
            return f"open failed: {e}"

    def _system_info(self) -> str:
        """快速系統資訊"""
        try:
            import psutil
            cpu    = psutil.cpu_percent(interval=1)
            mem    = psutil.virtual_memory()
            disk   = psutil.disk_usage("/")
            return (
                f"System Info\n"
                f"CPU: {cpu}%\n"
                f"RAM: {mem.used//1024//1024} MB / {mem.total//1024//1024} MB ({mem.percent}%)\n"
                f"Disk: {disk.used//1024//1024//1024} GB / {disk.total//1024//1024//1024} GB ({disk.percent}%)\n"
                f"OS: {platform.system()} {platform.release()}"
            )
        except ImportError:
            return self._execute("systeminfo | findstr /C:\"OS Name\" /C:\"Total Physical\"")

    def get_history(self, n: int = 10) -> str:
        """取得指令歷史"""
        if not self.history:
            return "（無指令歷史）"
        items = self.history[-n:]
        lines = []
        for h in reversed(items):
            icon = "✓" if h["code"] == 0 else "✗"
            lines.append(f"{icon} [{h['time']}] {h['cmd']}")
        return "\n".join(lines)


# ── 模組層級單例 ──────────────────────────────────────────────────────────────
_terminal: Optional[TerminalEngine] = None

def get_terminal() -> TerminalEngine:
    global _terminal
    if _terminal is None:
        _terminal = TerminalEngine()
    return _terminal


if __name__ == "__main__":
    t = TerminalEngine()
    print(t.handle("dir"))
    print(t.handle("python --version"))
    print(t.handle("查看系統資訊"))
