# repair_strategy_engine.py — 修復策略引擎（原本是空殼，現在補完）
# 負責根據錯誤類型和歷史記錄，動態選擇最佳修復策略

import json
import pathlib
from typing import Optional

try:
    from agent_logger import get_logger
    logger = get_logger("repair_strategy_engine")
except ImportError:
    import logging
    logger = logging.getLogger("repair_strategy_engine")

try:
    from repair_memory import RepairMemory
    _repair_memory = RepairMemory()
except Exception:
    _repair_memory = None


# 內建策略定義
BUILTIN_STRATEGIES = {
    "SYNTAX_ERROR": [
        {"name": "fix_missing_colon",   "priority": 1, "description": "補上缺少的冒號"},
        {"name": "fix_indent_error",    "priority": 2, "description": "修復縮排錯誤"},
        {"name": "fix_bracket_mismatch","priority": 3, "description": "修復括號不匹配"},
        {"name": "fix_incomplete_block","priority": 4, "description": "補完不完整的程式區塊"},
        {"name": "llm_repair",          "priority": 5, "description": "LLM 完整重寫"},
    ],
    "RUNTIME_ERROR": [
        {"name": "fix_zero_division",   "priority": 1, "description": "修復除以零"},
        {"name": "fix_attribute_error", "priority": 2, "description": "修復屬性錯誤"},
        {"name": "fix_type_error",      "priority": 3, "description": "修復型別錯誤"},
        {"name": "fix_name_error",      "priority": 4, "description": "修復未定義變數"},
        {"name": "fix_import_error",    "priority": 5, "description": "修復 import 錯誤"},
        {"name": "llm_repair",          "priority": 6, "description": "LLM 完整重寫"},
    ],
    "FILE_READ_ERROR": [
        {"name": "fix_encoding",        "priority": 1, "description": "修復編碼問題（BOM）"},
        {"name": "fix_path",            "priority": 2, "description": "修復檔案路徑"},
    ],
}


class RepairStrategyEngine:
    """
    動態修復策略選擇器
    - 根據錯誤類型取得候選策略清單
    - 根據 RepairMemory 的歷史成功率排序
    - 支援策略黑名單（避免重複失敗的策略）
    """

    def __init__(self):
        self.memory = _repair_memory
        self._blacklist: dict[str, set] = {}  # file_path → {strategy_name}

    def get_strategies(self, error_type: str, file_path: str = None) -> list[dict]:
        """
        取得針對此錯誤類型的策略清單（已按成功率排序）
        """
        base = BUILTIN_STRATEGIES.get(error_type, [
            {"name": "llm_repair", "priority": 1, "description": "LLM 完整重寫（未知錯誤備援）"}
        ])

        # 過濾黑名單
        blacklisted = self._blacklist.get(file_path, set()) if file_path else set()
        candidates = [s for s in base if s["name"] not in blacklisted]

        # 若有 RepairMemory，用歷史成功率重新排序
        if self.memory:
            priority_map = self.memory.get_strategy_priority(error_type)
            candidates.sort(
                key=lambda s: -priority_map.get(s["name"], 0)
            )

        logger.debug(f"[{error_type}] 候選策略：{[s['name'] for s in candidates]}")
        return candidates

    def pick_best(self, error_type: str, file_path: str = None) -> Optional[dict]:
        """取得最佳策略（第一個）"""
        strategies = self.get_strategies(error_type, file_path)
        if strategies:
            return strategies[0]
        return None

    def blacklist(self, file_path: str, strategy_name: str):
        """將某策略加入黑名單（此次修復循環不再使用）"""
        if file_path not in self._blacklist:
            self._blacklist[file_path] = set()
        self._blacklist[file_path].add(strategy_name)
        logger.info(f"策略黑名單：{file_path} → {strategy_name}")

    def clear_blacklist(self, file_path: str):
        """清除某檔案的黑名單（修復成功後呼叫）"""
        self._blacklist.pop(file_path, None)

    def record_result(self, error_type: str, strategy_name: str, success: bool, quality: float = None):
        """記錄策略執行結果，更新 RepairMemory"""
        if self.memory:
            self.memory.record(error_type, strategy_name, success, quality)
            logger.info(f"策略結果記錄：{strategy_name} → {'成功' if success else '失敗'}")

    def classify_error_difficulty(self, error_type: str) -> str:
        """評估此錯誤的修復難度"""
        if self.memory:
            return self.memory.classify_failure(error_type)
        return "unknown"

    def get_all_strategies(self) -> dict:
        """回傳所有內建策略（供除錯用）"""
        return BUILTIN_STRATEGIES


# 模組層級單例
_engine = None

def get_strategy_engine() -> RepairStrategyEngine:
    global _engine
    if _engine is None:
        _engine = RepairStrategyEngine()
    return _engine


if __name__ == "__main__":
    engine = RepairStrategyEngine()

    print("SYNTAX_ERROR 策略清單：")
    for s in engine.get_strategies("SYNTAX_ERROR"):
        print(f"  [{s['priority']}] {s['name']}: {s['description']}")

    print("\nRUNTIME_ERROR 最佳策略：")
    best = engine.pick_best("RUNTIME_ERROR")
    print(f"  → {best}")
