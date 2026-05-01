class LearningEngine:

    def evaluate(self, input_text, output_text):
        """
        最基礎學習評估
        之後會升級為 meta learning
        """

        score = 0

        # 簡單 heuristic（第一版）
        if len(output_text) < 5:
            score -= 1

        if "錯誤" in output_text:
            score -= 2

        if "完成" in output_text:
            score += 1

        if "成功" in output_text:
            score += 1

        return score