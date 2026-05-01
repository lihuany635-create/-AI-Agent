import ast
from pathlib import Path


class RepairValidator:

    def validate(self, before_code: str, after_code: str):
        result = {
            "valid": True,
            "score": 1.0,
            "flags": []
        }

        # 1️⃣空檔 / 幾乎空
        if len(after_code.strip()) < 5:
            result["valid"] = False
            result["score"] = 0.0
            result["flags"].append("EMPTY_FILE")
            return result

        # 2️⃣ 全註解（簡單判斷）
        lines = [l.strip() for l in after_code.splitlines() if l.strip()]
        if lines and all(l.startswith("#") for l in lines):
            result["valid"] = False
            result["score"] = 0.1
            result["flags"].append("ALL_COMMENTED")

        # 3️⃣ AST 可解析
        try:
            ast.parse(after_code)
        except Exception:
            result["valid"] = False
            result["score"] = 0.2
            result["flags"].append("AST_BROKEN")
            return result

        # 4️⃣ 改動幅度過大（粗略）
        before_len = len(before_code.splitlines())
        after_len = len(after_code.splitlines())
        if before_len > 0:
            ratio = abs(after_len - before_len) / before_len
            if ratio > 5:
                result["flags"].append("LARGE_REWRITE")
                result["score"] *= 0.5

        return result