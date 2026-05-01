# desktop_control.py — 桌面控制引擎
# 功能：截圖、OCR、滑鼠鍵盤控制、視窗管理、畫面監控
# 使用方式：在對話框輸入自然語言指令

import subprocess
import pathlib
import datetime
import time
import threading
import re
from typing import Optional

try:
    from agent_logger import get_logger
    logger = get_logger("desktop_control")
except ImportError:
    import logging
    logger = logging.getLogger("desktop_control")

# ── 套件載入 ──────────────────────────────────────────────────────────────────
import sys as _sys, site as _site
_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
# 強制加入所有可能的路徑
for _p in [_PKG, _site.getusersitepackages()]:
    if _p and _p not in _sys.path:
        _sys.path.insert(0, _p)

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.3
    _HAS_PYAUTOGUI = True
except Exception:
    try:
        _sys.path.insert(0, _PKG)
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3
        _HAS_PYAUTOGUI = True
    except Exception:
        _HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    _HAS_GW = True
except Exception:
    try:
        _sys.path.insert(0, _PKG)
        import pygetwindow as gw
        _HAS_GW = True
    except Exception:
        _HAS_GW = False

def _try_import_pil():
    for _p in [_PKG, None]:
        try:
            if _p and _p not in _sys.path:
                _sys.path.insert(0, _p)
            from PIL import Image, ImageGrab
            return True
        except Exception:
            continue
    return False

_HAS_PIL = _try_import_pil()
try:
    from PIL import Image, ImageGrab
except Exception:
    pass

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False

try:
    import cv2
    import numpy as np
    _HAS_CV = True
except ImportError:
    _HAS_CV = False

SCREENSHOT_DIR = pathlib.Path("memory/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class DesktopControl:
    """
    桌面控制引擎
    支援：截圖、OCR、滑鼠、鍵盤、視窗管理、畫面監控
    """

    def __init__(self):
        self._monitor_thread = None
        self._monitor_running = False
        self._last_screenshot = None

    # ── 主入口：自然語言指令 ──────────────────────────────────────────────────

    def handle(self, text: str) -> Optional[str]:
        """
        解析自然語言桌面控制指令
        回傳結果，或 None（不是桌面控制指令）
        """
        t = text.strip()

        # 截圖
        if any(k in t for k in ["截圖", "截取畫面", "screenshot", "拍照", "拍螢幕"]):
            return self.screenshot()

        # 系統資訊
        if any(k in t for k in ["螢幕大小", "解析度", "滑鼠位置"]):
            if "滑鼠" in t:
                return self.get_mouse_pos()
            return self.get_screen_size()

        # OCR 讀取畫面文字
        if any(k in t for k in ["讀取畫面", "畫面文字", "ocr", "OCR", "螢幕文字"]):
            return self.ocr_screen()

        # 點擊
        m = re.search(r"點擊(.+)", t)
        if m:
            return self.click_text(m.group(1).strip())

        # 輸入文字
        m = re.search(r"輸入[「""](.+)[」""]", t)
        if m:
            return self.type_text(m.group(1))

        # 按鍵
        m = re.search(r"按(下|鍵|住)?\s*(.+)", t)
        if m and any(k in t for k in ["按下", "按鍵", "快捷鍵", "Enter", "Ctrl", "Alt"]):
            return self.press_key(m.group(2).strip())

        # 視窗管理
        if "開啟視窗" in t or "切換到" in t or "最大化" in t or "最小化" in t or "關閉視窗" in t:
            return self.manage_window(t)

        # 列出所有視窗
        if any(k in t for k in ["列出視窗", "所有視窗", "開啟中的視窗"]):
            return self.list_windows()

        # 滑鼠移動
        m = re.search(r"移動滑鼠.*?(\d+).*?(\d+)", t)
        if m:
            return self.move_mouse(int(m.group(1)), int(m.group(2)))

        # 開始監控
        if any(k in t for k in ["監控畫面", "畫面監控", "開始監控", "啟動監控", "螢幕監控"]):
            return self.start_monitor()

        # 停止監控
        if any(k in t for k in ["停止監控", "關閉監控", "結束監控", "停止畫面監控", "監控停止", "不要監控"]):
            return self.stop_monitor()

        # 監控狀態
        if any(k in t for k in ["監控狀態", "監控中嗎", "有在監控"]):
            status = "監控中" if self._monitor_running else "未監控"
            return f"目前狀態：{status}"

        # 螢幕資訊
        if any(k in t for k in ["螢幕大小", "解析度", "畫面大小"]):
            return self.get_screen_size()

        # 滑鼠位置
        if any(k in t for k in ["滑鼠在哪", "滑鼠位置", "游標位置"]):
            return self.get_mouse_pos()

        # ── 開網頁 / 網址 ────────────────────────────────────────
        url_match = re.search(r'(開啟?|打開|open)\s*(https?://\S+)', t)
        if url_match:
            return self.open_url(url_match.group(2))
        if any(k in t for k in ["開網頁", "開瀏覽器", "開chrome", "開 chrome"]):
            url_match2 = re.search(r'https?://\S+', t)
            if url_match2:
                return self.open_url(url_match2.group(0))
            return self.open_url("https://www.google.com")
        # 搜尋
        search_match = re.search(r'(搜尋|google|查)\s+(.+)', t, re.IGNORECASE)
        if search_match and any(k in t for k in ["搜尋", "google", "查一下"]):
            query = search_match.group(2).strip()
            return self.open_url(f"https://www.google.com/search?q={query}")

        # ── 文件管理 ─────────────────────────────────────────────
        # 複製檔案
        copy_match = re.search(r'(複製|copy)\s+(.+?)\s+(到|to)\s+(.+)', t, re.IGNORECASE)
        if copy_match:
            return self.copy_file(copy_match.group(2).strip(), copy_match.group(4).strip())
        # 移動檔案
        move_match = re.search(r'(移動|move|搬)\s+(.+?)\s+(到|to)\s+(.+)', t, re.IGNORECASE)
        if move_match:
            return self.move_file(move_match.group(2).strip(), move_match.group(4).strip())
        # 刪除檔案
        del_match = re.search(r'(刪除|delete|移除)\s+(.+)', t, re.IGNORECASE)
        if del_match and any(k in t for k in ["刪除", "delete", "移除"]):
            return self.delete_file(del_match.group(2).strip())
        # 查看資料夾
        dir_match = re.search(r'(查看|列出|顯示)\s*(.+)?(資料夾|目錄|folder)', t)
        if dir_match:
            folder = dir_match.group(2).strip() if dir_match.group(2) else "."
            return self.list_folder(folder)

        # ── 系統控制 ─────────────────────────────────────────────
        if any(k in t for k in ["音量", "聲音"]):
            vol_match = re.search(r'(\d+)', t)
            if "靜音" in t or "mute" in t.lower():
                return self.set_volume(0)
            if "大聲" in t or "調高" in t or "增加" in t:
                return self.adjust_volume(10)
            if "小聲" in t or "調低" in t or "減少" in t:
                return self.adjust_volume(-10)
            if vol_match:
                return self.set_volume(int(vol_match.group(1)))
            return self.get_volume()

        # ── 排程任務 ─────────────────────────────────────────────
        sched_match = re.search(r'(\d+)\s*(分鐘|秒|小時|min|sec|hour)後\s*(執行|跑|run)\s+(.+)', t)
        if sched_match:
            amount = int(sched_match.group(1))
            unit = sched_match.group(2)
            cmd = sched_match.group(4).strip()
            return self.schedule_task(amount, unit, cmd)
        if any(k in t for k in ["定時", "排程", "schedule"]):
            sched_match2 = re.search(r'(定時|排程|schedule)\s+(.+)', t)
            if sched_match2:
                return self.schedule_task_parse(sched_match2.group(2).strip())

        # ── 開啟檔案 / 編輯 ──────────────────────────────────────
        edit_match = re.search(r'(開啟|打開|編輯|edit|open)\s+(.+\.\w+)', t, re.IGNORECASE)
        if edit_match:
            return self.open_file(edit_match.group(2).strip())

        return None

    # ── 截圖 ──────────────────────────────────────────────────────────────────

    def _fix_pil(self):
        """確保載入正確的 PIL"""
        import sys
        _p = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
        if _p not in sys.path:
            sys.path.insert(0, _p)
        # 清除舊的 PIL 快取，重新載入
        for key in list(sys.modules.keys()):
            if key == "PIL" or key.startswith("PIL."):
                del sys.modules[key]
        sys.path.insert(0, _p)

    def screenshot(self, save: bool = True) -> str:
        try:
            import mss, mss.tools
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = SCREENSHOT_DIR / f"screenshot_{ts}.png"
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                img = sct.grab(monitor)
                if save:
                    mss.tools.to_png(img.rgb, img.size, output=str(path))
                self._last_screenshot_mss = img
                w, h = img.size
            logger.info(f"[桌面控制] 截圖完成：{path.name} ({w}x{h})")
            return f"截圖完成：{path}\n解析度：{w}x{h}"
        except Exception as e:
            return f"❌ 截圖失敗：{e}"

    # ── OCR 文字辨識 ──────────────────────────────────────────────────────────

    def ocr_screen(self, lang: str = "chi_tra+eng") -> str:
        try:
            import mss, mss.tools, pytesseract
            from PIL import Image
            import io
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        except Exception as e:
            return f"❌ 缺少套件：{e}"
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                img_mss = sct.grab(monitor)
                # mss -> PIL Image
                img_pil = Image.frombytes("RGB", img_mss.size, img_mss.bgra, "raw", "BGRX")
            text = pytesseract.image_to_string(img_pil, lang=lang)
            text = text.strip()
            if not text:
                return "畫面上沒有偵測到文字"
            logger.info(f"[桌面控制] OCR 完成，辨識 {len(text)} 字")
            if len(text) > 1000:
                text = text[:1000] + "\n...（已截斷）"
            return f"畫面文字：\n{text}"
        except Exception as e:
            return f"❌ OCR 失敗：{e}"

    def ocr_find_text(self, target: str) -> Optional[tuple]:
        """在畫面上找到指定文字的位置，回傳 (x, y) 或 None"""
        if not _HAS_OCR or not _HAS_PIL:
            return None
        try:
            img = ImageGrab.grab()
            data = pytesseract.image_to_data(img, lang="chi_tra+eng",
                                              output_type=pytesseract.Output.DICT)
            for i, word in enumerate(data["text"]):
                if target in word and int(data["conf"][i]) > 30:
                    x = data["left"][i] + data["width"][i] // 2
                    y = data["top"][i] + data["height"][i] // 2
                    return (x, y)
        except Exception:
            pass
        return None

    # ── 滑鼠控制 ──────────────────────────────────────────────────────────────

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> str:
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui"
        try:
            pyautogui.click(x, y, button=button, clicks=clicks, interval=0.2)
            logger.info(f"[桌面控制] 點擊 ({x}, {y})")
            return f"已點擊 ({x}, {y})"
        except Exception as e:
            return f"❌ 點擊失敗：{e}"

    def click_text(self, target: str) -> str:
        """在畫面上找到文字並點擊"""
        pos = self.ocr_find_text(target)
        if pos:
            return self.click(pos[0], pos[1])
        # 找不到文字，嘗試用 pyautogui 圖片比對
        return f"❌ 找不到「{target}」，請確認文字是否在畫面上"

    def move_mouse(self, x: int, y: int, duration: float = 0.5) -> str:
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui"
        try:
            pyautogui.moveTo(x, y, duration=duration)
            return f"滑鼠已移動到 ({x}, {y})"
        except Exception as e:
            return f"❌ 移動失敗：{e}"

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui"
        try:
            pyautogui.moveTo(x1, y1, duration=0.3)
            pyautogui.dragTo(x2, y2, duration=duration, button="left")
            return f"已拖曳 ({x1},{y1}) → ({x2},{y2})"
        except Exception as e:
            return f"❌ 拖曳失敗：{e}"

    def scroll(self, clicks: int = 3, direction: str = "down") -> str:
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui"
        try:
            amount = -clicks if direction == "down" else clicks
            pyautogui.scroll(amount)
            return f"已向{direction}滾動 {clicks} 格"
        except Exception as e:
            return f"❌ 滾動失敗：{e}"

    # ── 鍵盤控制 ──────────────────────────────────────────────────────────────

    def type_text(self, text: str, interval: float = 0.05) -> str:
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui"
        try:
            pyautogui.write(text, interval=interval)
            logger.info(f"[桌面控制] 輸入文字：{text[:30]}")
            return f"已輸入：{text[:50]}"
        except Exception as e:
            # 中文需要用剪貼簿
            return self.type_chinese(text)

    def type_chinese(self, text: str) -> str:
        """用剪貼簿輸入中文"""
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            pyautogui.hotkey("ctrl", "v")
            return f"已輸入（剪貼簿）：{text[:50]}"
        except Exception as e:
            return f"❌ 中文輸入失敗：{e}"

    def press_key(self, key: str) -> str:
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui"
        try:
            # 組合鍵處理（Ctrl+C, Alt+F4 等）
            if "+" in key:
                keys = [k.strip().lower() for k in key.split("+")]
                pyautogui.hotkey(*keys)
                return f"已按下組合鍵：{key}"
            else:
                pyautogui.press(key.lower())
                return f"已按下：{key}"
        except Exception as e:
            return f"❌ 按鍵失敗：{e}"

    # ── 視窗管理 ──────────────────────────────────────────────────────────────

    def list_windows(self) -> str:
        try:
            import sys
            _p = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
            if _p not in sys.path:
                sys.path.insert(0, _p)
            import pygetwindow as gw
        except Exception as e:
            return f"❌ 需要安裝 pygetwindow：{e}"
        try:
            windows = [w for w in gw.getAllWindows() if w.title.strip()]
            if not windows:
                return "找不到任何視窗"
            lines = [f"目前開啟的視窗（{len(windows)} 個）："]
            for i, w in enumerate(windows[:15], 1):
                lines.append(f"{i}. {w.title[:50]}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ 列出視窗失敗：{e}"

    def manage_window(self, text: str) -> str:
        if not _HAS_GW:
            return "❌ 需要安裝 pygetwindow"
        try:
            # 切換到指定視窗
            m = re.search(r"切換到\s*(.+)", text)
            if m:
                target = m.group(1).strip()
                wins = gw.getWindowsWithTitle(target)
                if wins:
                    win = wins[0]
                    try:
                        # 先還原（如果最小化）
                        if win.isMinimized:
                            win.restore()
                            time.sleep(0.3)
                        # 用 win32 強制切換
                        import win32gui, win32con
                        hwnd = win.getHandle() if hasattr(win, 'getHandle') else win._hWnd
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                        return f"已切換到：{win.title}"
                    except Exception:
                        win.activate()
                        return f"已切換到：{win.title}"
                return f"找不到視窗：{target}"

            # 最大化
            if "最大化" in text:
                m2 = re.search(r"最大化\s*(.+)", text)
                title = m2.group(1).strip() if m2 else None
                wins = gw.getWindowsWithTitle(title) if title else [gw.getActiveWindow()]
                if wins:
                    wins[0].maximize()
                    return f"已最大化：{wins[0].title}"

            # 最小化
            if "最小化" in text:
                win = gw.getActiveWindow()
                if win:
                    win.minimize()
                    return f"已最小化：{win.title}"

            # 關閉視窗
            if "關閉視窗" in text:
                win = gw.getActiveWindow()
                if win:
                    win.close()
                    return f"已關閉：{win.title}"

            return "無法識別視窗操作"
        except Exception as e:
            return f"❌ 視窗操作失敗：{e}"

    def get_active_window(self) -> str:
        if not _HAS_GW:
            return "❌ 需要安裝 pygetwindow"
        try:
            win = gw.getActiveWindow()
            if win:
                return f"目前視窗：{win.title}（{win.width}x{win.height}）"
            return "沒有活動視窗"
        except Exception as e:
            return f"❌ 失敗：{e}"

    # ── 畫面監控 ──────────────────────────────────────────────────────────────

    def start_monitor(self, interval: float = 3.0, callback=None) -> str:
        if self._monitor_running:
            return "監控已在執行中"
        try:
            import mss
        except Exception as e:
            return f"❌ 需要安裝 mss：pip install mss"

        # 預設通知函式：寫入 queue 讓桌面顯示
        if callback is None:
            def callback(msg):
                try:
                    import json, pathlib as pl, datetime
                    qf = pl.Path("memory/mobile_queue.json")
                    qf.parent.mkdir(exist_ok=True)
                    q = []
                    if qf.exists():
                        try: q = json.loads(qf.read_text(encoding="utf-8"))
                        except: q = []
                    q.append({"time": datetime.datetime.now().strftime("%H:%M:%S"),
                              "user": "[監控]", "ai": msg})
                    q = q[-20:]
                    qf.write_text(json.dumps(q, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass

        self._monitor_running = True

        def _loop():
            prev_hash = None
            logger.info("[桌面控制] 畫面監控啟動")
            while self._monitor_running:
                try:
                    import mss
                    with mss.mss() as sct:
                        monitor = sct.monitors[0]
                        img = sct.grab(monitor)
                    curr_hash = hash(bytes(img.rgb[::100]))  # 取樣計算 hash
                    if prev_hash is not None and curr_hash != prev_hash:
                        logger.info("[桌面控制] 畫面內容變化偵測到")
                        # 截圖並嘗試 OCR 說明變化
                        try:
                            import pytesseract
                            from PIL import Image
                            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                            img_pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                            text = pytesseract.image_to_string(img_pil, lang="chi_tra+eng").strip()
                            text_short = text[:80] if text else "（無文字）"
                            msg = f"畫面變化偵測！畫面文字：{text_short}"
                        except Exception:
                            msg = "畫面內容發生變化"
                        if callback:
                            callback(msg)
                    prev_hash = curr_hash
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"[桌面控制] 監控錯誤：{e}")
                    time.sleep(interval)

        self._monitor_thread = threading.Thread(target=_loop, daemon=True)
        self._monitor_thread.start()
        return f"畫面監控已啟動（每 {interval} 秒檢查一次）"

    def stop_monitor(self) -> str:
        self._monitor_running = False
        return "畫面監控已停止"

    # ── 系統資訊 ──────────────────────────────────────────────────────────────

    def get_screen_size(self) -> str:
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui"
        size = pyautogui.size()
        return f"螢幕解析度：{size.width} x {size.height}"

    def get_mouse_pos(self) -> str:
        if not _HAS_PYAUTOGUI:
            return "need pyautogui"
        pos = pyautogui.position()
        return f"mouse: ({pos.x}, {pos.y})"

    # ── 開網頁 ────────────────────────────────────────────────────────────────

    def open_url(self, url: str) -> str:
        try:
            import webbrowser
            webbrowser.open(url)
            return f"opened: {url}"
        except Exception as e:
            return f"failed: {e}"

    # ── 文件管理 ──────────────────────────────────────────────────────────────

    def copy_file(self, src: str, dst: str) -> str:
        try:
            import shutil
            src_p = pathlib.Path(src)
            dst_p = pathlib.Path(dst)
            if not src_p.exists():
                return f"not found: {src}"
            if dst_p.is_dir():
                shutil.copy2(src_p, dst_p / src_p.name)
            else:
                shutil.copy2(src_p, dst_p)
            return f"copied: {src} -> {dst}"
        except Exception as e:
            return f"copy failed: {e}"

    def move_file(self, src: str, dst: str) -> str:
        try:
            import shutil
            src_p = pathlib.Path(src)
            if not src_p.exists():
                return f"not found: {src}"
            shutil.move(str(src_p), dst)
            return f"moved: {src} -> {dst}"
        except Exception as e:
            return f"move failed: {e}"

    def delete_file(self, path: str) -> str:
        try:
            p = pathlib.Path(path)
            if not p.exists():
                return f"not found: {path}"
            if p.is_dir():
                return f"that is a folder, use 'del /s {path}' in terminal"
            p.unlink()
            return f"deleted: {path}"
        except Exception as e:
            return f"delete failed: {e}"

    def list_folder(self, folder: str = ".") -> str:
        try:
            p = pathlib.Path(folder)
            if not p.exists():
                return f"not found: {folder}"
            items = sorted(p.iterdir())
            lines = [f"{folder} ({len(items)} items):"]
            for item in items[:30]:
                icon = "[D]" if item.is_dir() else "[F]"
                size = ""
                if item.is_file():
                    s = item.stat().st_size
                    if s > 1024*1024:
                        size = f" ({s//1024//1024}MB)"
                    elif s > 1024:
                        size = f" ({s//1024}KB)"
                lines.append(f"  {icon} {item.name}{size}")
            if len(items) > 30:
                lines.append(f"  ...({len(items)-30} more)")
            return "\n".join(lines)
        except Exception as e:
            return f"failed: {e}"

    # ── 系統控制 ──────────────────────────────────────────────────────────────

    def set_volume(self, level: int) -> str:
        try:
            # Windows: use nircmd or PowerShell
            level = max(0, min(100, level))
            # 用 PowerShell 設定音量
            ps_cmd = f'(New-Object -ComObject WScript.Shell).SendKeys([char]173)' if level == 0 else ''
            if level == 0:
                subprocess.run(['powershell', '-c',
                    '(New-Object -ComObject WScript.Shell).SendKeys([char]173)'],
                    capture_output=True, timeout=5)
                return "muted"
            # 用 nircmd（如果有的話）
            try:
                subprocess.run(['nircmd', 'setsysvolume', str(int(level/100*65535))],
                    capture_output=True, timeout=5)
                return f"volume: {level}%"
            except FileNotFoundError:
                # 沒有 nircmd，用按鍵模擬
                return f"cannot set volume (install nircmd for volume control)"
        except Exception as e:
            return f"failed: {e}"

    def adjust_volume(self, delta: int) -> str:
        try:
            if delta > 0:
                for _ in range(abs(delta) // 2):
                    subprocess.run(['powershell', '-c',
                        '(New-Object -ComObject WScript.Shell).SendKeys([char]175)'],
                        capture_output=True, timeout=5)
                return f"volume up"
            else:
                for _ in range(abs(delta) // 2):
                    subprocess.run(['powershell', '-c',
                        '(New-Object -ComObject WScript.Shell).SendKeys([char]174)'],
                        capture_output=True, timeout=5)
                return f"volume down"
        except Exception as e:
            return f"failed: {e}"

    def get_volume(self) -> str:
        return "use 'volume up' / 'volume down' / 'mute' to control"

    # ── 排程任務 ──────────────────────────────────────────────────────────────

    def schedule_task(self, amount: int, unit: str, cmd: str) -> str:
        unit_map = {"秒": 1, "sec": 1, "分鐘": 60, "min": 60, "小時": 3600, "hour": 3600}
        seconds = amount * unit_map.get(unit, 60)

        def _run():
            time.sleep(seconds)
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True,
                    text=True, timeout=60, encoding="utf-8", errors="ignore")
                logger.info(f"[schedule] done: {cmd} -> {result.returncode}")
            except Exception as e:
                logger.error(f"[schedule] failed: {cmd} -> {e}")

        threading.Thread(target=_run, daemon=True).start()
        return f"scheduled: '{cmd}' in {amount} {unit} ({seconds}s)"

    def schedule_task_parse(self, text: str) -> str:
        m = re.search(r'(\d+)\s*(分鐘|秒|小時|min|sec|hour)', text)
        cmd_m = re.search(r'(執行|跑|run)\s+(.+)', text)
        if m and cmd_m:
            return self.schedule_task(int(m.group(1)), m.group(2), cmd_m.group(2).strip())
        return "format: 10 分鐘後執行 python test.py"

    # ── 開啟/編輯檔案 ─────────────────────────────────────────────────────────

    def open_file(self, filepath: str) -> str:
        try:
            p = pathlib.Path(filepath)
            if not p.exists():
                return f"not found: {filepath}"
            import os
            os.startfile(str(p.resolve()))
            return f"opened: {filepath}"
        except Exception as e:
            return f"open failed: {e}"


# ── 模組層級單例 ──────────────────────────────────────────────────────────────
_ctrl: Optional[DesktopControl] = None

def get_control() -> DesktopControl:
    global _ctrl
    if _ctrl is None:
        _ctrl = DesktopControl()
    return _ctrl


if __name__ == "__main__":
    ctrl = DesktopControl()
    print(ctrl.get_screen_size())
    print(ctrl.get_active_window())
    print(ctrl.list_windows())
