# reasoning_supervisor.py

import requests


class ReasoningSupervisor:

    def __init__(self):
        self.repair_history = {}
        self.loop_threshold = 3
        self.model = "gpt-oss:20b"   # 固定模型，不允許外部變更
        self.url = "http://localhost:11434/api/chat"

    # =========================
    # 主監督入口
    # =========================
    def approve_repair(self, file, error_type, action):

        # ===== 第一層：規則防呆 =====
        rule = self._rule_check(file, error_type)
        if not rule["approved"]:
            return rule

        # ===== 第二層：LLM 推理 =====
        llm = self._llm_reason(file, error_type, action)

        return llm

    # =========================
    # 規則審核
    # =========================
    def _rule_check(self, file, error_type):

        key = (file, error_type)

        if key not in self.repair_history:
            self.repair_history[key] = 0

        self.repair_history[key] += 1

        if self.repair_history[key] > self.loop_threshold:
            return {
                "approved": False,
                "reason": "repair_loop_detected"
            }

        if error_type == "UNKNOWN_ERROR":
            return {
                "approved": False,
                "reason": "unknown_error"
            }

        return {"approved": True}

    # =========================
    # LLM 推理審核
    # =========================
    def _llm_reason(self, file, error_type, action):

        prompt = f"""
系統準備執行一個自動修復動作。

檔案: {file}
錯誤類型: {error_type}
修復策略: {action}

請判斷這個修復是否合理？
只回答：

APPROVE
或
REJECT:理由
"""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是嚴格的程式碼修復審核員，只回答 APPROVE 或 REJECT:理由。"},
                {"role": "user",   "content": prompt}
            ],
            "stream": False
        }

        try:
            r = requests.post(self.url, json=payload, timeout=None)
            text = r.json().get("message", {}).get("content", "").strip()

            if text.startswith("REJECT"):
                return {
                    "approved": False,
                    "reason": text
                }

            return {"approved": True}

        except Exception as e:
            return {
                "approved": False,
                "reason": f"LLM_ERROR {e}"
            }