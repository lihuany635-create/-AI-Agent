# cleanup.py — 清理垃圾檔案
# 執行：python cleanup.py

import pathlib, shutil

WORKSPACE = pathlib.Path(".")

# 要刪除的垃圾檔案
DELETE_FILES = [
    "error_detector.pyerror_detector.py",  # 雙重檔名垃圾
    "test_bug.py",      # 有語法錯誤的測試檔
    "broken.py",        # 有語法錯誤
    "syntax_error.py",  # 有語法錯誤
    "attribute_error.py",  # 測試用，不需要
    "import_error.py",     # 測試用
    "name_error.py",       # 測試用
    "type_error.py",       # 測試用
    "undefined_call.py",   # 測試用
    "zero_division.py",    # 測試用
]

deleted = []
skipped = []

for fname in DELETE_FILES:
    f = WORKSPACE / fname
    if f.exists():
        f.unlink()
        deleted.append(fname)
        print(f"已刪除：{fname}")
    else:
        skipped.append(fname)

print(f"\n完成！刪除 {len(deleted)} 個，跳過 {len(skipped)} 個")
