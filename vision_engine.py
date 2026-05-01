# vision_engine.py — 立AI 視覺辨識模組
# 使用 llava:7b 本地視覺模型理解畫面內容
# 整合位置：在任何需要看懂畫面的地方呼叫

import base64
import json
import time
import pathlib
import requests
import logging
from datetime import datetime

try:
    from agent_logger import get_logger
    logger = get_logger("vision_engine")
except ImportError:
    logger = logging.getLogger("vision_engine")

# ── 設定 ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE   = "http://localhost:11434"
VISION_MODEL  = "llava:7b"
SCREENSHOT_DIR = pathlib.Path("logs/vision")
TIMEOUT        = 180


# ── 圖片處理 ──────────────────────────────────────────────────────────────────

def _img_to_base64(img_input) -> str:
    """
    接受：
    - 檔案路徑（str / Path）
    - numpy array（mss / cv2 截圖）
    - bytes
    回傳 base64 字串
    """
    import numpy as np

    if isinstance(img_input, (str, pathlib.Path)):
        with open(img_input, "rb") as f:
            return base64.b64encode(f.read()).decode()

    if isinstance(img_input, bytes):
        return base64.b64encode(img_input).decode()

    if isinstance(img_input, np.ndarray):
        import cv2
        _, buf = cv2.imencode(".png", img_input)
        return base64.b64encode(buf.tobytes()).decode()

    raise TypeError(f"不支援的圖片格式：{type(img_input)}")


def _save_screenshot(img) -> pathlib.Path:
    """儲存截圖到 logs/vision/"""
    import cv2
    import numpy as np
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOT_DIR / f"vision_{ts}.png"
    if isinstance(img, np.ndarray):
        cv2.imwrite(str(path), img)
    else:
        with open(path, "wb") as f:
            f.write(img if isinstance(img, bytes) else open(img, "rb").read())
    return path


# ── 截圖 ──────────────────────────────────────────────────────────────────────

def capture_screen(save: bool = False, scale: float = 0.5):
    """
    截取目前螢幕，回傳 numpy array。
    scale=0.5 代表縮到一半，減少 gemma4 處理時間。
    """
    import mss
    import numpy as np
    import cv2
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])
        img = cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)
    if scale != 1.0:
        h, w = img.shape[:2]
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
        logger.info(f"[Vision] 截圖縮放至 {img.shape[1]}x{img.shape[0]}")
    if save:
        _save_screenshot(img)
    return img


# ── 核心：問 gemma4 看圖 ───────────────────────────────────────────────────────

def ask_vision(img_input, question: str, save: bool = False) -> str:
    """
    傳入圖片 + 問題，讓 llava:7b 回答。

    參數：
        img_input  — 截圖 numpy array、檔案路徑、或 bytes
        question   — 你想問的問題
        save       — 是否儲存截圖

    回傳：llava:7b 的回答文字
    """
    try:
        b64 = _img_to_base64(img_input)
        if save:
            _save_screenshot(img_input)

        payload = {
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": question,
                    "images": [b64]
                }
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 512}
        }

        logger.info(f"[Vision] 問題：{question[:60]}")
        r = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json=payload,
            timeout=TIMEOUT
        )
        r.raise_for_status()
        result = r.json().get("message", {}).get("content", "").strip()
        logger.info(f"[Vision] 回答（{len(result)}字）：{result[:80]}")
        return result

    except Exception as e:
        logger.error(f"[Vision] 辨識失敗：{e}")
        return ""


# ── 常用功能封裝 ──────────────────────────────────────────────────────────────

def describe_screen() -> str:
    """截圖並描述目前畫面在做什麼"""
    img = capture_screen()
    return ask_vision(img, "請用繁體中文描述這個畫面上有什麼、正在發生什麼事。")


def find_element(element_desc: str) -> str:
    """截圖並找出指定 UI 元素的位置或狀態"""
    img = capture_screen()
    return ask_vision(
        img,
        f"請用繁體中文回答：畫面上有沒有「{element_desc}」？"
        f"如果有，它在畫面的哪個位置（左上、右上、中間等）？"
    )


def read_screen_text() -> str:
    """截圖並讀取畫面上的所有文字"""
    img = capture_screen()
    return ask_vision(img, "請把畫面上所有看得到的文字都列出來，用繁體中文回答。")


def understand_error() -> str:
    """截圖並解讀畫面上的錯誤訊息"""
    img = capture_screen()
    return ask_vision(
        img,
        "畫面上有沒有錯誤訊息或異常狀況？"
        "如果有，請用繁體中文說明是什麼錯誤、可能的原因。"
    )


def ask_screen(question: str) -> str:
    """截圖並用自訂問題詢問畫面"""
    img = capture_screen()
    return ask_vision(img, question)


# ── 對外簡單介面 ──────────────────────────────────────────────────────────────

def see(question: str = None) -> str:
    """
    最簡單的呼叫方式：
        from vision_engine import see
        see()                        # 描述畫面
        see("這個視窗是什麼程式？")   # 自訂問題
    """
    if question:
        return ask_screen(question)
    return describe_screen()


# ── 測試 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    print("=== 立AI 視覺辨識測試 ===")
    print("\n[1] 描述畫面：")
    print(describe_screen())
    print("\n[2] 讀取文字：")
    print(read_screen_text())
