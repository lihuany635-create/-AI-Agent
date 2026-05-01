from pathlib import Path
from repair_engine import RepairEngine
from error_detector import ErrorDetector

engine = RepairEngine()
detector = ErrorDetector()

test_root = Path("repair_test_suite")

results = []

for f in test_root.glob("*.py"):
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
