"""
workshop_evaluator.py — 工坊評測工具
用固定的測試需求評測工坊流程，記錄完整思考過程。

使用方式：
    python workshop_evaluator.py
    python workshop_evaluator.py --test "自訂測試需求"
"""

import argparse
import json
import pathlib
import time
import datetime
import threading
import requests
import socketio

WORKSHOP_URL = "http://localhost:7862"
OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "gpt-oss:20b"

# ── 固定測試案例 ───────────────────────────────────────────────────────────────
DEFAULT_TESTS = [
    {
        "name":        "簡單計算器",
        "requirement": "做一個 Python 計算器，有 add(a,b)、subtract(a,b)、multiply(a,b)、divide(a,b) 四個函式，執行後印出測試結果",
    },
    {
        "name":        "檔案讀寫",
        "requirement": "做一個工具，能讀取 txt 檔案並統計字數、行數、最常出現的10個詞，結果存成 JSON 檔",
    },
    {
        "name":        "桌面通知",
        "requirement": "使用 desktop_control.py 的 DesktopControl 類別，做一個發送桌面通知的函式",
    },
]

# ── 評測記錄 ──────────────────────────────────────────────────────────────────
class EvalRecord:
    def __init__(self, test_name: str, requirement: str):
        self.test_name   = test_name
        self.requirement = requirement
        self.start_time  = time.time()
        self.events      = []  # 所有事件
        self.project_id  = None
        self.tasks       = []
        self.final_status = None

    def add_event(self, event_type: str, data: dict):
        self.events.append({
            "time":  datetime.datetime.now().strftime("%H:%M:%S"),
            "type":  event_type,
            "data":  data,
        })

    def duration(self) -> float:
        return time.time() - self.start_time

    def save(self, output_dir: pathlib.Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = self.test_name.replace(" ", "_")
        path = output_dir / f"{ts}_{name}.json"
        path.write_text(
            json.dumps({
                "test_name":   self.test_name,
                "requirement": self.requirement,
                "duration_s":  round(self.duration(), 1),
                "final_status": self.final_status,
                "events":      self.events,
                "tasks":       self.tasks,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return path


# ── AI 解說 ───────────────────────────────────────────────────────────────────
def _narrate(event_type: str, data: dict) -> str:
    """用 AI 把工坊事件翻譯成繁體中文白話解說。"""
    templates = {
        "plan":    f"工坊剛完成規劃，任務清單是：{data.get('tasks', [])}",
        "code":    f"工坊正在生成第 {data.get('seq')} 個任務「{data.get('title')}」的程式碼",
        "success": f"任務「{data.get('title')}」執行成功，輸出：{str(data.get('output',''))[:200]}",
        "fail":    f"任務「{data.get('title')}」失敗，錯誤：{str(data.get('error',''))[:200]}",
        "repair":  f"正在修復任務「{data.get('title')}」，第 {data.get('attempt')} 次嘗試",
        "skip":    f"任務「{data.get('title')}」被跳過，原因：{data.get('reason','')}",
        "done":    f"專案完成，共 {data.get('task_count', 0)} 個任務",
    }
    prompt = templates.get(event_type, f"事件：{event_type}，資料：{data}")

    try:
        r = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": "你是工坊旁白，用繁體中文白話解說工坊正在做什麼、為什麼這樣做。2-3句話，簡潔生動。"},
                {"role": "user",   "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.5, "num_predict": 150},
        }, timeout=30)
        return r.json().get("message", {}).get("content", "").strip()
    except Exception:
        return prompt


# ── 主評測流程 ────────────────────────────────────────────────────────────────
def run_evaluation(test: dict, output_dir: pathlib.Path, verbose: bool = True) -> EvalRecord:
    record = EvalRecord(test["name"], test["requirement"])

    print(f"\n{'='*60}")
    print(f"📋 測試：{test['name']}")
    print(f"需求：{test['requirement']}")
    print(f"{'='*60}")

    # 連接 socket.io 監聽工坊事件
    sio    = socketio.Client()
    done_ev = threading.Event()

    @sio.on("project_updated")
    def on_project(data):
        pid = data.get("id") or data.get("project_id")
        if pid != record.project_id:
            return
        record.add_event("project_updated", data)

    @sio.on("task_updated")
    def on_task(data):
        if data.get("project_id") != record.project_id:
            return
        record.add_event("task_updated", data)

    @sio.on("log")
    def on_log(data):
        if data.get("project_id") != record.project_id:
            return
        msg   = data.get("message", "")
        level = data.get("level", "INFO")
        ts    = datetime.datetime.now().strftime("%H:%M:%S")

        # 偵測關鍵事件並旁白
        narration = None
        if "施工計畫" in msg:
            narration = _narrate("code", {"seq": "?", "title": msg[6:40]})
        elif "執行成功" in msg or "✅" in msg:
            narration = _narrate("success", {"title": msg[:40], "output": msg})
        elif "執行失敗" in msg or "❌" in msg:
            narration = _narrate("fail", {"title": msg[:40], "error": msg})
        elif "修復" in msg or "🔧" in msg:
            narration = _narrate("repair", {"title": msg[:40], "attempt": "?"})
        elif "自動跳過" in msg or "⏭" in msg:
            narration = _narrate("skip", {"title": msg[:40], "reason": msg})
        elif "全部完成" in msg or "✅ 全部" in msg:
            record.final_status = "done"
            narration = _narrate("done", {"task_count": len(record.tasks)})
            done_ev.set()
        elif "失敗" in msg and "全部" in msg:
            record.final_status = "failed"
            done_ev.set()

        record.add_event("log", {"message": msg, "level": level})

        if verbose:
            print(f"[{ts}] {msg}")
            if narration:
                print(f"  💬 {narration}\n")

    try:
        sio.connect(WORKSHOP_URL)
    except Exception as e:
        print(f"❌ 無法連接工坊：{e}")
        return record

    # 建立專案並開始規劃
    try:
        r = requests.post(f"{WORKSHOP_URL}/api/projects", json={
            "name": f"[評測] {test['name']}",
        })
        record.project_id = r.json()["id"]
        print(f"✅ 專案建立：{record.project_id[:8]}")

        # 開始規劃
        requests.post(f"{WORKSHOP_URL}/api/projects/{record.project_id}/plan",
                      json={"requirement": test["requirement"]},
                      stream=True, timeout=None)

    except Exception as e:
        print(f"❌ 建立專案失敗：{e}")
        sio.disconnect()
        return record

    # 等待完成（最多 30 分鐘）
    print("⏳ 等待工坊完成...")
    done_ev.wait(timeout=1800)

    sio.disconnect()

    # 儲存記錄
    path = record.save(output_dir)
    duration = record.duration()
    print(f"\n{'='*60}")
    print(f"✅ 評測完成：{record.final_status}")
    print(f"⏱ 耗時：{duration:.0f} 秒")
    print(f"📄 記錄：{path}")

    # 清除測試專案（不留痕跡）
    if record.project_id:
        try:
            requests.delete(f"{WORKSHOP_URL}/api/projects/{record.project_id}")
            print(f"🗑 已清除測試專案")
        except Exception:
            pass

        # 清除組裝的測試器官
        try:
            assembled = pathlib.Path("workshop_data/assembled")
            skills    = pathlib.Path("workshop_data/skills")
            name_tag  = f"[評測]_{test['name'].replace(' ','_')}"
            for f in list(assembled.glob("*.py")) + list(skills.glob("*.json")):
                if name_tag in f.stem or f"評測" in f.stem:
                    f.unlink()
                    print(f"🗑 已清除：{f.name}")
        except Exception:
            pass

    return record


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="工坊評測工具")
    parser.add_argument("--test",   "-t", type=str, help="自訂測試需求")
    parser.add_argument("--name",   "-n", type=str, default="自訂測試", help="測試名稱")
    parser.add_argument("--all",    "-a", action="store_true", help="執行所有內建測試")
    parser.add_argument("--output", "-o", type=str, default="workshop_data/eval_results", help="輸出目錄")
    parser.add_argument("--quiet",  "-q", action="store_true", help="不顯示詳細 log")
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output)
    verbose    = not args.quiet

    if args.test:
        tests = [{"name": args.name, "requirement": args.test}]
    elif args.all:
        tests = DEFAULT_TESTS
    else:
        # 預設跑第一個測試
        tests = [DEFAULT_TESTS[0]]
        print("提示：用 --all 執行所有測試，--test '需求' 自訂測試")

    for test in tests:
        run_evaluation(test, output_dir, verbose)
        if len(tests) > 1:
            print("\n等待 10 秒再跑下一個測試...")
            time.sleep(10)

    print("\n評測結束！")
