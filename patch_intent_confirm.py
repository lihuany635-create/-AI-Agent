import pathlib, ast, shutil, datetime
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)
src = TARGET.read_text(encoding="utf-8", errors="replace")

# 在 process_input 最前面，加入意圖確認機制
# 只有在 dev 模式且明確包含 .py 檔名，才走 self_dev_engine
# 其他情況一律走 LLM 對話

old_healer = "        # 3. 自我診斷指令攔截"

new_healer = """        # 2.5 改程式模式：只有明確包含 .py 檔名才走 self_dev_engine
        # 避免「新增元素」「修改設計」等一般文字被誤判為開發需求
        if mode == "dev":
            import re as _re_dev
            _has_py = bool(_re_dev.search(r'\\w+\\.py', text))
            if not _has_py:
                # 沒有 .py 檔名，直接走 LLM 對話（不走 self_dev_engine）
                return self._think(text)

        # 3. 自我診斷指令攔截"""

if old_healer in src:
    src = src.replace(old_healer, new_healer)
    print("修補成功")
else:
    print("找不到插入點")

# 同時讓 self_dev_engine 的攔截只在有 .py 檔名時才觸發
old_dev_intercept = "        # 5. 自主開發指令攔截（只在 dev 模式，或明確包含 .py 檔名）"
if old_dev_intercept in src:
    # 已有之前的 patch，更新它
    old_block = """        # 5. 自主開發指令攔截（只在 dev 模式，或明確包含 .py 檔名）
        import re as _re2
        _is_dev_mode = (mode == "dev")
        _has_py_file = bool(_re2.search(r'\w+\.py', text))
        if _USE_DEV and (_is_dev_mode or _has_py_file):"""
    new_block = """        # 5. 自主開發指令攔截（只有明確包含 .py 檔名才走）
        import re as _re2
        _has_py_file = bool(_re2.search(r'\\w+\\.py', text))
        if _USE_DEV and _has_py_file:"""
    src = src.replace(old_block, new_block)
    print("更新自主開發攔截")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("OK - 請重啟")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    lines = src.splitlines()
    for i in range(max(0,e.lineno-3), min(len(lines),e.lineno+3)):
        print(f"{i+1}: {repr(lines[i])}")
    shutil.copy2(backup, TARGET)
    print("已還原")
