"""
organ_pipeline.py — 器官串聯執行器
讓立AI 能把多個器官組成管道，A 的輸出直接傳給 B。

用法：
    from organ_pipeline import run_pipeline
    result = run_pipeline([
        {"organ": "視覺辨識系統"},
        {"organ": "知識庫存入", "args": ["{{prev}}"]},
    ])

立AI 呼叫方式：
    pipeline = [
        {"organ": "器官名稱1", "args": []},
        {"organ": "器官名稱2", "args": ["{{prev}}"]},  # {{prev}} 代表上一步輸出
    ]
    run_pipeline(pipeline, initial_input="初始資料")
"""

import json
import pathlib
import subprocess
import sys
from typing import Any

ASSEMBLED_DIR = pathlib.Path(__file__).parent / "workshop_data" / "assembled"
SKILLS_DIR    = pathlib.Path(__file__).parent / "workshop_data" / "skills"


def _find_organ(name: str) -> pathlib.Path | None:
    """根據名稱找到器官檔案（支援模糊比對）。"""
    name_clean = name.lower().replace(" ", "_").replace("　", "_")
    # 精確比對
    for f in ASSEMBLED_DIR.glob("*.py"):
        if f.stem.lower() == name_clean:
            return f
    # 模糊比對
    for f in ASSEMBLED_DIR.glob("*.py"):
        if name_clean in f.stem.lower() or f.stem.lower() in name_clean:
            return f
    return None


def _run_organ(organ_path: pathlib.Path, args: list, prev_output: str = "") -> dict:
    """執行單一器官，回傳 {success, output, error}。"""
    # 把 {{prev}} 替換成上一步的輸出
    resolved_args = []
    for a in args:
        if a == "{{prev}}" or a == "{{prev_output}}":
            resolved_args.append(prev_output)
        else:
            resolved_args.append(str(a))

    cmd = [sys.executable, str(organ_path)] + resolved_args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=60, encoding="utf-8", errors="replace"
        )
        out = (result.stdout + result.stderr).strip()
        return {
            "success": result.returncode == 0,
            "output":  out[:2000] if out else "（無輸出）",
            "error":   "" if result.returncode == 0 else out,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "執行超時（60秒）"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def run_pipeline(steps: list, initial_input: str = "") -> dict:
    """
    串聯執行多個器官。

    參數：
        steps: 步驟列表，每步格式：
            {"organ": "器官名稱", "args": ["參數1", "{{prev}}"]}
        initial_input: 傳給第一個器官的初始資料

    回傳：
        {
            "success": bool,
            "steps": [{"organ", "success", "output", "error"}],
            "final_output": str,
        }

    使用範例：
        result = run_pipeline([
            {"organ": "視覺辨識系統", "args": []},
            {"organ": "知識庫存入",   "args": ["{{prev}}"]},
        ])
    """
    results = []
    prev_output = initial_input

    for i, step in enumerate(steps):
        organ_name = step.get("organ", "")
        args       = step.get("args", [])

        organ_path = _find_organ(organ_name)
        if not organ_path:
            result = {
                "organ":   organ_name,
                "success": False,
                "output":  "",
                "error":   f"找不到器官：{organ_name}",
            }
            results.append(result)
            print(f"❌ Step {i+1} 失敗：找不到器官「{organ_name}」")
            break

        print(f"▶ Step {i+1}：{organ_name}")
        r = _run_organ(organ_path, args, prev_output)
        r["organ"] = organ_name
        results.append(r)

        if r["success"]:
            print(f"  ✅ 輸出：{r['output'][:100]}")
            prev_output = r["output"]
        else:
            print(f"  ❌ 失敗：{r['error'][:100]}")
            break

    all_success = all(r.get("success") for r in results)
    return {
        "success":      all_success,
        "steps":        results,
        "final_output": prev_output,
    }


def list_organs() -> list:
    """列出所有可用器官。"""
    organs = []
    for f in sorted(ASSEMBLED_DIR.glob("*.py"), key=lambda x: x.stat().st_mtime, reverse=True):
        desc = ""
        try:
            skill_json = SKILLS_DIR / (f.stem + ".json")
            if skill_json.exists():
                data = json.loads(skill_json.read_text(encoding="utf-8"))
                desc = data.get("description", "")
        except Exception:
            pass
        organs.append({"name": f.stem.replace("_", " "), "filename": f.name, "description": desc})
    return organs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="器官管道執行器")
    parser.add_argument("--pipeline", "-p", type=str, help="JSON 管道定義")
    parser.add_argument("--input",    "-i", type=str, default="", help="初始輸入")
    parser.add_argument("--list",     "-l", action="store_true", help="列出所有器官")
    args = parser.parse_args()

    if args.list:
        organs = list_organs()
        print(f"📦 器官庫（{len(organs)} 個）：")
        for o in organs:
            print(f"  🔩 {o['name']}：{o['description']}")
    elif args.pipeline:
        steps = json.loads(args.pipeline)
        result = run_pipeline(steps, args.input)
        print(f"\n{'✅ 管道執行成功' if result['success'] else '❌ 管道執行失敗'}")
        print(f"最終輸出：{result['final_output'][:300]}")
    else:
        parser.print_help()
