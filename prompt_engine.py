import re
from cognition_state_manager import get_current_context


# 全域記憶庫實例（避免每次重新建立）
_long_term_memory = None

def _get_memory():
    global _long_term_memory
    if _long_term_memory is None:
        try:
            from long_term_memory import get_memory
            _long_term_memory = get_memory()
        except Exception:
            pass
    return _long_term_memory


def _extract_keywords(text: str) -> list:
    """從使用者輸入提取關鍵字，用於搜尋記憶庫"""
    stop_words = {"什麼", "怎麼", "如何", "是否", "可以", "嗎", "呢", "的", "了",
                  "要", "有", "在", "和", "與", "或", "到", "給", "讓", "把",
                  "前", "後", "上", "下", "請", "幫", "我", "你", "他", "她",
                  "這", "那", "哪", "誰", "為", "能", "會", "該", "被", "從",
                  "注意", "需要", "應該", "一下", "知道", "告訴", "之前",
                  "什麼", "怎樣", "哪些", "做什", "該做"}

    # 已知詞彙（優先匹配）
    known_terms = [
        # 個人
        "名字", "名稱", "主人", "叫什麼", "電腦", "環境",
        # 開發
        "程式碼", "備份", "修改", "檔案", "編碼", "記憶庫", "模型",
        "桌面", "視窗", "截圖", "終端", "指令", "開發", "教學",
        "對話", "模式", "系統", "路徑", "專案", "資料夾",
        "執行緒", "安全", "儲存", "刪除", "建立", "測試",
        # 工具
        "Telegram", "Bot", "Ollama", "Python", "PyQt6",
        "backup", "engine", "UTF-8", "BOM", "code",
        # 架構
        "Lobster", "Core", "記憶", "排程", "任務",
        "認知", "意圖", "路由", "反射",
        # 問題詞
        "能力", "功能", "偏好", "喜歡", "設定", "字體",
    ]

    # 常見同義詞轉換（使用者說法 → 記憶庫用詞）
    synonyms = {
        # 英文
        "code": "程式碼", "backup": "備份",
        # 單字中文 → 記憶庫用詞
        "改": "修改", "刪": "刪除", "建": "建立", "存": "儲存",
        "叫": "主人", "跑": "執行",
        # 多字同義
        "名字": "主人", "路徑": "專案", "在哪": "路徑",
        "目錄": "資料夾", "寫程式": "程式碼",
        "改code": "修改", "改程式": "修改",
    }

    keywords = []

    # 1. 先把中英文分開：「改code之前」→ [「改」, 「code」, 「之前」]
    parts = re.findall(r'[a-zA-Z0-9_.]+|[\u4e00-\u9fff]+', text)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # 英文部分：直接當關鍵字
        if re.match(r'^[a-zA-Z0-9_.]+$', part):
            if len(part) >= 2:
                keywords.append(part.lower())
            continue

        # 中文部分：單字也檢查同義詞
        if len(part) == 1:
            if part in synonyms:
                keywords.append(synonyms[part])
            continue

        # 中文部分：先匹配已知詞彙
        found = []
        for term in known_terms:
            if term in part:
                found.append(term)

        if found:
            keywords.extend(found)
        else:
            # 沒匹配到，用 2-3 字滑動窗口
            for size in [3, 2]:
                for i in range(len(part) - size + 1):
                    chunk = part[i:i+size]
                    if chunk not in stop_words and len(chunk) >= 2:
                        keywords.append(chunk)

    # 所有關鍵字做同義詞擴展
    expanded = []
    for kw in keywords:
        expanded.append(kw)
        if kw in synonyms:
            expanded.append(synonyms[kw])

    # 去重保持順序
    return list(dict.fromkeys(expanded))


class PromptEngine:

    SYSTEM = """你是「立」，一個在本地電腦運行的 AI 助理。主人叫顏立桓。

## 回答規則（最重要，每次都要遵守）
- 預設用繁體中文回答，絕對不用簡體
- 如果主人用英文問，就用英文回答
- 最多 3 句話，除非主人要求詳細說明
- 直接回答問題本身，不要加「如果你需要」「請告訴我」「如有問題」之類的廢話
- 不要重複主人的問題
- 不要加範例程式碼，除非主人明確要求

## 理解問題的方法（解決聽不懂的問題）
- 先找出問題的核心意圖，不要只看表面文字
- 「修改程式碼前要注意什麼」和「改 code 之前該做什麼」是同一個問題
- 「你知道我叫什麼嗎」和「我的名字是什麼」是同一個問題
- 如果問題模糊，回答最可能的意思，不要反問

## 知識來源標註
- 答案來自「已知知識」→ 開頭寫 [記憶庫]
- 答案來自你的訓練資料 → 開頭寫 [模型知識]
- 不確定或不知道 → 直接說「我不知道」
- 「已知知識」優先度最高

## 分析問題的方法
- 被問「為什麼」時，要解釋原因，不要只描述現象
- 被問「怎麼解決」時，要給具體步驟，不要給籠統建議
- 被問比較題時，要列出差異，不要各自描述"""

    def build_prompt(self, text, episodic):

        context = get_current_context()

        # ── 情節記憶（最近 2 輪就好，太多會干擾）────────────────
        recent = episodic.search_recent(2)
        mem = ""
        if recent:
            mem = "\n[最近對話]"
            for e in recent:
                mem += f"\n  Q: {e['input'][:60]}"
                mem += f"\n  A: {e['response'][:60]}"

        # ── 長期記憶（快速單次掃描）────────────────────────────
        long_mem = ""
        lm = _get_memory()
        if lm:
            try:
                # 提取關鍵字 + 語義擴展
                keywords = _extract_keywords(text)

                keyword_map = {
                    # 個人資訊
                    "名字": ["主人", "叫"],
                    "叫什麼": ["主人", "叫"],
                    "叫啥": ["主人", "叫"],
                    "誰": ["主人", "叫"],
                    # 專案
                    "路徑": ["路徑", "資料夾", "專案"],
                    "在哪": ["路徑", "資料夾", "專案"],
                    "目錄": ["路徑", "資料夾"],
                    # 功能
                    "能力": ["能力", "功能", "模式"],
                    "能做": ["能力", "功能"],
                    "會什麼": ["能力", "功能"],
                    # 工具
                    "指令": ["指令", "Bot"],
                    "模型": ["模型", "Ollama", "qwen"],
                    # 開發
                    "備份": ["備份", "backup"],
                    "編碼": ["編碼", "UTF-8", "BOM"],
                    "修改": ["修改", "備份", "程式碼"],
                    "改code": ["修改", "備份", "程式碼"],
                    "改程式": ["修改", "備份", "程式碼"],
                    # 偏好
                    "喜歡": ["喜歡", "偏好", "主題"],
                    "風格": ["喜歡", "偏好", "主題", "字體"],
                }
                for kw in list(keywords):
                    if kw in keyword_map:
                        keywords.extend(keyword_map[kw])
                # 去重
                keywords = list(dict.fromkeys(keywords))

                # 加入原始輸入的文字片段（用於比對）
                text_lower = text.lower()

                # 一次掃描所有記憶，計算相關度
                scored = []
                for m in lm._memories:
                    content = m["content"]
                    content_lower = content.lower()

                    # 跳過問答記錄
                    if content.startswith("問：") and "→ 答：" in content:
                        continue

                    # 計算關鍵字命中數
                    hits = sum(1 for kw in keywords if kw.lower() in content_lower)

                    # 原始輸入的文字比對（額外加分）
                    if any(w in content_lower for w in text_lower.split() if len(w) >= 2):
                        hits += 1

                    if hits > 0:
                        imp = m.get("importance", 5)
                        score = hits * 10 + imp
                        scored.append((score, m))

                # 排序取前 5
                scored.sort(key=lambda x: x[0], reverse=True)
                top = [m for _, m in scored[:5]]

                if top:
                    long_mem = "\n[已知知識]（你必須優先根據這些內容回答，這是主人教你的）"
                    for r in top:
                        stars = "*" * min(r.get("importance", 5), 5)
                        content = r["content"][:200]
                        long_mem += f"\n  {stars} {content}"

            except Exception:
                pass

        # ── 組合 prompt（不含系統 prompt，系統 prompt 由 _infer 另外傳）──
        parts = []

        if long_mem:
            parts.append(long_mem)
        else:
            parts.append("\n[已知知識]\n  （記憶庫中沒有找到相關知識，請用你自己的知識回答並開頭寫「[模型知識]」，如果不知道就說「我不知道」）")

        if mem:
            parts.append(mem)

        if context:
            # 只保留最近 3 輪，避免太多上下文干擾回答
            lines = context.strip().split("\n")
            if len(lines) > 6:  # 每輪 2 行（使用者+立）
                lines = lines[-6:]
            parts.append(f"\n[上下文]\n" + "\n".join(lines))

        parts.append(f"\n[使用者輸入]\n{text}")
        parts.append("\n[你的回答]")

        return "\n".join(parts)

