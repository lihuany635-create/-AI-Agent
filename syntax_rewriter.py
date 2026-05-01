from pathlib import Path


class SyntaxRewriter:

    def fix_missing_colon(self, file_path, line_no):

        lines = Path(file_path).read_text().splitlines()

        if line_no is None:
            return False

        idx = line_no - 1

        if idx < 0 or idx >= len(lines):
            return False

        line = lines[idx]

        if line.strip().endswith(":"):
            return False

        lines[idx] = line + ":"

        Path(file_path).write_text("\n".join(lines))

        return True