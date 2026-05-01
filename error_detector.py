import ast

# 不安全的函式名稱前綴，偵測時跳過
_UNSAFE_PREFIXES = ("delete", "remove", "drop", "send", "post", "upload",
                    "write", "save", "destroy", "clean", "wipe", "format")

class ErrorDetector:

    def detect_file_error(self, file_path):

        # 1️⃣ 讀檔
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            return {
                "type": "FILE_READ_ERROR",
                "message": str(e)
            }

        # 2️⃣ Syntax 檢測（強制）
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "type": "SYNTAX_ERROR",
                "message": str(e),
                "line": e.lineno,
                "error_class": "SyntaxError"
            }

        # 3️⃣ 檢查 top-level execution（AST）
        for node in tree.body:
            if isinstance(node, ast.Expr):
                return {
                    "type": "RUNTIME_ERROR",
                    "message": "top-level execution detected",
                    "line": node.lineno,
                    "error_class": "TopLevelExecution"
                }

        # 4️⃣ 用 subprocess 隔離執行，避免副作用污染主行程
        import subprocess, sys
        try:
            result = subprocess.run(
                [sys.executable, "-c",
                 f"import importlib.util; "
                 f"spec=importlib.util.spec_from_file_location('m',r'{file_path}'); "
                 f"mod=importlib.util.module_from_spec(spec); "
                 f"spec.loader.exec_module(mod)"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                # 解析 traceback 取得行號
                line_no = None
                for line in stderr.splitlines():
                    m = __import__('re').search(r'line (\d+)', line)
                    if m:
                        line_no = int(m.group(1))
                return {
                    "type": "RUNTIME_ERROR",
                    "message": stderr.splitlines()[-1] if stderr else "未知錯誤",
                    "line": line_no,
                    "error_class": "RuntimeError"
                }
        except subprocess.TimeoutExpired:
            return {
                "type": "RUNTIME_ERROR",
                "message": "模組載入超時（可能有無限迴圈或阻塞呼叫）",
                "line": None,
                "error_class": "TimeoutError"
            }
        except Exception as e:
            return {
                "type": "RUNTIME_ERROR",
                "message": str(e),
                "line": None,
                "error_class": type(e).__name__
            }

        return None