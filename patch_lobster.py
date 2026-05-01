# patch_lobster.py — 直接修補 Lobster_Core.py
# 不需要下載，直接在電腦上執行修改
# 執行：python patch_lobster.py

import pathlib
import ast
import shutil
import datetime

TARGET = pathlib.Path("Lobster_Core.py")

if not TARGET.exists():
    print("找不到 Lobster_Core.py，請在 AI-Agent 資料夾執行")
    exit(1)

# 備份
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)
print(f"已備份：{backup.name}")

src = TARGET.read_text(encoding="utf-8")

# ── 修補 1：糾正學習攔截 ──────────────────────────────────────────────────────
CORRECTION_CODE = '''        # -1. 糾正學習攔截
        _correct_kw = ["你剛才", "你做錯", "你錯了", "應該要", "不對，", "不是這樣", "你應該", "記住，下次"]
        if any(k in text for k in _correct_kw):
            try:
                from long_term_memory import get_memory
                get_memory().store(
                    f"使用者糾正：{text}",
                    tags=["correction", "feedback"],
                    importance=9,
                    source="user_correction"
                )
            except Exception:
                pass
            return f"好的，我記住了。下次會改正。"

'''

# 找到 process_input 方法的開頭，插入糾正學習攔截
if "糾正學習攔截" not in src:
    # 找 process_input 裡第一個 # 1. 的位置
    marker = "        # 1. 反射記憶"
    if marker in src:
        src = src.replace(marker, CORRECTION_CODE + marker)
        print("修補 1：糾正學習攔截 ✓")
    else:
        print("修補 1：找不到插入點，跳過")
else:
    print("修補 1：已存在，跳過")

# ── 修補 2：檔案管理關鍵字 ────────────────────────────────────────────────────
FM_IMPORT = '''try:
    from file_manager import get_fm
    _USE_FM = True
except ImportError:
    _USE_FM = False

'''

if "from file_manager import" not in src:
    # 在 desktop_control import 前加入
    marker2 = "try:\n    from desktop_control import get_control"
    if marker2 in src:
        src = src.replace(marker2, FM_IMPORT + marker2)
        print("修補 2：file_manager import ✓")
    else:
        print("修補 2：找不到插入點，跳過")
else:
    print("修補 2：已存在，跳過")

# ── 修補 3：在桌面控制攔截加入檔案管理 ───────────────────────────────────────
FM_KW_CODE = '''            # 檔案管理攔截
            _fm_kw = [
                "列出檔案", "查看資料夾", "資料夾內容",
                "建立資料夾", "新增資料夾",
                "刪除資料夾", "刪除檔案",
                "重命名", "改名",
                "複製檔案", "移動檔案", "搬移",
                "搜尋檔案", "找檔案",
                "開啟檔案", "壓縮", "解壓縮",
                "檔案資訊", "檔案大小",
                "切換目錄", "目前位置",
            ]
            if _USE_FM and any(k in text for k in _fm_kw):
                result = get_fm().handle(text)
                if result is not None:
                    return result

'''

if "_fm_kw" not in src:
    marker3 = "        # 1. 反射記憶"
    if marker3 in src:
        src = src.replace(marker3, FM_KW_CODE + marker3)
        print("修補 3：檔案管理關鍵字 ✓")
    else:
        print("修補 3：找不到插入點，跳過")
else:
    print("修補 3：已存在，跳過")

# ── 語法檢查並寫入 ────────────────────────────────────────────────────────────
try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print(f"\n✅ 修補完成！Lobster_Core.py 已更新")
    print("請重啟 desktop_agent.py")
except SyntaxError as e:
    print(f"\n❌ 語法錯誤：{e}")
    print(f"已還原備份：{backup.name}")
    shutil.copy2(backup, TARGET)

