class RepairTrigger:

    def __init__(self, repair_engine, supervisor):
        self.repair_engine = repair_engine
        self.supervisor = supervisor

    def trigger(self, file_path, error_info):

        # ⭐ 1. error sanity check
        if not error_info or not isinstance(error_info, dict):
            return {
                "status": "INVALID_ERROR_INFO"
            }

        if error_info.get("type") not in ("SYNTAX_ERROR", "RUNTIME_ERROR"):
            return {
                "status": "UNSUPPORTED_ERROR"
            }

        # ⭐ 2. supervisor global gating
        decision = self.supervisor.approve_repair(
            file_path,
            error_info.get("type"),
            "GLOBAL_TRIGGER"
        )

        if not decision.get("approved", True):
            return {
                "status": "REPAIR_BLOCKED",
                "reason": decision
            }

        # ⭐ 3. 執行修復
        result = self.repair_engine.repair(
            file_path,
            error_info,
            self.supervisor
        )

        # ⭐ 4. outcome normalization
        if not isinstance(result, dict):
            return {
                "status": "INVALID_REPAIR_RESULT"
            }

        if "status" not in result:
            result["status"] = "UNKNOWN"

        return result