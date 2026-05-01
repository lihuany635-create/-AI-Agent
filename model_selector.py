# model_selector.py — 智能模型選擇器
# 根據任務類型自動選擇最適合的本地模型
# 立會根據你的需求自動切換，不需要手動指定
# 修復：deepseek-r1:1.5b 分數過高的問題，加入模型大小權重

import requests
from typing import Optional

try:
    from agent_logger import get_logger
    logger = get_logger("model_selector")
except ImportError:
    import logging
    logger = logging.getLogger("model_selector")

# ── 模型能力評分表 ────────────────────────────────────────────────────────────
# 分數 1~10，越高越適合該任務
# 重要：分數要反映「實際回答品質」，不只是模型的設計用途
#       1.5B 模型再怎麼專精，實際品質都不如 7B 通用模型
MODEL_PROFILES = {
    "qwen2.5:14b": {
        "coding":      10,  # 程式生成最強
        "reasoning":   10,
        "chinese":     10,  # 中文極強
        "general":     10,
        "creative":     9,
        "math":         9,
        "size":        14,  # 14B 參數
        "description": "最強模型，適合自主開發、複雜推理、程式生成",
    },
    "qwen2:7b-instruct-q4_0": {
        "coding":       8,
        "reasoning":    8,
        "chinese":     10,  # 中文最強
        "general":     10,  # 通用最強
        "creative":     8,
        "math":         7,
        "size":         7,  # 7B 參數
        "description": "中文最強，適合一般對話、繁體中文回覆、程式問答",
    },
    "qwen2:7b": {
        "coding":       8,
        "reasoning":    8,
        "chinese":     10,
        "general":      9,
        "creative":     8,
        "math":         7,
        "size":         7,
        "description": "中文最強，適合一般對話",
    },
    "mistral:7b": {
        "coding":       8,
        "reasoning":    8,
        "chinese":      5,  # 中文較弱
        "general":      8,
        "creative":     7,
        "math":         8,
        "size":         7,
        "description": "英文能力強，適合英文程式碼、debug",
    },
    "llama3.2:latest": {
        "coding":       8,
        "reasoning":    8,
        "chinese":      5,
        "general":      8,
        "creative":     7,
        "math":         7,
        "size":         7,
        "description": "均衡能力強，適合英文任務",
    },
    "llama3:latest": {
        "coding":       8,
        "reasoning":    8,
        "chinese":      5,
        "general":      8,
        "creative":     7,
        "math":         7,
        "size":         7,
        "description": "均衡能力強",
    },
    "gemma4:latest": {
        "coding":       6,
        "reasoning":    6,
        "chinese":      5,
        "general":      7,
        "creative":     8,
        "math":         5,
        "size":         4,
        "description": "創意和寫作能力強，但模型較小",
    },
    "deepseek-r1:1.5b": {
        "coding":       3,  # 1.5B 太小，實際程式碼品質差
        "reasoning":    4,  # 推理能力受限於參數量
        "chinese":      3,  # 中文品質差
        "general":      2,  # 通用能力最弱
        "creative":     2,
        "math":         5,  # 數學稍好但仍不如 7B
        "size":       1.5,
        "description": "模型太小（1.5B），僅供簡單數學計算備用",
    },
}

# ── 最低模型大小 ──────────────────────────────────────────────────────────────
# 低於這個大小的模型不會被自動選擇（手動切換仍可用）
MIN_MODEL_SIZE = 4  # 至少 4B 參數

# ── 任務類型關鍵字 ────────────────────────────────────────────────────────────
TASK_KEYWORDS = {
    "coding": [
        "寫程式", "寫code", "寫碼", "程式碼", "函式", "函數", "class",
        "debug", "修bug", "錯誤", "exception", "import", "def ",
        "幫我做", "幫我建", "開發", "實作", "implement",
        "python", "javascript", "html", "css", "sql",
        "修改", ".py",
    ],
    "reasoning": [
        "分析", "判斷", "推理", "邏輯", "為什麼", "原因", "解釋",
        "比較", "優缺點", "評估", "診斷", "規劃", "策略",
        "注意什麼", "要注意", "怎麼做",
    ],
    "math": [
        "計算", "數學", "公式", "方程式", "統計", "機率",
        "加減乘除", "平均", "百分比", "微積分",
    ],
    "creative": [
        "寫文章", "寫故事", "創作", "詩", "廣告", "文案",
        "想法", "靈感", "設計", "創意",
    ],
    "chinese": [
        "翻譯", "繁體", "中文", "台灣", "文章", "說明",
    ],
}


class ModelSelector:

    def __init__(self):
        self._available = self._get_available_models()
        self._current   = self._default_model()
        logger.info(f"模型選擇器啟動，可用模型：{self._available}")
        logger.info(f"預設模型：{self._current}")

    def _get_available_models(self) -> list:
        """取得目前 Ollama 已下載的模型"""
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            return [m for m in models if m in MODEL_PROFILES]
        except Exception:
            return ["qwen2:7b-instruct-q4_0"]

    def _default_model(self) -> str:
        """預設使用 gemma4，備用 qwen2 系列"""
        for preferred in ["gemma4:latest", "qwen2.5:14b", "qwen2:7b-instruct-q4_0", "qwen2:7b"]:
            if preferred in self._available:
                return preferred
        return self._available[0] if self._available else "gemma4:latest"

    def detect_task_type(self, text: str) -> str:
        """偵測任務類型"""
        text_lower = text.lower()
        scores = {task: 0 for task in TASK_KEYWORDS}

        for task, keywords in TASK_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[task] += 1

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return "general"
        return best

    def select(self, text: str) -> str:
        """強制使用 gemma4:latest"""
        self._current = "gemma4:latest"
        return "gemma4:latest"

    def force_switch(self, model_name: str) -> str:
        """手動強制切換模型（不受大小限制）"""
        if model_name in self._available:
            self._current = model_name
            logger.info(f"[手動切換] 模型切換為：{model_name}")
            return f"已切換到 {model_name}"
        # 模糊比對
        for m in self._available:
            if model_name.lower() in m.lower():
                self._current = m
                logger.info(f"[手動切換] 模型切換為：{m}")
                return f"已切換到 {m}"
        return f"找不到模型：{model_name}，可用：{', '.join(self._available)}"

    def current(self) -> str:
        return self._current

    def status(self) -> str:
        """回傳目前模型狀態"""
        lines = [f"目前模型：{self._current}\n", "可用模型："]
        for m in self._available:
            profile = MODEL_PROFILES.get(m, {})
            desc = profile.get("description", "")
            size = profile.get("size", "?")
            marker = "▶ " if m == self._current else "  "
            lines.append(f"{marker}{m} ({size}B) — {desc}")
        return "\n".join(lines)


# ── 模組層級單例 ──────────────────────────────────────────────────────────────
_selector: Optional[ModelSelector] = None

def get_selector() -> ModelSelector:
    global _selector
    if _selector is None:
        _selector = ModelSelector()
    return _selector


if __name__ == "__main__":
    s = ModelSelector()
    tests = [
        "幫我寫一個 Python 函式",
        "修改程式碼前要注意什麼？",
        "分析這個問題的原因",
        "計算 123 * 456",
        "你好，今天天氣怎麼樣",
        "幫我寫一篇文章",
        "我的專案路徑在哪？",
    ]
    print(f"預設模型：{s.current()}\n")
    for t in tests:
        model = s.select(t)
        task  = s.detect_task_type(t)
        print(f"[{task:10s}] {model:35s} ← {t}")
