# analyze_module.py — 局部系統分析工具
# 用法：python analyze_module.py telegram_bot.py
# 輸出：模組結構、函式清單、import 關係、關鍵邏輯

import ast
import sys
import pathlib
import re

def analyze(filepath: str):
    path = pathlib.Path(filepath)
    if not path.exists():
        print(f"❌ 找不到檔案：{filepath}")
        return

    source = path.read_text(encoding="utf-8", errors="ignore")
    print(f"\n{'='*60}")
    print(f"📄 模組分析：{path.name}")
    print(f"{'='*60}")
    print(f"總行數：{len(source.splitlines())} 行")

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"⚠️ 語法錯誤：{e}")
        return

    # ── Import 分析 ──────────────────────────────────────────────────────────
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    # 分開本地模組和第三方
    local_imports = [i for i in imports if not i.startswith(("os", "sys", "re", "json",
        "time", "datetime", "pathlib", "shutil", "subprocess", "threading", "queue",
        "logging", "ast", "math", "random", "hashlib", "base64", "io", "collections",
        "functools", "itertools", "typing", "abc", "unittest", "argparse", "csv",
        "sqlite3", "http", "urllib", "string", "struct", "copy", "enum", "dataclasses",
        "contextlib", "traceback", "warnings", "inspect", "importlib",
    ))]

    print(f"\n📦 依賴模組（{len(set(local_imports))} 個）：")
    for imp in sorted(set(local_imports)):
        print(f"   → {imp}")

    # ── 類別分析 ─────────────────────────────────────────────────────────────
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if classes:
        print(f"\n🏗 類別（{len(classes)} 個）：")
        for cls in classes:
            methods = [n.name for n in ast.walk(cls) if isinstance(n, ast.FunctionDef)]
            print(f"   class {cls.name}（第 {cls.lineno} 行）")
            if methods:
                print(f"      方法：{', '.join(methods[:8])}" +
                      (f"... 共{len(methods)}個" if len(methods) > 8 else ""))

    # ── 函式分析 ─────────────────────────────────────────────────────────────
    top_funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if top_funcs:
        print(f"\n⚙️ 頂層函式（{len(top_funcs)} 個）：")
        for fn in top_funcs:
            # 取第一行 docstring
            doc = ""
            if (fn.body and isinstance(fn.body[0], ast.Expr) and
                    isinstance(fn.body[0].value, ast.Constant)):
                doc = str(fn.body[0].value.value)[:60]
            args = [a.arg for a in fn.args.args]
            print(f"   def {fn.name}({', '.join(args)})  第{fn.lineno}行")
            if doc:
                print(f"      「{doc}」")

    # ── 全域變數 ─────────────────────────────────────────────────────────────
    globals_list = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    globals_list.append(target.id)

    if globals_list:
        print(f"\n🔧 全域常數：{', '.join(globals_list)}")

    # ── 關鍵字搜尋 ───────────────────────────────────────────────────────────
    keywords = {
        "signal/slot": r"pyqtSignal|\.connect\(|\.emit\(",
        "threading":   r"threading\.Thread|QThread",
        "Telegram":    r"@bot\.|bot\.send|message_handler|callback_query",
        "Ollama":      r"ollama|safe_infer|LLAMA",
        "Claude橋接":  r"claude_bridge|get_bridge|ClaudeBridge",
        "推送":        r"push_to_phone|send_message|push\(",
        "記憶庫":      r"long_term_memory|_memory\.store|LongTermMemory",
    }

    found_kw = []
    for label, pattern in keywords.items():
        if re.search(pattern, source):
            found_kw.append(label)

    if found_kw:
        print(f"\n🔍 涉及功能：{' | '.join(found_kw)}")

    # ── 入口點 ───────────────────────────────────────────────────────────────
    if "__main__" in source:
        main_lines = []
        in_main = False
        for line in source.splitlines():
            if '__name__ == "__main__"' in line or "__name__ == '__main__'" in line:
                in_main = True
            if in_main:
                main_lines.append(line.strip())
                if len(main_lines) > 6:
                    break
        print(f"\n🚀 入口點：")
        for l in main_lines[:6]:
            print(f"   {l}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python analyze_module.py <檔名.py> [檔名2.py ...]")
        print("例如：python analyze_module.py telegram_bot.py self_dev_engine.py")
    else:
        for f in sys.argv[1:]:
            analyze(f)
