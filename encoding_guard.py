import os
from pathlib import Path
from datetime import datetime

BOM = b'\xef\xbb\xbf'

class EncodingGuard:

    def __init__(self, root):
        self.root = Path(root)
        self.infected = []
        self.cleaned = []

    def scan_file(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                if content.startswith(BOM):
                    self.infected.append(file_path)
        except:
            pass

    def scan(self):
        for path in self.root.rglob("*.py"):
            self.scan_file(path)

    def clean_file(self, file_path):
        with open(file_path, 'rb') as f:
            content = f.read()

        if content.startswith(BOM):
            content = content[len(BOM):]
            with open(file_path, 'wb') as f:
                f.write(content)
            self.cleaned.append(file_path)

    def clean(self):
        for f in self.infected:
            self.clean_file(f)

    def report(self):
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_name = f"encoding_report_{now}.txt"

        with open(report_name, 'w', encoding='utf-8') as r:
            r.write("ENCODING GUARD REPORT\n")
            r.write("="*40 + "\n")

            r.write("\nINFECTED FILES:\n")
            for f in self.infected:
                r.write(str(f) + "\n")

            r.write("\nCLEANED FILES:\n")
            for f in self.cleaned:
                r.write(str(f) + "\n")

        print(f"\nReport generated: {report_name}")

def run_guard():
    root = os.getcwd()
    guard = EncodingGuard(root)

    print("\nScanning for BOM infection...")
    guard.scan()

    if not guard.infected:
        print("No BOM infection detected.")
        return

    print(f"\nDetected {len(guard.infected)} infected files.")

    guard.clean()
    print(f"Cleaned {len(guard.cleaned)} files.")

    guard.report()

if __name__ == "__main__":
    run_guard()