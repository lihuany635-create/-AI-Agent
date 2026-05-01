# desktop_pet_3d.py — 圓圓 3D 桌面小人
# moderngl 離屏渲染 VRM → PIL → PyQt6 透明視窗
# 使用：python desktop_pet_3d.py

import sys, math, random, struct, json, pathlib, time, io
import numpy as np
from PIL import Image
import moderngl

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import (QCursor, QColor, QPainter, QFont, QPolygon,
                          QBrush, QPen, QPixmap, QImage)

VRM_FILE = "圓圓.vrm"
PET_W, PET_H = 260, 400
SPEED = 2.0

PHRASES = ["你好～ (´▽`)", "今天天氣真好！", "需要我幫什麼嗎？",
           "我在這裡喔！", "咦，你看我做什麼？", "工作加油！(ง •̀_•́)ง",
           "要喝水喔～", "我是圓圓！", "點我幹嘛啦 (*/ω＼*)", "嗯嗯～"]
SLEEP_PHRASES = ["zzz...", "呼～呼～", "好困喔..."]
STATE_WALK="walk"; STATE_IDLE="idle"
STATE_SLEEP="sleep"; STATE_FOLLOW="follow"; STATE_REACT="react"

# ── 矩陣工具 ──────────────────────────────────────────────────────────────────
def _persp(fov, asp, n, f):
    t = math.tan(math.radians(fov)/2)
    return np.array([
        [1/(asp*t), 0,          0,               0],
        [0,         1/t,        0,               0],
        [0,         0, -(f+n)/(f-n), -2*f*n/(f-n)],
        [0,         0,         -1,               0]
    ], dtype=np.float32)

def _look_at(eye, center, up):
    e=np.array(eye,dtype=np.float32); c=np.array(center,dtype=np.float32)
    u=np.array(up,dtype=np.float32)
    f=c-e; f/=np.linalg.norm(f)
    r=np.cross(f,u); r/=np.linalg.norm(r)
    u2=np.cross(r,f)
    return np.array([
        [r[0], r[1], r[2], -r@e],
        [u2[0],u2[1],u2[2],-u2@e],
        [-f[0],-f[1],-f[2], f@e],
        [0,    0,    0,     1]
    ], dtype=np.float32)

def _ry(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[c,0,s,0],[0,1,0,0],[-s,0,c,0],[0,0,0,1]],dtype=np.float32)

def _rz(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[c,-s,0,0],[s,c,0,0],[0,0,1,0],[0,0,0,1]],dtype=np.float32)

def _trans(x,y,z):
    m=np.eye(4,dtype=np.float32); m[0,3]=x; m[1,3]=y; m[2,3]=z
    return m

# ── VRM 解析 ──────────────────────────────────────────────────────────────────
class VRMLoader:
    def __init__(self, path):
        data = pathlib.Path(path).read_bytes()
        cl = struct.unpack_from('<I', data, 12)[0]
        self.jd = json.loads(data[20:20+cl])
        bo = 20+cl
        bl = struct.unpack_from('<I', data, bo)[0]
        self.bin = data[bo+8: bo+8+bl]
        self.meshes=[]; self.materials=[]; self.tex_images=[]
        self._parse()

    def _bv(self, i):
        b=self.jd['bufferViews'][i]; s=b.get('byteOffset',0)
        return self.bin[s:s+b['byteLength']]

    def _acc(self, i):
        a=self.jd['accessors'][i]; bv=self._bv(a['bufferView'])
        off=a.get('byteOffset',0); cnt=a['count']
        n={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        dt={5126:np.float32,5123:np.uint16,5125:np.uint32}[a['componentType']]
        arr=np.frombuffer(bv,dtype=dt,count=cnt*n,offset=off)
        return arr.reshape(cnt,n) if n>1 else arr

    def _parse(self):
        all_imgs=[]
        for img_info in self.jd.get('images',[]):
            try:
                img=Image.open(io.BytesIO(bytes(self._bv(img_info['bufferView'])))).convert('RGBA')
                all_imgs.append(img)
            except: all_imgs.append(None)
        for tex in self.jd.get('textures',[]):
            src_idx=tex.get('source',0)
            self.tex_images.append(all_imgs[src_idx] if src_idx<len(all_imgs) else None)
        for m in self.jd.get('materials',[]):
            pbr=m.get('pbrMetallicRoughness',{})
            ext=m.get('extensions',{})
            mtoon=ext.get('VRMC_materials_mtoon',{})
            lit=pbr.get('baseColorFactor',[1,1,1,1])
            shade_raw=mtoon.get('shadeColorFactor',None)
            if shade_raw:
                shade=(list(shade_raw)+[1.0])[:4]
                brightness=(lit[0]+lit[1]+lit[2])/3
                c=[lit[i]*0.6+shade[i]*0.4 for i in range(4)] if brightness>0.5 else list(lit)
            else:
                c=list(lit)
            ti=pbr.get('baseColorTexture',{}).get('index')
            self.materials.append({'color':c,'tex':ti})
        for mesh in self.jd.get('meshes',[]):
            for prim in mesh.get('primitives',[]):
                at=prim.get('attributes',{})
                try:
                    v=self._acc(at['POSITION']).astype(np.float32)
                    n=(self._acc(at['NORMAL']).astype(np.float32) if 'NORMAL' in at else np.zeros_like(v))
                    uv=(self._acc(at['TEXCOORD_0']).astype(np.float32) if 'TEXCOORD_0' in at else np.zeros((len(v),2),np.float32))
                    idx=self._acc(prim['indices']).flatten().astype(np.uint32)
                    self.meshes.append({'v':v,'n':n,'uv':uv,'idx':idx,'mat':prim.get('material',0)})
                except: pass

# ── moderngl 渲染器 ────────────────────────────────────────────────────────────
VERT = """
#version 330
in vec3 in_pos;
in vec3 in_normal;
in vec2 in_uv;
uniform mat4 mvp;
out vec3 vn;
out vec2 vuv;
void main(){
    gl_Position = mvp * vec4(in_pos, 1.0);
    vn  = in_normal;
    vuv = in_uv;
}
"""
FRAG = """
#version 330
in vec3 vn;
in vec2 vuv;
uniform sampler2D tex;
uniform vec4 base_color;
uniform bool has_tex;
out vec4 fragColor;
void main(){
    vec4 col = has_tex ? texture(tex, vuv) * base_color : base_color;
    if(col.a < 0.05) discard;
    vec3 n   = normalize(vn);
    float d1 = max(dot(n, normalize(vec3(1.5,3.0,2.0))), 0.0);
    float d2 = max(dot(n, normalize(vec3(-1.0,1.0,1.5))), 0.0);
    float light = 0.5 + d1*0.5 + d2*0.15;
    fragColor = vec4(col.rgb * light, col.a);
}
"""

class Renderer:
    def __init__(self, vrm, W, H):
        self.vrm=vrm; self.W=W; self.H=H
        self.ctx=moderngl.create_standalone_context()
        self.prog=self.ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
        self.fbo=self.ctx.framebuffer(
            color_attachments=[self.ctx.texture((W,H),4)],
            depth_attachment=self.ctx.depth_renderbuffer((W,H)))
        self.vaos=[]; self.gl_texs=[]
        self._build()

    def _build(self):
        for mesh in self.vrm.meshes:
            vb=self.ctx.buffer(mesh['v'].tobytes())
            nb=self.ctx.buffer(mesh['n'].tobytes())
            ub=self.ctx.buffer(mesh['uv'].tobytes())
            ib=self.ctx.buffer(mesh['idx'].tobytes())
            vao=self.ctx.vertex_array(self.prog,[
                (vb,'3f','in_pos'),
                (nb,'3f','in_normal'),
                (ub,'2f','in_uv'),
            ], index_buffer=ib, index_element_size=4)
            self.vaos.append(vao)
        for img in self.vrm.tex_images:
            if img:
                t=self.ctx.texture(img.size,4,img.tobytes())
                t.filter=(moderngl.LINEAR,moderngl.LINEAR)
                self.gl_texs.append(t)
            else: self.gl_texs.append(None)

    def render(self, tilt_x=0, tilt_z=0, bob=0, sleep=False):
        self.fbo.use()
        self.ctx.clear(0,0,0,0)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func=moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        proj  = _persp(32, self.W/self.H, 0.01, 50)
        view  = _look_at([0,1.1,1.8],[0,1.1,0],[0,1,0])
        model = _trans(0,bob,0) @ _ry(math.radians(tilt_x)) @ _rz(math.radians(tilt_z*0.4))
        mvp   = (proj @ view @ model).T

        self.prog['mvp'].write(mvp.astype(np.float32).tobytes())

        for i,(mesh,vao) in enumerate(zip(self.vrm.meshes,self.vaos)):
            mat=self.vrm.materials[mesh['mat']] if mesh['mat']<len(self.vrm.materials) else {'color':[1,1,1,1],'tex':None}
            c=mat['color']
            self.prog['base_color'].value=(c[0],c[1],c[2],0.75 if sleep else c[3])
            ti=mat['tex']
            if ti is not None and ti<len(self.gl_texs) and self.gl_texs[ti]:
                self.gl_texs[ti].use(0); self.prog['tex'].value=0
                self.prog['has_tex'].value=True
            else: self.prog['has_tex'].value=False
            vao.render(moderngl.TRIANGLES)

        raw=self.fbo.read(components=4)
        return Image.frombytes('RGBA',(self.W,self.H),raw).transpose(Image.FLIP_TOP_BOTTOM)

# ── 說話泡泡 ──────────────────────────────────────────────────────────────────
class Bubble(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(200,54); self._text=""
        self._t=QTimer(); self._t.setSingleShot(True); self._t.timeout.connect(self.hide)
    def show_text(self,text,dur=2800):
        self._text=text; self.update(); self.show(); self._t.start(dur)
    def paintEvent(self,e):
        if not self._text: return
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(255,255,255,235))); p.setPen(QPen(QColor(180,180,210),1.5))
        p.drawRoundedRect(0,0,self.width()-1,self.height()-14,12,12)
        p.drawPolygon(QPolygon([QPoint(24,self.height()-14),QPoint(40,self.height()-14),QPoint(32,self.height()-1)]))
        p.setPen(QColor(40,40,65)); p.setFont(QFont("Microsoft JhengHei UI",11))
        p.drawText(QRect(8,4,self.width()-16,self.height()-18),
                   Qt.AlignmentFlag.AlignCenter|Qt.AlignmentFlag.AlignVCenter,self._text)

# ── 主視窗 ────────────────────────────────────────────────────────────────────
class PetWindow(QWidget):
    def __init__(self, renderer):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(PET_W,PET_H)
        self.ren=renderer; self._pix=QPixmap(PET_W,PET_H); self._pix.fill(QColor(0,0,0,0))
        sc=QApplication.primaryScreen().availableGeometry()
        self._x=float(sc.right()-PET_W-60); self._y=float(sc.bottom()-PET_H-20)
        self.move(int(self._x),int(self._y))
        self._state=STATE_WALK; self._dir=-1; self._vy=0.0
        self._t=0.0; self._tilt_x=0.0; self._tilt_z=0.0
        self._wob=0.0; self._wob_v=0.0
        self._drag=False; self._dp=QPoint(); self._zzz=0.0
        self._lt=time.time()
        self._bubble=Bubble()
        QTimer(self, timeout=self._tick, interval=33).start()
        QTimer(self, timeout=self._change_state, interval=random.randint(5000,10000)).start()

    def _change_state(self):
        if self._state==STATE_REACT: return
        self._state=random.choices([STATE_WALK,STATE_WALK,STATE_IDLE,STATE_SLEEP,STATE_FOLLOW],[40,30,20,10,15])[0]
        if self._state==STATE_WALK: self._dir=random.choice([-1,1])
        if self._state==STATE_FOLLOW:
            QTimer.singleShot(random.randint(4000,8000),lambda:setattr(self,'_state',STATE_WALK))

    def _tick(self):
        now=time.time(); dt=min(now-self._lt,0.1); self._lt=now
        self._t+=dt; self._zzz+=dt
        sc=QApplication.primaryScreen().availableGeometry()
        cur=QCursor.pos()
        tx=(cur.x()/max(sc.width(),1)-0.5)*20
        tz=(cur.y()/max(sc.height(),1)-0.5)*8
        self._tilt_x+=(tx-self._tilt_x)*0.07
        self._tilt_z+=(tz-self._tilt_z)*0.07
        if self._state in(STATE_WALK,STATE_FOLLOW):
            self._wob_v+=(-self._wob*0.15-self._wob_v*0.25)
            self._wob+=self._wob_v
            if int(self._t*60)%18==0: self._wob_v+=self._dir*3
        else: self._wob*=0.85; self._wob_v*=0.85
        floor=sc.bottom()-PET_H-10
        if self._state==STATE_WALK:
            self._x+=SPEED*self._dir
            if self._x<0: self._x=0; self._dir=1
            if self._x>sc.width()-PET_W: self._x=sc.width()-PET_W; self._dir=-1
            if random.random()<0.005: self._vy=-7.0
            self._vy+=0.4; self._y+=self._vy
            if self._y>=floor: self._y=floor; self._vy=0.0
        elif self._state==STATE_FOLLOW:
            tx2=cur.x()-PET_W//2; ty2=cur.y()-PET_H+20
            dx=tx2-self._x; dy=ty2-self._y; dist=math.hypot(dx,dy)
            if dist>6:
                spd=min(SPEED*3,dist); self._x+=dx/dist*spd; self._y+=dy/dist*spd
                self._dir=1 if dx>0 else -1
        elif self._state==STATE_IDLE:
            if random.random()<0.002: self._say(random.choice(PHRASES))
        elif self._state==STATE_SLEEP:
            if int(self._zzz*10)%80==0: self._say(random.choice(SLEEP_PHRASES),1800)
        bob=math.sin(self._t*6)*0.018 if self._state in(STATE_WALK,STATE_FOLLOW) else math.sin(self._t*1.5)*0.005
        img=self.ren.render(tilt_x=self._tilt_x,tilt_z=self._wob*0.5,bob=bob,sleep=(self._state==STATE_SLEEP))
        qimg=QImage(img.tobytes('raw','RGBA'),img.width,img.height,QImage.Format.Format_RGBA8888)
        if self._dir<0: qimg=qimg.mirrored(True,False)
        self._pix=QPixmap.fromImage(qimg)
        self.move(int(self._x),int(self._y))
        bx=max(0,min(int(self._x)-10,sc.width()-200))
        by=max(0,int(self._y)-62)
        self._bubble.move(bx,by)
        self.update()

    def _say(self,text,dur=2800): self._bubble.show_text(text,dur)

    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(0,0,self._pix)
        if self._state==STATE_SLEEP:
            for i in range(3):
                ph=self._zzz*1.5+i*0.9; al=int(max(0,min(255,190*abs(math.sin(ph)))))
                sz=10+i*4; x=PET_W-20-i*12+int(math.sin(ph)*5); y=30-i*18+int(math.cos(ph)*3)
                p.setPen(QPen(QColor(80,130,220,al),1.5))
                p.setFont(QFont("Arial",sz,QFont.Weight.Bold))
                p.drawText(x,y+sz,"z")

    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._drag=False; self._dp=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseReleaseEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton and not self._drag:
            self._state=STATE_REACT; self._say(random.choice(PHRASES))
            QTimer.singleShot(3000,lambda:setattr(self,'_state',STATE_WALK))
    def mouseMoveEvent(self,e):
        if e.buttons()==Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint()-self._dp)
            self._x=float(self.x()); self._y=float(self.y()); self._drag=True
    def mouseDoubleClickEvent(self,e):
        if self._state==STATE_FOLLOW: self._state=STATE_WALK; self._say("自己玩囉～",2000)
        else: self._state=STATE_FOLLOW; self._say("好的，我跟著你！(｡･ω･｡)",2000)
    def contextMenuEvent(self,e):
        menu=QMenu(self)
        menu.setStyleSheet("QMenu{background:#16161a;border:1px solid #2a2a32;border-radius:8px;color:#e8e6e0;padding:4px}"
                           "QMenu::item{padding:7px 20px;font-size:13px;font-family:'Microsoft JhengHei UI'}"
                           "QMenu::item:selected{background:rgba(232,197,71,.15);color:#e8c547}"
                           "QMenu::separator{height:1px;background:#2a2a32;margin:3px 0}")
        menu.addAction("👋 打招呼",  lambda:self._say(random.choice(PHRASES)))
        menu.addAction("😴 去睡覺",  lambda:setattr(self,'_state',STATE_SLEEP))
        menu.addAction("🏃 開始走路",lambda:(setattr(self,'_state',STATE_WALK),setattr(self,'_dir',random.choice([-1,1]))))
        menu.addAction("🖱 跟隨滑鼠",lambda:(setattr(self,'_state',STATE_FOLLOW),self._say("跟著你了！",1500)))
        menu.addSeparator()
        menu.addAction("❌ 關閉",    QApplication.quit)
        menu.exec(e.globalPos())

if __name__=="__main__":
    app=QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    base=pathlib.Path(__file__).parent
    vp=base/VRM_FILE
    if not vp.exists(): print(f"找不到：{vp}"); sys.exit(1)
    print("載入 VRM..."); vrm=VRMLoader(str(vp))
    print(f"Mesh:{len(vrm.meshes)} 材質:{len(vrm.materials)} 貼圖:{len(vrm.tex_images)}")
    print("初始化渲染器..."); ren=Renderer(vrm,PET_W,PET_H); print("完成！")
    pet=PetWindow(ren); pet.show()
    QTimer.singleShot(1000,lambda:pet._say("我是圓圓，好高興見到你！(｡･ω･｡)",3000))
    sys.exit(app.exec())
