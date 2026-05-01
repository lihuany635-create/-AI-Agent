# claude_knowledge.py — Claude 知識庫管理系統
# 儲存結構：每個分類一個資料夾，每個問題一個 .txt 檔
# memory/claude_knowledge/
#   ├── 機器學習/
#   │   ├── 20250402_143022_Adam的偏差修正為何必要.txt
#   │   └── 20250402_150011_什麼是dropout.txt
#   ├── 程式設計/
#   │   └── 20250402_144500_Python遞迴怎麼用.txt
#   └── 其他/
#       └── ...

import pathlib
import datetime
import re

try:
    from agent_logger import get_logger
    logger = get_logger("claude_knowledge")
except ImportError:
    import logging
    logger = logging.getLogger("claude_knowledge")

# ── 設定 ─────────────────────────────────────────────────────────────────────
KNOWLEDGE_DIR = pathlib.Path("memory/claude_knowledge")
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

# 知識分類與關鍵字
CATEGORIES = {
    "機器學習": [
        "神經網路", "深度學習", "訓練", "模型", "梯度", "反向傳播",
        "注意力", "Transformer", "Adam", "損失函數", "過擬合",
        "batch", "epoch", "learning rate", "CNN", "RNN", "LSTM",
        "embedding", "softmax", "activation", "dropout", "正則化",
        "KV Cache", "attention", "Q/K/V", "backpropagation",
    ],
    "程式設計": [
        "Python", "函式", "類別", "演算法", "資料結構", "API",
        "除錯", "重構", "設計模式", "框架", "套件", "程式碼",
        "變數", "迴圈", "條件", "遞迴", "複雜度", "SQL",
        "JavaScript", "HTML", "CSS", "Git", "Docker",
    ],
    "數學": [
        "矩陣", "向量", "微積分", "線性代數", "機率", "統計",
        "導數", "積分", "偏微分", "特徵值", "行列式", "貝式",
        "期望值", "方差", "正態分布", "優化", "凸函數",
    ],
    "系統架構": [
        "架構", "微服務", "資料庫", "伺服器", "分散式", "快取",
        "負載均衡", "API設計", "RESTful", "容器", "雲端",
        "記憶體", "CPU", "GPU", "效能", "擴展", "部署",
    ],
    "工具使用": [
        "VS Code", "PyCharm", "Jupyter", "pip", "conda",
        "Linux", "Windows", "終端", "Shell", "指令", "工具",
        "設定", "安裝", "環境", "套件管理",
    ],
    "AI概念": [
        "人工智慧", "自然語言處理", "NLP", "生成式", "GPT",
        "大語言模型", "LLM", "提示工程", "prompt", "微調",
        "推論", "tokenizer", "向量資料庫", "RAG",
    ],
}

# ── 工具函式 ─────────────────────────────────────────────────────────────────

def _safe_filename(text: str, max_len: int = 30) -> str:
    """把問題文字轉成安全的檔名（去除不合法字元和換行符）"""
    cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]', "", text)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned[:max_len] if cleaned else "未命名"


def _category_dir(category: str) -> pathlib.Path:
    """取得分類資料夾路徑，不存在就建立"""
    d = KNOWLEDGE_DIR / category
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 核心類別 ─────────────────────────────────────────────────────────────────

class ClaudeKnowledge:
    """Claude 知識庫管理（資料夾 + 個別文字檔）"""

    def classify(self, question: str, answer: str) -> str:
        """自動分類：根據問題和回答的關鍵字判斷分類"""
        text = (question + " " + answer).lower()
        scores = {}
        for cat, keywords in CATEGORIES.items():
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > 0:
                scores[cat] = score
        return max(scores, key=scores.get) if scores else "其他"

    def store(self, question: str, answer: str, source: str = "claude_bridge") -> str:
        """
        存入一筆知識：
        - 自動分類 → 建立對應資料夾
        - 每個問題建立一個獨立 .txt 檔
        回傳分類名稱
        """
        category = self.classify(question, answer)
        cat_dir  = _category_dir(category)

        # 檔名：時間戳 + 問題前綴
        ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        q_slug   = _safe_filename(question)
        filename = f"{ts}_{q_slug}.txt"
        filepath = cat_dir / filename

        # 檔案內容
        content = (
            f"分類：{category}\n"
            f"來源：{source}\n"
            f"時間：{datetime.datetime.now().isoformat(timespec='seconds')}\n"
            f"{'─' * 40}\n"
            f"問：{question}\n"
            f"{'─' * 40}\n"
            f"答：{answer}\n"
        )

        try:
            filepath.write_text(content, encoding="utf-8")
            logger.info(f"[ClaudeKnowledge] 存入 [{category}]：{filename}")
        except Exception as e:
            logger.error(f"[ClaudeKnowledge] 寫檔失敗：{e}")

        return category

    def search(self, query: str, top_k: int = 5) -> list:
        """搜尋所有分類資料夾內的 .txt 檔"""
        query_lower = query.lower()
        results = []

        for txt_file in KNOWLEDGE_DIR.rglob("*.txt"):
            try:
                content = txt_file.read_text(encoding="utf-8")
            except Exception:
                continue

            score = sum(1 for word in query_lower.split() if word in content.lower())
            if score > 0:
                results.append({
                    "file":     txt_file.name,
                    "category": txt_file.parent.name,
                    "content":  content,
                    "_score":   score,
                })

        results.sort(key=lambda x: x["_score"], reverse=True)
        return results[:top_k]

    def get_stats(self) -> str:
        """取得知識庫統計（各分類資料夾的檔案數）"""
        lines = ["📚 Claude 知識庫統計\n"]
        total = 0
        for cat_dir in sorted(KNOWLEDGE_DIR.iterdir()):
            if not cat_dir.is_dir():
                continue
            count = len(list(cat_dir.glob("*.txt")))
            if count > 0:
                lines.append(f"  {cat_dir.name}：{count} 筆")
                total += count
        lines.insert(1, f"共 {total} 筆\n")
        return "\n".join(lines)

    def get_by_category(self, category: str, limit: int = 10) -> list:
        """取得某分類最新的 N 筆知識"""
        cat_dir = KNOWLEDGE_DIR / category
        if not cat_dir.exists():
            return []

        files = sorted(cat_dir.glob("*.txt"), reverse=True)[:limit]
        results = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
                question, answer = "", ""
                for line in text.splitlines():
                    if line.startswith("問："):
                        question = line[2:].strip()
                    elif line.startswith("答："):
                        answer = line[2:].strip()
                results.append({
                    "file":     f.name,
                    "question": question,
                    "answer":   answer,
                    "category": category,
                })
            except Exception:
                continue
        return results

    def get_all_categories(self) -> list:
        """取得所有有資料的分類名稱"""
        return [
            d.name for d in KNOWLEDGE_DIR.iterdir()
            if d.is_dir() and any(d.glob("*.txt"))
        ]


# ── 模組層級單例 ─────────────────────────────────────────────────────────────
_knowledge: ClaudeKnowledge = None

def get_knowledge() -> ClaudeKnowledge:
    global _knowledge
    if _knowledge is None:
        _knowledge = ClaudeKnowledge()
    return _knowledge


if __name__ == "__main__":
    kb = ClaudeKnowledge()
    cat = kb.store(
        "Adam 的偏差修正為何必要",
        "Adam 使用指數移動平均（EMA）追蹤梯度的一階和二階矩..."
    )
    print(f"分類結果：{cat}")
    print(kb.get_stats())
