import pathlib, ast, shutil, datetime

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

src = TARGET.read_text(encoding="utf-8", errors="replace")

# 在最後的 return self._think(text) 前插入檔案管理攔截
insert_code = (
    "        if _USE_FM:\n"
    "            _c = [\"\u5217\u51fa\u6a94\u6848\",\"\u67e5\u770b\u8cc7\u6599\u593e\","
    "\"\u8cc7\u6599\u593e\",\"\u8cc7\u6599\",\"\u6a94\u6848\","
    "\"\u5efa\u7acb\u8cc7\u6599\u593e\",\"\u522a\u9664\u6a94\u6848\","
    "\"\u91cd\u547d\u540d\",\"\u641c\u5c0b\u6a94\u6848\","
    "\"\u958b\u555f\u6a94\u6848\",\"\u58d3\u7e2e\",\"\u89e3\u58d3\u7e2e\","
    "\"\u6a94\u6848\u8cc7\u8a0a\",\"\u76ee\u524d\u4f4d\u7f6e\"]\n"
    "            if any(k in text for k in _c):\n"
    "                _r = get_fm().handle(text)\n"
    "                if _r is not None:\n"
    "                    return _r\n"
)

# 找最後一個 return self._think(text)
marker = "        return self._think(text)"
last_pos = src.rfind(marker)

if last_pos == -1:
    print("找不到 return self._think(text)")
    exit(1)

src = src[:last_pos] + insert_code + src[last_pos:]

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("OK")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    shutil.copy2(backup, TARGET)
