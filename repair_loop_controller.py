class RepairLoopController:

    def __init__(self, detector, trigger, max_rounds=3):
        self.detector = detector
        self.trigger = trigger
        self.max_rounds = max_rounds

    def run(self, file_path):

        last_error_signature = None

        for round_id in range(1, self.max_rounds + 1):

            error = self.detector.detect_file_error(file_path)

            if not error:
                return {
                    "status": "SUCCESS",
                    "rounds": round_id - 1
                }

            # ⭐ 建立錯誤簽名
            current_signature = (
                error.get("type"),
                error.get("error_class"),
                error.get("message")
            )

            # ⭐ 無進展檢查
            if current_signature == last_error_signature:
                return {
                    "status": "STOP_NO_PROGRESS",
                    "round": round_id,
                    "error": error
                }

            last_error_signature = current_signature

            result = self.trigger.trigger(file_path, error)

            if result.get("status") != "FIXED":
                return {
                    "status": "FAILED",
                    "round": round_id,
                    "reason": result
                }

        return {
            "status": "MAX_ROUNDS_REACHED"
        }