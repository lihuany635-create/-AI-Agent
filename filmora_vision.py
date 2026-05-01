"""
filmora_vision.py
螢幕辨識模組：截圖 → 分析 Filmora 當前狀態 → 回報給立 AI。
"""

import base64
import time
from pathlib import Path
from typing import Optional

import pyautogui
import requests
from PIL import Image
import io

OLLAMA_URL   = "http://localhost:11434"
VISION_MODEL = "llava:7b"   # 支援圖片的 model
SCREENSHOT_DIR = Path("filmora_screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# ── 截圖工具 ──────────────────────────────────────────────────────────────────

def screenshot_full() -> Image.Image:
    """截取全螢幕。"""
    return pyautogui.screenshot()


def screenshot_filmora() -> Optional[Image.Image]:
    """只截取 Filmora 視窗。"""
    try:
        import pygetwindow as gw
        wins = gw.getWindowsWithTitle("Filmora")
        if not wins:
            return screenshot_full()
        win = wins[0]
        region = (win.left, win.top, win.width, win.height)
        return pyautogui.screenshot(region=region)
    except Exception:
        return screenshot_full()


def save_screenshot(img: Image.Image, name: str = "") -> Path:
    """儲存截圖並回傳路徑。"""
    ts = int(time.time())
    fname = f"{name}_{ts}.png" if name else f"shot_{ts}.png"
    path = SCREENSHOT_DIR / fname
    img.save(path)
    return path


def img_to_base64(img: Image.Image) -> str:
    """將 PIL Image 轉為 base64 字串。"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ── 視覺分析 ──────────────────────────────────────────────────────────────────

def analyze_screen(question: str = "描述目前 Filmora 的狀態") -> str:
    """
    截圖後用 llava 分析螢幕狀態。
    question: 要問的問題
    """
    img = screenshot_filmora()
    if not img:
        return "無法截圖"

    b64 = img_to_base64(img)

    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": f"這是 Wondershare Filmora 14 的截圖。{question}請用繁體中文回答。",
                "images": [b64],
            }],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 300},
        }, timeout=None)
        return r.json().get("message", {}).get("content", "無回應").strip()
    except Exception as e:
        return f"分析失敗：{e}"


def check_dialog() -> Optional[str]:
    """偵測是否有對話框出現（確認/錯誤框）。"""
    return analyze_screen("畫面上有沒有彈出對話框、確認框或錯誤訊息？如果有，說明內容。")


def get_timeline_status() -> str:
    """取得時間軸當前狀態。"""
    return analyze_screen("時間軸上有幾個片段？目前播放頭在哪個位置？")


def verify_action(action_desc: str) -> bool:
    """
    驗證操作是否成功。
    action_desc: 剛執行的操作描述
    """
    result = analyze_screen(f"請確認以下操作是否已成功執行：{action_desc}。回答「成功」或「失敗」，並說明原因。")
    print(f"  📸 驗證：{result[:100]}")
    return "成功" in result


# ── 元素定位 ──────────────────────────────────────────────────────────────────

def find_button(button_name: str) -> Optional[tuple]:
    """
    在螢幕上找到指定按鈕的位置。
    先用 pyautogui.locateOnScreen，找不到再用 llava 問。
    回傳 (x, y) 或 None。
    """
    # 方法一：用圖片比對（需要預先截取按鈕圖片）
    btn_img = Path(f"filmora_ui/{button_name}.png")
    if btn_img.exists():
        loc = pyautogui.locateOnScreen(str(btn_img), confidence=0.8)
        if loc:
            return pyautogui.center(loc)

    # 方法二：用 llava 問位置
    result = analyze_screen(
        f"「{button_name}」按鈕或選項在哪裡？"
        f"請描述它在畫面的哪個區域（左上/右上/中間/左下/右下），以及大概的位置比例（如：左側25%，上方80%）。"
    )
    print(f"  🔍 找按鈕「{button_name}」：{result[:80]}")
    return None   # 需要人工確認或進一步解析


def capture_ui_elements():
    """
    截圖並識別所有可見的 UI 元素。
    """
    return analyze_screen(
        "列出畫面中所有可見的按鈕、選單、工具列。"
        "格式：「元素名稱：位置描述」，每行一個。"
    )


# ── 狀態監控 ──────────────────────────────────────────────────────────────────

class FilmoraMonitor:
    """持續監控 Filmora 狀態的類別。"""

    def __init__(self, interval: float = 5.0):
        self.interval  = interval
        self._running  = False
        self._last_state = ""

    def start(self, callback=None):
        """開始監控，狀態改變時呼叫 callback。"""
        import threading
        self._running = True

        def _loop():
            while self._running:
                state = analyze_screen("Filmora 目前的狀態是什麼？有沒有錯誤或需要處理的對話框？")
                if state != self._last_state:
                    self._last_state = state
                    if callback:
                        callback(state)
                time.sleep(self.interval)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        print(f"📡 開始監控 Filmora（每 {self.interval} 秒）")

    def stop(self):
        self._running = False
        print("📡 停止監控")


# ── 快速測試 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔍 分析 Filmora 當前狀態...")
    status = analyze_screen("Filmora 目前顯示什麼？時間軸上有素材嗎？")
    print(f"\n狀態：{status}")

    print("\n🔍 列出 UI 元素...")
    elements = capture_ui_elements()
    print(f"\nUI 元素：{elements}")
