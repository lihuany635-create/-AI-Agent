import os
import ast
from pathlib import Path
from datetime import datetime

BOM = b'\xef\xbb\xbf'

class SystemHealthGuard:

    def __init__(self, root):
        self.root = Path(root)
        self.bom_infected = []
        self.parse_failed = []
        self.empty_modules = []
        self.total_files = 0

    # ---------- 編碼掃描 ----------
    def check_bom(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                if content.startswith(BOM):
                    self.bom_infected.append(file_path)
        except:
            pass

    # ---------- AST 健康 ----------
    def check_parse(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            ast.parse(code)
        except:
            self.parse_failed.append(file_path)

    # ---------- 空模組 ----------
    def check_empty(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read().strip()
                if not code or code == "":
                    self.empty_modules.append(file_path)
        except:
            pass

    # ---------- 掃描 ----------
    def scan(self):
        for path in self.root.rglob("*.py"):
            self.total_files += 1
            self.check_bom(path)
            self.check_parse(path)
            self.check_empty(path)

    # ---------- 修復 BOM ----------
    def clean_bom(self):
        for file_path in self.bom_infected:
            with open(file_path, 'rb') as f:
                content = f.read()
            content = content[len(BOM):]
            with open(file_path, 'wb') as f:
                f.write(content)

    # ---------- 報告 ----------
    def generate_report(self):
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = f"system_health_report_{now}.txt"

        with open(name, 'w', encoding='utf-8') as r:
            r.write("AI SYSTEM HEALTH REPORT\n")
            r.write("="*50 + "\n")
            r.write(f"Total Python Files: {self.total_files}\n\n")

            r.write("BOM INFECTED:\n")
            for f in self.bom_infected:
                r.write(str(f) + "\n")

            r.write("\nPARSE FAILED:\n")
            for f in self.parse_failed:
                r.write(str(f) + "\n")

            r.write("\nEMPTY MODULES:\n")
            for f in self.empty_modules:
                r.write(str(f) + "\n")

        print(f"\nHealth report generated: {name}")

    # ---------- 主流程 ----------
    def run(self):
        print("\n[HealthGuard] scanning system...")
        self.scan()

        if self.bom_infected:
            print(f"[HealthGuard] BOM detected in {len(self.bom_infected)} files → cleaning")
            self.clean_bom()

        print(f"[HealthGuard] parse failed: {len(self.parse_failed)}")
        print(f"[HealthGuard] empty modules: {len(self.empty_modules)}")

        self.generate_report()


def run_health_guard():
    root = os.getcwd()
    guard = SystemHealthGuard(root)
    guard.run()


if __name__ == "__main__":
    run_health_guard()