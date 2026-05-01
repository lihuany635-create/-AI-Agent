import pathlib, ast, shutil, datetime

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

src = TARGET.read_text(encoding="utf-8", errors="replace")

# 加入 file_manager import（在最前面找一個好位置）
fm_import = (
    "try:\n"
    "    from file_manager import get_fm\n"
    "    _USE_FM = True\n"
    "except Exception:\n"
    "    _USE_FM = False\n\n"
)

# 找 _USE_DEV 的 import，在它前面插入
marker = "try:\n    from self_dev_engine import get_engine as get_dev_engine"
if marker in src and "from file_manager import get_fm" not in src:
    src = src.replace(marker, fm_import + marker)
    print("插入 file_manager import")
elif "from file_manager import get_fm" in src:
    print("import 已存在，只修正變數")
    # 確保 _USE_FM 有定義
    if "_USE_FM = True" not in src:
        src = fm_import + src
else:
    # 插在檔案開頭的 import 區
    src = fm_import + src
    print("插入到檔案開頭")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("OK - 請重啟 desktop_agent.py")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    shutil.copy2(backup, TARGET)
    print("已還原")
