# patch_fm_keywords.py — 加強檔案管理關鍵字匹配
import pathlib, ast, shutil, datetime

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

src = TARGET.read_text(encoding="utf-8")

old_fm_kw = '''            _fm_kw = [
                "列出檔案", "查看資料夾", "資料夾內容",
                "建立資料夾", "新增資料夾",
                "刪除資料夾", "刪除檔案",
                "重命名", "改名",
                "複製檔案", "移動檔案", "搬移",
                "搜尋檔案", "找檔案",
                "開啟檔案", "壓縮", "解壓縮",
                "檔案資訊", "檔案大小",
                "切換目錄", "目前位置",
            ]'''

new_fm_kw = '''            _fm_kw = [
                "列出檔案", "查看資料夾", "資料夾內容", "查看資料",
                "資料夾", "目錄內容", "裡面有什麼", "有哪些檔案",
                "建立資料夾", "新增資料夾", "建立目錄",
                "刪除資料夾", "刪除檔案", "刪除目錄",
                "重命名", "改名", "rename",
                "複製檔案", "複製資料夾", "移動檔案", "搬移",
                "搜尋檔案", "找檔案", "尋找檔案",
                "開啟檔案", "打開檔案",
                "壓縮", "解壓縮", "zip", "unzip",
                "檔案資訊", "檔案大小", "檔案日期",
                "切換目錄", "進入資料夾", "目前位置", "pwd",
            ]'''

if old_fm_kw in src:
    src = src.replace(old_fm_kw, new_fm_kw)
    print("關鍵字擴充成功")
else:
    print("找不到原始關鍵字，請確認 patch_lobster.py 已執行")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("完成！請重啟 desktop_agent.py")
except SyntaxError as e:
    print(f"語法錯誤：{e}")
    shutil.copy2(backup, TARGET)
