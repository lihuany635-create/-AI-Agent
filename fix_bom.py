"""
fix_bom.py - 自動修復所有 BOM 字元錯誤
使用方式：把這個檔案放到您的 AI-Agent 專案資料夾，然後執行：
    python fix_bom.py
"""

import pathlib
import sys

# 需要修復的檔案清單
BOM_FILES = [
    "agent_basic.py",
    "config.py",
    "desktop_agent.py",
    "repair_test_runner_fixed.py",
]

def fix_bom(filepath: str) -> bool:
    p = pathlib.Path(filepath)
    if not p.exists():
        print(f"  [略過] 找不到檔案：{filepath}")
        return False
    try:
        original = p.read_bytes()
        if original[:3] == b'\xef\xbb\xbf':
            p.write_bytes(original[3:])
            print(f"  [✓] 已修復：{filepath}")
            return True
        else:
            print(f"  [OK] 無需修復：{filepath}")
            return False
    except Exception as e:
        print(f"  [✗] 修復失敗：{filepath}，原因：{e}")
        return False

if __name__ == "__main__":
    print("=== BOM 字元修復工具 ===\n")
    fixed = 0
    for f in BOM_FILES:
        if fix_bom(f):
            fixed += 1
    print(f"\n完成！共修復 {fixed} 個檔案。")
    if fixed > 0:
        print("請重新執行 master_run.py 測試是否正常啟動。")
