import pathlib, ast, shutil, datetime

TARGET = pathlib.Path("file_manager.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

src = TARGET.read_text(encoding="utf-8", errors="replace")

# 加強 _extract_name 方法，能從「查看 XXX 資料夾」提取名稱
old_list_dir_call = (
    "        # \u5bec\u9b06\u5339\u914d\uff1a\u53ea\u8981\u6709\u300c\u8cc7\u6599\u593e\u300d\u5c31\u89f8\u767c\uff09\n"
)

# 找到 handle 裡的查看資料夾邏輯並加強
old_view = """        if any(k in t for k in ["\u5217\u51fa\u6a94\u6848", "\u67e5\u770b\u8cc7\u6599\u593e", "\u8cc7\u6599\u593e\u5167\u5bb9", "ls ", "\u5217\u51fa\u76ee\u9304",
                                  "\u88e1\u9762\u6709\u4ec0\u9ebc", "\u6709\u54ea\u4e9b\u6a94\u6848", "\u8cc7\u6599\u593e", "\u76ee\u9304\u5167\u5bb9"]):\n            # \u5617\u8a66\u5f9e\u6587\u5b57\u4e2d\u63d0\u53d6\u8def\u5f91\u6216\u8cc7\u6599\u593e\u540d\u7a31\n            path = self._extract_path(t)\n            if path is None:\n                # \u5617\u8a66\u63d0\u53d6\u8cc7\u6599\u593e\u540d\u7a31\n                import re\n                m = re.search(r"(?:\u67e5\u770b|\u5217\u51fa|\u770b\u770b|\u9032\u5165)\s*(.+?)\s*(?:\u8cc7\u6599\u593e|\u76ee\u9304|\u5167\u5bb9|\u88e1\u9762)?$", t)\n                if m:\n                    name = m.group(1).strip()\n                    candidate = self._resolve(name)\n                    if candidate.exists() and candidate.is_dir():\n                        path = candidate\n                    else:\n                        # \u5728\u684c\u9762\u641c\u5c0b\n                        import pathlib as pl\n                        desktop = pl.Path.home() / "OneDrive" / "\u684c\u9762"\n                        for d in desktop.iterdir():\n                            if name.lower() in d.name.lower() and d.is_dir():\n                                path = d\n                                break\n            return self.list_dir(path or self.cwd)"""

new_view = """        if any(k in t for k in ["\u5217\u51fa\u6a94\u6848", "\u67e5\u770b\u8cc7\u6599\u593e", "\u8cc7\u6599\u593e\u5167\u5bb9", "ls ", "\u5217\u51fa\u76ee\u9304",
                                  "\u88e1\u9762\u6709\u4ec0\u9ebc", "\u6709\u54ea\u4e9b\u6a94\u6848", "\u8cc7\u6599\u593e", "\u76ee\u9304\u5167\u5bb9"]):\n            import re\n            path = self._extract_path(t)\n            if path is None:\n                # \u5617\u8a66\u63d0\u53d6\u8cc7\u6599\u593e\u540d\u7a31\uff08\u66f4\u5bc6\u7684\u6a21\u5f0f\uff09\n                patterns = [\n                    r"(?:\u67e5\u770b|look at|open)\s+([A-Za-z0-9_\\-\u4e00-\u9fff]+(?:\\.\\w+)?)\s*(?:\u8cc7\u6599\u593e|\u76ee\u9304|folder)?",\n                    r"([A-Za-z0-9_\\-]+(?:-[A-Za-z0-9_]+)*)\s*\u8cc7\u6599\u593e",\n                    r"\u8cc7\u6599\u593e\s*([A-Za-z0-9_\\-\u4e00-\u9fff]+)",\n                ]\n                name = None\n                for pat in patterns:\n                    m = re.search(pat, t, re.IGNORECASE)\n                    if m:\n                        name = m.group(1).strip()\n                        break\n                if name:\n                    # \u5148\u5728\u76ee\u524d\u76ee\u9304\u627e\n                    candidate = self._resolve(name)\n                    if candidate.exists() and candidate.is_dir():\n                        path = candidate\n                    else:\n                        # \u5728\u684c\u9762\u627e\n                        import pathlib as _pl\n                        for base in [_pl.Path.home() / "OneDrive" / "\u684c\u9762", _pl.Path.home() / "Desktop"]:\n                            if base.exists():\n                                for d in base.iterdir():\n                                    if name.lower() in d.name.lower() and d.is_dir():\n                                        path = d\n                                        break\n                        if path is None:\n                            # \u5728 AI-Agent \u76ee\u9304\u627e\n                            for d in self.cwd.iterdir():\n                                if d.is_dir() and name.lower() in d.name.lower():\n                                    path = d\n                                    break\n            return self.list_dir(path or self.cwd)"""

if old_view in src:
    src = src.replace(old_view, new_view)
    print("修補成功")
else:
    print("找不到原始碼，跳過")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("OK")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    shutil.copy2(backup, TARGET)
