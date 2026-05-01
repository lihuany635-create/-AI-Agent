# patch_file_manager.py — 修補 file_manager.py 的關鍵字匹配
import pathlib, ast, shutil, datetime

TARGET = pathlib.Path("file_manager.py")
if not TARGET.exists():
    print("找不到 file_manager.py")
    exit(1)

backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

src = TARGET.read_text(encoding="utf-8")

old_list = '''        # 查看資料夾內容
        if any(k in t for k in ["列出檔案", "查看資料夾", "資料夾內容", "ls ", "列出目錄"]):
            path = self._extract_path(t) or self.cwd
            return self.list_dir(path)'''

new_list = '''        # 查看資料夾內容（寬鬆匹配：只要有「資料夾」就觸發）
        if any(k in t for k in ["列出檔案", "查看資料夾", "資料夾內容", "ls ", "列出目錄",
                                  "裡面有什麼", "有哪些檔案", "資料夾", "目錄內容"]):
            # 嘗試從文字中提取路徑或資料夾名稱
            path = self._extract_path(t)
            if path is None:
                # 嘗試提取資料夾名稱
                import re
                m = re.search(r"(?:查看|列出|看看|進入)\s*(.+?)\s*(?:資料夾|目錄|內容|裡面)?$", t)
                if m:
                    name = m.group(1).strip()
                    candidate = self._resolve(name)
                    if candidate.exists() and candidate.is_dir():
                        path = candidate
                    else:
                        # 在桌面搜尋
                        import pathlib as pl
                        desktop = pl.Path.home() / "OneDrive" / "桌面"
                        for d in desktop.iterdir():
                            if name.lower() in d.name.lower() and d.is_dir():
                                path = d
                                break
            return self.list_dir(path or self.cwd)'''

if old_list in src:
    src = src.replace(old_list, new_list)
    print("修補成功")
else:
    print("找不到目標，嘗試替代方式...")
    # 直接在 handle 方法開頭加上寬鬆匹配
    old_handle = '''    def handle(self, text: str) -> Optional[str]:
        t = text.strip()'''
    new_handle = '''    def handle(self, text: str) -> Optional[str]:
        t = text.strip()
        # 寬鬆匹配：包含「資料夾」且不是其他操作
        if "資料夾" in t and not any(k in t for k in ["建立", "刪除", "重命名", "複製", "移動", "壓縮", "解壓"]):
            if any(k in t for k in ["查看", "列出", "看看", "裡面", "內容", "有什麼", "有哪些"]):
                path = self._extract_path(t)
                if path is None:
                    import re
                    m = re.search(r"(\w[\w\s\-_]*?)(?:資料夾|目錄)", t)
                    if m:
                        name = m.group(1).strip()
                        candidate = self._resolve(name)
                        if candidate.exists():
                            path = candidate
                        else:
                            import pathlib as pl
                            desktop = pl.Path.home() / "OneDrive" / "桌面"
                            for d in desktop.iterdir():
                                if name.lower() in d.name.lower() and d.is_dir():
                                    path = d
                                    break
                return self.list_dir(path or self.cwd)'''
    if old_handle in src:
        src = src.replace(old_handle, new_handle)
        print("替代修補成功")
    else:
        print("無法修補，請手動處理")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("完成！請重啟 desktop_agent.py")
except SyntaxError as e:
    print(f"語法錯誤：{e}")
    shutil.copy2(backup, TARGET)
    print("已還原備份")
