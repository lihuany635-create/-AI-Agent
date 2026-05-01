# word_toolbar.py — 文字格式工具列
# 提供粗體、斜體、底線、字型、字型大小、顏色等格式化按鈕

from PyQt6.QtWidgets import (
    QToolBar, QComboBox, QFontComboBox, QLabel, QPushButton
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont, QColor, QAction, QIcon
from PyQt6.QtWidgets import QColorDialog


class FormatToolbar(QToolBar):

    # 格式變更 signal，傳出 dict 給主視窗套用
    format_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__("格式工具列", parent)
        self.setMovable(False)
        self.setStyleSheet("""
            QToolBar { background: #f0f0f0; border-bottom: 1px solid #d0d0d0; spacing: 4px; padding: 2px 6px; }
            QPushButton { background: transparent; border: 1px solid transparent; border-radius: 4px;
                          padding: 3px 8px; font-size: 13px; min-width: 28px; }
            QPushButton:hover { background: #d8e8f5; border-color: #b0c8e0; }
            QPushButton:checked { background: #c0d8f0; border-color: #7aaecc; font-weight: bold; }
            QFontComboBox, QComboBox { border: 1px solid #c0c0c0; border-radius: 4px;
                                       padding: 2px 4px; background: white; min-width: 40px; }
        """)
        self._build()

    def _build(self):
        # 字型選擇
        self.addWidget(QLabel(" 字型："))
        self.font_combo = QFontComboBox()
        self.font_combo.setFixedWidth(160)
        self.font_combo.currentFontChanged.connect(self._on_font_changed)
        self.addWidget(self.font_combo)

        # 字型大小
        self.addWidget(QLabel(" 大小："))
        self.size_combo = QComboBox()
        self.size_combo.setFixedWidth(60)
        for size in [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72]:
            self.size_combo.addItem(str(size))
        self.size_combo.setCurrentText("12")
        self.size_combo.currentTextChanged.connect(self._on_size_changed)
        self.addWidget(self.size_combo)

        self.addSeparator()

        # 粗體
        self.btn_bold = QPushButton("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.btn_bold.setToolTip("粗體 (Ctrl+B)")
        self.btn_bold.clicked.connect(lambda c: self.format_changed.emit({"bold": c}))
        self.addWidget(self.btn_bold)

        # 斜體
        self.btn_italic = QPushButton("I")
        self.btn_italic.setCheckable(True)
        f = QFont("Arial", 11)
        f.setItalic(True)
        self.btn_italic.setFont(f)
        self.btn_italic.setToolTip("斜體 (Ctrl+I)")
        self.btn_italic.clicked.connect(lambda c: self.format_changed.emit({"italic": c}))
        self.addWidget(self.btn_italic)

        # 底線
        self.btn_underline = QPushButton("U")
        self.btn_underline.setCheckable(True)
        fu = QFont("Arial", 11)
        fu.setUnderline(True)
        self.btn_underline.setFont(fu)
        self.btn_underline.setToolTip("底線 (Ctrl+U)")
        self.btn_underline.clicked.connect(lambda c: self.format_changed.emit({"underline": c}))
        self.addWidget(self.btn_underline)

        self.addSeparator()

        # 字體顏色
        self.btn_color = QPushButton("A")
        self.btn_color.setToolTip("字體顏色")
        self.btn_color.setStyleSheet("QPushButton { color: #cc0000; font-weight: bold; }")
        self.btn_color.clicked.connect(self._pick_color)
        self.addWidget(self.btn_color)

        # 對齊
        self.addSeparator()
        for label, align, tip in [
            ("≡", "left",    "靠左"),
            ("≡", "center",  "置中"),
            ("≡", "right",   "靠右"),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.clicked.connect(lambda c, a=align: self.format_changed.emit({"align": a}))
            self.addWidget(btn)

    def _on_font_changed(self, font: QFont):
        self.format_changed.emit({"font": font})

    def _on_size_changed(self, size_str: str):
        try:
            size = int(size_str)
            self.format_changed.emit({"size": size})
        except ValueError:
            pass

    def _pick_color(self):
        color = QColorDialog.getColor(QColor("#000000"), self.parent())
        if color.isValid():
            self.btn_color.setStyleSheet(
                f"QPushButton {{ color: {color.name()}; font-weight: bold; }}"
            )
            self.format_changed.emit({"color": color.name()})

    def update_format(self, fmt: QFont, color: QColor):
        """主視窗游標移動時，同步更新工具列狀態"""
        self.font_combo.setCurrentFont(fmt)
        self.size_combo.setCurrentText(str(int(fmt.pointSize())))
        self.btn_bold.setChecked(fmt.bold())
        self.btn_italic.setChecked(fmt.italic())
        self.btn_underline.setChecked(fmt.underline())
