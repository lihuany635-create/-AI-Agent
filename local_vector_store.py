# local_vector_store.py — 本地向量記憶庫（原本是空殼，現在補完）
# 使用純 Python 實現關鍵字向量搜尋，不需要安裝額外套件
# 若想升級為真正的向量搜尋，可安裝 chromadb：pip install chromadb

import json
import math
import pathlib
import datetime
from collections import Counter

try:
    from agent_logger import get_logger
    logger = get_logger("local_vector_store")
except ImportError:
    import logging
    logger = logging.getLogger("local_vector_store")

STORE_DIR  = pathlib.Path("memory")
STORE_FILE = STORE_DIR / "vector_store.json"
STORE_DIR.mkdir(exist_ok=True)


def _tokenize(text: str) -> list[str]:
    """簡易中英文分詞"""
    import re
    text = text.lower()
    # 英文單字 + 中文字元
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text)
    return tokens


def _tf_idf_score(query_tokens: list[str], doc_tokens: list[str]) -> float:
    """TF 相似度（簡化版）"""
    if not doc_tokens:
        return 0.0
    doc_counter = Counter(doc_tokens)
    score = sum(doc_counter.get(t, 0) for t in query_tokens)
    return score / len(doc_tokens)


class LocalVectorStore:
    """
    本地輕量向量記憶庫
    - 用 TF 相似度實現語意搜尋（不需要 GPU 或外部套件）
    - 支援命名空間分類（namespace）
    - 持久化到 JSON
    """

    def __init__(self, store_file: pathlib.Path = STORE_FILE):
        self.store_file = store_file
        self._docs: list[dict] = []
        self._load()
        logger.info(f"LocalVectorStore 啟動，已載入 {len(self._docs)} 筆")

    def add(self, text: str, metadata: dict = None, namespace: str = "default") -> str:
        """新增一筆文件"""
        doc_id = f"{namespace}_{len(self._docs)}_{datetime.datetime.now().strftime('%H%M%S')}"
        doc = {
            "id":        doc_id,
            "text":      text,
            "tokens":    _tokenize(text),
            "metadata":  metadata or {},
            "namespace": namespace,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self._docs.append(doc)
        self._save()
        logger.debug(f"新增文件：{text[:50]}")
        return doc_id

    def search(self, query: str, top_k: int = 5, namespace: str = None) -> list[dict]:
        """搜尋最相似的文件"""
        query_tokens = _tokenize(query)
        results = []
        for doc in self._docs:
            if namespace and doc["namespace"] != namespace:
                continue
            score = _tf_idf_score(query_tokens, doc["tokens"])
            if score > 0:
                results.append({**doc, "_score": score})
        results.sort(key=lambda x: x["_score"], reverse=True)
        return results[:top_k]

    def delete(self, doc_id: str) -> bool:
        before = len(self._docs)
        self._docs = [d for d in self._docs if d["id"] != doc_id]
        if len(self._docs) < before:
            self._save()
            return True
        return False

    def clear_namespace(self, namespace: str) -> int:
        before = len(self._docs)
        self._docs = [d for d in self._docs if d["namespace"] != namespace]
        removed = before - len(self._docs)
        if removed:
            self._save()
        return removed

    def count(self, namespace: str = None) -> int:
        if namespace:
            return sum(1 for d in self._docs if d["namespace"] == namespace)
        return len(self._docs)

    def _load(self):
        if self.store_file.exists():
            try:
                data = json.loads(self.store_file.read_text(encoding="utf-8"))
                # tokens 欄位不存舊資料，重新計算
                for d in data:
                    if "tokens" not in d:
                        d["tokens"] = _tokenize(d.get("text", ""))
                self._docs = data
            except Exception as e:
                logger.error(f"向量庫載入失敗：{e}")
                self._docs = []
        else:
            self._docs = []

    def _save(self):
        # 存檔時不儲存 tokens（太占空間，每次載入重算）
        to_save = [{k: v for k, v in d.items() if k != "tokens"} for d in self._docs]
        self.store_file.write_text(
            json.dumps(to_save, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


# 模組層級單例（與 core_boot.py 對齊）
_store = None

def get_store() -> LocalVectorStore:
    global _store
    if _store is None:
        _store = LocalVectorStore()
    return _store


if __name__ == "__main__":
    store = LocalVectorStore()
    store.add("修復 BOM 錯誤的方法", metadata={"type": "repair"}, namespace="knowledge")
    store.add("Ollama 預設端點是 localhost:11434", metadata={"type": "config"}, namespace="knowledge")
    store.add("qwen2.5:7b 中文效果最好", metadata={"type": "model"}, namespace="knowledge")

    print("搜尋「修復錯誤」：")
    for r in store.search("修復錯誤", namespace="knowledge"):
        print(f"  [{r['_score']:.3f}] {r['text']}")
