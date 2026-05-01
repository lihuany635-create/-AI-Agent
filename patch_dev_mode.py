import pathlib, ast, shutil, datetime
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)
src = TARGET.read_text(encoding="utf-8", errors="replace")

# 找到自主開發攔截，加上模式判斷
# 只有在 dev 模式，或明確包含 .py 檔名時才走 self_dev_engine

old_dev = """        # 5. 自主開發指令攔截（優先於一般任務路由）
        if _USE_DEV:"""

new_dev = """        # 5. 自主開發指令攔截（只在 dev 模式，或明確包含 .py 檔名）
        import re as _re2
        _is_dev_mode = (mode == "dev")
        _has_py_file = bool(_re2.search(r'\w+\.py', text))
        if _USE_DEV and (_is_dev_mode or _has_py_file):"""

if old_dev in src:
    src = src.replace(old_dev, new_dev)
    print("修補自主開發攔截")
else:
    print("找不到自主開發攔截，嘗試其他方式")
    # 找 self_dev_engine 的 handle 呼叫
    old_dev2 = "        if _USE_DEV:\n            eng = get_dev_engine()"
    new_dev2 = "        _is_dev_mode = (mode == 'dev')\n        _has_py_file = bool(__import__('re').search(r'\\w+\\.py', text))\n        if _USE_DEV and (_is_dev_mode or _has_py_file):\n            eng = get_dev_engine()"
    if old_dev2 in src:
        src = src.replace(old_dev2, new_dev2)
        print("修補成功（替代方式）")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("OK")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    shutil.copy2(backup, TARGET)
