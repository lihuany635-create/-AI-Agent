# pc_api.py — 立AI 個人電腦控制 API
# 啟動方式：python pc_api.py
# API 位置：http://localhost:8899

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import subprocess
import pathlib
import base64
import time
import os

try:
    from agent_logger import get_logger
    logger = get_logger("pc_api")
except ImportError:
    import logging
    logger = logging.getLogger("pc_api")

app = FastAPI(title="立AI 電腦控制 API", version="1.0.0")

# ── 資料模型 ──────────────────────────────────────────────────────────────────

class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"    # left / right / middle
    clicks: int = 1

class TypeRequest(BaseModel):
    text: str
    interval: float = 0.05  # 每個字的間隔秒數

class HotkeyRequest(BaseModel):
    keys: list[str]          # 例如 ["ctrl", "c"]

class MoveRequest(BaseModel):
    x: int
    y: int
    duration: float = 0.2

class ScrollRequest(BaseModel):
    x: int
    y: int
    amount: int              # 正數向上，負數向下

class RunRequest(BaseModel):
    command: str
    wait: bool = False       # 是否等待執行完成
    timeout: int = 30

class OpenRequest(BaseModel):
    path: str                # 檔案或資料夾路徑

class VisionRequest(BaseModel):
    question: str = "請描述這個畫面"
    scale: float = 0.5


# ── 滑鼠控制 ─────────────────────────────────────────────────────────────────

@app.post("/mouse/click")
def mouse_click(req: ClickRequest):
    try:
        import pyautogui
        pyautogui.click(req.x, req.y, button=req.button, clicks=req.clicks)
        logger.info(f"[API] 點擊 ({req.x}, {req.y}) button={req.button}")
        return {"ok": True, "x": req.x, "y": req.y}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mouse/move")
def mouse_move(req: MoveRequest):
    try:
        import pyautogui
        pyautogui.moveTo(req.x, req.y, duration=req.duration)
        return {"ok": True, "x": req.x, "y": req.y}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mouse/scroll")
def mouse_scroll(req: ScrollRequest):
    try:
        import pyautogui
        pyautogui.scroll(req.amount, x=req.x, y=req.y)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/mouse/position")
def mouse_position():
    try:
        import pyautogui
        x, y = pyautogui.position()
        return {"x": x, "y": y}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 鍵盤控制 ─────────────────────────────────────────────────────────────────

@app.post("/keyboard/type")
def keyboard_type(req: TypeRequest):
    try:
        import pyautogui
        pyautogui.typewrite(req.text, interval=req.interval)
        logger.info(f"[API] 輸入文字：{req.text[:30]}")
        return {"ok": True, "length": len(req.text)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/keyboard/hotkey")
def keyboard_hotkey(req: HotkeyRequest):
    try:
        import pyautogui
        pyautogui.hotkey(*req.keys)
        logger.info(f"[API] 快捷鍵：{'+'.join(req.keys)}")
        return {"ok": True, "keys": req.keys}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/keyboard/press")
def keyboard_press(key: str):
    try:
        import pyautogui
        pyautogui.press(key)
        return {"ok": True, "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 截圖 ─────────────────────────────────────────────────────────────────────

@app.get("/screen/capture")
def screen_capture(scale: float = 1.0):
    """截圖並回傳 base64 圖片"""
    try:
        import mss, numpy as np, cv2
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1])
            img = cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)
        if scale != 1.0:
            h, w = img.shape[:2]
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
        _, buf = cv2.imencode(".png", img)
        b64 = base64.b64encode(buf.tobytes()).decode()
        logger.info(f"[API] 截圖 {img.shape[1]}x{img.shape[0]}")
        return {"ok": True, "image": b64, "width": img.shape[1], "height": img.shape[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/screen/size")
def screen_size():
    try:
        import pyautogui
        w, h = pyautogui.size()
        return {"width": w, "height": h}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 視覺理解 ─────────────────────────────────────────────────────────────────

@app.post("/screen/ask")
def screen_ask(req: VisionRequest):
    """截圖後讓 llava:7b 回答問題"""
    try:
        from vision_engine import ask_screen
        result = ask_screen(req.question)
        return {"ok": True, "answer": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 系統操作 ─────────────────────────────────────────────────────────────────

@app.post("/system/run")
def system_run(req: RunRequest):
    """執行系統指令"""
    try:
        logger.info(f"[API] 執行指令：{req.command}")
        if req.wait:
            result = subprocess.run(
                req.command, shell=True, capture_output=True,
                text=True, timeout=req.timeout
            )
            return {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:500]
            }
        else:
            subprocess.Popen(req.command, shell=True)
            return {"ok": True, "command": req.command}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/system/open")
def system_open(req: OpenRequest):
    """開啟檔案或資料夾"""
    try:
        path = pathlib.Path(req.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"找不到：{req.path}")
        os.startfile(str(path))
        logger.info(f"[API] 開啟：{req.path}")
        return {"ok": True, "path": str(path)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/system/clipboard")
def get_clipboard():
    """讀取剪貼簿"""
    try:
        import pyperclip
        text = pyperclip.paste()
        return {"ok": True, "text": text, "length": len(text)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/system/clipboard")
def set_clipboard(text: str):
    """寫入剪貼簿"""
    try:
        import pyperclip
        pyperclip.copy(text)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 狀態 ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"name": "立AI 電腦控制 API", "version": "1.0.0", "status": "running"}

@app.get("/health")
def health():
    return {"ok": True, "time": time.strftime("%Y-%m-%d %H:%M:%S")}


# ── 啟動 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("=" * 40)
    print("立AI 電腦控制 API 啟動中...")
    print("位置：http://localhost:8899")
    print("文件：http://localhost:8899/docs")
    print("=" * 40)
    uvicorn.run(app, host="0.0.0.0", port=8899, log_level="warning")


# ══════════════════════════════════════════════════════════════════════════════
# 擴充功能區
# ══════════════════════════════════════════════════════════════════════════════

# ── 擴充資料模型 ──────────────────────────────────────────────────────────────

class FileReadRequest(BaseModel):
    path: str
    encoding: str = "utf-8"

class FileWriteRequest(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"
    append: bool = False

class FileCopyRequest(BaseModel):
    src: str
    dst: str

class FileSearchRequest(BaseModel):
    directory: str
    pattern: str = "*"
    recursive: bool = True

class HttpRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: dict = {}
    body: dict = {}
    timeout: int = 30

class DownloadRequest(BaseModel):
    url: str
    save_path: str

class NotifyRequest(BaseModel):
    title: str
    message: str
    duration: int = 5

class VolumeRequest(BaseModel):
    level: int   # 0~100

class RecordRequest(BaseModel):
    duration: int = 10          # 秒數
    save_path: str = "record.mp4"

class WindowRequest(BaseModel):
    title: str = ""             # 視窗標題關鍵字


# ── 視窗管理 ─────────────────────────────────────────────────────────────────

@app.get("/window/list")
def window_list():
    """列出所有開啟的視窗"""
    try:
        import win32gui
        windows = []
        def _enum(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    windows.append({"hwnd": hwnd, "title": title})
        win32gui.EnumWindows(_enum, None)
        return {"ok": True, "windows": windows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/window/focus")
def window_focus(req: WindowRequest):
    """切換到指定視窗"""
    try:
        import win32gui, win32con
        hwnd = win32gui.FindWindow(None, req.title)
        if not hwnd:
            # 模糊搜尋
            def _find(h, _):
                if req.title.lower() in win32gui.GetWindowText(h).lower():
                    raise StopIteration(h)
            try:
                win32gui.EnumWindows(_find, None)
            except StopIteration as e:
                hwnd = e.args[0]
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return {"ok": True, "hwnd": hwnd}
        raise HTTPException(status_code=404, detail=f"找不到視窗：{req.title}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/window/maximize")
def window_maximize(req: WindowRequest):
    """最大化視窗"""
    try:
        import win32gui, win32con
        hwnd = win32gui.FindWindow(None, req.title)
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return {"ok": True}
        raise HTTPException(status_code=404, detail=f"找不到視窗：{req.title}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/window/close")
def window_close(req: WindowRequest):
    """關閉視窗"""
    try:
        import win32gui, win32con
        hwnd = win32gui.FindWindow(None, req.title)
        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return {"ok": True}
        raise HTTPException(status_code=404, detail=f"找不到視窗：{req.title}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 檔案操作 ─────────────────────────────────────────────────────────────────

@app.post("/file/read")
def file_read(req: FileReadRequest):
    """讀取檔案內容"""
    try:
        p = pathlib.Path(req.path)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"找不到檔案：{req.path}")
        content = p.read_text(encoding=req.encoding)
        return {"ok": True, "content": content, "size": len(content)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/file/write")
def file_write(req: FileWriteRequest):
    """寫入檔案"""
    try:
        p = pathlib.Path(req.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if req.append:
            with open(p, "a", encoding=req.encoding) as f:
                f.write(req.content)
        else:
            p.write_text(req.content, encoding=req.encoding)
        logger.info(f"[API] 寫入檔案：{req.path}")
        return {"ok": True, "path": str(p), "size": len(req.content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/file/copy")
def file_copy(req: FileCopyRequest):
    """複製檔案"""
    try:
        import shutil
        shutil.copy2(req.src, req.dst)
        return {"ok": True, "src": req.src, "dst": req.dst}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DeleteRequest(BaseModel):
    path: str
    confirm: bool = False   # 必須明確傳 True 才會刪除

@app.post("/file/delete")
def file_delete(req: DeleteRequest):
    """刪除檔案（必須傳 confirm=true 才會執行）"""
    if not req.confirm:
        p = pathlib.Path(req.path)
        exists = p.exists()
        ftype = "資料夾" if p.is_dir() else "檔案"
        return {
            "ok": False,
            "need_confirm": True,
            "message": f"確定要刪除{ftype}「{req.path}」嗎？請傳入 confirm=true 確認。",
            "exists": exists,
            "type": ftype,
        }
    try:
        p = pathlib.Path(req.path)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"找不到：{req.path}")
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            import shutil
            shutil.rmtree(p)
        logger.info(f"[API] 已刪除：{req.path}")
        return {"ok": True, "path": req.path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/file/search")
def file_search(req: FileSearchRequest):
    """搜尋檔案"""
    try:
        import fnmatch
        d = pathlib.Path(req.directory)
        if not d.exists():
            raise HTTPException(status_code=404, detail=f"資料夾不存在：{req.directory}")
        if req.recursive:
            results = [str(p) for p in d.rglob(req.pattern)]
        else:
            results = [str(p) for p in d.glob(req.pattern)]
        return {"ok": True, "results": results[:200], "count": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/file/list")
def file_list(directory: str = "."):
    """列出資料夾內容"""
    try:
        d = pathlib.Path(directory)
        items = []
        for p in d.iterdir():
            items.append({
                "name": p.name,
                "type": "dir" if p.is_dir() else "file",
                "size": p.stat().st_size if p.is_file() else 0,
            })
        return {"ok": True, "items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 網路 ─────────────────────────────────────────────────────────────────────

@app.post("/network/request")
def network_request(req: HttpRequest):
    """發送 HTTP 請求"""
    try:
        import requests as _req
        r = _req.request(
            req.method, req.url,
            headers=req.headers,
            json=req.body if req.body else None,
            timeout=req.timeout
        )
        try:
            body = r.json()
        except Exception:
            body = r.text[:2000]
        return {"ok": True, "status": r.status_code, "body": body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/network/download")
def network_download(req: DownloadRequest):
    """下載檔案"""
    try:
        import requests as _req
        p = pathlib.Path(req.save_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        r = _req.get(req.url, stream=True, timeout=60)
        r.raise_for_status()
        with open(p, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        size = p.stat().st_size
        logger.info(f"[API] 下載完成：{req.save_path}（{size} bytes）")
        return {"ok": True, "path": str(p), "size": size}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 通知 ─────────────────────────────────────────────────────────────────────

@app.post("/notify")
def notify(req: NotifyRequest):
    """發送 Windows 桌面通知"""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(req.title, req.message, duration=req.duration, threaded=True)
        return {"ok": True}
    except ImportError:
        # fallback：用 PowerShell 通知
        script = (
            f'Add-Type -AssemblyName System.Windows.Forms;'
            f'[System.Windows.Forms.MessageBox]::Show("{req.message}", "{req.title}")'
        )
        subprocess.Popen(["powershell", "-Command", script])
        return {"ok": True, "method": "powershell"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 音量控制 ─────────────────────────────────────────────────────────────────

@app.post("/system/volume")
def set_volume(req: VolumeRequest):
    """設定系統音量 0~100"""
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        import ctypes
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(req.level / 100.0, None)
        return {"ok": True, "level": req.level}
    except ImportError:
        # fallback：用 PowerShell
        script = f"(New-Object -com Shell.Application).SetVolume({req.level})"
        subprocess.run(["powershell", "-Command", script])
        return {"ok": True, "method": "powershell", "level": req.level}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/system/volume")
def get_volume():
    """取得目前音量"""
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        import ctypes
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        level = int(volume.GetMasterVolumeLevelScalar() * 100)
        return {"ok": True, "level": level}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 螢幕亮度 ─────────────────────────────────────────────────────────────────

@app.post("/system/brightness")
def set_brightness(level: int):
    """設定螢幕亮度 0~100（需要 WMI）"""
    try:
        import wmi
        c = wmi.WMI(namespace="wmi")
        methods = c.WmiMonitorBrightnessMethods()[0]
        methods.WmiSetBrightness(level, 0)
        return {"ok": True, "level": level}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 錄影 ─────────────────────────────────────────────────────────────────────

_recording = {"active": False, "thread": None}

@app.post("/record/start")
def record_start(req: RecordRequest):
    """開始錄製螢幕"""
    try:
        if _recording["active"]:
            return {"ok": False, "message": "已在錄製中"}

        import cv2, mss, numpy as np, threading as _th

        def _do_record():
            _recording["active"] = True
            p = pathlib.Path(req.save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with mss.mss() as sct:
                mon = sct.monitors[1]
                w, h = mon["width"], mon["height"]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                out = cv2.VideoWriter(str(p), fourcc, 10.0, (w, h))
                start = time.time()
                while _recording["active"] and (time.time() - start) < req.duration:
                    frame = cv2.cvtColor(np.array(sct.grab(mon)), cv2.COLOR_BGRA2BGR)
                    out.write(frame)
                    time.sleep(0.1)
                out.release()
            _recording["active"] = False
            logger.info(f"[API] 錄影完成：{req.save_path}")

        t = _th.Thread(target=_do_record, daemon=True)
        _recording["thread"] = t
        t.start()
        return {"ok": True, "save_path": req.save_path, "duration": req.duration}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/record/stop")
def record_stop():
    """停止錄製"""
    _recording["active"] = False
    return {"ok": True}

@app.get("/record/status")
def record_status():
    return {"active": _recording["active"]}
