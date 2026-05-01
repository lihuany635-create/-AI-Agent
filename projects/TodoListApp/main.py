# main.py - 待辦清單主程式
# 由立 AI 自主開發
# 執行：python main.py

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QLabel, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import database

STYLE = """
QMainWindow, QWidget { background: #1a1d27; color: #e0e0e0; font-family: 'Microsoft JhengHei UI'; }
QLineEdit { background: #111318; border: 1px solid #2a2d3a; border-radius: 8px; padding: 8px 12px; color: #e0e0e0; font-size: 13px; }
QLineEdit:focus { border: 1px solid #2563eb; }
QPushButton { background: #2563eb; color: #fff; border: none; border-radius: 8px; padding: 8px 18px; font-size: 13px; }
QPushButton:hover { background: #1d4ed8; }
QPushButton#btn_del { background: #7f1d1d; color: #fca5a5; }
QPushButton#btn_del:hover { background: #991b1b; }
QListWidget { background: #111318; border: 1px solid #2a2d3a; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 8px; border-radius: 6px; margin: 2px; }
QListWidget::item:selected { background: #1e3a5f; }
QLabel#title { color: #7eb8f7; font-size: 18px; font-weight: bold; }
QLabel#count { color: #555; font-size: 12px; }
"""

class TodoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("待辦清單 - 立 AI")
        self.setGeometry(200, 200, 500, 600)
        self.setMinimumSize(400, 400)
        self.setStyleSheet(STYLE)
        self._build_ui()
        self._load_tasks()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        # 標題
        title = QLabel("待辦清單")
        title.setObjectName("title")
        v.addWidget(title)

        # 輸入列
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("輸入待辦事項，按 Enter 新增...")
        self.input.returnPressed.connect(self._add_task)
        btn_add = QPushButton("新增")
        btn_add.setFixedWidth(72)
        btn_add.clicked.connect(self._add_task)
        row.addWidget(self.input)
        row.addWidget(btn_add)
        v.addLayout(row)

        # 清單
        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Microsoft JhengHei UI", 12))
        v.addWidget(self.list_widget)

        # 底部列
        bottom = QHBoxLayout()
        self.count_label = QLabel("0 個待辦")
        self.count_label.setObjectName("count")
        btn_del = QPushButton("刪除選取")
        btn_del.setObjectName("btn_del")
        btn_del.setFixedWidth(90)
        btn_del.clicked.connect(self._delete_task)
        btn_clear = QPushButton("清除已完成")
        btn_clear.setObjectName("btn_del")
        btn_clear.clicked.connect(self._clear_done)
        bottom.addWidget(self.count_label)
        bottom.addStretch()
        bottom.addWidget(btn_clear)
        bottom.addWidget(btn_del)
        v.addLayout(bottom)

    def _load_tasks(self):
        self.list_widget.clear()
        tasks = database.get_all_tasks()
        for task_id, task_text, done in tasks:
            item = QListWidgetItem()
            item.setText(("✓ " if done else "○ ") + task_text)
            item.setData(Qt.ItemDataRole.UserRole, task_id)
            if done:
                item.setForeground(Qt.GlobalColor.gray)
            self.list_widget.addItem(item)
        self.count_label.setText(f"{len(tasks)} 個待辦")

    def _add_task(self):
        text = self.input.text().strip()
        if not text:
            return
        database.add_task(text)
        self.input.clear()
        self._load_tasks()

    def _delete_task(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        database.delete_task(task_id)
        self._load_tasks()

    def _clear_done(self):
        tasks = database.get_all_tasks()
        for task_id, _, done in tasks:
            if done:
                database.delete_task(task_id)
        self._load_tasks()

    def mouseDoubleClickEvent(self, event):
        item = self.list_widget.currentItem()
        if item:
            task_id = item.data(Qt.ItemDataRole.UserRole)
            database.toggle_done(task_id)
            self._load_tasks()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = TodoApp()
    win.show()
    sys.exit(app.exec())
