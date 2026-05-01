# batch_teach_software_dev.py — 軟體開發知識批次匯入
# 使用：python batch_teach_software_dev.py

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

try:
    from long_term_memory import get_memory
    lm = get_memory()
except ImportError:
    print("找不到 long_term_memory.py，請在 AI-Agent 目錄下執行")
    sys.exit(1)

KNOWLEDGE = [
    # ── Python 基礎設計原則 ──────────────────────────────────────────────────
    ("好的 Python 程式碼要遵守 PEP8：縮排用4空格、函式名用小寫底線、類別名用大駝峰、常數用大寫", 9, ["python", "設計原則"]),
    ("每個函式只做一件事（單一職責原則），超過30行就考慮拆分", 9, ["設計原則", "函式"]),
    ("函式要有 docstring 說明用途、參數、回傳值，讓其他人容易理解", 8, ["python", "文件"]),
    ("用 try/except 處理可能失敗的操作，不要讓程式直接崩潰", 9, ["python", "錯誤處理"]),
    ("避免魔法數字，用常數或變數代替，例如 MAX_RETRY = 3 而不是直接寫 3", 8, ["python", "設計原則"]),
    ("用 pathlib.Path 處理檔案路徑，比字串拼接更安全", 8, ["python", "檔案"]),
    ("用 f-string 格式化字串，比 % 和 .format() 更清楚", 7, ["python", "字串"]),
    ("List comprehension 比 for loop 更 Pythonic，但不要讓它太複雜", 7, ["python", "語法"]),

    # ── PyQt6 UI 開發 ────────────────────────────────────────────────────────
    ("PyQt6 的 UI 操作必須在主執行緒，耗時操作要放在 QThread 避免凍結畫面", 10, ["pyqt6", "執行緒"]),
    ("QThread 完成後用 signal 回傳結果給主執行緒，不能直接操作 UI 元件", 10, ["pyqt6", "signal"]),
    ("PyQt6 的 signal 定義方式：class MyWorker(QThread): finished = pyqtSignal(str)", 9, ["pyqt6", "signal"]),
    ("PyQt6 Layout 種類：QVBoxLayout（垂直）、QHBoxLayout（水平）、QGridLayout（格狀）", 8, ["pyqt6", "layout"]),
    ("用 setStyleSheet 設定 QSS 樣式，語法類似 CSS", 7, ["pyqt6", "樣式"]),
    ("QTimer.singleShot(0, fn) 可以在主執行緒安全地延遲執行函式", 8, ["pyqt6", "timer"]),
    ("PyQt6 關閉事件用 closeEvent(self, event) 覆寫，event.accept() 允許關閉", 7, ["pyqt6", "事件"]),
    ("QFileDialog.getOpenFileName() 開啟檔案對話框，回傳 (路徑, 過濾器)", 8, ["pyqt6", "對話框"]),
    ("QMessageBox.question() 顯示確認對話框，回傳使用者選擇的按鈕", 8, ["pyqt6", "對話框"]),

    # ── 軟體架構設計 ─────────────────────────────────────────────────────────
    ("MVC 架構：Model（資料）、View（UI）、Controller（邏輯），三者分離", 9, ["架構", "設計模式"]),
    ("單例模式（Singleton）：整個程式只有一個實例，適合設定檔、記憶庫等全域物件", 8, ["設計模式", "singleton"]),
    ("工廠模式：用函式或類別建立物件，隱藏建立邏輯，例如 get_engine() 回傳引擎單例", 8, ["設計模式", "factory"]),
    ("Observer 模式：物件狀態改變時通知其他物件，PyQt6 的 signal/slot 就是這個概念", 8, ["設計模式", "observer"]),
    ("模組化設計：把相關功能放在同一個 .py 檔，用 import 引入，降低耦合", 9, ["架構", "模組化"]),
    ("介面設計要從使用者角度出發，先想好 API 再實作內部邏輯", 8, ["架構", "設計"]),

    # ── 檔案與資料處理 ───────────────────────────────────────────────────────
    ("JSON 存取用 json.loads() 讀取字串、json.load() 讀取檔案，json.dumps() 轉字串", 9, ["python", "json"]),
    ("讀寫檔案要指定 encoding='utf-8'，避免中文亂碼", 9, ["python", "檔案", "編碼"]),
    ("大型設定檔用 JSON 或 YAML，不要寫死在程式碼裡", 8, ["設計原則", "設定檔"]),
    ("備份重要檔案前先複製：shutil.copy2(src, dst) 保留元資料", 8, ["python", "備份"]),
    ("用 datetime.now().strftime('%Y%m%d_%H%M%S') 產生時間戳記用於備份檔名", 7, ["python", "時間"]),

    # ── 程式碼品質 ───────────────────────────────────────────────────────────
    ("寫程式前先規劃：需求 → 拆分功能 → 設計介面 → 實作 → 測試", 9, ["流程", "開發"]),
    ("先讓程式跑起來，再優化效能，不要過早優化", 8, ["設計原則"]),
    ("函式參數加上型別提示：def process(text: str, count: int = 0) -> str", 8, ["python", "型別"]),
    ("用 logging 記錄程式狀態，不要只用 print，方便除錯", 9, ["python", "logging"]),
    ("重要操作前備份，寫入前驗證，失敗時回滾", 9, ["設計原則", "安全"]),
    ("測試邊界條件：空字串、None、0、負數、超大數值", 8, ["測試", "設計原則"]),

    # ── subprocess 和系統操作 ────────────────────────────────────────────────
    ("subprocess.run() 執行外部指令，capture_output=True 捕捉輸出，timeout 防止卡住", 9, ["python", "subprocess"]),
    ("Windows 指令輸出可能是 cp950 編碼，用 errors='ignore' 避免解碼錯誤", 8, ["python", "編碼", "windows"]),
    ("用 shutil.which('程式名') 檢查外部程式是否存在，再執行", 7, ["python", "subprocess"]),

    # ── API 和網路 ───────────────────────────────────────────────────────────
    ("requests.get/post() 發送 HTTP 請求，timeout 參數避免永久等待", 9, ["python", "requests", "api"]),
    ("API 回應要檢查 status_code，200 才是成功，4xx 是客戶端錯誤，5xx 是伺服器錯誤", 8, ["api", "http"]),
    ("用 try/except requests.exceptions.RequestException 捕捉所有網路錯誤", 8, ["python", "requests", "錯誤處理"]),
    ("RESTful API 設計：GET 查詢、POST 新增、PUT 更新、DELETE 刪除", 7, ["api", "設計"]),

    # ── 自主開發最佳實踐 ─────────────────────────────────────────────────────
    ("新增功能前先備份原始檔案，確認新版正確再刪除備份", 10, ["開發流程", "備份"]),
    ("生成程式碼後用 ast.parse() 做語法檢查，語法錯誤就重試", 10, ["程式碼生成", "驗證"]),
    ("複雜需求要拆成多個步驟，每步只做一件事，逐步確認", 9, ["開發流程", "拆分"]),
    ("新功能用獨立的小檔案實作，整合前確認單獨可以跑", 9, ["開發流程", "模組化"]),
    ("修改現有大型檔案容易出錯，改用補丁模式：只加新函式，不動原有程式碼", 9, ["開發流程", "補丁"]),
    ("程式碼要能處理失敗情況：網路斷線、檔案不存在、格式錯誤都要有對應處理", 9, ["設計原則", "錯誤處理"]),
]

def main():
    success = 0
    for content, importance, tags in KNOWLEDGE:
        try:
            lm.store(content, tags=tags + ["software_dev"], importance=importance, source="batch_teach_software_dev")
            success += 1
        except Exception as e:
            print(f"存入失敗：{content[:40]}... → {e}")

    print(f"\n✅ 完成！成功存入 {success}/{len(KNOWLEDGE)} 筆軟體開發知識")
    print("立 AI 現在知道如何更好地開發軟體了！")

if __name__ == "__main__":
    main()

