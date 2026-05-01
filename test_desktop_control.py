# test_desktop_control.py — 桌面控制完整測試
# 執行：python test_desktop_control.py

import sys
sys.path.insert(0, r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages")

results = []

def test(name, fn):
    try:
        result = fn()
        status = "OK"
        print(f"  [OK] {name}: {str(result)[:60]}")
    except Exception as e:
        status = "FAIL"
        result = str(e)
        print(f"  [FAIL] {name}: {e}")
    results.append((status, name, result))

print("=" * 55)
print("桌面控制完整測試")
print("=" * 55)

# 1. 套件檢查
print("\n【套件】")
test("pyautogui",    lambda: __import__("pyautogui").size())
test("pygetwindow",  lambda: len(__import__("pygetwindow").getAllWindows()))
test("PIL",          lambda: __import__("PIL.ImageGrab", fromlist=["ImageGrab"]))
test("pytesseract",  lambda: __import__("pytesseract"))
test("win32gui",     lambda: __import__("win32gui"))
test("cv2",          lambda: __import__("cv2").__version__)

# 2. 截圖
print("\n【截圖】")
def do_screenshot():
    from PIL import ImageGrab
    img = ImageGrab.grab()
    return f"{img.size[0]}x{img.size[1]}"
test("截圖", do_screenshot)

# 3. OCR
print("\n【OCR】")
def do_ocr():
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    from PIL import ImageGrab
    img = ImageGrab.grab()
    text = pytesseract.image_to_string(img, lang="chi_tra+eng")
    return f"辨識 {len(text)} 字"
test("OCR", do_ocr)

# 4. 滑鼠
print("\n【滑鼠】")
test("取得位置", lambda: str(__import__("pyautogui").position()))
test("取得螢幕大小", lambda: str(__import__("pyautogui").size()))

# 5. 視窗管理
print("\n【視窗管理】")
def list_wins():
    import pygetwindow as gw
    wins = [w.title for w in gw.getAllWindows() if w.title.strip()]
    return f"{len(wins)} 個視窗"
test("列出視窗", list_wins)

def get_active():
    import pygetwindow as gw
    win = gw.getActiveWindow()
    return win.title if win else "無"
test("目前視窗", get_active)

# 6. 鍵盤
print("\n【鍵盤】")
test("keyboard import", lambda: __import__("pyautogui").hotkey)

# 7. desktop_control 模組
print("\n【desktop_control 模組】")
def test_module():
    from desktop_control import get_control
    c = get_control()
    return f"PIL:{c._HAS_PIL if hasattr(c,'_HAS_PIL') else '?'} GW:{c._HAS_GW if hasattr(c,'_HAS_GW') else '?'}"

import desktop_control as _dc
test("_HAS_PIL",       lambda: str(_dc._HAS_PIL))
test("_HAS_GW",        lambda: str(_dc._HAS_GW))
test("_HAS_PYAUTOGUI", lambda: str(_dc._HAS_PYAUTOGUI))
test("_HAS_OCR",       lambda: str(_dc._HAS_OCR))
test("screenshot()",   lambda: _dc.get_control().screenshot())
test("list_windows()", lambda: _dc.get_control().list_windows()[:50])
test("get_screen_size()", lambda: _dc.get_control().get_screen_size())
test("get_mouse_pos()",   lambda: _dc.get_control().get_mouse_pos())

# 總結
print("\n" + "=" * 55)
ok   = sum(1 for r in results if r[0] == "OK")
fail = sum(1 for r in results if r[0] == "FAIL")
print(f"結果：{ok} 通過，{fail} 失敗")

if fail:
    print("\n失敗項目：")
    for r in results:
        if r[0] == "FAIL":
            print(f"  - {r[1]}: {r[2][:80]}")
else:
    print("所有功能正常！立可以完全控制您的電腦桌面。")
print("=" * 55)
