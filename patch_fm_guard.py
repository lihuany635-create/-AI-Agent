import pathlib, ast, shutil, datetime
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)
src = TARGET.read_text(encoding="utf-8", errors="replace")

# 找到 _fm_cn 的攔截，加上更嚴格的判斷
# 「新增元素」不應觸發，只有「新增資料夾」「新增檔案」才觸發

old_fm = '''        if _USE_FM:
            _c = ["\u5217\u51fa\u6a94\u6848","\u67e5\u770b\u8cc7\u6599\u593e",
                  "\u8cc7\u6599\u593e","\u5efa\u7acb\u8cc7\u6599\u593e","\u522a\u9664\u6a94\u6848",
                  "\u91cd\u547d\u540d","\u641c\u5c0b\u6a94\u6848","\u958b\u555f\u6a94\u6848",
                  "\u58d3\u7e2e","\u89e3\u58d3\u7e2e","\u6a94\u6848\u8cc7\u8a0a","\u76ee\u524d\u4f4d\u7f6e"]
            if any(k in text for k in _c):
                result = get_fm().handle(text)
                if result is not None:
                    return result'''

new_fm = '''        if _USE_FM:
            _c = ["\u5217\u51fa\u6a94\u6848","\u67e5\u770b\u8cc7\u6599\u593e",
                  "\u5efa\u7acb\u8cc7\u6599\u593e","\u65b0\u589e\u8cc7\u6599\u593e",
                  "\u522a\u9664\u6a94\u6848","\u522a\u9664\u8cc7\u6599\u593e",
                  "\u91cd\u547d\u540d","\u641c\u5c0b\u6a94\u6848","\u958b\u555f\u6a94\u6848",
                  "\u58d3\u7e2e","\u89e3\u58d3\u7e2e","\u6a94\u6848\u8cc7\u8a0a","\u76ee\u524d\u4f4d\u7f6e",
                  "\u8cc7\u6599\u593e\u5167\u5bb9","\u76ee\u9304\u5167\u5bb9"]
            # 「資料夾」單獨出現才觸發，避免誤判一般文字
            _has_fm_kw = any(k in text for k in _c)
            _has_folder = "\u8cc7\u6599\u593e" in text or "\u6a94\u6848" in text
            _is_general = any(k in text for k in ["\u5143\u7d20","\u65b9\u6cd5","\u51fd\u6578","\u8b8a\u6578","\u8cc7\u6599\u5eab","\u6a21\u5f0f","\u6280\u8853"])
            if _has_fm_kw and not _is_general:
                result = get_fm().handle(text)
                if result is not None:
                    return result'''

if old_fm in src:
    src = src.replace(old_fm, new_fm)
    print("修補成功")
else:
    print("找不到目標，手動搜尋...")
    idx = src.find("_USE_FM")
    while idx != -1:
        print(f"pos {idx}: {repr(src[idx:idx+50])}")
        idx = src.find("_USE_FM", idx+1)
        if idx > 15000:
            break

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("OK - 請重啟")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    shutil.copy2(backup, TARGET)
    print("已還原")
