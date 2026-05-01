# yuanyuan_bubble.py — 圓圓說話泡泡
# 浮在 VMagicMirror 角色旁邊，定時顯示可愛台詞
# 使用：python yuanyuan_bubble.py

import sys, random, ctypes, ctypes.wintypes, time
import pathlib

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath, QPolygon

# ── 台詞庫 ────────────────────────────────────────────────────────────────────

PHRASES = [
    "你好～ 我是圓圓！(｡･ω･｡)",
    "今天也要加油喔！(ง •̀_•́)ง",
    "要記得喝水喔～ 💧",
    "你在做什麼呢？好奇好奇～",
    "嗯嗯～ 我在這裡喔！",
    "工作辛苦了！休息一下吧 ☕",
    "今天天氣怎麼樣呀？",
    "我可以幫你嗎？(´▽`)",
    "點我幹嘛啦 (*/ω＼*)",
    "嘿嘿，被你發現了～",
    "要保持心情愉快喔！🌸",
    "記得吃飯嗎？餓了要說喔！",
    "你今天看起來很努力呢！",
    "我陪著你喔～ (っ´ω`c)",
    "哇，你回來了！我想你了～",
    "一起加油吧！✊",
    "休息也是工作的一部分喔！",
    "你的努力我都看到了！",
    "需要我幫什麼嗎？儘管說！",
    "呼呼～ 微風好舒服 (≧▽≦)",
]

INTERVAL_MS = 15000  # 每 15 秒說一次

# ── 泡泡視窗 ──────────────────────────────────────────────────────────────────

class BubbleWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(220)

        self._text = ""
        self._opacity = 0.0
        self._build_ui()

        # 找 VMagicMirror 視窗位置
        self._vmagic_hwnd = None
        self._find_vmagic()

        # 定時說話
        self._phrase_timer = QTimer()
        self._phrase_timer.timeout.connect(self._say_random)
        self._phrase_timer.start(INTERVAL_MS)

        # 淡入淡出計時器
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        # 追蹤 VMagicMirror 位置（100ms 更新一次，讓泡泡緊跟圓圓）
        self._track_timer = QTimer()
        self._track_timer.timeout.connect(self._update_pos)
        self._track_timer.start(100)

        # 啟動
        self._update_pos()
        self.show()
        QTimer.singleShot(800, self._say_random)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 20)  # 底部留空給尾巴

        self._card = QFrame()
        self._card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 235);
                border-radius: 16px;
                border: 1.5px solid rgba(200, 180, 220, 180);
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(150, 100, 200, 80))
        shadow.setOffset(0, 4)
        self._card.setGraphicsEffect(shadow)

        inner = QVBoxLayout(self._card)
        inner.setContentsMargins(14, 10, 14, 10)

        # 名字標籤
        name = QLabel("圓圓")
        name.setStyleSheet("""
            color: #b06ec4;
            font-size: 11px;
            font-weight: 800;
            font-family: 'Microsoft JhengHei UI';
        """)
        inner.addWidget(name)

        # 台詞文字
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setStyleSheet("""
            color: #3a3050;
            font-size: 13px;
            font-family: 'Microsoft JhengHei UI';
            line-height: 1.5;
        """)
        self._label.setMinimumHeight(20)
        inner.addWidget(self._label)

        outer.addWidget(self._card)

    def paintEvent(self, e):
        """畫泡泡尾巴"""
        super().paintEvent(e)
        if not self._label.text():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        # 尾巴（三角形）在底部中間
        card_bottom = self._card.y() + self._card.height()
        tip_x = self.width() // 2
        path = QPainterPath()
        path.moveTo(tip_x - 10, card_bottom)
        path.lineTo(tip_x + 10, card_bottom)
        path.lineTo(tip_x, card_bottom + 14)
        path.closeSubpath()

        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.setPen(QPen(QColor(200, 180, 220, 180), 1.5))
        p.drawPath(path)

    def _find_vmagic(self):
        """找到 VMagicMirror 角色視窗 handle（標題是純 "VMagicMirror"）"""
        result = []
        def cb(hwnd, _):
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value
            # 角色視窗標題是純 "VMagicMirror"，設定視窗含版本號
            if title == "VMagicMirror":
                result.append(hwnd)
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(cb), 0)
        self._vmagic_hwnd = result[0] if result else None
        if self._vmagic_hwnd:
            print(f"[BUBBLE] 找到 VMagicMirror 視窗: {self._vmagic_hwnd}")

    def _update_pos(self):
        """持續跟隨 VMagicMirror 角色位置"""
        sc = QApplication.primaryScreen().availableGeometry()
        self._find_vmagic()
        if self._vmagic_hwnd:
            try:
                rect = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(
                    ctypes.c_void_p(self._vmagic_hwnd), ctypes.byref(rect))
                vw = rect.right - rect.left
                win_x = rect.left + vw // 2 - self.width() // 2
                win_y = rect.top - self.height() - 8
                win_x = max(sc.left(), min(win_x, sc.right() - self.width()))
                win_y = max(sc.top(), min(win_y, sc.bottom() - self.height()))
                print(f"[BUBBLE] VMagic rect=({rect.left},{rect.top},{rect.right},{rect.bottom}) → bubble=({win_x},{win_y})")
                self.move(win_x, win_y)
                return
            except Exception as e:
                print(f"[BUBBLE] 位置更新失敗: {e}")
        # VMagicMirror 找不到 → 右下角
        self.move(sc.right() - self.width() - 20, sc.bottom() - self.height() - 180)

    def _say_random(self):
        self._say(random.choice(PHRASES))

    def _say(self, text: str, duration: int = 6000):
        self._label.setText(text)
        self._card.adjustSize()
        self.adjustSize()
        self._opacity = 1.0
        self.show()
        self.update()
        self._hide_timer.start(duration)

    def _fade_out(self):
        # 不隱藏視窗，只清空文字（讓視窗繼續跟隨圓圓）
        self._label.setText("")
        self.update()


# ── 啟動 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    bubble = BubbleWindow()
    sys.exit(app.exec())
