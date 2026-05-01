import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
except Exception:
    pass

# teach_li.py — 批次知識匯入工具
# 使用方式：python teach_li.py
# 把知識直接存入立的長期記憶庫，不需要透過對話

import sys
import pathlib

# 確認在正確目錄
if not pathlib.Path("long_term_memory.py").exists():
    print("請在 AI-Agent 資料夾執行此程式")
    sys.exit(1)

from long_term_memory import get_memory
mem = get_memory()

# ── 知識庫 ────────────────────────────────────────────────────────────────────

KNOWLEDGE = [

    # ── Python 基礎 ──────────────────────────────────────────────────────────
    {
        "content": "Python 變數不需要宣告型別。字串用引號、整數直接寫、浮點數有小數點、布林值是 True/False。例如：name='立'、age=1、score=9.5、active=True",
        "tags": ["python", "基礎", "變數"],
        "importance": 8,
    },
    {
        "content": "Python 條件判斷用 if/elif/else，縮排是語法的一部分不能省略。例如：if x > 0: print('正數') elif x == 0: print('零') else: print('負數')",
        "tags": ["python", "基礎", "條件判斷"],
        "importance": 8,
    },
    {
        "content": "Python 有兩種迴圈。for 遍歷序列：for i in range(10): print(i)。while 條件重複：while x > 0: x -= 1。break 跳出迴圈，continue 跳過這次",
        "tags": ["python", "基礎", "迴圈"],
        "importance": 8,
    },
    {
        "content": "Python 函式用 def 定義，可以有預設參數和回傳值。例如：def greet(name='世界'): return f'你好，{name}！'。呼叫：greet('立') 回傳 '你好，立！'",
        "tags": ["python", "基礎", "函式"],
        "importance": 8,
    },
    {
        "content": "Python 串列 list 用中括號 [1,2,3]，字典 dict 用大括號 {'key': 'value'}。串列常用：append新增、pop移除、len長度。字典常用：keys()、values()、get()",
        "tags": ["python", "基礎", "資料結構"],
        "importance": 8,
    },
    {
        "content": "Python 用 try/except 處理錯誤。例如：try: result = 10/x except ZeroDivisionError: print('不能除以零') except Exception as e: print(f'錯誤：{e}') finally: print('一定執行')",
        "tags": ["python", "基礎", "錯誤處理"],
        "importance": 8,
    },
    {
        "content": "Python 用 class 定義類別，__init__ 是建構子，self 代表自己。例如：class Dog: def __init__(self, name): self.name = name def bark(self): return f'{self.name}：汪！'",
        "tags": ["python", "基礎", "類別"],
        "importance": 8,
    },
    {
        "content": "Python 讀寫檔案用 open()，建議用 with 語法自動關閉。讀取：with open('file.txt', 'r', encoding='utf-8') as f: content = f.read()。寫入：with open('file.txt', 'w', encoding='utf-8') as f: f.write('內容')",
        "tags": ["python", "基礎", "檔案"],
        "importance": 8,
    },

    # ── Python 進階 ──────────────────────────────────────────────────────────
    {
        "content": "Python 裝飾器 decorator 用 @ 符號，可以在不修改函式的情況下增加功能。例如：@timer 可以計算函式執行時間。常見裝飾器：@property、@staticmethod、@classmethod",
        "tags": ["python", "進階", "裝飾器"],
        "importance": 7,
    },
    {
        "content": "Python 串列生成式（list comprehension）可以簡化迴圈。例如：squares = [x**2 for x in range(10)]。條件版：evens = [x for x in range(20) if x % 2 == 0]",
        "tags": ["python", "進階", "生成式"],
        "importance": 7,
    },
    {
        "content": "Python lambda 是匿名函式，適合簡單的一次性函式。例如：add = lambda x, y: x + y。常搭配 sorted()、map()、filter() 使用：sorted(items, key=lambda x: x['name'])",
        "tags": ["python", "進階", "lambda"],
        "importance": 7,
    },
    {
        "content": "Python import 用來載入模組。標準庫：import os, sys, json, datetime, pathlib。第三方：import requests, numpy, pandas。自訂模組：from my_module import MyClass",
        "tags": ["python", "進階", "模組"],
        "importance": 8,
    },

    # ── AI 相關 ──────────────────────────────────────────────────────────────
    {
        "content": "Ollama 是本地 AI 模型伺服器，API 端點是 http://localhost:11434。呼叫方式：requests.post('http://localhost:11434/api/generate', json={'model': 'qwen2:7b-instruct-q4_0', 'prompt': '你好', 'stream': False})",
        "tags": ["ai", "ollama", "api"],
        "importance": 9,
    },
    {
        "content": "Prompt Engineering 基本原則：1.角色設定（你是一個...）2.明確任務 3.輸出格式（輸出JSON）4.範例（few-shot）5.限制條件。好的 prompt 比大的模型更重要",
        "tags": ["ai", "prompt", "engineering"],
        "importance": 9,
    },
    {
        "content": "JSON 在 Python 中的使用：import json。序列化：json.dumps(data, ensure_ascii=False)。反序列化：json.loads(text)。讀檔：json.loads(Path('file.json').read_text(encoding='utf-8'))。寫檔：Path('file.json').write_text(json.dumps(data, indent=2), encoding='utf-8')",
        "tags": ["python", "json", "資料"],
        "importance": 8,
    },

    # ── 系統程式 ─────────────────────────────────────────────────────────────
    {
        "content": "Python subprocess 用來執行系統指令。簡單執行：subprocess.run(['python', 'script.py'], capture_output=True, text=True, timeout=30)。背景執行：subprocess.Popen(['notepad'])",
        "tags": ["python", "系統", "subprocess"],
        "importance": 8,
    },
    {
        "content": "Python pathlib 是現代化的路徑處理方式。建立路徑：p = Path('memory/data.json')。讀取：p.read_text(encoding='utf-8')。寫入：p.write_text(content, encoding='utf-8')。檢查：p.exists()。建立資料夾：p.mkdir(parents=True, exist_ok=True)",
        "tags": ["python", "系統", "pathlib"],
        "importance": 8,
    },
    {
        "content": "Python threading 用來執行多執行緒。背景執行：t = threading.Thread(target=fn, daemon=True); t.start()。daemon=True 表示主程式結束時執行緒也跟著結束。避免競態條件用 threading.Lock()",
        "tags": ["python", "系統", "threading"],
        "importance": 7,
    },

    # ── 編程最佳實踐 ─────────────────────────────────────────────────────────
    {
        "content": "編程最佳實踐：1.函式只做一件事 2.變數名稱要有意義 3.加上 type hint（def fn(x: int) -> str）4.寫文件字串（docstring）5.錯誤要處理不要忽略 6.不要重複自己（DRY原則）",
        "tags": ["編程", "最佳實踐"],
        "importance": 9,
    },
    {
        "content": "Python AST（抽象語法樹）可以分析程式碼結構。import ast; tree = ast.parse(code)。用 ast.walk(tree) 遍歷所有節點。常用節點：FunctionDef、ClassDef、Import、ImportFrom。可以在不執行程式碼的情況下檢查語法",
        "tags": ["python", "ast", "程式碼分析"],
        "importance": 7,
    },
]

# ── 匯入執行 ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("立 AI 知識匯入工具")
    print("=" * 50)
    print(f"準備匯入 {len(KNOWLEDGE)} 筆知識\n")

    success = 0
    for i, item in enumerate(KNOWLEDGE, 1):
        try:
            mem_id = mem.store(
                content=item["content"],
                tags=item["tags"],
                importance=item["importance"],
                source="claude_teaching"
            )
            tag_str = ", ".join(item["tags"])
            print(f"[{i:2d}/{len(KNOWLEDGE)}] OK {tag_str}")
            success += 1
        except Exception as e:
            print(f"[{i:2d}/{len(KNOWLEDGE)}] FAIL 失敗：{e}")

    print(f"\n完成！成功匯入 {success}/{len(KNOWLEDGE)} 筆")
    print(f"立的記憶庫現在共有 {len(mem._memories)} 筆知識")
    print("\n現在可以問立 Python 相關問題了！")

if __name__ == "__main__":
    main()

