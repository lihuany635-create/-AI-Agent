import pathlib, ast, shutil, datetime, re

TARGET = pathlib.Path("file_manager.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

src = TARGET.read_text(encoding="utf-8", errors="replace")

# 找到 handle 方法的開頭
handle_start = src.find("    def handle(self, text")
if handle_start == -1:
    print("找不到 handle 方法")
    exit(1)

# 找到 handle 方法的結尾（下一個 def）
next_def = src.find("\n    def ", handle_start + 10)
if next_def == -1:
    next_def = len(src)

# 取出 handle 以外的部分
before_handle = src[:handle_start]
after_handle = src[next_def:]

# 新的 handle 方法（判斷順序正確）
new_handle = '''    def handle(self, text: str):
        t = text.strip()
        import re as _re

        # 1. 建立資料夾（最優先）
        if any(k in t for k in ["\u5efa\u7acb\u8cc7\u6599\u593e", "\u65b0\u589e\u8cc7\u6599\u593e", "\u5efa\u8cc7\u6599\u593e", "mkdir"]):
            name = self._extract_name(t, ["\u5efa\u7acb\u8cc7\u6599\u593e", "\u65b0\u589e\u8cc7\u6599\u593e", "\u5efa\u8cc7\u6599\u593e", "mkdir"])
            return self.make_dir(name) if name else "\u8acb\u6307\u5b9a\u8cc7\u6599\u593e\u540d\u7a31\uff0c\u4f8b\u5982\uff1a\u5efa\u7acb\u8cc7\u6599\u593e \u6e2c\u8a66"

        # 2. 刪除
        if any(k in t for k in ["\u522a\u9664\u8cc7\u6599\u593e", "\u522a\u9664\u6a94\u6848", "\u522a\u9664"]) and "\u4e0d\u8981\u522a\u9664" not in t:
            name = self._extract_name(t, ["\u522a\u9664\u8cc7\u6599\u593e", "\u522a\u9664\u6a94\u6848", "\u522a\u9664"])
            return self.delete(name) if name else "\u8acb\u6307\u5b9a\u8981\u522a\u9664\u7684\u540d\u7a31"

        # 3. 重命名
        if any(k in t for k in ["\u91cd\u547d\u540d", "\u6539\u540d", "rename"]):
            return self.rename_from_text(t)

        # 4. 複製
        if any(k in t for k in ["\u8907\u88fd\u6a94\u6848", "\u8907\u88fd\u8cc7\u6599\u593e", "\u8907\u88fd"]):
            return self.copy_from_text(t)

        # 5. 移動
        if any(k in t for k in ["\u79fb\u52d5\u6a94\u6848", "\u79fb\u52d5", "\u641c\u79fb"]):
            return self.move_from_text(t)

        # 6. 搜尋
        if any(k in t for k in ["\u641c\u5c0b\u6a94\u6848", "\u627e\u6a94\u6848", "\u5c0b\u627e"]):
            keyword = self._extract_name(t, ["\u641c\u5c0b\u6a94\u6848", "\u627e\u6a94\u6848", "\u5c0b\u627e"])
            return self.search(keyword) if keyword else "\u8acb\u6307\u5b9a\u641c\u5c0b\u95dc\u9375\u5b57"

        # 7. 開啟
        if any(k in t for k in ["\u958b\u555f\u6a94\u6848", "\u6253\u958b\u6a94\u6848", "\u958b\u555f"]):
            name = self._extract_name(t, ["\u958b\u555f\u6a94\u6848", "\u6253\u958b\u6a94\u6848", "\u958b\u555f"])
            return self.open_file(name) if name else "\u8acb\u6307\u5b9a\u6a94\u6848"

        # 8. 解壓縮
        if any(k in t for k in ["\u89e3\u58d3\u7e2e", "unzip"]):
            name = self._extract_name(t, ["\u89e3\u58d3\u7e2e", "unzip"])
            return self.unzip(name) if name else "\u8acb\u6307\u5b9a\u6a94\u6848"

        # 9. 壓縮
        if any(k in t for k in ["\u58d3\u7e2e", "zip"]):
            return self.zip_from_text(t)

        # 10. 檔案資訊
        if any(k in t for k in ["\u6a94\u6848\u8cc7\u8a0a", "\u6a94\u6848\u5927\u5c0f", "\u6a94\u6848\u65e5\u671f"]):
            name = self._extract_name(t, ["\u6a94\u6848\u8cc7\u8a0a", "\u6a94\u6848\u5927\u5c0f", "\u6a94\u6848\u65e5\u671f"])
            return self.file_info(name) if name else "\u8acb\u6307\u5b9a\u6a94\u6848"

        # 11. 切換目錄
        if any(k in t for k in ["\u5207\u63db\u76ee\u9304", "\u9032\u5165\u8cc7\u6599\u593e", "cd "]):
            name = self._extract_name(t, ["\u5207\u63db\u76ee\u9304", "\u9032\u5165\u8cc7\u6599\u593e", "cd"])
            return self.change_dir(name) if name else "\u8acb\u6307\u5b9a\u76ee\u9304"

        # 12. 目前位置
        if any(k in t for k in ["\u76ee\u524d\u4f4d\u7f6e", "\u76ee\u524d\u76ee\u9304", "pwd"]):
            return f"\u76ee\u524d\u4f4d\u7f6e\uff1a{self.cwd}"

        # 13. 查看資料夾（最後）
        if any(k in t for k in ["\u5217\u51fa\u6a94\u6848", "\u67e5\u770b\u8cc7\u6599\u593e", "\u8cc7\u6599\u593e\u5167\u5bb9",
                                  "\u8cc7\u6599\u593e", "\u6709\u4ec0\u9ebc", "\u6709\u54ea\u4e9b", "\u5217\u51fa"]):
            path = self._extract_path(t)
            if path is None:
                # 從文字提取資料夾名稱
                m = _re.search(r"(?:\u67e5\u770b|look)\s+([A-Za-z0-9_\\-\u4e00-\u9fff]+)\s*(?:\u8cc7\u6599\u593e|\u76ee\u9304|folder)?", t, _re.I)
                if m:
                    name = m.group(1).strip()
                    candidate = self._resolve(name)
                    if candidate.exists() and candidate.is_dir():
                        path = candidate
                    else:
                        import pathlib as _pl
                        for base in [_pl.Path.home() / "OneDrive" / "\u684c\u9762", _pl.Path.home() / "Desktop"]:
                            if base.exists():
                                for d in base.iterdir():
                                    if name.lower() in d.name.lower() and d.is_dir():
                                        path = d
                                        break
                        if path is None:
                            for d in self.cwd.iterdir():
                                if d.is_dir() and name.lower() in d.name.lower():
                                    path = d
                                    break
            return self.list_dir(path or self.cwd)

        return None

'''

new_src = before_handle + new_handle + after_handle

try:
    ast.parse(new_src)
    TARGET.write_text(new_src, encoding="utf-8")
    print("OK")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    shutil.copy2(backup, TARGET)
    print("已還原")
