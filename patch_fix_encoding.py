# patch_fix_encoding.py — 修復 Lobster_Core.py 的編碼問題
# 把亂碼的中文關鍵字替換成正確的版本
import pathlib, ast, shutil, datetime

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

# 用 latin-1 讀取（保留原始位元組）
src = TARGET.read_text(encoding="utf-8", errors="replace")

# 找到 _fm_kw 的位置，直接替換整個區塊
import re

# 找到 _fm_kw = [ ... ] 區塊並替換
old_pattern = re.compile(r'_fm_kw = \[.*?\]', re.DOTALL)

new_fm_kw = '''_fm_kw = [
                "list", "dir", "ls",
                "folder", "directory",
            ]
            # 中文關鍵字（unicode）
            _fm_kw_cn = [
                "\u5217\u51fa\u6a94\u6848",
                "\u67e5\u770b\u8cc7\u6599\u593e",
                "\u8cc7\u6599\u593e\u5167\u5bb9",
                "\u67e5\u770b\u8cc7\u6599",
                "\u8cc7\u6599\u593e",
                "\u76ee\u9304\u5167\u5bb9",
                "\u88e1\u9762\u6709\u4ec0\u9ebc",
                "\u6a94\u6848",
                "\u5efa\u7acb\u8cc7\u6599\u593e",
                "\u65b0\u589e\u8cc7\u6599\u593e",
                "\u5efa\u7acb\u76ee\u9304",
                "\u522a\u9664\u8cc7\u6599\u593e",
                "\u522a\u9664\u6a94\u6848",
                "\u522a\u9664\u76ee\u9304",
                "\u91cd\u547d\u540d",
                "\u6539\u540d",
                "\u8907\u88fd\u6a94\u6848",
                "\u8907\u88fd\u8cc7\u6599\u593e",
                "\u79fb\u52d5\u6a94\u6848",
                "\u641c\u5c0b\u6a94\u6848",
                "\u627e\u6a94\u6848",
                "\u5c0b\u627e\u6a94\u6848",
                "\u958b\u555f\u6a94\u6848",
                "\u6253\u958b\u6a94\u6848",
                "\u58d3\u7e2e",
                "\u89e3\u58d3\u7e2e",
                "\u6a94\u6848\u8cc7\u8a0a",
                "\u6a94\u6848\u5927\u5c0f",
                "\u6a94\u6848\u65e5\u671f",
                "\u5207\u63db\u76ee\u9304",
                "\u76ee\u524d\u4f4d\u7f6e",
            ]
            if any(k in text for k in _fm_kw_cn) or any(k in text for k in _fm_kw)'''

match = old_pattern.search(src)
if match:
    src = src[:match.start()] + new_fm_kw + src[match.end():]
    print("找到並替換 _fm_kw 區塊")
else:
    print("找不到 _fm_kw 區塊，嘗試其他方式...")
    # 直接在 _think 前加入新的攔截
    old_think = "        return self._think(text)"
    new_think = '''        # 檔案管理攔截（unicode 版本）
        if _USE_FM:
            _fm_cn = ["\u5217\u51fa\u6a94\u6848","\u67e5\u770b\u8cc7\u6599\u593e","\u8cc7\u6599\u593e","\u8cc7\u6599","\u6a94\u6848","\u5efa\u7acb\u8cc7\u6599\u593e","\u522a\u9664\u8cc7\u6599\u593e","\u522a\u9664\u6a94\u6848","\u91cd\u547d\u540d","\u8907\u88fd\u6a94\u6848","\u79fb\u52d5\u6a94\u6848","\u641c\u5c0b\u6a94\u6848","\u958b\u555f\u6a94\u6848","\u58d3\u7e2e","\u89e3\u58d3\u7e2e","\u6a94\u6848\u8cc7\u8a0a","\u76ee\u524d\u4f4d\u7f6e"]
            if any(k in text for k in _fm_cn):
                result = get_fm().handle(text)
                if result is not None:
                    return result
        return self._think(text)'''
    if old_think in src:
        # 只替換最後一個 return self._think(text)
        src = src[:src.rfind(old_think)] + new_think + src[src.rfind(old_think)+len(old_think):]
        print("已在 _think 前加入攔截")
    else:
        print("無法找到插入點")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("完成！請重啟 desktop_agent.py")
except SyntaxError as e:
    print(f"語法錯誤 L{e.lineno}：{e.msg}")
    shutil.copy2(backup, TARGET)
    print("已還原備份")
