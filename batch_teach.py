# batch_teach.py — 立 AI 批次知識匯入腳本
# 使用方式：把這個檔案放到 AI-Agent 資料夾，執行 python batch_teach.py
# 會自動把下方的知識清單存入記憶庫

import sys

# 修復 Windows cp950 編碼問題
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import logging
for h in logging.root.handlers:
    if hasattr(h, 'stream'):
        h.stream = sys.stdout

import datetime

# 確保套件路徑
_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from long_term_memory import get_memory

memory = get_memory()
print(f"記憶庫已載入，目前有 {len(memory._memories)} 筆記憶\n")

# ════════════════════════════════════════════════════════════════
# 知識清單 — 直接編輯這裡就好
# 格式：(內容, 重要性1-9, [標籤列表])
# ════════════════════════════════════════════════════════════════

KNOWLEDGE = [

    # ── 關於主人 ──────────────────────────────────────────────
    ("我的主人使用 Windows 11，Python 3.11",
     9, ["主人", "環境"]),

    ("專案路徑是 C:\\Users\\ACER\\OneDrive\\桌面\\AI-Agent",
     9, ["主人", "環境"]),

    ("使用 Ollama 本地模型，預設 qwen2，程式問題用 deepseek-r1",
     9, ["主人", "模型"]),

    # ── 專案規則 ──────────────────────────────────────────────
    ("修改任何 .py 檔案前必須先用 backup_engine 備份",
     8, ["規則", "開發"]),

    ("所有程式碼檔案使用 UTF-8 編碼，不能有 BOM",
     8, ["規則", "編碼"]),

    ("self._log() 不能在子執行緒直接呼叫，要用 QTimer.singleShot 回主執行緒",
     8, ["規則", "PyQt6", "執行緒"]),

    ("desktop_agent.py 有五個模式：對話、終端、自主開發、教學、桌面",
     8, ["規則", "架構"]),

    ("教學模式直接存記憶庫不走 Ollama，其他四個模式走 AgentWorker",
     8, ["規則", "架構"]),

    # ── 架構知識 ──────────────────────────────────────────────
    ("Lobster_Core.py 是核心，負責接收輸入並呼叫各模組處理",
     7, ["架構", "核心"]),

    ("self_dev_engine.py 負責自主修改程式碼，修改前要備份，改完要確認",
     7, ["架構", "開發"]),

    ("intent_router.py 判斷使用者意圖，決定走哪個處理流程",
     7, ["架構", "路由"]),

    ("reflex_engine.py 處理快速回應，不需要 AI 模型的簡單問答",
     7, ["架構", "回應"]),

    ("long_term_memory.py 管理記憶庫，支援搜尋、儲存、遺忘",
     7, ["架構", "記憶"]),

    ("memory_curator.py 負責記憶的整理和清理",
     7, ["架構", "記憶"]),

    ("cognition_state_manager.py 追蹤對話上下文狀態",
     7, ["架構", "認知"]),

    ("task_scheduler.py 管理排程任務，例如自動修復",
     7, ["架構", "排程"]),

    # ── 桌面控制 ──────────────────────────────────────────────
    ("desktop_control.py 使用 pyautogui 控制滑鼠鍵盤",
     6, ["桌面控制", "pyautogui"]),

    ("螢幕截圖用 mss 庫，文字辨識用 pytesseract",
     6, ["桌面控制", "OCR"]),

    ("視窗管理用 pygetwindow，需要 win32gui 輔助",
     6, ["桌面控制", "視窗"]),

    ("危險指令（刪除、格式化）執行前必須先確認",
     6, ["桌面控制", "安全"]),

    # ── Telegram Bot ──────────────────────────────────────────
    ("Telegram Bot 在 desktop_agent.py 的 _start_telegram_bot 中啟動",
     6, ["Telegram", "架構"]),

    ("Bot 設定在 bot_config.py，包含 TOKEN 和 ALLOWED_CHAT_IDS",
     6, ["Telegram", "設定"]),

    ("手機訊息透過 memory/mobile_queue.json 同步到桌面視窗",
     6, ["Telegram", "同步"]),

    ("Bot 指令：/status /cmd /open /ls /read /dev /confirm /cancel /restore /history",
     6, ["Telegram", "指令"]),

    # ── 開發偏好 ──────────────────────────────────────────────
    ("主人喜歡深色主題的 UI 介面",
     5, ["偏好", "UI"]),

    ("程式碼要有中文註解",
     5, ["偏好", "程式碼"]),

    ("錯誤訊息要用中文顯示",
     5, ["偏好", "UI"]),

    ("UI 字體用 Microsoft JhengHei UI",
     5, ["偏好", "UI"]),
]


# ════════════════════════════════════════════════════════════════
# 執行匯入
# ════════════════════════════════════════════════════════════════

def main():
    added = 0
    skipped = 0

    for content, importance, tags in KNOWLEDGE:
        # 檢查是否已存在（避免重複匯入）
        existing = memory.search(content[:30], top_k=3)
        already = False
        for e in existing:
            if e["content"].strip() == content.strip():
                already = True
                break

        if already:
            print(f"  [skip] {content[:50]}")
            skipped += 1
            continue

        memory.store(
            content,
            tags=["batch_teach"] + tags,
            importance=importance,
            source="batch_teach"
        )
        stars = "*" * min(importance, 5)
        tag_str = " ".join(f"[{t}]" for t in tags)
        print(f"  [ok] {stars} {content[:50]}  {tag_str}")
        added += 1

    print(f"\n{'='*50}")
    print(f"  done!")
    print(f"  added: {added}")
    print(f"  skipped: {skipped}")
    print(f"  total: {len(memory._memories)}")
    print(f"{'='*50}")
    print(f"\n  edit KNOWLEDGE list and run again to add more.")


if __name__ == "__main__":
    main()

