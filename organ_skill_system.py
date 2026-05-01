"""
organ_skill_system.py — 器官技能描述系統
功能：
  1. 掃描 assembled/ 資料夾，為每個 .py 器官自動產生 .json 描述
  2. 載入所有 .json 描述到記憶體，供立AI 查詢
  3. 根據使用者需求選擇合適的器官
  4. 執行器官並回傳結果
"""

import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
ASSEMBLED_DIR = Path(__file__).parent / "workshop_data" / "assembled"
SKILLS_DIR    = Path(__file__).parent / "workshop_data" / "skills"
ASSEMBLED_DIR.mkdir(parents=True, exist_ok=True)
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


# ── 1. JSON 描述產生器 ────────────────────────────────────────────────────────

def _load_module(path: Path) -> Any:
    """安全載入 Python 模組。"""
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    if not spec or not spec.loader:
        raise ImportError(f"無法載入：{path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _extract_func_meta(func: Any) -> dict:
    """從函式提取 metadata。"""
    sig    = inspect.signature(func)
    doc    = inspect.getdoc(func) or ""
    inputs = []
    for name, param in sig.parameters.items():
        ann = param.annotation
        inputs.append({
            "name":     name,
            "type":     ann.__name__ if hasattr(ann, "__name__") else str(ann),
            "required": param.default is inspect.Parameter.empty,
        })
    return_ann = sig.return_annotation
    return {
        "name":        func.__name__,
        "description": doc,
        "inputs":      inputs,
        "output_type": return_ann.__name__ if hasattr(return_ann, "__name__") else str(return_ann),
    }


def generate_skill_json(organ_path: Path) -> dict:
    """
    分析 .py 器官，產生技能描述 dict。
    使用靜態分析（AST），不實際執行模組。
    """
    import ast, re

    source = organ_path.read_text(encoding="utf-8", errors="replace")
    name   = organ_path.stem.replace("_", " ")

    # 從多個來源提取功能說明，優先順序：docstring > 函式說明 > 有意義的註解
    description = ""
    skip_keywords = ["需求：", "工坊組裝", "組裝時間", "任務數", "規劃審查",
                     "審查建議", "──", "Example usage", "ISSUE_", "TOTAL:"]

    # 優先：module docstring
    try:
        tree_doc = ast.parse(source)
        doc = ast.get_docstring(tree_doc)
        if doc:
            first_line = doc.splitlines()[0].strip()
            if first_line and not any(kw in first_line for kw in skip_keywords):
                description = first_line
    except Exception:
        pass

    # 次選：第一個公開函式的 docstring
    if not description:
        try:
            tree_doc = ast.parse(source)
            for node in ast.walk(tree_doc):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("_"):
                        continue
                    doc = ast.get_docstring(node)
                    if doc:
                        first = doc.splitlines()[0].strip()
                        if first and not any(kw in first for kw in skip_keywords):
                            description = first
                            break
        except Exception:
            pass

    # 最後：從有意義的註解取
    if not description:
        for line in source.splitlines()[:50]:
            line = line.strip()
            if not line.startswith("#"):
                continue
            text = line.lstrip("#").strip()
            if not text or len(text) < 4:
                continue
            if any(kw in text for kw in skip_keywords):
                continue
            if text[0].isalpha() or '\u4e00' <= text[0] <= '\u9fff':
                description = text
                break

    if not description:
        description = f"{name} 功能模組"

    # 用 AST 找所有函式
    functions = []
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                args = [a.arg for a in node.args.args]
                doc  = ast.get_docstring(node) or ""
                functions.append({
                    "name":        node.name,
                    "description": doc,
                    "inputs":      args,
                })
    except SyntaxError:
        pass

    # 找 main() 的 argparse 參數作為使用範例
    example = f"python {organ_path.name}"
    args_match = re.findall(r'add_argument\(["\']([^"\']+)["\']', source)
    if args_match:
        example += " " + " ".join(args_match[:3])

    return {
        "name":        name,
        "filename":    organ_path.name,
        "path":        str(organ_path),
        "description": description or f"{name} 功能模組",
        "functions":   functions,
        "example":     example,
        "has_main":    "if __name__" in source,
        "needs_args":  "argparse" in source or "ArgumentParser" in source,
    }


def _ai_describe_skill(organ_path: Path, basic: dict) -> dict:
    """
    用 gpt-oss:20b 分析器官程式碼，生成完整的技能描述。
    失敗時回傳 basic（基本描述）。
    """
    try:
        import requests
        code = organ_path.read_text(encoding="utf-8", errors="replace")[:3000]
        prompt = f"""分析以下 Python 器官程式碼，輸出嚴格 JSON（不要其他文字）：

{{
  "description": "一句話說明這個程式的主要功能（繁體中文，20字以內）",
  "when_to_use": "什麼情況下應該使用這個技能（繁體中文，30字以內）",
  "inputs": [{{"name": "參數名", "description": "說明", "required": true}}],
  "outputs": "輸出結果的描述（繁體中文）",
  "example": "使用範例指令"
}}

程式碼：
{code}"""

        r = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "gpt-oss:20b",
                "messages": [
                    {"role": "system", "content": "你是程式碼分析師，只輸出 JSON，第一個字必須是 {"},
                    {"role": "user",   "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 500}
            },
            timeout=None
        )
        raw = r.json().get("message", {}).get("content", "").strip()
        import re
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            return basic
        ai_info = json.loads(raw[start:end])

        # 合併 basic 和 AI 生成的描述
        result = dict(basic)
        result.update({
            "description":  ai_info.get("description",  basic.get("description","")),
            "when_to_use":  ai_info.get("when_to_use",  ""),
            "inputs":       ai_info.get("inputs",        basic.get("functions",[])),
            "outputs":      ai_info.get("outputs",       ""),
            "example":      ai_info.get("example",       basic.get("example","")),
            "ai_described": True,
        })
        return result
    except Exception as e:
        print(f"  ⚠ AI 描述失敗，使用基本描述：{e}")
        return basic


def scan_and_generate(assembled_dir: Path = ASSEMBLED_DIR,
                      skills_dir: Path = SKILLS_DIR,
                      use_ai: bool = True) -> list[dict]:
    """
    掃描 assembled/ 資料夾，為每個 .py 產生對應的 .json 技能描述。
    use_ai=True 時用 gpt-oss:20b 生成完整描述。
    """
    results = []
    for py_file in assembled_dir.glob("*.py"):
        json_path = skills_dir / (py_file.stem + ".json")
        try:
            basic = generate_skill_json(py_file)
            if use_ai:
                print(f"  🤖 AI 分析：{py_file.name}...")
                skill = _ai_describe_skill(py_file, basic)
            else:
                skill = basic
            json_path.write_text(
                json.dumps(skill, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            results.append(skill)
            print(f"✅ 產生技能描述：{json_path.name}")
        except Exception as e:
            print(f"⚠ 無法處理 {py_file.name}：{e}")
    return results


# ── 2. 技能描述載入器 ─────────────────────────────────────────────────────────

class OrganRegistry:
    """載入並索引所有器官技能描述。"""

    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self._dir   = skills_dir
        self._skills: dict[str, dict] = {}
        self.reload()

    def reload(self):
        """重新載入所有技能描述。"""
        self._skills.clear()
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                key  = data.get("name", f.stem).lower()
                self._skills[key] = data
            except Exception:
                pass

    def all(self) -> list[dict]:
        return list(self._skills.values())

    def find_by_name(self, name: str) -> dict | None:
        return self._skills.get(name.lower())

    def find_by_keyword(self, keyword: str) -> list[dict]:
        kw = keyword.lower()
        return [
            s for s in self._skills.values()
            if kw in s.get("name","").lower()
            or kw in s.get("description","").lower()
            or any(kw in f.get("description","").lower()
                   for f in s.get("functions",[]))
        ]

    def summary(self) -> str:
        """給立AI 看的技能清單摘要。"""
        if not self._skills:
            return "（器官庫是空的）"
        lines = []
        for s in self._skills.values():
            needs = "（需要參數）" if s.get("needs_args") else ""
            desc  = s.get("description", "")
            when  = s.get("when_to_use", "")
            line  = f"🔩 {s['name']}{needs}：{desc}"
            if when:
                line += f"\n   使用時機：{when}"
            lines.append(line)
        return "\n".join(lines)


# ── 3. 器官選擇器 ─────────────────────────────────────────────────────────────

def select_organ(query: str, registry: OrganRegistry) -> dict | None:
    """
    根據使用者需求，選擇最合適的器官。
    先精確比對名稱，再關鍵字搜尋。
    """
    # 精確比對
    direct = registry.find_by_name(query)
    if direct:
        return direct

    # 關鍵字搜尋
    matches = registry.find_by_keyword(query)
    if matches:
        return matches[0]

    return None


# ── 4. 器官執行器 ─────────────────────────────────────────────────────────────

def execute_organ(skill: dict, args: list[str] = None, timeout: int = 30) -> dict:
    """
    執行器官，回傳 {success, output, error}。
    args：額外命令列參數（給有 argparse 的器官用）
    """
    path = Path(skill.get("path", ""))
    if not path.exists():
        # 用 filename 找
        path = ASSEMBLED_DIR / skill.get("filename", "")
    if not path.exists():
        return {"success": False, "output": "", "error": f"找不到器官：{skill.get('filename')}"}

    cmd = [sys.executable, str(path)] + (args or [])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        out = (result.stdout + result.stderr).strip()
        return {
            "success": result.returncode == 0,
            "output":  out[:1000] if out else "（無輸出）",
            "error":   "" if result.returncode == 0 else out,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": f"執行超時（{timeout}秒）"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


# ── 全域 registry（單例）──────────────────────────────────────────────────────
_registry: OrganRegistry | None = None

def get_registry() -> OrganRegistry:
    global _registry
    if _registry is None:
        # 先掃描產生描述，再載入
        scan_and_generate()
        _registry = OrganRegistry()
    return _registry

def refresh_registry():
    """重新掃描並載入。"""
    global _registry
    scan_and_generate()
    if _registry:
        _registry.reload()
    else:
        _registry = OrganRegistry()


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("🔩 器官技能描述系統")
    print("掃描並產生技能描述...")
    skills = scan_and_generate()
    print(f"\n共產生 {len(skills)} 份技能描述")
    reg = OrganRegistry()
    print("\n技能清單：")
    print(reg.summary())
