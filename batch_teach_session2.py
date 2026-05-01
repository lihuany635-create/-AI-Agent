import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import logging
for h in logging.root.handlers:
    if hasattr(h, 'stream'):
        h.stream = sys.stdout

from long_term_memory import get_memory
memory = get_memory()

KNOWLEDGE = [
    # 雙電腦共用算力
    ("兩台電腦透過 Tailscale VPN 連接，延遲約 10-15ms。ollama_guard.py 支援智慧切換：低延遲用分散式推論（llama.cpp RPC），高延遲用競速模式（兩台各自跑 Ollama）", 9, ["架構", "雙電腦"]),
    ("電腦 B 的 rpc_listener.py 會自動偵測電腦 A 的 Ollama 是否在線，偵測到就自動啟動 rpc-server，離線就自動關閉", 8, ["架構", "雙電腦", "自動化"]),
    ("llama.cpp 分散式推論需要同網路低延遲才有效。透過 Tailscale（13ms）跑反而比單台慢，因為每層都要傳資料", 8, ["架構", "效能", "經驗"]),
    ("電腦 A 的 Ollama 要設 OLLAMA_HOST=0.0.0.0 才能讓電腦 B 透過 Tailscale 連到", 8, ["設定", "Ollama", "Tailscale"]),

    # 記憶管理
    ("所有記憶（episodic、reflex、long_term）都需要使用者同意才能存入。Lobster_Core._think() 不再自動存，由 desktop_agent 的存入/跳過按鈕控制", 9, ["架構", "記憶", "重要"]),
    ("已經學習過的問題不會再問要不要存入記憶，會自動跳過確認", 8, ["架構", "記憶"]),
    ("手機 Telegram 也有記憶存入確認，用 inline keyboard 的存入/跳過按鈕", 7, ["Telegram", "記憶"]),

    # 教學系統
    ("learn_inbox 資料夾有 10 分鐘猶豫期，偵測到新檔案後等 10 分鐘才學習，期間刪除檔案可取消", 8, ["教學", "learn_inbox"]),
    ("學習完成後會透過 Telegram 推送通知到手機", 7, ["教學", "通知"]),
    ("教學模式支援讀取 PDF 檔案（需要 pypdf 套件），按段落分段存入記憶庫", 7, ["教學", "PDF"]),

    # 桌面控制新功能
    ("desktop_control.py 新增五大功能：開網頁/搜尋Google、文件管理（複製/移動/刪除）、音量控制（PowerShell SendKeys）、排程任務（N秒後執行指令）、開啟/編輯檔案（os.startfile）", 8, ["桌面控制", "功能"]),

    # 終端改善
    ("terminal_engine.py 支援連續指令（用 && 分隔），例如 cd learn_inbox && dir", 7, ["終端", "功能"]),
    ("terminal_engine.py 移除所有 emoji 避免 cp950 編碼錯誤，timeout 從 30 秒增加到 120 秒", 7, ["終端", "編碼"]),

    # Telegram 升級
    ("Telegram Bot 支援 /mode 指令和 inline keyboard 按鈕切換模式（對話/終端/自主開發/教學）", 8, ["Telegram", "模式"]),
    ("啟動時上線通知附帶模式選擇按鈕，說「換介面」「切換模式」也會彈出按鈕", 7, ["Telegram", "UX"]),

    # UI 改善
    ("desktop_agent.py 有取消按鈕，思考中時傳送按鈕變成紅色取消按鈕，按下中斷 worker", 7, ["UI", "取消"]),
    ("記憶庫每 10 分鐘自動備份到 memory/backups/，保留最近 10 份", 7, ["備份", "記憶"]),
]

added = 0
skipped = 0
for content, importance, tags in KNOWLEDGE:
    existing = memory.search(content[:30], top_k=3)
    already = any(e["content"].strip() == content.strip() for e in existing)
    if already:
        print(f"  [skip] {content[:50]}")
        skipped += 1
        continue
    memory.store(content, tags=["session_20260401"] + tags, importance=importance, source="session_summary")
    print(f"  [ok] {content[:60]}")
    added += 1

print(f"\nadded: {added}, skipped: {skipped}, total: {len(memory._memories)}")

