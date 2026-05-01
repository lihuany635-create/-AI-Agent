import ast
import subprocess

class ValidatorPipeline:

    def syntax_check(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                ast.parse(f.read())
            return True
        except Exception:
            return False

    def runtime_check(self, file_path):
        result = subprocess.run(
            ["python", file_path],
            capture_output=True
        )
        return result.returncode == 0


if __name__ == "__main__":
    from pathlib import Path

    validator = ValidatorPipeline()

    test_file = Path("../datasets/syntax/case_001_colon_missing/broken.py")

    print("Syntax OK:", validator.syntax_check(test_file))
    print("Runtime OK:", validator.runtime_check(test_file))