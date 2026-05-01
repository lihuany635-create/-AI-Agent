# desktop_pet.py — 桌面小人（圓圓）立體版
# 陰影 + 視差移動 + 3D搖擺 + 隨機遊走 + 睡覺 + 跟隨滑鼠 + 點擊互動

import sys, math, random
import pathlib

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import (QPainter, QColor, QBrush, QPen, QFont,
                          QPixmap, QTransform, QPolygon, QRadialGradient)

IMG_NAME = "yuanyuan.webp"
PET_W    = 200
SPEED    = 2.0

PHRASES = [
    "你好～ (´▽`)", "今天天氣真好！", "需要我幫什麼嗎？",
    "我在這裡喔！", "嗯嗯嗯～", "咦，你看我做什麼？",
    "工作加油！(ง •̀_•́)ง", "要喝水喔～", "我是圓圓！",
    "點我幹嘛啦 (*/ω＼*)",
]
SLEEP_PHRASES = ["zzz...", "呼～呼～", "好困喔..."]

STATE_WALK = "walk"; STATE_IDLE = "idle"
STATE_SLEEP = "sleep"; STATE_FOLLOW = "follow"; STATE_REACT = "react"

# ── 說話泡泡 ──────────────────────────────────────────────────────────────────
class BubbleLabel(QWidget):
    def __init__(self):
        super().__init__(None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(200, 54)
        self._text = ""
        self._timer = QTimer(); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text, duration=2800):
        self._text = text; self.update(); self.show()
        self._timer.start(duration)

    def paintEvent(self, e):
        if not self._text: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.setPen(QPen(QColor(180, 180, 210), 1.5))
        p.drawRoundedRect(0, 0, self.width()-1, self.height()-14, 12, 12)
        tri = QPolygon([QPoint(24, self.height()-14),
                        QPoint(40, self.height()-14),
                        QPoint(32, self.height()-1)])
        p.drawPolygon(tri)
        p.setPen(QColor(40, 40, 65))
        p.setFont(QFont("Microsoft JhengHei UI", 11))
        p.drawText(QRect(8, 4, self.width()-16, self.height()-18),
                   Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                   self._text)

# ── 主角色 ────────────────────────────────────────────────────────────────────
class PetWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        base = pathlib.Path(__file__).parent
        img_path = base / IMG_NAME
        self._pixmap_orig = QPixmap(str(img_path))
        if self._pixmap_orig.isNull():
            print(f"[錯誤] 找不到圖片：{img_path}")

        ratio = (self._pixmap_orig.height() / self._pixmap_orig.width()
                 if not self._pixmap_orig.isNull() else 1.0)
        self._pet_h = int(PET_W * ratio)

        # 視窗加大以容納陰影 + 視差偏移
        self._pad   = 30   # 四周留白供陰影
        self._par   = 18   # 視差最大位移
        self.setFixedSize(PET_W + self._pad*2 + self._par,
                          self._pet_h + self._pad*2 + self._par)

        self._pix_r = self._pixmap_orig.scaled(
            PET_W, self._pet_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._pix_l = self._pix_r.transformed(QTransform().scale(-1, 1))

        sc = QApplication.primaryScreen().availableGeometry()
        self._sx = sc.width(); self._sy = sc.height()
        self._x  = float(sc.right() - self.width() - 50)
        self._y  = float(sc.bottom() - self.height() - 20)
        self.move(int(self._x), int(self._y))

        self._state     = STATE_WALK
        self._dir       = -1
        self._vy        = 0.0
        self._anim_tick = 0
        self._zzz_phase = 0.0
        self._drag      = False
        self._drag_pos  = QPoint()

        # 3D 搖擺角度
        self._tilt_x    = 0.0   # 左右傾斜（視差用）
        self._tilt_y    = 0.0   # 上下傾斜
        self._tilt_tx   = 0.0   # 目標傾斜
        self._tilt_ty   = 0.0
        self._wobble    = 0.0   # 走路搖擺角度
        self._wobble_v  = 0.0

        # 滑鼠追蹤（視差）
        self._mouse_x   = sc.width() / 2
        self._mouse_y   = sc.height() / 2

        self._bubble = BubbleLabel()

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # 60fps

        self._state_timer = QTimer()
        self._state_timer.timeout.connect(self._change_state)
        self._state_timer.start(random.randint(5000, 10000))

        # 追蹤滑鼠位置（用全域計時器）
        self._mouse_timer = QTimer()
        self._mouse_timer.timeout.connect(self._track_mouse)
        self._mouse_timer.start(32)

    def _track_mouse(self):
        from PyQt6.QtGui import QCursor
        pos = QCursor.pos()
        self._mouse_x = pos.x()
        self._mouse_y = pos.y()
        # 計算相對於角色中心的方向，轉成傾斜目標
        cx = self._x + self.width() / 2
        cy = self._y + self.height() / 2
        dx = (self._mouse_x - cx) / max(self._sx, 1)
        dy = (self._mouse_y - cy) / max(self._sy, 1)
        self._tilt_tx = dx * self._par   # 視差目標
        self._tilt_ty = dy * self._par * 0.5

    def _change_state(self):
        if self._state == STATE_REACT: return
        states  = [STATE_WALK, STATE_WALK, STATE_IDLE, STATE_SLEEP, STATE_FOLLOW]
        weights = [40, 30, 20, 10, 15]
        self._state = random.choices(states, weights)[0]
        if self._state == STATE_WALK:
            self._dir = random.choice([-1, 1])
        if self._state == STATE_FOLLOW:
            QTimer.singleShot(random.randint(4000, 8000),
                lambda: setattr(self, '_state', STATE_WALK))
        self._state_timer.start(random.randint(4000, 11000))

    def _tick(self):
        self._anim_tick += 1
        self._zzz_phase += 0.05

        # 視差平滑插值
        self._tilt_x += (self._tilt_tx - self._tilt_x) * 0.08
        self._tilt_y += (self._tilt_ty - self._tilt_y) * 0.08

        # 走路搖擺（左右晃）
        if self._state in (STATE_WALK, STATE_FOLLOW):
            self._wobble_v += (-self._wobble * 0.15 - self._wobble_v * 0.25)
            self._wobble   += self._wobble_v
            if self._anim_tick % 18 == 0:
                self._wobble_v += self._dir * 3.0
        else:
            self._wobble   *= 0.85
            self._wobble_v *= 0.85

        sc = QApplication.primaryScreen().availableGeometry()
        self._sx = sc.width(); self._sy = sc.height()
        floor = sc.bottom() - self.height() - 10

        if self._state == STATE_WALK:
            self._x += SPEED * self._dir
            if self._x < 0: self._x = 0; self._dir = 1
            if self._x > self._sx - self.width(): self._x = self._sx - self.width(); self._dir = -1
            if random.random() < 0.005: self._vy = -7.0
            self._vy += 0.4; self._y += self._vy
            if self._y >= floor: self._y = floor; self._vy = 0.0

        elif self._state == STATE_FOLLOW:
            tx = self._mouse_x - self.width() // 2
            ty = self._mouse_y - self.height() + self._pad
            dx = tx - self._x; dy = ty - self._y
            dist = math.hypot(dx, dy)
            if dist > 6:
                spd = min(SPEED * 3, dist)
                self._x += dx / dist * spd; self._y += dy / dist * spd
                self._dir = 1 if dx > 0 else -1

        elif self._state == STATE_IDLE:
            if random.random() < 0.002:
                self._say(random.choice(PHRASES))

        elif self._state == STATE_SLEEP:
            if self._anim_tick % 80 == 0:
                self._say(random.choice(SLEEP_PHRASES), 1800)

        self.move(int(self._x), int(self._y))
        self._update_bubble()
        self.update()

    def _update_bubble(self):
        bx = int(self._x) + self._pad - 10
        by = int(self._y) - 62
        sc = QApplication.primaryScreen().availableGeometry()
        bx = max(0, min(bx, sc.width() - 200))
        by = max(0, by)
        self._bubble.move(bx, by)

    def _say(self, text, duration=2800):
        self._bubble.show_text(text, duration)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        pad = self._pad
        pw  = PET_W
        ph  = self._pet_h

        # 視差偏移量
        ox = int(self._tilt_x)
        oy = int(self._tilt_y)

        # ── 地面陰影（橢圓漸層）────────────────────────────────────────────
        shadow_cx = pad + pw // 2 + ox
        shadow_cy = pad + ph + 8
        shadow_rx  = int(pw * 0.38)
        shadow_ry  = int(pw * 0.08)

        grad = QRadialGradient(shadow_cx, shadow_cy, shadow_rx)
        grad.setColorAt(0,   QColor(0, 0, 0, 80))
        grad.setColorAt(0.5, QColor(0, 0, 0, 40))
        grad.setColorAt(1,   QColor(0, 0, 0, 0))
        p.save()
        p.translate(0, 0)
        p.scale(1.0, shadow_ry / shadow_rx)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(shadow_cx - shadow_rx,
                      int((shadow_cy) * shadow_rx / shadow_ry) - shadow_rx,
                      shadow_rx * 2, shadow_rx * 2)
        p.restore()

        # ── 3D 搖擺 + 視差變形 ──────────────────────────────────────────────
        pix = self._pix_l if self._dir < 0 else self._pix_r

        # Bob（上下彈跳）
        bob = int(math.sin(self._anim_tick * 0.22) * 2.5) if self._state in (STATE_WALK, STATE_FOLLOW) else 0

        # 用 QTransform 做透視傾斜（模擬3D）
        # wobble: 左右傾斜（走路搖擺）
        # tilt_x: 視差左右（跟滑鼠方向）
        wobble_rad = math.radians(self._wobble * 0.8)
        tilt_shear = self._tilt_x * 0.003   # 輕微水平剪切

        transform = QTransform()
        transform.translate(pad + pw/2 + ox, pad + ph/2 + bob + oy)
        transform.shear(tilt_shear + math.sin(wobble_rad)*0.06, 0)
        # 縮放（靠近滑鼠稍微放大）
        scale_factor = 1.0 + abs(self._tilt_x) * 0.001
        transform.scale(scale_factor, scale_factor)
        transform.translate(-pw/2, -ph/2)

        if self._state == STATE_SLEEP:
            p.setOpacity(0.82)
        p.setTransform(transform)
        p.drawPixmap(0, 0, pix)
        p.resetTransform()
        p.setOpacity(1.0)

        # ── 睡覺 zzz ──────────────────────────────────────────────────────
        if self._state == STATE_SLEEP:
            self._draw_zzz(p, pad + ox, pad + oy)

    def _draw_zzz(self, p, ox, oy):
        for i in range(3):
            phase = self._zzz_phase + i * 0.9
            alpha = int(max(0, min(255, 190 * abs(math.sin(phase)))))
            size  = 10 + i * 4
            x = ox + PET_W - 10 - i * 10 + int(math.sin(phase) * 5)
            y = oy + 20 - i * 16 + int(math.cos(phase) * 3)
            p.setPen(QPen(QColor(80, 130, 220, alpha), 1.5))
            p.setFont(QFont("Arial", size, QFont.Weight.Bold))
            p.drawText(x, y + size, "z")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = False
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self._drag:
            self._state = STATE_REACT
            self._say(random.choice(PHRASES))
            QTimer.singleShot(3000, lambda: setattr(self, '_state', STATE_WALK))

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            self._x = float(self.x()); self._y = float(self.y())
            self._drag = True

    def mouseDoubleClickEvent(self, e):
        if self._state == STATE_FOLLOW:
            self._state = STATE_WALK
            self._say("自己玩囉～", 2000)
        else:
            self._state = STATE_FOLLOW
            self._say("好的，我跟著你！(｡･ω･｡)", 2000)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#16161a; border:1px solid #2a2a32;
                    border-radius:8px; color:#e8e6e0; padding:4px; }
            QMenu::item { padding:7px 20px; font-size:13px;
                          font-family:'Microsoft JhengHei UI'; }
            QMenu::item:selected { background:rgba(232,197,71,.15); color:#e8c547; }
            QMenu::separator { height:1px; background:#2a2a32; margin:3px 0; }
        """)
        menu.addAction("👋 打招呼",   lambda: self._say(random.choice(PHRASES)))
        menu.addAction("😴 去睡覺",   lambda: setattr(self, '_state', STATE_SLEEP))
        menu.addAction("🏃 開始走路", lambda: (setattr(self, '_state', STATE_WALK),
                                               setattr(self, '_dir', random.choice([-1,1]))))
        menu.addAction("🖱 跟隨滑鼠", lambda: (setattr(self, '_state', STATE_FOLLOW),
                                               self._say("跟著你了！", 1500)))
        menu.addSeparator()
        menu.addAction("❌ 關閉",     QApplication.quit)
        menu.exec(e.globalPos())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = PetWidget()
    pet.show()
    QTimer.singleShot(800, lambda: pet._say("我是圓圓，好高興見到你！(｡･ω･｡)", 3000))
    sys.exit(app.exec())
