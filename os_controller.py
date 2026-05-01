import subprocess
import os
from pathlib import Path


class OSController:

    ALLOWED_COMMANDS = {
        "python",
        "pytest",
        "git",
        "pip",
    }

    def __init__(self, workspace=None):
        self.workspace = Path(workspace or os.getcwd())

    # ======================
    # Command execution
    # ======================
    def safe_run(self, command):

        if command[0] not in self.ALLOWED_COMMANDS:
            return {
                "success": False,
                "error": f"Command not allowed: {command[0]}"
            }

        try:
            result = subprocess.run(
                command,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # ======================
    # File ops
    # ======================
    def read_file(self, relative_path):
        try:
            file_path = self.workspace / relative_path
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            return str(e)

    def write_file(self, relative_path, content):
        try:
            file_path = self.workspace / relative_path

            if ".." in str(file_path):
                return "Invalid path"

            file_path.write_text(content, encoding="utf-8")
            return "OK"
        except Exception as e:
            return str(e)

    def list_dir(self, relative="."):
        try:
            path = self.workspace / relative
            return [str(p.name) for p in path.iterdir()]
        except Exception as e:
            return str(e)

    # ======================
    # ⭐ NEW: open folder
    # ======================
    def open_folder(self, absolute_path):
        try:
            os.startfile(absolute_path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}