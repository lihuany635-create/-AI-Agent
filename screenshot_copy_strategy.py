# screenshot_copy_strategy.py
import mss
import cv2
import numpy as np
import time
import logging
import requests as _pc_req
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# ── PC API helper（優先走 API，失敗 fallback pyautogui/pyperclip）──────────────

def _pc_available():
    try:
        return _pc_req.get("http://localhost:8899/health", timeout=2).status_code == 200
    except Exception:
        return False

def _click(x, y):
    if _pc_available():
        _pc_req.post("http://localhost:8899/mouse/click", json={"x": x, "y": y}, timeout=5)
    else:
        import pyautogui
        pyautogui.click(x, y)

def _hotkey(*keys):
    if _pc_available():
        _pc_req.post("http://localhost:8899/keyboard/hotkey", json={"keys": list(keys)}, timeout=5)
    else:
        import pyautogui
        pyautogui.hotkey(*keys)

def _copy_text(text):
    if _pc_available():
        _pc_req.post("http://localhost:8899/system/clipboard", json={"text": text}, timeout=5)
    else:
        import pyperclip
        pyperclip.copy(text)

def _paste_text() -> str:
    if _pc_available():
        r = _pc_req.get("http://localhost:8899/system/clipboard", timeout=5)
        return r.json().get("text", "")
    else:
        import pyperclip
        return pyperclip.paste()

def _screen_size() -> tuple:
    if _pc_available():
        r = _pc_req.get("http://localhost:8899/screen/size", timeout=5)
        return r.json().get("width", 1920), r.json().get("height", 1080)
    else:
        import pyautogui
        return pyautogui.size()

SCREENSHOT_SAVE_DIR         = Path("logs/screenshots")
CONTENT_CLICK_X_RATIO       = 0.55
CONTENT_CLICK_Y_RATIO       = 0.50

# artifact 偵測：偵測右側區域是否有深色背景（程式碼側邊欄）
# Claude.ai artifact 側邊欄出現在畫面右側約 75%~100%
ARTIFACT_DETECT_X_START     = 0.75   # 從畫面 75% 寬開始偵測
ARTIFACT_COLOR_LOWER        = np.array([0, 0, 0])    # HSV 深色下限
ARTIFACT_COLOR_UPPER        = np.array([180, 30, 45]) # HSV 深色上限（亮度<45）
ARTIFACT_DARK_RATIO_THRESH  = 0.30   # 右側深色像素超過 30% → 有 artifact
SCREENSHOT_CONFIRM_COUNT    = 3
SCREENSHOT_CONFIRM_INTERVAL = 4
SCREENSHOT_PRE_DELAY        = 3


def take_screenshot(save: bool = True) -> tuple:
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        img = np.array(raw)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    saved_path = None
    if save and SCREENSHOT_SAVE_DIR:
        SCREENSHOT_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = SCREENSHOT_SAVE_DIR / f"screenshot_{ts}.png"
        cv2.imwrite(str(saved_path), img)
        logger.info(f"[截圖] 已儲存：{saved_path}")
    return img, saved_path


def delete_screenshots(paths: list):
    for p in paths:
        if p and Path(p).exists():
            try:
                Path(p).unlink()
                logger.info(f"[截圖] 已刪除：{p}")
            except Exception as e:
                logger.warning(f"[截圖] 刪除失敗：{p}，原因：{e}")


def confirm_screen_stable(count=SCREENSHOT_CONFIRM_COUNT,
                           interval=SCREENSHOT_CONFIRM_INTERVAL) -> tuple:
    """
    每隔 interval 秒截圖一次，共 count 次。
    回傳 (第一張, 最後一張, 所有截圖路徑)，用於比較前後差異。
    """
    saved_paths = []
    imgs = []
    for i in range(count):
        logger.info(f"[截圖確認] 第 {i+1}/{count} 次確認...")
        img, path = take_screenshot(save=True)
        if path:
            saved_paths.append(path)
        imgs.append(img)
        if i < count - 1:
            logger.info(f"[截圖確認] 等待 {interval} 秒後進行下一次確認...")
            time.sleep(interval)
    logger.info(f"[截圖確認] {count} 次確認完畢")
    return imgs[0], imgs[-1], saved_paths


def has_artifact(img_before: np.ndarray, img_after: np.ndarray) -> bool:
    """
    比較兩張截圖的右側區域差異，判斷 artifact 側邊欄是否出現。
    artifact 出現時右側會多一個欄位，像素差異會很大。
    """
    h, w = img_before.shape[:2]
    x_start = int(w * ARTIFACT_DETECT_X_START)

    right_before = img_before[:, x_start:].astype(np.int16)
    right_after  = img_after[:, x_start:].astype(np.int16)

    diff = np.abs(right_after - right_before)
    # 差異超過 30 的像素比例
    changed_ratio = np.sum(diff.max(axis=2) > 30) / (right_before.shape[0] * right_before.shape[1])

    logger.info(f"[artifact偵測] 右側畫面變化比例：{changed_ratio:.2%}（門檻：{ARTIFACT_DARK_RATIO_THRESH:.0%}）")
    return changed_ratio > ARTIFACT_DARK_RATIO_THRESH


def is_sidebar_expanded(img: np.ndarray, img_after: np.ndarray = None) -> bool:
    """保留舊名稱相容"""
    if img_after is None:
        return False
    return has_artifact(img, img_after)


def copy_with_ctrl_a() -> str:
    logger.info("[複製策略] 使用 Ctrl+A 全選複製")
    _copy_text("")
    screen_w, screen_h = _screen_size()
    click_x = int(screen_w * CONTENT_CLICK_X_RATIO)
    click_y = int(screen_h * CONTENT_CLICK_Y_RATIO)
    logger.info(f"[複製策略] 點擊取焦：({click_x}, {click_y})")
    _click(click_x, click_y)
    time.sleep(5.3)
    _hotkey("ctrl", "a")
    time.sleep(5.3)
    _hotkey("ctrl", "c")
    time.sleep(5.3)
    result = _paste_text()
    logger.info(f"[複製結果] 取得文字長度：{len(result)}")
    return result


def copy_with_mouse_position(img: np.ndarray) -> str:
    h, w = img.shape[:2]
    click_x = int(w * CONTENT_CLICK_X_RATIO)
    click_y = int(h * CONTENT_CLICK_Y_RATIO)
    logger.info(f"[複製策略] 使用滑鼠位置複製，點擊座標：({click_x}, {click_y})")
    _click(click_x, click_y)
    time.sleep(5.3)
    _hotkey("ctrl", "a")
    time.sleep(5.3)
    _hotkey("ctrl", "c")
    time.sleep(5.3)
    result = _paste_text()
    logger.info(f"[複製結果] 取得文字長度：{len(result)}")
    return result


def smart_copy_after_model_selected(save_screenshot: bool = True) -> str:
    logger.info("=" * 50)
    logger.info("[smart_copy] 開始截圖判斷流程")

    # 1. 截圖前等待 3 秒
    logger.info(f"[smart_copy] 等待 {SCREENSHOT_PRE_DELAY} 秒後開始截圖...")
    time.sleep(SCREENSHOT_PRE_DELAY)

    # 2. 每 4 秒確認一次，共 3 次（保留第一張和最後一張比較）
    first_img, last_img, saved_paths = confirm_screen_stable()

    # 3. 比較第一張和最後一張，判斷右側是否多出 artifact 欄位
    artifact_present = has_artifact(first_img, last_img)

    # 4. 複製
    if artifact_present:
        logger.info("[smart_copy] 偵測到 artifact（右側出現新欄位）→ 滑鼠點擊複製")
        content = copy_with_mouse_position(last_img)
    else:
        logger.info("[smart_copy] 無 artifact → 使用 Ctrl+A 複製純文字")
        content = copy_with_ctrl_a()

    logger.info(f"[smart_copy] 複製完成，內容前 100 字：{content[:100]!r}")

    # 5. 刪除截圖
    logger.info("[smart_copy] 進入下一階段，刪除截圖檔案...")
    delete_screenshots(saved_paths)

    logger.info("=" * 50)
    return content


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    result = smart_copy_after_model_selected()
    print("\n====== 複製結果 ======")
    print(result[:500] if result else "（空白）")
