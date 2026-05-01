class SyntaxClassifier:

    def classify(self, error_message):

        if not error_message:
            return "UNKNOWN"

        msg = error_message.lower()

        # ⭐ colon missing（第一條 heuristic）
        if "invalid syntax" in msg:
            return "MISSING_COLON"

        if "unexpected indent" in msg:
            return "INDENT_ERROR"

        if "unindent does not match" in msg:
            return "INDENT_ERROR"

        if "was never closed" in msg:
            return "BRACKET_MISMATCH"

        if "expected an indented block" in msg:
            return "INCOMPLETE_BLOCK"

        return "UNKNOWN"