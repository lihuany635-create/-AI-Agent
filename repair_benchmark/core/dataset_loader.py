from pathlib import Path

class DatasetLoader:

    def __init__(self, dataset_root):
        self.root = Path(dataset_root)

    def load_cases(self):
        cases = []

        for error_type_dir in self.root.iterdir():
            if not error_type_dir.is_dir():
                continue

            for case_dir in error_type_dir.iterdir():
                broken_file = case_dir / "broken.py"
                if broken_file.exists():
                    cases.append(broken_file)

        return cases


if __name__ == "__main__":
    loader = DatasetLoader("../datasets")
    cases = loader.load_cases()

    print("Loaded cases:")
    for c in cases:
        print(c)