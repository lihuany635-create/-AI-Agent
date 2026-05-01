import os

class TerminalEditor:

    def open_file(self, path):
        if not os.path.exists(path):
            return "❌ 檔案不存在"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path, content):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return "✅ 已寫入"

    def replace_in_file(self, path, old, new):
        if not os.path.exists(path):
            return "❌ 檔案不存在"

        with open(path, "r", encoding="utf-8") as f:
            data = f.read()

        data = data.replace(old, new)

        with open(path, "w", encoding="utf-8") as f:
            f.write(data)

        return "✅ 已修改"