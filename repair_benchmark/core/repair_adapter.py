import sys
from pathlib import Path
import shutil
import tempfile

# ⭐ 加入主專案路徑
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

from error_detector import ErrorDetector
from repair_engine import RepairEngine


class RepairAdapter:

    def __init__(self):
        self.detector = ErrorDetector()
        self.engine = RepairEngine()

    def repair(self, file_path: Path) -> Path:

        temp_dir = Path(tempfile.mkdtemp())
        target = temp_dir / "test.py"

        shutil.copy(file_path, target)

        error = self.detector.detect_file_error(target)

        if error:
            self.engine.repair(target, error, supervisor=None)

        return target


if __name__ == "__main__":

    adapter = RepairAdapter()

    test_file = Path("../datasets/syntax/case_001_colon_missing/broken.py")
    repaired = adapter.repair(test_file)

    print("Repaired file at:", repaired)