# word_editor.py — 類 Word 文字編輯器主程式
# 依賴：pip install PyQt6
# 使用：python word_editor.py

import sys
import pathlib

try:
    _PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    if _PKG not in sys.path:
        sys.path.insert(0, _PKG)
except Exception:
    pass

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QVBoxLayout,
    QWidget, QStatusBar, QLabel, QFileDialog, QMessageBox,
    QFontDialog, QColorDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QKeySequence, QAction

try:
    from word_toolbar import FormatToolbar
    _HAS_TOOLBAR = True
except ImportError:
    _HAS_TOOLBAR = False

try:
    from word_file import FileManager
    _HAS_FILE = True
except ImportError:
    _HAS_FILE = False

STYLE = """
QMainWindow, QWidget {
    background-color: #f5f5f5;
    font-family: 'Microsoft JhengHei UI', 'Segoe UI', sans-serif;
}
QTextEdit {
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    padding: 20px 40px;
    font-size: 13px;
    color: #1a1a1a;
    line-height: 1.6;
    selection-background-color: #b3d4f5;
}
QMenuBar {
    background-color: #f0f0f0;
    border-bottom: 1px solid #d0d0d0;
}
QMenuBar::item:selected { background-color: #d0e4f5; }
QMenu { background-color: #ffffff; border: 1px solid #c0c0c0; }
QMenu::item:selected { background-color: #d0e4f5; }
QStatusBar { background-color: #f0f0f0; border-top: 1px solid #d0d0d0; color: #555; font-size: 11px; }
"""


class WordEditor(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("文字編輯器 — 未命名")
        self.setGeometry(100, 80, 900, 680)
        self.setMinimumSize(600, 400)
        self.setStyleSheet(STYLE)

        self._current_file = None
        self._modified     = False

        self._build_ui()
        self._build_menu()
        self._start_timers()

    # ── UI 建立 ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具列
        if _HAS_TOOLBAR:
            self.toolbar = FormatToolbar(self)
            self.addToolBar(self.toolbar)
            self.toolbar.format_changed.connect(self._apply_format)
        else:
            self._add_basic_toolbar()

        # 編輯區
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Microsoft JhengHei UI", 12))
        self.editor.setPlaceholderText("開始輸入...")
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._update_status)
        layout.addWidget(self.editor)

        # 狀態列
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_pos     = QLabel("行 1，欄 1")
        self.lbl_words   = QLabel("0 字")
        self.lbl_file    = QLabel("未命名")
        self.status.addWidget(self.lbl_file)
        self.status.addPermanentWidget(self.lbl_words)
        self.status.addPermanentWidget(self.lbl_pos)

    def _add_basic_toolbar(self):
        """沒有 word_toolbar.py 時用基本工具列"""
        from PyQt6.QtWidgets import QToolBar
        tb = QToolBar("格式")
        self.addToolBar(tb)

        bold_act = QAction("粗體", self)
        bold_act.setShortcut(QKeySequence.StandardKey.Bold)
        bold_act.setCheckable(True)
        bold_act.triggered.connect(lambda c: self._toggle_bold(c))
        tb.addAction(bold_act)

        italic_act = QAction("斜體", self)
        italic_act.setShortcut(QKeySequence.StandardKey.Italic)
        italic_act.setCheckable(True)
        italic_act.triggered.connect(lambda c: self._toggle_italic(c))
        tb.addAction(italic_act)

        underline_act = QAction("底線", self)
        underline_act.setShortcut(QKeySequence.StandardKey.Underline)
        underline_act.setCheckable(True)
        underline_act.triggered.connect(lambda c: self._toggle_underline(c))
        tb.addAction(underline_act)

        tb.addSeparator()

        font_act = QAction("字型...", self)
        font_act.triggered.connect(self._choose_font)
        tb.addAction(font_act)

        color_act = QAction("顏色...", self)
        color_act.triggered.connect(self._choose_color)
        tb.addAction(color_act)

    # ── 選單 ─────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        # 檔案選單
        file_menu = mb.addMenu("檔案(&F)")
        self._add_action(file_menu, "新增(&N)",     self._new,       "Ctrl+N")
        self._add_action(file_menu, "開啟(&O)...",  self._open,      "Ctrl+O")
        file_menu.addSeparator()
        self._add_action(file_menu, "儲存(&S)",     self._save,      "Ctrl+S")
        self._add_action(file_menu, "另存新檔(&A)...", self._save_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        self._add_action(file_menu, "結束(&X)",     self.close,      "Alt+F4")

        # 編輯選單
        edit_menu = mb.addMenu("編輯(&E)")
        self._add_action(edit_menu, "復原(&U)",     self.editor.undo, "Ctrl+Z")
        self._add_action(edit_menu, "取消復原(&R)", self.editor.redo, "Ctrl+Y")
        edit_menu.addSeparator()
        self._add_action(edit_menu, "剪下(&X)",     self.editor.cut,  "Ctrl+X")
        self._add_action(edit_menu, "複製(&C)",     self.editor.copy, "Ctrl+C")
        self._add_action(edit_menu, "貼上(&V)",     self.editor.paste,"Ctrl+V")
        edit_menu.addSeparator()
        self._add_action(edit_menu, "全選(&A)",     self.editor.selectAll, "Ctrl+A")

        # 格式選單
        fmt_menu = mb.addMenu("格式(&O)")
        self._add_action(fmt_menu, "字型(&F)...",   self._choose_font)
        self._add_action(fmt_menu, "字體顏色(&C)...", self._choose_color)

    def _add_action(self, menu, label, slot, shortcut=None):
        act = QAction(label, self)
        if shortcut:
            act.setShortcut(shortcut)
        act.triggered.connect(slot)
        menu.addAction(act)

    # ── 檔案操作 ─────────────────────────────────────────────────────────────

    def _new(self):
        if self._modified and not self._ask_save():
            return
        self.editor.clear()
        self._current_file = None
        self._modified     = False
        self.setWindowTitle("文字編輯器 — 未命名")
        self.lbl_file.setText("未命名")

    def _open(self):
        if self._modified and not self._ask_save():
            return
        if _HAS_FILE:
            path = FileManager.open_dialog(self)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "開啟檔案", "",
                "文字檔 (*.txt);;HTML 檔 (*.html);;所有檔案 (*.*)"
            )
        if not path:
            return
        try:
            content = pathlib.Path(path).read_text(encoding="utf-8", errors="ignore")
            if path.endswith(".html"):
                self.editor.setHtml(content)
            else:
                self.editor.setPlainText(content)
            self._current_file = path
            self._modified     = False
            name = pathlib.Path(path).name
            self.setWindowTitle(f"文字編輯器 — {name}")
            self.lbl_file.setText(name)
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"無法開啟：{e}")

    def _save(self):
        if not self._current_file:
            self._save_as()
            return
        self._write(self._current_file)

    def _save_as(self):
        if _HAS_FILE:
            path = FileManager.save_dialog(self)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "另存新檔", "",
                "文字檔 (*.txt);;HTML 檔 (*.html);;所有檔案 (*.*)"
            )
        if path:
            self._write(path)

    def _write(self, path: str):
        try:
            if path.endswith(".html"):
                content = self.editor.toHtml()
            else:
                content = self.editor.toPlainText()
            pathlib.Path(path).write_text(content, encoding="utf-8")
            self._current_file = path
            self._modified     = False
            name = pathlib.Path(path).name
            self.setWindowTitle(f"文字編輯器 — {name}")
            self.lbl_file.setText(name)
            self.status.showMessage("已儲存", 2000)
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"無法儲存：{e}")

    def _ask_save(self) -> bool:
        """詢問是否儲存，回傳 True 表示可以繼續"""
        reply = QMessageBox.question(
            self, "未儲存的變更",
            "文件有未儲存的變更，是否儲存？",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        if reply == QMessageBox.StandardButton.Save:
            self._save()
            return True
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        return False

    # ── 格式操作 ─────────────────────────────────────────────────────────────

    def _apply_format(self, fmt: dict):
        """接收 FormatToolbar 發出的格式變更"""
        cursor = self.editor.textCursor()
        cf = QTextCharFormat()
        if "bold" in fmt:
            cf.setFontWeight(QFont.Weight.Bold if fmt["bold"] else QFont.Weight.Normal)
        if "italic" in fmt:
            cf.setFontItalic(fmt["italic"])
        if "underline" in fmt:
            cf.setFontUnderline(fmt["underline"])
        if "font" in fmt:
            cf.setFont(fmt["font"])
        if "color" in fmt:
            cf.setForeground(QColor(fmt["color"]))
        if not cursor.hasSelection():
            self.editor.setCurrentCharFormat(cf)
        else:
            cursor.mergeCharFormat(cf)

    def _toggle_bold(self, checked):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if checked else QFont.Weight.Normal)
        self.editor.textCursor().mergeCharFormat(fmt)

    def _toggle_italic(self, checked):
        fmt = QTextCharFormat()
        fmt.setFontItalic(checked)
        self.editor.textCursor().mergeCharFormat(fmt)

    def _toggle_underline(self, checked):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(checked)
        self.editor.textCursor().mergeCharFormat(fmt)

    def _choose_font(self):
        font, ok = QFontDialog.getFont(self.editor.currentFont(), self)
        if ok:
            fmt = QTextCharFormat()
            fmt.setFont(font)
            cursor = self.editor.textCursor()
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.editor.setCurrentCharFormat(fmt)

    def _choose_color(self):
        color = QColorDialog.getColor(self.editor.textColor(), self)
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            cursor = self.editor.textCursor()
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.editor.setCurrentCharFormat(fmt)

    # ── 狀態更新 ─────────────────────────────────────────────────────────────

    def _on_text_changed(self):
        if not self._modified:
            self._modified = True
            title = self.windowTitle()
            if not title.startswith("*"):
                self.setWindowTitle("*" + title)
        self._update_status()

    def _update_status(self):
        cursor = self.editor.textCursor()
        line   = cursor.blockNumber() + 1
        col    = cursor.columnNumber() + 1
        words  = len(self.editor.toPlainText().split())
        self.lbl_pos.setText(f"行 {line}，欄 {col}")
        self.lbl_words.setText(f"{words} 字")

    def _start_timers(self):
        pass

    def closeEvent(self, event):
        if self._modified:
            if not self._ask_save():
                event.ignore()
                return
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("文字編輯器")
    win = WordEditor()
    win.show()
    sys.exit(app.exec())
