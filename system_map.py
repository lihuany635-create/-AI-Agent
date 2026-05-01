"""
system_map.py — 掃描 AI-Agent 系統現有檔案結構
提供給工坊生成程式碼時參考，讓新器官知道可以對接什麼
"""

import ast
import json
import pathlib
from typing import Any

BASE_DIR   = pathlib.Path(__file__).parent
CACHE_FILE = BASE_DIR / "workshop_data" / "system_map.json"

# 跳過的目錄和檔案
SKIP_DIRS  = {".git", "__pycache__", "node_modules", ".venv", "venv",
              "workshop_data", "review_sessions", ".repair_backup"}
SKIP_FILES = {"system_map.py"}


def _extract_file_info(path: pathlib.Path) -> dict:
    """用 AST 靜態分析一個 .py 檔，提取公開的函式、類別、變數。"""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree   = ast.parse(source)
    except Exception as e:
        return {"error": str(e), "functions": [], "classes": [], "constants": []}

    functions = []
    classes   = []
    constants = []

    for node in tree.body:
        # 公開函式
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            doc  = ast.get_docstring(node) or ""
            args = [a.arg for a in node.args.args if a.arg != "self"]
            functions.append({
                "name":        node.name,
                "args":        args,
                "description": doc.splitlines()[0][:80] if doc else "",
            })

        # 公開類別
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            doc     = ast.get_docstring(node) or ""
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not item.name.startswith("_") or item.name in ("__init__",):
                        mdoc = ast.get_docstring(item) or ""
                        methods.append({
                            "name":        item.name,
                            "description": mdoc.splitlines()[0][:60] if mdoc else "",
                        })
            classes.append({
                "name":        node.name,
                "description": doc.splitlines()[0][:80] if doc else "",
                "methods":     methods[:8],
            })

        # 頂層常數（全大寫）
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    constants.append(target.id)

    # Module docstring
    module_doc = ast.get_docstring(tree) or ""

    return {
        "description": module_doc.splitlines()[0][:100] if module_doc else "",
        "functions":   functions[:15],
        "classes":     classes[:8],
        "constants":   constants[:10],
    }


def scan_system(base_dir: pathlib.Path = BASE_DIR) -> dict:
    """
    掃描整個 AI-Agent 系統，回傳結構化的系統地圖。
    """
    result = {
        "base_dir": str(base_dir),
        "files":    {},
        "assembled_organs": [],
        "skill_descriptions": [],
    }

    # 掃描 .py 檔
    for py_file in sorted(base_dir.glob("*.py")):
        if py_file.name in SKIP_FILES:
            continue
        info = _extract_file_info(py_file)
        if info.get("functions") or info.get("classes"):
            result["files"][py_file.name] = info

    # 列出器官庫
    assembled = base_dir / "workshop_data" / "assembled"
    if assembled.exists():
        result["assembled_organs"] = [f.name for f in assembled.glob("*.py")]

    # 列出技能描述
    skills_dir = base_dir / "workshop_data" / "skills"
    if skills_dir.exists():
        for jf in skills_dir.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                result["skill_descriptions"].append({
                    "name":        data.get("name",""),
                    "description": data.get("description",""),
                    "filename":    data.get("filename",""),
                })
            except Exception:
                pass

    return result


def get_system_context(max_chars: int = 2000) -> str:
    """
    回傳給 LLM 用的系統 context 字串。
    精簡到 max_chars 以內。
    """
    system = scan_system()
    lines  = ["【現有系統檔案】"]

    for fname, info in system["files"].items():
        desc = info.get("description","")
        funcs = [f["name"] for f in info.get("functions", [])]
        classes = [c["name"] for c in info.get("classes", [])]
        parts = []
        if desc:       parts.append(desc)
        if funcs:      parts.append(f"函式：{', '.join(funcs[:5])}")
        if classes:    parts.append(f"類別：{', '.join(classes[:3])}")
        if parts:
            lines.append(f"  {fname}：{' | '.join(parts)}")

    if system["assembled_organs"]:
        lines.append(f"\n【已組裝器官】")
        for o in system["assembled_organs"]:
            lines.append(f"  {o}")

    if system["skill_descriptions"]:
        lines.append(f"\n【技能描述】")
        for s in system["skill_descriptions"]:
            lines.append(f"  {s['name']}：{s.get('description','')}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...（截斷）"
    return text


def save_cache(base_dir: pathlib.Path = BASE_DIR) -> pathlib.Path:
    """掃描並儲存快取。"""
    data = scan_system(base_dir)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return CACHE_FILE


if __name__ == "__main__":
    print("🗺  掃描系統結構...")
    ctx = get_system_context()
    print(ctx)
    save_cache()
    print(f"\n✅ 快取已儲存：{CACHE_FILE}")
