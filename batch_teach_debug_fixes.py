# batch_teach_debug_fixes.py — 本次除錯修復經驗匯入
# 記錄 2026-03-28 的完整除錯過程，讓立 AI 學會這些經驗
# 使用方式：py batch_teach_debug_fixes.py

import sys

# 修復 Windows cp950 編碼問題
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import logging
for h in logging.root.handlers:
    if hasattr(h, 'stream'):
        h.stream = sys.stdout

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from long_term_memory import get_memory

memory = get_memory()
print(f"記憶庫已載入，目前有 {len(memory._memories)} 筆記憶\n")

KNOWLEDGE = [

    # ══════════════════════════════════════════════════════════════
    # 1. desktop_agent.py 五個模式窗口修復經驗
    # ══════════════════════════════════════════════════════════════

    ("desktop_agent.py 的 _run_worker 方法原本不存在，導致確認/取消按鈕點了會 crash。修復方式：新增 _run_worker 方法建立 AgentWorker",
     8, ["修復經驗", "desktop_agent", "crash"]),

    ("語音輸入 voice_input 不能用 input_box.setText 再呼叫 send_text，因為 send_text 會先 clear() 清空 input_box。修復方式：語音辨識結果直接走 _run_worker",
     8, ["修復經驗", "desktop_agent", "語音"]),

    ("_poll_mobile_queue 裡面不能建立新的 QTimer，每次 timer 觸發都會建一個新的，造成記憶體洩漏。Timer 應該在 _start_timers 中統一建立",
     8, ["修復經驗", "desktop_agent", "記憶體洩漏"]),

    ("_refresh_quick_actions 必須真的替換按鈕（removeWidget + deleteLater + 建新按鈕），不能只改標籤顏色。需要在 _left_panel 儲存 _quick_action_layout 和 _quick_action_btns 參考",
     7, ["修復經驗", "desktop_agent", "UI"]),

    ("模式按鈕不要用 setCheckable(True)，checkable 按鈕在 PyQt6 會有 toggle 問題。改用普通按鈕，靠 setStyleSheet 顯示啟用狀態",
     7, ["修復經驗", "desktop_agent", "PyQt6"]),

    ("確認/取消按鈕（_on_confirm/_on_cancel）應固定用 mode='chat' 送給 AgentWorker，不受當前模式影響，因為待確認的行動來自 AI 不是使用者",
     7, ["修復經驗", "desktop_agent", "確認取消"]),

    # ══════════════════════════════════════════════════════════════
    # 2. 執行緒安全修復經驗
    # ══════════════════════════════════════════════════════════════

    ("PyQt6 規則：只有主執行緒能操作 UI 元件。Telegram Bot 的 _run() 在 daemon thread 裡，不能直接呼叫 self._log()。修復方式：用 QTimer.singleShot(0, lambda: self._log(...)) 把 UI 操作拋回主執行緒",
     9, ["修復經驗", "執行緒安全", "PyQt6", "重要"]),

    ("_update_log_status 裡的 requests.get(timeout=2) 會阻塞主執行緒 2 秒。修復方式：把 Ollama 檢查移到背景 threading.Thread，結果用 QTimer.singleShot 回主執行緒更新 UI",
     8, ["修復經驗", "執行緒安全", "效能"]),

    # ══════════════════════════════════════════════════════════════
    # 3. Ollama 模型呼叫修復經驗
    # ══════════════════════════════════════════════════════════════

    ("qwen2:7b-instruct-q4_0 用 Ollama 的 chat API 會卡住超時（180秒），必須用 generate API。但 generate API 的 system 參數會被 qwen2 無視",
     9, ["修復經驗", "Ollama", "qwen2", "重要"]),

    ("解決 qwen2 無視 system prompt 的方法：把系統指令直接嵌入 prompt 裡面，格式為 [系統指令]\\n{system}\\n\\n{prompt}。這樣模型一定看得到",
     9, ["修復經驗", "Ollama", "prompt", "重要"]),

    ("ollama_guard.py 的 generate API 原本 num_predict 只有 256，太短了。改成 512 才夠用。temperature 從 0.7 降到 0.6 讓回答更穩定",
     7, ["修復經驗", "Ollama", "參數"]),

    # ══════════════════════════════════════════════════════════════
    # 4. 模型選擇修復經驗
    # ══════════════════════════════════════════════════════════════

    ("deepseek-r1:1.5b 只有 1.5B 參數，不管設計用途是什麼，實際回答品質都不如 7B 模型。model_selector 的分數要反映實際品質，不能只看設計用途",
     8, ["修復經驗", "model_selector", "模型選擇"]),

    ("model_selector 加入 MIN_MODEL_SIZE = 4，低於 4B 的模型不會被自動選擇。使用者是繁體中文，中文能力 >= 8 的模型額外 +2 分確保 qwen2 優先",
     8, ["修復經驗", "model_selector", "模型選擇"]),

    # ══════════════════════════════════════════════════════════════
    # 5. 記憶庫搜尋修復經驗
    # ══════════════════════════════════════════════════════════════

    ("long_term_memory.py 的 search() 用空格分詞，但中文沒有空格，所以搜尋中文關鍵字幾乎都搜不到。prompt_engine 用三層搜尋繞過：1.完整句子搜 2.拆關鍵字分別搜 3.直接文字比對",
     9, ["修復經驗", "記憶庫", "搜尋", "重要"]),

    ("中文分詞要用 known_terms 匹配已知詞彙（程式碼、備份、修改、名字、主人等），不能只靠空格或標點拆詞。沒匹配到就用滑動窗口取 2-3 字組合",
     8, ["修復經驗", "記憶庫", "中文分詞"]),

    ("語義擴展很重要：使用者問「名字」「叫什麼」時，要自動也搜「主人」「叫」。用 keyword_map 字典做映射",
     8, ["修復經驗", "記憶庫", "語義擴展"]),

    ("記憶搜尋結果的排序要用「相關度」而不是只看「重要性」。相關度 = 關鍵字命中數 × 10 + 重要性。這樣命中兩個關鍵字的記憶會排在只命中一個的前面",
     8, ["修復經驗", "記憶庫", "排序"]),

    # ══════════════════════════════════════════════════════════════
    # 6. Prompt 工程修復經驗
    # ══════════════════════════════════════════════════════════════

    ("系統 prompt 要明確寫「一律使用繁體中文回答，絕對不要用簡體中文」，不然 qwen2 預設會用簡體。還要寫「回答不超過 5 行」「不要加多餘的範例程式碼」",
     8, ["修復經驗", "prompt", "系統指令"]),

    ("prompt 裡的已知知識區塊要寫「你必須優先根據這些內容回答，這是主人教你的」，這樣模型才會優先看記憶庫而不是自己亂編",
     8, ["修復經驗", "prompt", "知識優先"]),

    ("記憶庫沒搜到相關知識時，prompt 要告訴模型「請用你自己的知識回答，開頭加上（根據我的理解）」，讓使用者知道這不是來自記憶庫的知識",
     7, ["修復經驗", "prompt", "來源標記"]),

    # ══════════════════════════════════════════════════════════════
    # 7. 記憶庫污染修復經驗
    # ══════════════════════════════════════════════════════════════

    ("memory_curator 的 maybe_learn 會自動把每次問答存入長期記憶庫，導致簡體垃圾回答污染搜尋結果。修復方式：在 Lobster_Core._think() 裡註解掉 maybe_learn，知識應該只透過教學模式或 batch_teach.py 手動存入",
     9, ["修復經驗", "記憶庫", "污染", "重要"]),

    ("cognition_state_manager 的 runtime_state.json 會存 16 輪對話歷史（get_current_context），舊的簡體回答會帶偏模型風格。修復方式：用 clear_context() 清除。清完 episodic_memory 還要清 runtime_state.json",
     9, ["修復經驗", "對話歷史", "污染", "重要"]),

    ("過濾記憶搜尋結果時，要跳過「問：... → 答：...」格式的問答記錄，只保留純知識",
     7, ["修復經驗", "記憶庫", "過濾"]),

    # ══════════════════════════════════════════════════════════════
    # 8. 其他修復經驗
    # ══════════════════════════════════════════════════════════════

    ("on_cmd 的 Telegram 指令裡，result.stdout 是 bytes 型別，不能和 str '（無輸出）' 混用（result.stdout or '（無輸出）'）。要先 decode 成 out_text 再用",
     7, ["修復經驗", "Telegram", "bytes/str"]),

    ("_last_mobile_count 必須在 _start_timers() 之前初始化，不然 timer 可能在變數存在之前就觸發",
     7, ["修復經驗", "初始化順序"]),

    ("PowerShell 的引號處理和 CMD 不同，複雜的 Python 單行指令在 PowerShell 容易出錯。解法：把指令寫成 .py 檔案再用 py 執行",
     6, ["修復經驗", "PowerShell", "開發技巧"]),

    ("切換模式時在對話框顯示提示泡泡（例如「📚 已切換到教學模式」），讓使用者清楚知道目前在哪個模式，避免在錯誤模式下輸入",
     6, ["修復經驗", "UX", "防呆"]),

    ("send_text 在每次送出時記錄 log（模式=xxx，輸入=xxx），方便除錯時確認輸入有沒有走對路徑",
     6, ["修復經驗", "除錯", "日誌"]),
]

def main():
    added = 0
    skipped = 0

    for content, importance, tags in KNOWLEDGE:
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
            tags=["debug_fix_20260328"] + tags,
            importance=importance,
            source="batch_teach_debug"
        )
        stars = "*" * min(importance, 5)
        print(f"  [ok] {stars} {content[:60]}")
        added += 1

    print(f"\n{'='*50}")
    print(f"  done!")
    print(f"  added: {added}")
    print(f"  skipped: {skipped}")
    print(f"  total: {len(memory._memories)}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()

