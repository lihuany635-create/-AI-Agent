"""
long_term_memory.py - 長期記憶持久化系統
功能：
  - 跨次對話保留重要知識（寫入 JSON 檔案）
  - 支援標籤分類、重要性評分、過期清理
  - 語義搜尋（關鍵字比對，不需要向量資料庫）
  - 與現有 episodic_memory / reflex_memory 整合
使用方式：
    from long_term_memory import LongTermMemory
    mem = LongTermMemory()
    mem.store("修復 BOM 錯誤的方法是移除 \\xef\\xbb\\xbf", tags=["repair", "encoding"])
    results = mem.search("BOM 錯誤")
"""

import json
import pathlib
import datetime
import uuid
from typing import Optional

try:
    from agent_logger import get_logger
    logger = get_logger("long_term_memory")
except ImportError:
    import logging
    logger = logging.getLogger("long_term_memory")

# 記憶存放路徑
MEMORY_DIR  = pathlib.Path("memory")
MEMORY_FILE = MEMORY_DIR / "long_term_memory.json"
MEMORY_DIR.mkdir(exist_ok=True)

class LongTermMemory:
    """
    長期記憶系統
    每筆記憶包含：
      id        - 唯一識別碼
      content   - 記憶內容（字串）
      tags      - 標籤清單（方便分類搜尋）
      importance - 重要性 1~10（越高越不會被清除）
      created_at - 建立時間
      accessed_at - 最後存取時間
      access_count - 被存取次數（越常用越重要）
    """

    def __init__(self, memory_file: pathlib.Path = MEMORY_FILE):
        self.memory_file = memory_file
        self._memories: list[dict] = []
        self._load()
        logger.info(f"長期記憶系統啟動，已載入 {len(self._memories)} 筆記憶")

    # ── 存取 ────────────────────────────────────────────────────────────────

    # 只允許這些來源寫入長期記憶（其他來源全部拒絕）
    ALLOWED_SOURCES = {
        "manual",        # 桌面手動輸入
        "mobile_manual", # 手機手動輸入
        "correction",    # 使用者糾正
        "user_teach",    # 教學模式手動輸入
    }

    def store(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        importance: int = 5,
        source: str = "agent",
    ) -> str:
        """儲存一筆記憶，回傳記憶 ID（只允許手動來源）"""
        if source not in self.ALLOWED_SOURCES:
            logger.debug(f"[記憶] 拒絕自動寫入（來源：{source}）：{content[:40]}")
            return ""
        if not content.strip():
            return ""
        # 去重：內容完全相同就不重複存
        for m in self._memories:
            if m["content"].strip() == content.strip():
                m["access_count"] += 1
                m["accessed_at"] = self._now()
                self._save()
                logger.debug(f"記憶已存在，更新存取次數：{content[:40]}...")
                return m["id"]

        memory = {
            "id":           str(uuid.uuid4())[:8],
            "content":      content,
            "tags":         tags or [],
            "importance":   max(1, min(10, importance)),
            "source":       source,
            "created_at":   self._now(),
            "accessed_at":  self._now(),
            "access_count": 1,
        }
        self._memories.append(memory)
        self._save()
        logger.info(f"[記憶] 儲存：{content[:60]}...")
        return memory["id"]

    def search(self, query: str, top_k: int = 5, tag: Optional[str] = None) -> list[dict]:
        """關鍵字搜尋記憶，回傳最相關的 top_k 筆"""
        query_words = set(query.lower().split())
        results = []
        for m in self._memories:
            # 標籤過濾
            if tag and tag not in m["tags"]:
                continue
            # 關鍵字比對得分
            text = (m["content"] + " " + " ".join(m["tags"])).lower()
            score = sum(1 for w in query_words if w in text)
            score += m["importance"] * 0.1  # 重要性加成
            score += min(m["access_count"] * 0.05, 1.0)  # 常用加成
            if score > 0:
                results.append({**m, "_score": score})

        results.sort(key=lambda x: x["_score"], reverse=True)
        top = results[:top_k]

        # 更新存取時間
        ids = {r["id"] for r in top}
        for m in self._memories:
            if m["id"] in ids:
                m["accessed_at"] = self._now()
                m["access_count"] += 1
        if top:
            self._save()

        logger.debug(f"搜尋「{query}」，找到 {len(top)} 筆")
        return top

    def get_by_tag(self, tag: str) -> list[dict]:
        """取得某標籤下所有記憶"""
        return [m for m in self._memories if tag in m["tags"]]

    def forget(self, memory_id: str) -> bool:
        """刪除指定記憶"""
        before = len(self._memories)
        self._memories = [m for m in self._memories if m["id"] != memory_id]
        if len(self._memories) < before:
            self._save()
            logger.info(f"已刪除記憶 ID：{memory_id}")
            return True
        return False

    def prune(self, max_memories: int = 500) -> int:
        """清理低重要性、少存取的舊記憶，保持在 max_memories 以內"""
        if len(self._memories) <= max_memories:
            return 0
        # 排序：importance 低、access_count 少、最舊的優先刪除
        self._memories.sort(key=lambda m: (m["importance"], m["access_count"], m["created_at"]))
        to_remove = len(self._memories) - max_memories
        self._memories = self._memories[to_remove:]
        self._save()
        logger.info(f"記憶清理完成，刪除 {to_remove} 筆，剩餘 {len(self._memories)} 筆")
        return to_remove

    def summary(self) -> dict:
        """回傳記憶庫概況"""
        tags = {}
        for m in self._memories:
            for t in m["tags"]:
                tags[t] = tags.get(t, 0) + 1
        return {
            "total": len(self._memories),
            "tags":  tags,
            "oldest": self._memories[0]["created_at"] if self._memories else None,
        }

    # ── 內部工具 ────────────────────────────────────────────────────────────

    def _load(self):
        if self.memory_file.exists():
            try:
                self._memories = json.loads(self.memory_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"記憶載入失敗：{e}，重置為空白")
                self._memories = []
        else:
            self._memories = []

    def _save(self):
        try:
            self.memory_file.write_text(
                json.dumps(self._memories, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"記憶儲存失敗：{e}")

    def _now(self) -> str:
        return datetime.datetime.now().isoformat(timespec="seconds")



# ── 單例 ─────────────────────────────────────────────────────────────────
_instance = None

def get_memory():
    """取得全域唯一的 LongTermMemory 實例（避免重複載入 JSON）"""
    global _instance
    if _instance is None:
        _instance = LongTermMemory()
    return _instance

# ── 使用範例 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mem = LongTermMemory()

    # 儲存幾筆記憶
    mem.store("修復 BOM 錯誤：移除檔案開頭的 \\xef\\xbb\\xbf 字元", tags=["repair", "encoding"], importance=8)
    mem.store("Ollama 預設 API 端點為 http://localhost:11434", tags=["ollama", "config"], importance=9)
    mem.store("qwen2.5:7b 是中文最強的本地模型之一", tags=["model", "ollama"], importance=7)
    mem.store("repair_engine 修復策略：先 AST 分析，再語法重寫", tags=["repair", "strategy"], importance=8)

    # 搜尋
    print("\n搜尋「修復錯誤」：")
    for r in mem.search("修復錯誤"):
        print(f"  [{r['importance']}★] {r['content'][:60]}")

    print("\n記憶庫概況：")
    print(mem.summary())
