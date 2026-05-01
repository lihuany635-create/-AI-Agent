# dual_ai_chat.py — 雙 AI 對話視窗（獨立模組）
# 功能：與 Claude / ChatGPT 多輪對話學習
# 使用：python dual_ai_chat.py
# 或從其他模組 import：from dual_ai_chat import DualAIChatWindow

import sys
import threading
import pathlib

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QLineEdit, QTabWidget,
    QFrame, QProgressBar, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor, QColor

# ── 樣式 ──────────────────────────────────────────────────────────────────────

STYLE = """
QMainWindow, QWidget {
    background-color: #0f1117;
    color: #e0e0e0;
    font-family: 'Microsoft JhengHei UI', 'Segoe UI', sans-serif;
    font-size: 13px;
}
QTabWidget::pane { border: 1px solid #2a2d3a; border-radius: 8px; background: #1a1d27; }
QTabBar::tab { background: #1a1d27; color: #888; padding: 7px 18px; border-radius: 6px 6px 0 0; margin-right: 2px; }
QTabBar::tab:selected { background: #2563eb; color: #fff; }
QTabBar::tab:hover:!selected { background: #252836; color: #ccc; }
QTextEdit {
    background: #0d1117; border: 1px solid #1e2130;
    border-radius: 8px; padding: 8px; color: #e0e0e0;
    font-family: 'Microsoft JhengHei UI'; font-size: 13px;
}
QLineEdit {
    background: #1a1d27; border: 1px solid #2a2d3a;
    border-radius: 8px; padding: 8px 14px; color: #e0e0e0;
    font-family: 'Microsoft JhengHei UI'; font-size: 13px;
}
QLineEdit:focus { border-color: #2563eb; }
QPushButton {
    background: #2563eb; color: #fff;
    border: none; border-radius: 8px; padding: 8px 18px;
}
QPushButton:hover { background: #1d4ed8; }
QPushButton:pressed { background: #1e40af; }
QPushButton#btn_claude {
    background: #1e3a5f; color: #93c5fd;
}
QPushButton#btn_claude:hover { background: #1d4ed8; color: #fff; }
QPushButton#btn_chatgpt {
    background: #064e3b; color: #6ee7b7;
}
QPushButton#btn_chatgpt:hover { background: #065f46; color: #fff; }
QPushButton#btn_stop {
    background: #7f1d1d; color: #fca5a5;
}
QPushButton#btn_stop:hover { background: #991b1b; }
QPushButton#btn_dim {
    background: #252836; color: #aaa;
}
QPushButton#btn_dim:hover { background: #2e3347; color: #fff; }
QProgressBar {
    background: #1a1d27; border: none; border-radius: 4px; height: 4px;
}
QProgressBar::chunk { background: #2563eb; border-radius: 4px; }
QFrame#card {
    background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 10px;
}
QLabel#sec {
    color: #555; font-size: 11px; font-weight: 600;
    letter-spacing: 1px; text-transform: uppercase;
}
"""

# ── AI 工作執行緒 ─────────────────────────────────────────────────────────────

class ClaudeWorker(QThread):
    message  = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        def _notify(msg):
            self.message.emit(msg)

        try:
            from claude_desktop_bridge import get_bridge
            bridge = get_bridge()

            class _ui_ref:
                pass
            ui = _ui_ref()
            ui._stop_claude = lambda: self._stop

            summary = bridge.chat_loop(
                self.text,
                max_rounds=9999,
                notify_fn=_notify,
                ui_ref=ui,
            )
        except Exception as e:
            summary = f"❌ Claude 學習失敗：{e}"
        self.finished.emit(summary)


class ChatGPTWorker(QThread):
    message  = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        def _notify(msg):
            self.message.emit(msg)

        try:
            from chatgpt_desktop_bridge import get_bridge
            bridge = get_bridge()

            class _ui_ref:
                pass
            ui = _ui_ref()
            ui._stop_chatgpt = lambda: self._stop

            summary = bridge.chat_loop(
                self.text,
                max_rounds=9999,
                notify_fn=_notify,
                ui_ref=ui,
            )
        except Exception as e:
            summary = f"❌ ChatGPT 橋接失敗：{e}"
        self.finished.emit(summary)


# ── 對話視窗 ──────────────────────────────────────────────────────────────────

class DualAIChatWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 雙 AI 對話")
        self.setMinimumSize(720, 560)
        self.resize(860, 640)
        self.setStyleSheet(STYLE)

        self._claude_worker   = None
        self._chatgpt_worker  = None

        self._build_ui()

    # ── UI 建構 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)

        # 標題列
        hdr = QHBoxLayout()
        title = QLabel("🤖 雙 AI 對話學習")
        title.setStyleSheet("color:#7eb8f7;font-size:15px;font-weight:700;")
        hdr.addWidget(title)
        hdr.addStretch()
        self.lbl_status = QLabel("● idle")
        self.lbl_status.setStyleSheet("color:#555;font-size:12px;")
        hdr.addWidget(self.lbl_status)
        v.addLayout(hdr)

        # 進度條
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setFixedHeight(4)
        v.addWidget(self.progress)

        # 分頁：Claude / ChatGPT / 同時
        self.tabs = QTabWidget()
        self.tabs.addTab(self._claude_tab(),  "🔵 Claude")
        self.tabs.addTab(self._chatgpt_tab(), "🟢 ChatGPT")
        self.tabs.addTab(self._both_tab(),    "⚡ 同時問")
        v.addWidget(self.tabs, 1)

        # 輸入列（共用）
        input_frame = QFrame()
        input_frame.setObjectName("card")
        ih = QHBoxLayout(input_frame)
        ih.setContentsMargins(10, 8, 10, 8)
        ih.setSpacing(8)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("輸入問題或學習主題...")
        self.input_box.returnPressed.connect(self._on_enter)
        ih.addWidget(self.input_box, 1)

        self.btn_claude = QPushButton("問 Claude")
        self.btn_claude.setObjectName("btn_claude")
        self.btn_claude.clicked.connect(self._ask_claude)
        ih.addWidget(self.btn_claude)

        self.btn_chatgpt = QPushButton("問 ChatGPT")
        self.btn_chatgpt.setObjectName("btn_chatgpt")
        self.btn_chatgpt.clicked.connect(self._ask_chatgpt)
        ih.addWidget(self.btn_chatgpt)

        self.btn_both = QPushButton("⚡ 同時問")
        self.btn_both.clicked.connect(self._ask_both)
        ih.addWidget(self.btn_both)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("btn_dim")
        self.btn_clear.clicked.connect(self._clear_all)
        ih.addWidget(self.btn_clear)

        v.addWidget(input_frame)

        # 停止列
        stop_row = QHBoxLayout()
        self.btn_stop_claude = QPushButton("⏹ 停止 Claude")
        self.btn_stop_claude.setObjectName("btn_stop")
        self.btn_stop_claude.setVisible(False)
        self.btn_stop_claude.clicked.connect(self._stop_claude)
        stop_row.addWidget(self.btn_stop_claude)

        self.btn_stop_chatgpt = QPushButton("⏹ 停止 ChatGPT")
        self.btn_stop_chatgpt.setObjectName("btn_stop")
        self.btn_stop_chatgpt.setVisible(False)
        self.btn_stop_chatgpt.clicked.connect(self._stop_chatgpt)
        stop_row.addWidget(self.btn_stop_chatgpt)
        stop_row.addStretch()
        v.addLayout(stop_row)

    def _claude_tab(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(4, 6, 4, 4)
        lbl = QLabel("Claude 對話記錄")
        lbl.setObjectName("sec"); v.addWidget(lbl)
        self.claude_history = QTextEdit()
        self.claude_history.setReadOnly(True)
        self.claude_history.setFont(QFont("Microsoft JhengHei UI", 12))
        self.claude_history.setPlaceholderText("Claude 的回答會顯示在這裡...")
        v.addWidget(self.claude_history)
        return w

    def _chatgpt_tab(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(4, 6, 4, 4)
        lbl = QLabel("ChatGPT 對話記錄")
        lbl.setObjectName("sec"); v.addWidget(lbl)
        self.chatgpt_history = QTextEdit()
        self.chatgpt_history.setReadOnly(True)
        self.chatgpt_history.setFont(QFont("Microsoft JhengHei UI", 12))
        self.chatgpt_history.setPlaceholderText("ChatGPT 的回答會顯示在這裡...")
        v.addWidget(self.chatgpt_history)
        return w

    def _both_tab(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(4, 6, 4, 4)
        lbl = QLabel("同時對話記錄（左: Claude｜右: ChatGPT）")
        lbl.setObjectName("sec"); v.addWidget(lbl)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.both_claude = QTextEdit()
        self.both_claude.setReadOnly(True)
        self.both_claude.setFont(QFont("Microsoft JhengHei UI", 11))
        self.both_claude.setPlaceholderText("Claude...")

        self.both_chatgpt = QTextEdit()
        self.both_chatgpt.setReadOnly(True)
        self.both_chatgpt.setFont(QFont("Microsoft JhengHei UI", 11))
        self.both_chatgpt.setPlaceholderText("ChatGPT...")

        splitter.addWidget(self.both_claude)
        splitter.addWidget(self.both_chatgpt)
        splitter.setSizes([400, 400])
        v.addWidget(splitter)
        return w

    # ── 訊息顯示 ──────────────────────────────────────────────────────────────

    def _append(self, box: QTextEdit, text: str, color: str = "#e0e0e0"):
        box.append(f'<span style="color:{color};">{text}</span>')
        box.moveCursor(QTextCursor.MoveOperation.End)

    def _user_msg(self, text: str):
        self._append(self.claude_history,
                     f'<b style="color:#7eb8f7;">你：</b> {text}')
        self._append(self.chatgpt_history,
                     f'<b style="color:#7eb8f7;">你：</b> {text}')
        self._append(self.both_claude,
                     f'<b style="color:#7eb8f7;">你：</b> {text}')
        self._append(self.both_chatgpt,
                     f'<b style="color:#7eb8f7;">你：</b> {text}')

    def _set_status(self, text: str, color: str = "#555"):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color:{color};font-size:12px;")

    # ── 操作 ──────────────────────────────────────────────────────────────────

    def _on_enter(self):
        idx = self.tabs.currentIndex()
        if idx == 0:   self._ask_claude()
        elif idx == 1: self._ask_chatgpt()
        else:          self._ask_both()

    def _ask_claude(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self._user_msg(text)
        self.tabs.setCurrentIndex(0)
        self.progress.setVisible(True)
        self.btn_stop_claude.setVisible(True)
        self._set_status("🔵 Claude 對話中...", "#93c5fd")

        self._claude_worker = ClaudeWorker(text)
        self._claude_worker.message.connect(
            lambda m: QTimer.singleShot(0, lambda msg=m: (
                self._append(self.claude_history, msg, "#d1d5db"),
                self._append(self.both_claude, msg, "#d1d5db")
            ))
        )
        self._claude_worker.finished.connect(self._on_claude_done)
        self._claude_worker.start()

    def _on_claude_done(self, summary: str):
        self.progress.setVisible(False)
        self.btn_stop_claude.setVisible(False)
        self._append(self.claude_history,
                     f'<b style="color:#86efac;">✅ 完成：</b> {summary}')
        self._append(self.both_claude,
                     f'<b style="color:#86efac;">✅ 完成</b>')
        self._set_status("● idle")

    def _stop_claude(self):
        if self._claude_worker:
            self._claude_worker.stop()
            try:
                from claude_desktop_bridge import get_bridge
                get_bridge().stop_chat()
            except Exception:
                pass
        self.btn_stop_claude.setVisible(False)
        self.progress.setVisible(False)
        self._append(self.claude_history,
                     '<span style="color:#fca5a5;">⏹ 已停止</span>')
        self._set_status("● idle")

    def _ask_chatgpt(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self._user_msg(text)
        self.tabs.setCurrentIndex(1)
        self.progress.setVisible(True)
        self.btn_stop_chatgpt.setVisible(True)
        self._set_status("🟢 ChatGPT 對話中...", "#6ee7b7")

        self._chatgpt_worker = ChatGPTWorker(text)
        self._chatgpt_worker.message.connect(
            lambda m: QTimer.singleShot(0, lambda msg=m: (
                self._append(self.chatgpt_history, msg, "#d1d5db"),
                self._append(self.both_chatgpt, msg, "#d1d5db")
            ))
        )
        self._chatgpt_worker.finished.connect(self._on_chatgpt_done)
        self._chatgpt_worker.start()

    def _on_chatgpt_done(self, summary: str):
        self.progress.setVisible(False)
        self.btn_stop_chatgpt.setVisible(False)
        self._append(self.chatgpt_history,
                     f'<b style="color:#86efac;">✅ 完成：</b> {summary}')
        self._append(self.both_chatgpt,
                     f'<b style="color:#86efac;">✅ 完成</b>')
        self._set_status("● idle")

    def _stop_chatgpt(self):
        if self._chatgpt_worker:
            self._chatgpt_worker.stop()
            try:
                from chatgpt_desktop_bridge import get_bridge
                get_bridge().stop_chat()
            except Exception:
                pass
        self.btn_stop_chatgpt.setVisible(False)
        self.progress.setVisible(False)
        self._append(self.chatgpt_history,
                     '<span style="color:#fca5a5;">⏹ 已停止</span>')
        self._set_status("● idle")

    def _ask_both(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self._user_msg(text)
        self.tabs.setCurrentIndex(2)
        self.progress.setVisible(True)
        self.btn_stop_claude.setVisible(True)
        self.btn_stop_chatgpt.setVisible(True)
        self._set_status("⚡ 同時對話中...", "#fbbf24")

        # 同時啟動兩個
        self._claude_worker = ClaudeWorker(text)
        self._claude_worker.message.connect(
            lambda m: QTimer.singleShot(0, lambda msg=m: (
                self._append(self.claude_history, msg, "#d1d5db"),
                self._append(self.both_claude, msg, "#d1d5db")
            ))
        )
        self._claude_worker.finished.connect(self._on_claude_done)
        self._claude_worker.start()

        self._chatgpt_worker = ChatGPTWorker(text)
        self._chatgpt_worker.message.connect(
            lambda m: QTimer.singleShot(0, lambda msg=m: (
                self._append(self.chatgpt_history, msg, "#d1d5db"),
                self._append(self.both_chatgpt, msg, "#d1d5db")
            ))
        )
        self._chatgpt_worker.finished.connect(self._on_chatgpt_done)
        self._chatgpt_worker.start()

    def _clear_all(self):
        self.claude_history.clear()
        self.chatgpt_history.clear()
        self.both_claude.clear()
        self.both_chatgpt.clear()


# ── 啟動 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = DualAIChatWindow()
    win.show()
    sys.exit(app.exec())
