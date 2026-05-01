# check_desktop_control.py — 檢查桌面控制所需套件
# 執行：python check_desktop_control.py

import subprocess
import sys

packages = [
    ("pyautogui",    "滑鼠鍵盤控制"),
    ("pygetwindow",  "視窗管理"),
    ("pillow",       "截圖處理"),
    ("pytesseract",  "OCR 文字辨識"),
    ("opencv-python","影像分析"),
    ("pywin32",      "Windows API"),
]

print("=" * 50)
print("桌面控制套件檢查")
print("=" * 50)

missing = []
for pkg, desc in packages:
    try:
        __import__(pkg.replace("-", "_").split("-")[0])
        print(f"[OK] {pkg:20s} - {desc}")
    except ImportError:
        print(f"[缺少] {pkg:20s} - {desc}")
        missing.append(pkg)

print()
if missing:
    print(f"需要安裝 {len(missing)} 個套件，請執行：")
    print(f"pip install {' '.join(missing)}")
else:
    print("所有套件已安裝！")

# 特別檢查 Tesseract OCR（需要獨立安裝）
print()
print("檢查 Tesseract OCR 引擎...")
try:
    result = subprocess.run(["tesseract", "--version"],
        capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"[OK] Tesseract 已安裝：{result.stdout.splitlines()[0]}")
    else:
        print("[缺少] Tesseract 未安裝")
        print("   下載：https://github.com/UB-Mannheim/tesseract/wiki")
except Exception:
    print("[缺少] Tesseract 未安裝")
    print("   下載：https://github.com/UB-Mannheim/tesseract/wiki")
    print("   安裝後需要重啟電腦")
