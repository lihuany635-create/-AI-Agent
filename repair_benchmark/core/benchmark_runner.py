from dataset_loader import DatasetLoader
from repair_adapter import RepairAdapter
from validator_pipeline import ValidatorPipeline

class BenchmarkRunner:

    def __init__(self):
        self.loader = DatasetLoader("../datasets")
        self.repair = RepairAdapter()
        self.validator = ValidatorPipeline()

    def run(self):
        cases = self.loader.load_cases()

        total = 0
        syntax_fail = 0
        runtime_fail = 0
        success = 0

        for case in cases:
            total += 1

            repaired = self.repair.repair(case)

            syntax_ok = self.validator.syntax_check(repaired)

            if not syntax_ok:
                syntax_fail += 1
                continue

            runtime_ok = self.validator.runtime_check(repaired)

            if not runtime_ok:
                runtime_fail += 1
                continue

            success += 1

        print("===== BENCHMARK RESULT =====")
        print("Total:", total)
        print("Success:", success)
        print("Syntax Fail:", syntax_fail)
        print("Runtime Fail:", runtime_fail)


if __name__ == "__main__":
    BenchmarkRunner().run()