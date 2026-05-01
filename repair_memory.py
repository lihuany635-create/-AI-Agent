import json
from pathlib import Path
from collections import defaultdict


class RepairMemory:

    def __init__(self, memory_file="repair_memory.json"):
        self.memory_file = Path(memory_file)
        self.data = self._load()

    # ================= CORE RECORD =================

    def record(self, error_type, strategy, success, quality=None):

        if error_type not in self.data:
            self.data[error_type] = {}

        if strategy not in self.data[error_type]:
            self.data[error_type][strategy] = {
                "success": 0,
                "fail": 0,
                "quality_sum": 0,
                "attempts": 0
            }

        entry = self.data[error_type][strategy]

        if success:
            entry["success"] += 1
        else:
            entry["fail"] += 1

        entry["attempts"] += 1

        if quality is not None:
            entry["quality_sum"] += quality

        self._save()

    # ================= LEARNING =================

    def get_strategy_priority(self, error_type):

        if error_type not in self.data:
            return {}

        scores = {}

        for strategy, stats in self.data[error_type].items():
            attempts = stats["attempts"]
            if attempts == 0:
                continue

            success_rate = stats["success"] / attempts
            avg_quality = (
                stats["quality_sum"] / stats["success"]
                if stats["success"] > 0 else 0
            )

            score = success_rate * 0.7 + avg_quality * 0.3
            scores[strategy] = score

        return dict(
            sorted(scores.items(), key=lambda x: x[1], reverse=True)
        )

    # ================= FAILURE TAXONOMY =================

    def classify_failure(self, error_type):

        if error_type not in self.data:
            return "unknown"

        total_success = sum(s["success"] for s in self.data[error_type].values())
        total_fail = sum(s["fail"] for s in self.data[error_type].values())

        if total_fail > total_success * 3:
            return "hard_error"

        if total_success == 0:
            return "unresolved"

        return "learnable"

    # ================= QUALITY TREND =================

    def get_quality_trend(self, error_type):

        if error_type not in self.data:
            return 0

        total_quality = 0
        total_success = 0

        for s in self.data[error_type].values():
            total_quality += s["quality_sum"]
            total_success += s["success"]

        if total_success == 0:
            return 0

        return total_quality / total_success

    # ================= STORAGE =================

    def _load(self):
        if self.memory_file.exists():
            return json.loads(self.memory_file.read_text())
        return {}

    def _save(self):
        self.memory_file.write_text(
            json.dumps(self.data, indent=2)
        )