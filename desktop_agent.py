# desktop_agent.py — 立 AI 桌面控制台（精簡版）
# 功能：自動修復閉環、語音輸入、對話
# 依賴：pip install PyQt6 SpeechRecognition pyaudio

import sys
_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

import threading
import traceback
import datetime
import pathlib

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QTextCursor

# ── LobsterCore（只用修復閉環）───────────────────────────────────────────────
try:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from Lobster_Core import LobsterCore
    _lobster = LobsterCore()
except Exception as e:
    print(f"[WARN] Lobster_Core 未載入：{e}")
    _lobster = None

try:
    from long_term_memory import get_memory
    _memory = get_memory()
except Exception:
    _memory = None

try:
    from task_scheduler import TaskScheduler, create_auto_repair_task
    _scheduler = TaskScheduler()
    _scheduler.run_all(block=False)
except Exception:
    _scheduler = None

# ── 對話 Worker ───────────────────────────────────────────────────────────────
class AgentWorker(QThread):
    result_sig   = pyqtSignal(str)
    status_sig   = pyqtSignal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self):
        try:
            self.status_sig.emit("thinking")
            reply = self._call()
            self.result_sig.emit(reply)
        except Exception as e:
            self.result_sig.emit(f"[錯誤] {e}")
        finally:
            self.status_sig.emit("idle")

    def _call(self):
        cmd = self.text.strip()
        if _memory and cmd.startswith("記住："):
            _memory.store(cmd[3:].strip(), tags=["manual"], importance=7)
            return f"✓ 已記住：{cmd[3:].strip()}"
        if _memory and cmd.startswith("搜尋："):
            res = _memory.search(cmd[3:].strip())
            return "\n".join(f"• {r['content'][:80]}" for r in res) if res else "找不到相關記憶"
        return "（對話功能請使用 knowledge_ui 的立AI — http://localhost:7861）"

    def _ts(self):
        return datetime.datetime.now().strftime("%H:%M:%S")

# ── 語音 Worker ───────────────────────────────────────────────────────────────
class VoiceWorker(QThread):
    recognized = pyqtSignal(str)
    status_sig = pyqtSignal(str)

    def run(self):
        if not HAS_SR:
            self.recognized.emit("")
            self.status_sig.emit("error")
            return
        r = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                self.status_sig.emit("listening")
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=8, phrase_time_limit=15)
            self.recognized.emit(r.recognize_google(audio, language="zh-TW"))
        except Exception:
            self.recognized.emit("")
        finally:
            self.status_sig.emit("idle")

# ── 主視窗 ────────────────────────────────────────────────────────────────────
STYLE = """
QMainWindow, QWidget { background: #0d1117; color: #c9d1d9; font-family: 'Microsoft JhengHei UI'; }
QTextEdit  { background: #0d1117; border: none; color: #c9d1d9; font-size: 13px; }
QLineEdit  { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
             color: #c9d1d9; padding: 8px 12px; font-size: 13px; }
QLineEdit:focus { border-color: #58a6ff; }
QPushButton { background: #2563eb; color: #fff; border: none; border-radius: 8px;
              padding: 8px 18px; font-size: 13px; }
QPushButton:hover   { background: #1d4ed8; }
QPushButton:pressed { background: #1e40af; }
QPushButton:disabled { background: #21262d; color: #6e7681; }
QPushButton#btn_voice   { background: #065f46; color: #6ee7b7; }
QPushButton#btn_voice:hover { background: #047857; }
QPushButton#btn_repair  { background: #1e3a5f; color: #93c5fd; }
QPushButton#btn_repair:hover { background: #1d4ed8; }
QPushButton#btn_stop    { background: #3d1f1f; color: #fca5a5; }
QPushButton#btn_stop:hover { background: #7f1d1d; }
QFrame#card { background: #161b22; border-radius: 10px; border: 1px solid #21262d; }
QLabel#status_bar { color: #8b949e; font-size: 11px; padding: 4px 12px;
                    background: #161b22; border-top: 1px solid #21262d; }
"""

class LobsterDesktop(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚙ 立 AI — 修復控制台")
        self.resize(680, 560)
        self.setStyleSheet(STYLE)
        self._worker  = None
        self._voice_w = None
        self._build_ui()
        self._start_timer()
        self._agent_msg("你好！我是立 AI 修復控制台。\n"
                        "對話請至 knowledge_ui（http://localhost:7861）\n"
                        "點「🔧 自動修復」啟動 LobsterCore 修復閉環。")

    # ── UI 建構 ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(12, 12, 12, 0); v.setSpacing(8)

        # 頂部工具列
        toolbar = QHBoxLayout()
        self.lbl_title = QLabel("⚙ 立 AI 修復控制台")
        self.lbl_title.setStyleSheet("font-size:15px;font-weight:700;color:#58a6ff;")
        toolbar.addWidget(self.lbl_title)
        toolbar.addStretch()

        self.btn_repair = QPushButton("🔧 自動修復")
        self.btn_repair.setObjectName("btn_repair")
        self.btn_repair.clicked.connect(self._quick_repair)
        toolbar.addWidget(self.btn_repair)

        self.btn_organs = QPushButton("🔩 器官庫")
        self.btn_organs.setObjectName("btn_repair")
        self.btn_organs.clicked.connect(self._toggle_organs)
        toolbar.addWidget(self.btn_organs)

        self.btn_workshop = QPushButton("⚙ 工坊")
        self.btn_workshop.setObjectName("btn_repair")
        self.btn_workshop.clicked.connect(self._open_workshop_ui)
        toolbar.addWidget(self.btn_workshop)

        v.addLayout(toolbar)

        # 器官庫面板（預設隱藏）
        self.organ_panel = QFrame()
        self.organ_panel.setObjectName("card")
        self.organ_panel.setVisible(False)
        op = QVBoxLayout(self.organ_panel)
        op.setContentsMargins(12, 10, 12, 10); op.setSpacing(6)

        organ_header = QHBoxLayout()
        organ_header.addWidget(QLabel("🔩 工坊器官庫"))
        self.btn_refresh_organs = QPushButton("↻ 重新整理")
        self.btn_refresh_organs.setFixedWidth(90)
        self.btn_refresh_organs.clicked.connect(self._load_organs)
        organ_header.addStretch()
        organ_header.addWidget(self.btn_refresh_organs)
        op.addLayout(organ_header)

        self.organ_list = QTextEdit()
        self.organ_list.setReadOnly(True)
        self.organ_list.setMaximumHeight(160)
        self.organ_list.setStyleSheet("background:#0d1117;border:1px solid #21262d;border-radius:6px;font-size:12px;")
        op.addWidget(self.organ_list)

        organ_actions = QHBoxLayout()
        self.organ_selector = QLineEdit()
        self.organ_selector.setPlaceholderText("輸入器官檔名（如 TCP_伺服器.py）")
        self.btn_run_organ   = QPushButton("▶ 執行")
        self.btn_run_organ.setFixedWidth(60)
        self.btn_run_organ.clicked.connect(self._run_organ)
        self.btn_repair_organ = QPushButton("🔧 修復")
        self.btn_repair_organ.setObjectName("btn_repair")
        self.btn_repair_organ.setFixedWidth(60)
        self.btn_repair_organ.clicked.connect(self._repair_organ)
        self.btn_preview_organ = QPushButton("👁 預覽")
        self.btn_preview_organ.setFixedWidth(60)
        self.btn_preview_organ.clicked.connect(self._preview_organ)
        organ_actions.addWidget(self.organ_selector)
        organ_actions.addWidget(self.btn_preview_organ)
        organ_actions.addWidget(self.btn_run_organ)
        organ_actions.addWidget(self.btn_repair_organ)
        op.addLayout(organ_actions)
        v.addWidget(self.organ_panel)

        # 對話區
        card = QFrame(); card.setObjectName("card")
        cv = QVBoxLayout(card); cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(0)
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setFont(QFont("Microsoft JhengHei UI", 12))
        cv.addWidget(self.chat_history, 1)
        v.addWidget(card, 1)

        # 輸入列
        input_row = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("輸入訊息，或「記住：...」「搜尋：...」")
        self.input_box.returnPressed.connect(self.send_text)

        self.send_btn = QPushButton("傳送")
        self.send_btn.setFixedWidth(64)
        self.send_btn.clicked.connect(self.send_text)

        self.stop_btn = QPushButton("取消")
        self.stop_btn.setObjectName("btn_stop")
        self.stop_btn.setFixedWidth(56)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_worker)

        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setObjectName("btn_voice")
        self.voice_btn.setFixedWidth(44)
        self.voice_btn.clicked.connect(self.voice_input)
        if not HAS_SR:
            self.voice_btn.setEnabled(False)
            self.voice_btn.setToolTip("需安裝 SpeechRecognition 和 pyaudio")

        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_btn)
        input_row.addWidget(self.stop_btn)
        input_row.addWidget(self.voice_btn)
        v.addLayout(input_row)

        # 狀態列
        self.lbl_status = QLabel("● 就緒")
        self.lbl_status.setObjectName("status_bar")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        v.addWidget(self.lbl_status)
        v.setContentsMargins(12, 12, 12, 8)

    # ── 對話 ──────────────────────────────────────────────────────────────────
    def send_text(self):
        text = self.input_box.text().strip()
        if not text or (self._worker and self._worker.isRunning()):
            return
        self.input_box.clear()
        self._user_msg(text)
        self._run_worker(text)

    def _run_worker(self, text: str):
        self._worker = AgentWorker(text, self)
        self._worker.result_sig.connect(self._agent_msg)
        self._worker.status_sig.connect(self._on_status)
        self._worker.start()
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._agent_msg("（已取消）")
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_status(self, s: str):
        icons = {"thinking": "⏳ 思考中...", "idle": "● 就緒",
                 "listening": "🎤 聆聽中...", "error": "❌ 錯誤"}
        self.lbl_status.setText(icons.get(s, s))
        if s == "idle":
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    # ── 訊息顯示 ──────────────────────────────────────────────────────────────
    def _user_msg(self, text: str):
        ts = datetime.datetime.now().strftime("%H:%M")
        self.chat_history.append(
            f'<div style="text-align:right;margin:4px 0;">'
            f'<span style="background:#2563eb;color:#fff;border-radius:8px;'
            f'padding:6px 12px;display:inline-block;max-width:80%;">{text}</span>'
            f'<span style="color:#6e7681;font-size:10px;margin-left:6px;">{ts}</span></div>'
        )
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)

    def _agent_msg(self, text: str):
        ts = datetime.datetime.now().strftime("%H:%M")
        safe = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br>")
        self.chat_history.append(
            f'<div style="margin:4px 0;">'
            f'<span style="color:#58a6ff;font-size:10px;">🦞 立AI {ts}</span><br>'
            f'<span style="background:#161b22;color:#c9d1d9;border-radius:8px;'
            f'padding:6px 12px;display:inline-block;max-width:85%;">{safe}</span></div>'
        )
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)

    # ── 語音輸入 ──────────────────────────────────────────────────────────────
    def voice_input(self):
        if self._voice_w and self._voice_w.isRunning():
            return
        self._voice_w = VoiceWorker(self)
        self._voice_w.recognized.connect(self._on_recognized)
        self._voice_w.status_sig.connect(self._on_status)
        self._voice_w.start()
        self.voice_btn.setEnabled(False)

    def _on_recognized(self, text: str):
        self.voice_btn.setEnabled(True)
        if text:
            self.input_box.setText(text)
            self.send_text()

    # ── 器官庫 ────────────────────────────────────────────────────────────────
    def _toggle_organs(self):
        visible = not self.organ_panel.isVisible()
        self.organ_panel.setVisible(visible)
        if visible:
            self._load_organs()

    def _get_assembled_dir(self) -> pathlib.Path:
        return pathlib.Path(__file__).parent / "workshop_data" / "assembled"

    def _load_organs(self):
        """從工坊器官庫載入已組裝的模組列表。"""
        import socket as _sk
        with _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM) as s:
            ws_on = s.connect_ex(('localhost', 7862)) == 0

        if ws_on:
            # 工坊在線：用 API 取得
            try:
                import urllib.request, json
                with urllib.request.urlopen("http://localhost:7862/api/assembled", timeout=3) as resp:
                    organs = json.loads(resp.read())
                self._render_organs(organs)
                return
            except Exception:
                pass

        # 工坊離線：直接讀資料夾
        d = self._get_assembled_dir()
        if not d.exists():
            self.organ_list.setPlainText("（工坊尚未產出任何器官）")
            return
        organs = []
        for f in sorted(d.glob("*.py"), key=lambda x: x.stat().st_mtime, reverse=True):
            import datetime as _dt
            organs.append({
                "name":     f.stem.replace("_", " "),
                "filename": f.name,
                "path":     str(f),
                "size":     f.stat().st_size,
                "mtime":    _dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        self._render_organs(organs)

    def _render_organs(self, organs: list):
        if not organs:
            self.organ_list.setPlainText("（器官庫是空的，請先在工坊完成並組裝專案）")
            return
        lines = []
        for o in organs:
            size_kb = o["size"] // 1024 or 1
            lines.append(f"🔩 {o['name']}  ·  {o['filename']}  ·  {size_kb}KB  ·  {o['mtime']}")
        self.organ_list.setPlainText("\n".join(lines))
        # 自動填入第一個
        if organs:
            self.organ_selector.setPlaceholderText(organs[0]["filename"])

    def _get_organ_path(self) -> pathlib.Path | None:
        filename = self.organ_selector.text().strip()
        if not filename:
            filename = self.organ_selector.placeholderText()
        if not filename:
            self._agent_msg("⚠ 請輸入器官檔名")
            return None
        path = self._get_assembled_dir() / filename
        if not path.exists():
            self._agent_msg(f"⚠ 找不到：{filename}")
            return None
        return path

    def _preview_organ(self):
        path = self._get_organ_path()
        if not path: return
        code = path.read_text(encoding="utf-8")
        preview = code[:800] + ("\n\n...（截斷）" if len(code) > 800 else "")
        self._agent_msg(f"👁 預覽：{path.name}\n\n```\n{preview}\n```")

    def _run_organ(self):
        path = self._get_organ_path()
        if not path: return
        import subprocess, sys, threading
        self._agent_msg(f"▶ 執行器官：{path.name}")
        def _go():
            result = subprocess.run(
                [sys.executable, str(path)],
                capture_output=True, text=True, timeout=30
            )
            out = (result.stdout + result.stderr).strip()
            self._agent_msg(f"執行完成（returncode={result.returncode}）\n{out[:500] if out else '（無輸出）'}")
        threading.Thread(target=_go, daemon=True).start()

    def _repair_organ(self):
        path = self._get_organ_path()
        if not path: return
        if not _scheduler:
            self._agent_msg("⚠ TaskScheduler 未啟動")
            return
        from task_scheduler import Task, Step
        task = Task(
            name=f"修復器官：{path.name}",
            priority=2,
            steps=[
                Step("detect",  "error_detector",  f"偵測錯誤：{path}"),
                Step("repair",  "repair_engine",    f"執行修復"),
                Step("learn",   "bug_learning_engine", "學習修復經驗"),
            ]
        )
        tid = _scheduler.submit(task)
        self._agent_msg(f"🔧 修復任務已提交：{path.name}（ID: {tid}）\n修復閉環啟動中...")

    # ── 自動修復 ──────────────────────────────────────────────────────────────
    def _quick_repair(self):
        if _scheduler:
            task = create_auto_repair_task(".")
            tid = _scheduler.submit(task)
            self._agent_msg(f"🔧 修復任務已提交（ID: {tid}）\n"
                            f"LobsterCore 修復閉環已啟動，請至日誌查看進度。")
        else:
            self._agent_msg("⚠ TaskScheduler 未啟動，請確認 task_scheduler.py 存在。")

    # ── 工坊 ──────────────────────────────────────────────────────────────────
    def _open_workshop_ui(self):
        import subprocess, webbrowser, threading, time, socket
        ui_path = pathlib.Path(__file__).parent / "workshop_ui.py"
        if not ui_path.exists():
            self._agent_msg("⚠ 找不到 workshop_ui.py")
            return
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', 7862)) == 0:
                webbrowser.open("http://localhost:7862")
                self._agent_msg("⚙ 工坊已在運行，已開啟瀏覽器")
                return
        def _go():
            base   = str(ui_path.parent)
            script = str(ui_path)
            subprocess.Popen(
                ["powershell", "-Command",
                 f"Start-Process powershell -ArgumentList '-NoExit','-Command',"
                 f"'cd \"{base}\"; python \"{script}\"'"],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            time.sleep(3)
            webbrowser.open("http://localhost:7862")
        threading.Thread(target=_go, daemon=True).start()
        self._agent_msg("⚙ 工坊啟動中，請稍候 3 秒...")

    # ── 狀態 timer ────────────────────────────────────────────────────────────
    def _start_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(5000)

    def _tick(self):
        parts = []
        # Ollama 狀態
        try:
            import socket as _sk
            with _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM) as s:
                ollama_ok = s.connect_ex(('localhost', 11434)) == 0
            parts.append("Ollama●" if ollama_ok else "Ollama○")
        except:
            pass
        # 修復閉環
        repair_ok = _scheduler is not None
        parts.append("修復閉環●" if repair_ok else "修復閉環○")
        # 記憶庫
        if _memory:
            try:
                mc = len(_memory._memories)
                parts.append(f"記憶 {mc} 筆")
            except:
                parts.append("記憶庫●")
        # 工坊
        try:
            import socket as _sk
            with _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM) as s:
                ws_ok = s.connect_ex(('localhost', 7862)) == 0
            parts.append("工坊●" if ws_ok else "工坊○")
        except:
            pass
        self.lbl_status.setText("  ".join(parts))

# ── 啟動 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("立 AI 修復控制台")
    win = LobsterDesktop()
    win.show()
    sys.exit(app.exec())
