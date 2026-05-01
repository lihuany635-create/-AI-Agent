import shutil
from pathlib import Path

from repair_engine import RepairEngine
from error_detector import ErrorDetector


DATASET = Path("repair_tests/dataset")
SANDBOX = Path("repair_tests/sandbox")

engine = RepairEngine()
detector = ErrorDetector()

if SANDBOX.exists():
    shutil.rmtree(SANDBOX)

shutil.copytree(DATASET, SANDBOX)

results = []

for f in SANDBOX.glob("*.py"):

    print(f"TESTING: {f.name}")

    err = detector.detect_file_error(str(f))

    if not err:
        results.append((f.name, "NO_ERROR"))
        continue

    res = engine.repair(str(f), err, supervisor=None)

    results.append((f.name, res["status"]))

print("\n=== RESULT ===")
for r in results:
    print(r)