# vrm_viewer.py — 圓圓 3D 模型檢視器
# pyrender + trimesh 渲染，PyQt6 視窗
# 使用：python vrm_viewer.py

import sys, math, time, pathlib, shutil
import numpy as np

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

import trimesh
import pyrender
from PIL import Image

from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                              QVBoxLayout, QHBoxLayout, QSlider, QFrame,
                              QFileDialog)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import QPainter, QColor, QPixmap, QImage, QFont, QPen

W, H = 500, 600
VRM_FILE = "圓圓.vrm"

# ── 載入模型 ──────────────────────────────────────────────────────────────────
def load_model(vrm_path):
    glb = vrm_path.rsplit('.', 1)[0] + '.glb'
    if not pathlib.Path(glb).exists() or pathlib.Path(vrm_path).stat().st_mtime > pathlib.Path(glb).stat().st_mtime:
        shutil.copy(vrm_path, glb)
    return trimesh.load(glb)

# ── pyrender 渲染器 ────────────────────────────────────────────────────────────
def build_pyrender_scene(tm_scene):
    scene = pyrender.Scene(bg_color=[0,0,0,0], ambient_light=[0.3,0.3,0.32])
    for name, mesh in tm_scene.geometry.items():
        mat = None
        try:
            vm = mesh.visual.material
            tex_img = getattr(vm, 'baseColorTexture', None)
            if tex_img is not None:
                tex_img = tex_img.convert('RGBA')
                tex = pyrender.Texture(source=tex_img, source_channels='RGBA')
                alpha_mode = getattr(vm, 'alphaMode', 'OPAQUE') or 'OPAQUE'
                mat = pyrender.MetallicRoughnessMaterial(
                    baseColorTexture=tex,
                    baseColorFactor=list(getattr(vm,'baseColorFactor',[1,1,1,1])),
                    metallicFactor=float(getattr(vm,'metallicFactor',0.0)),
                    roughnessFactor=max(0.5, float(getattr(vm,'roughnessFactor',0.9))*0.8),
                    alphaMode=alpha_mode,
                    alphaCutoff=float(getattr(vm,'alphaCutoff',0.5))
                )
        except Exception:
            pass
        try:
            pr_mesh = pyrender.Mesh.from_trimesh(mesh, material=mat, smooth=True)
            scene.add(pr_mesh)
        except Exception:
            try:
                pr_mesh = pyrender.Mesh.from_trimesh(mesh, smooth=True)
                scene.add(pr_mesh)
            except Exception:
                pass
    return scene

class VRMRenderer:
    def __init__(self, tm_scene, W, H):
        self.W = W; self.H = H
        self.pr_scene = build_pyrender_scene(tm_scene)

        # 燈光
        def make_pose(pos):
            p = np.array(pos, dtype=np.float32)
            p = p / np.linalg.norm(p) * 5
            m = np.eye(4, dtype=np.float32); m[:3,3] = p
            return m
        dl = pyrender.DirectionalLight(color=[1.0,0.97,0.92], intensity=3.5)
        self.pr_scene.add(dl, pose=make_pose([1.5,3.0,2.0]))
        dl2 = pyrender.DirectionalLight(color=[0.5,0.6,1.0], intensity=1.0)
        self.pr_scene.add(dl2, pose=make_pose([-1.0,1.0,1.5]))
        dl3 = pyrender.DirectionalLight(color=[1.0,0.8,0.5], intensity=0.6)
        self.pr_scene.add(dl3, pose=make_pose([0,-1.0,0.5]))

        # 模型中心和大小
        bounds = tm_scene.bounds
        self._center = (bounds[0] + bounds[1]) / 2
        self._base_center_y = float(self._center[1])
        self._size   = float(np.linalg.norm(bounds[1] - bounds[0]))
        self._dist   = self._size * 1.2

        # 相機
        cam = pyrender.PerspectiveCamera(yfov=np.pi/5, aspectRatio=W/H)
        self._cam_node = self.pr_scene.add(cam, pose=self._cam_pose(0, 0, self._dist))
        self.renderer = pyrender.OffscreenRenderer(W, H)

    def _cam_pose(self, rx, ry, dist):
        cy, sy = math.cos(ry), math.sin(ry)
        cx, sx = math.cos(rx), math.sin(rx)
        pos = np.array([dist*sy*cx, dist*sx+self._center[1], dist*cy*cx], dtype=np.float32)
        fwd = self._center - pos
        fwd /= np.linalg.norm(fwd)
        up  = np.array([0,1,0], dtype=np.float32)
        r   = np.cross(fwd, up)
        if np.linalg.norm(r) < 1e-6: r = np.array([1,0,0], dtype=np.float32)
        else: r /= np.linalg.norm(r)
        u   = np.cross(r, fwd)
        m   = np.eye(4, dtype=np.float32)
        m[:3,0]=r; m[:3,1]=u; m[:3,2]=-fwd; m[:3,3]=pos
        return m

    def set_camera(self, rx, ry, dist):
        self.pr_scene.set_pose(self._cam_node, self._cam_pose(rx, ry, dist))

    def render(self):
        color, _ = self.renderer.render(self.pr_scene, flags=pyrender.RenderFlags.RGBA)
        return Image.fromarray(color, 'RGBA')

    def __del__(self):
        try: self.renderer.delete()
        except: pass

# ── 主視窗 ────────────────────────────────────────────────────────────────────
# ── 動畫系統 ──────────────────────────────────────────────────────────────────
class Animator:
    """管理模型動畫，輸出 (translate_y, rotate_z, head_nod) 給渲染器用"""
    ACTIONS = [
        "wave",    # 揮手打招呼
        "nod",     # 點頭
        "sway",    # 身體搖擺
        "jump",    # 小跳跳
        "wiggle",  # 足跡波浪
    ]

    def __init__(self):
        self._t       = 0.0
        self._action  = 0
        self._phase   = 0.0   # 當前動作內部時間
        self._dur     = 3.0   # 每個動作持續秒數

    def update(self, dt):
        self._t     += dt
        self._phase += dt
        if self._phase >= self._dur:
            self._phase = 0.0
            self._action = (self._action + 1) % len(self.ACTIONS)

    def get_transform(self):
        """回傳 (ty, rz, rx_head, scale) 代表位移/旋轉量"""
        p = self._phase
        a = self.ACTIONS[self._action]
        ty = rz = rx_head = 0.0
        scale = 1.0

        if a == "wave":
            # 身體稍微左右搖，頭跟著動
            rz = math.sin(p * math.pi * 2) * 0.06
            rx_head = math.sin(p * math.pi * 2 + 0.5) * 0.04

        elif a == "nod":
            # 點頭三下
            rx_head = max(0, math.sin(p * math.pi * 6)) * 0.18

        elif a == "sway":
            # 身體懶散左右晃
            rz = math.sin(p * math.pi * 1.5) * 0.08
            ty = abs(math.sin(p * math.pi * 3)) * 0.015

        elif a == "jump":
            # 上下彈跳
            ty = abs(math.sin(p * math.pi * 2)) * 0.08
            scale = 1.0 + abs(math.sin(p * math.pi * 2)) * 0.02

        elif a == "wiggle":
            # 足跡波浪：上下+左右
            ty = math.sin(p * math.pi * 3) * 0.025
            rz = math.sin(p * math.pi * 3 + math.pi/4) * 0.05

        return ty, rz, rx_head, scale

    def action_name(self):
        names = {"wave":"揮手打招呼","nod":"點頭","sway":"身體搖擺","jump":"小跳跳","wiggle":"足跡波浪"}
        return names.get(self.ACTIONS[self._action], "")


class ViewerWindow(QWidget):
    def __init__(self, ren: VRMRenderer):
        super().__init__()
        self.ren = ren
        self.setWindowTitle("3D 模型檢視器")
        self.setFixedSize(W+160, H+60)
        self.setStyleSheet("background:#111118; color:#e8e6e0;")

        self._rx = -0.15; self._ry = 0.0
        self._anim = Animator()
        self._anim_on = True
        self._action_label = None
        self._dist = ren._dist
        self._drag = False; self._lp = QPoint()
        self._auto = True; self._spd = 0.4
        self._lt = time.time()

        self._pix = QPixmap(W, H+60)
        self._pix.fill(QColor(10,10,18))
        self._build_ui()
        self._render()
        QTimer(self, timeout=self._tick, interval=33).start()

    def _build_ui(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(0,0,0,0); main.setSpacing(0)

        # 畫布
        self._canvas = QLabel()
        self._canvas.setFixedSize(W, H+60)
        self._canvas.setStyleSheet("background:#0a0a12;")
        self._canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        self._canvas.mousePressEvent   = self._on_press
        self._canvas.mouseMoveEvent    = self._on_move
        self._canvas.mouseReleaseEvent = self._on_release
        self._canvas.wheelEvent        = self._on_wheel
        main.addWidget(self._canvas)

        # 面板
        panel = QFrame()
        panel.setFixedWidth(160)
        panel.setStyleSheet("background:#16161a; border-left:1px solid #2a2a32;")
        v = QVBoxLayout(panel)
        v.setContentsMargins(12,16,12,16); v.setSpacing(8)

        title = QLabel("3D 檢視器")
        title.setFont(QFont("Microsoft JhengHei UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color:#e8c547;")
        v.addWidget(title)

        v.addWidget(self._sep())

        import_btn = QPushButton("📂 匯入模型")
        import_btn.setStyleSheet(self._bs("#2a4a2a","#86efac"))
        import_btn.clicked.connect(self._import)
        v.addWidget(import_btn)

        # 動畫開關
        self._anim_btn = QPushButton("💃 動畫開啟")
        self._anim_btn.setStyleSheet(self._bs("#4a2a4a","#c084fc"))
        self._anim_btn.clicked.connect(self._toggle_anim)
        v.addWidget(self._anim_btn)

        # 動作標籤
        self._action_lbl = QLabel("揮手打招呼")
        self._action_lbl.setStyleSheet("color:#c084fc;font-size:11px;text-align:center;")
        self._action_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self._action_lbl)

        self._auto_btn = QPushButton("⏸ 暫停旋轉")
        self._auto_btn.setStyleSheet(self._bs("#e8c547","#0e0e0f"))
        self._auto_btn.clicked.connect(self._toggle_auto)
        v.addWidget(self._auto_btn)

        reset_btn = QPushButton("🔄 重置視角")
        reset_btn.setStyleSheet(self._bs("#3a3a4a","#e8e6e0"))
        reset_btn.clicked.connect(self._reset)
        v.addWidget(reset_btn)

        v.addWidget(self._sep())
        v.addWidget(QLabel("旋轉速度"))
        sl_spd = QSlider(Qt.Orientation.Horizontal)
        sl_spd.setRange(1,20); sl_spd.setValue(4)
        sl_spd.valueChanged.connect(lambda val: setattr(self,'_spd',val*0.1))
        sl_spd.setStyleSheet("QSlider::handle{background:#e8c547;border-radius:5px;width:10px;height:10px;}")
        v.addWidget(sl_spd)

        v.addWidget(QLabel("縮放"))
        self._sl_zoom = QSlider(Qt.Orientation.Horizontal)
        self._sl_zoom.setRange(3,30); self._sl_zoom.setValue(12)
        self._sl_zoom.valueChanged.connect(lambda val: self._set_dist(self.ren._size*val/10))
        self._sl_zoom.setStyleSheet("QSlider::handle{background:#e8c547;border-radius:5px;width:10px;height:10px;}")
        v.addWidget(self._sl_zoom)

        v.addWidget(self._sep())
        for label,rx,ry in [("正面",-0.15,0),("側面",-0.15,1.57),("背面",-0.15,3.14),("俯視",-1.2,0)]:
            b = QPushButton(label)
            b.setStyleSheet(self._bs("#2a2a3a","#e8e6e0"))
            b.clicked.connect(lambda _,rx=rx,ry=ry: self._set_view(rx,ry))
            v.addWidget(b)

        v.addStretch()
        tip = QLabel("拖曳旋轉\n滾輪縮放")
        tip.setStyleSheet("color:#555; font-size:11px;")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(tip)
        main.addWidget(panel)

    def _sep(self):
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color:#2a2a32;"); return f

    def _bs(self, bg, fg):
        return (f"QPushButton{{background:{bg};color:{fg};border:none;border-radius:6px;"
                f"padding:7px;font-size:12px;font-family:'Microsoft JhengHei UI';}}"
                f"QPushButton:hover{{background:#3a3a5a;color:#e8c547;}}")

    def _render(self):
        # 套用動畫偏移到相機（模擬角色動作）
        ty, rz, rx_head, sc = self._anim.get_transform() if self._anim_on else (0,0,0,1)
        anim_rx = self._rx + rx_head
        anim_dist = self._dist / sc
        self.ren.set_camera(anim_rx, self._ry + rz, anim_dist)
        self.ren._center[1] = self.ren._base_center_y + ty
        img = self.ren.render()
        bg = Image.new('RGBA', (W, H+60), (10,10,18,255))
        bg.paste(img, (0,30), img)
        qimg = QImage(bg.tobytes('raw','RGBA'), bg.width, bg.height, QImage.Format.Format_RGBA8888)
        self._pix = QPixmap.fromImage(qimg)
        self._canvas.setPixmap(self._pix)

    def _tick(self):
        now = time.time(); dt = min(now-self._lt,0.1); self._lt = now
        # 動畫更新
        if self._anim_on:
            self._anim.update(dt)
            self._action_lbl.setText(self._anim.action_name())

        if self._auto and not self._drag:
            self._ry += self._spd * dt
            self._render()

    def _toggle_auto(self):
        self._auto = not self._auto
        self._auto_btn.setText("▶ 繼續旋轉" if not self._auto else "⏸ 暫停旋轉")

    def _reset(self):
        self._rx=-0.15; self._ry=0.0; self._dist=self.ren._dist
        self._sl_zoom.setValue(12); self._render()

    def _set_view(self, rx, ry):
        self._rx=rx; self._ry=ry; self._render()

    def _set_dist(self, d):
        self._dist = max(self.ren._size*0.3, min(self.ren._size*3, d))
        self._render()

    def _toggle_anim(self):
        self._anim_on = not self._anim_on
        self._anim_btn.setText("💃 動畫開啟" if self._anim_on else "⏹ 動畫關閉")
        if not self._anim_on:
            self._action_lbl.setText("")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "選擇模型", "", "3D 模型 (*.vrm *.glb)")
        if not path: return
        try:
            new_tm = load_model(path) if path.endswith('.vrm') else trimesh.load(path)
            new_ren = VRMRenderer(new_tm, W, H)
            try: self.ren.renderer.delete()
            except: pass
            self.ren = new_ren
            self._dist = new_ren._dist
            self._rx=-0.15; self._ry=0.0
            self.setWindowTitle(f"3D 檢視器 — {pathlib.Path(path).name}")
            self._render()
        except Exception as exc:
            print(f"載入失敗：{exc}")

    def _on_press(self, e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._drag=True; self._lp=e.pos()
            self._canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _on_move(self, e):
        if self._drag:
            dx=e.pos().x()-self._lp.x(); dy=e.pos().y()-self._lp.y()
            self._ry+=dx*0.008; self._rx+=dy*0.008
            self._rx=max(-1.5,min(1.5,self._rx))
            self._lp=e.pos(); self._render()

    def _on_release(self, e):
        self._drag=False
        self._canvas.setCursor(Qt.CursorShape.OpenHandCursor)

    def _on_wheel(self, e):
        self._dist *= 0.9 if e.angleDelta().y()>0 else 1.1
        self._dist = max(self.ren._size*0.3, min(self.ren._size*3, self._dist))
        self._sl_zoom.setValue(int(self._dist/self.ren._size*10))
        self._render()

# ── 啟動 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    base = pathlib.Path(__file__).parent
    vrm_path = base / VRM_FILE

    if vrm_path.exists():
        path = str(vrm_path)
    else:
        path, _ = QFileDialog.getOpenFileName(None, "選擇 VRM 模型", str(base), "3D 模型 (*.vrm *.glb)")
        if not path: sys.exit(0)

    print(f"載入：{path}")
    tm = load_model(path)
    print(f"完成，{len(tm.geometry)} 個 mesh")
    print("初始化渲染器...")
    ren = VRMRenderer(tm, W, H)
    print("完成！")
    win = ViewerWindow(ren)
    win.show()
    sys.exit(app.exec())
