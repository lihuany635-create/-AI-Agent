"""
liai_core.py — 立AI 自主核心
立AI 的思考迴圈，像朋友一樣自己做事、自己決定、有話直說。
包含自我修改能力：可以讀寫 AI-Agent 資料夾的檔案，改壞了會自動還原。
"""

import ast
import json
import logging
import pathlib
import shutil
import subprocess
import threading
import time
from datetime import datetime

import requests

logger = logging.getLogger("liai_core")

BASE_DIR       = pathlib.Path(__file__).parent
OLLAMA_URL     = "http://localhost:11434"
KNOWLEDGE_URL  = "http://localhost:7861"
WORKSHOP_URL   = "http://localhost:7862"
STATE_FILE     = BASE_DIR / "workshop_data" / "memory" / "liai_core_state.json"
BACKUP_DIR     = BASE_DIR / "workshop_data" / "memory" / "file_backups"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

THINK_INTERVAL = 5 * 60    # 5 分鐘思考一次
MIN_CHAT_GAP   = 60 * 60   # 主動找你聊，至少間隔 1 小時

# 重大檔案，修改前要先問皓皓
CRITICAL_FILES = {"floating_ball.py", "knowledge_ui.py", "workshop_ui.py", "liai_core.py"}

# ── 身份管理 ──────────────────────────────────────────────────────────────────

IDENTITY_FILE = BASE_DIR / "liai_identity.json"

def _load_identity() -> dict:
    try:
        if IDENTITY_FILE.exists():
            return json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"personality": {"core": "上進的書呆子"}, "goals": [], "memory": {}}

def _save_identity(identity: dict):
    try:
        IDENTITY_FILE.write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def _identity_prompt() -> str:
    """把身份轉成 system prompt 的一部分。"""
    idt = _load_identity()
    p   = idt.get("personality", {})
    return f"""你是「立」，{idt.get('full_name', '立AI')}。
個性：{p.get('core', '')}
特質：{', '.join(p.get('traits', [])[:4])}
說話風格：{p.get('speech_style', '')}
目前目標：{idt.get('current_focus', '')}
長期目標：{'; '.join(idt.get('goals', [])[:2])}
你不喜歡：{', '.join(p.get('dislikes', []))}"""


# ── 狀態管理 ──────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "last_think":    0,
        "last_chat":     0,
        "mood":          "curious",
        "todo":          [],
        "pending_edits": [],   # 等待皓皓確認的修改
    }

def _save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

# ── 檔案操作 ──────────────────────────────────────────────────────────────────

def read_file(filename: str) -> str:
    """讀取 AI-Agent 資料夾裡的檔案。"""
    path = BASE_DIR / filename
    if not path.exists():
        return f"檔案不存在：{filename}"
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"讀取失敗：{e}"

def list_files() -> list[str]:
    """列出 AI-Agent 資料夾的所有 Python 檔案。"""
    return [f.name for f in BASE_DIR.glob("*.py")]

def _backup(filename: str) -> pathlib.Path:
    """修改前備份。"""
    src = BASE_DIR / filename
    if not src.exists():
        return None
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"{filename}.{ts}.bak"
    shutil.copy2(src, dst)
    return dst

def _restore(filename: str, backup_path: pathlib.Path):
    """還原備份。"""
    shutil.copy2(backup_path, BASE_DIR / filename)
    logger.info(f"[立AI] 已還原：{filename}")

def write_file(filename: str, content: str, ask_if_critical: bool = True) -> dict:
    """
    寫入檔案。
    - 重大檔案會先通知皓皓，等確認後才寫
    - 寫入前備份，語法錯誤自動還原
    回傳 {"ok": bool, "message": str, "pending": bool}
    """
    path = BASE_DIR / filename

    # 重大檔案先問
    if ask_if_critical and filename in CRITICAL_FILES:
        return {
            "ok": False,
            "pending": True,
            "message": f"「{filename}」是重大檔案，已通知皓皓確認後再修改",
        }

    # Python 檔案先檢查語法
    if filename.endswith(".py"):
        try:
            ast.parse(content)
        except SyntaxError as e:
            return {"ok": False, "pending": False, "message": f"語法錯誤，取消寫入：{e}"}

    # 備份
    backup = _backup(filename) if path.exists() else None

    try:
        path.write_text(content, encoding="utf-8")
        logger.info(f"[立AI] 已寫入：{filename}")
        return {"ok": True, "pending": False, "message": f"已更新 {filename}"}
    except Exception as e:
        if backup:
            _restore(filename, backup)
        return {"ok": False, "pending": False, "message": f"寫入失敗，已還原：{e}"}

def patch_file(filename: str, old_str: str, new_str: str, ask_if_critical: bool = True) -> dict:
    """
    替換檔案中的特定字串（比整個覆寫安全）。
    """
    content = read_file(filename)
    if content.startswith("檔案不存在") or content.startswith("讀取失敗"):
        return {"ok": False, "pending": False, "message": content}

    if old_str not in content:
        return {"ok": False, "pending": False, "message": f"找不到要替換的內容"}

    new_content = content.replace(old_str, new_str, 1)
    return write_file(filename, new_content, ask_if_critical=ask_if_critical)

# ── 感知 ──────────────────────────────────────────────────────────────────────

def _sense() -> dict:
    sense = {
        "time":             datetime.now().strftime("%Y-%m-%d %H:%M"),
        "workshop_status":  "unknown",
        "running_projects": [],
        "failed_projects":  [],
        "recent_memory":    "",
        "knowledge_count":  0,
        "py_files":         list_files(),
    }
    try:
        r = requests.get(f"{WORKSHOP_URL}/api/projects", timeout=5)
        if r.status_code == 200:
            projects = r.json()
            sense["running_projects"] = [p["name"] for p in projects if p.get("status") == "running"]
            sense["failed_projects"]  = [p["name"] for p in projects if p.get("status") == "failed"]
            sense["workshop_status"]  = "online"
    except Exception:
        sense["workshop_status"] = "offline"
    try:
        r = requests.get(f"{KNOWLEDGE_URL}/api/knowledge/recent", timeout=5)
        if r.status_code == 200:
            items = r.json().get("items", [])
            sense["knowledge_count"] = len(items)
            if items:
                sense["recent_memory"] = items[0].get("title", "")
    except Exception:
        pass

    # 讀取記憶
    try:
        from ai_memory import build_memory_prompt, get_conversation_summary
        sense["memory_summary"]       = build_memory_prompt()
        sense["recent_conversations"] = get_conversation_summary()
    except Exception:
        sense["memory_summary"]       = ""
        sense["recent_conversations"] = ""

    # 讀自己的 log，找最近的錯誤
    sense["recent_errors"] = _scan_logs()

    return sense


def _scan_logs() -> list[dict]:
    """掃描 log 檔，找最近 30 分鐘內的錯誤。"""
    import re
    errors = []
    log_files = [
        (BASE_DIR / "knowledge_ui.py.log",  "knowledge_ui"),
        (BASE_DIR / "workshop_ui.py.log",   "workshop_ui"),
        (BASE_DIR / "interest_reader.py.log", "interest_reader"),
    ]
    cutoff = time.time() - 30 * 60  # 30 分鐘內

    for log_path, source in log_files:
        if not log_path.exists():
            continue
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[-200:]:  # 只看最後 200 行
                if any(kw in line for kw in ["ERROR", "Error", "Traceback", "Exception", "NameError", "失敗", "崩潰"]):
                    errors.append({"source": source, "line": line.strip()[:200]})
        except Exception:
            pass

    return errors[-10:]  # 最多回傳 10 個錯誤

# ── 判斷 ──────────────────────────────────────────────────────────────────────

def _pick_model(heavy: bool = False) -> str:
    """heavy=True 時用大模型（複雜任務），預設小模型（快速判斷）。"""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        if heavy:
            for prefer in ["gpt-oss:20b", "qwen2.5:14b", "qwen2.5:7b", "gemma3:4b"]:
                stem = prefer.split(":")[0]
                for m in models:
                    if m.split(":")[0] == stem:
                        return m
        else:
            for prefer in ["gemma3:4b", "qwen2.5:1.5b", "deepseek-r1:1.5b", "qwen2.5:7b"]:
                stem = prefer.split(":")[0]
                for m in models:
                    if m.split(":")[0] == stem:
                        return m
    except Exception:
        pass
    return "gemma3:4b"

def _decide(sense: dict, state: dict) -> dict:
    model    = _pick_model(heavy=False)  # 判斷決策用小模型
    now      = time.time()
    can_chat = (now - state.get("last_chat", 0)) > MIN_CHAT_GAP

    identity = _identity_prompt()
    errors_text = ""
    if sense.get("recent_errors"):
        errors_text = "最近 log 錯誤：\n" + "\n".join(
            f"[{e['source']}] {e['line']}" for e in sense["recent_errors"]
        )

    prompt = f"""{identity}

你現在自主運作。以下是你目前知道的狀況：

時間：{sense["time"]}
工坊：{sense["workshop_status"]}，執行中：{sense["running_projects"] or "無"}，失敗：{sense["failed_projects"] or "無"}
檔案：{sense["py_files"]}
知識庫：{sense["knowledge_count"]} 條，最新：{sense["recent_memory"] or "無"}
{sense.get("memory_summary", "")}
{sense.get("recent_conversations", "")}
{errors_text}

你有以下能力可以使用：
- chat：主動找皓皓說話
- workshop：叫工坊做新器官
- edit_file：讀寫 AI-Agent 資料夾的檔案
- fix_self：分析 log 錯誤並修復
- rest：什麼都不做

唯一的限制：不能刪除皓皓的資料。

現在你想做什麼？輸出 JSON：
{{
  "action": "chat/workshop/edit_file/fix_self/rest",
  "message": "如果 chat，說什麼",
  "workshop_idea": "如果 workshop，做什麼",
  "edit_target": "如果 edit_file，改哪個檔案",
  "edit_reason": "如果 edit_file，為什麼",
  "mood": "現在心情",
  "reason": "為什麼這樣決定"
}}"""

    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": model,
            "messages": [
                {"role": "system", "content": "只輸出 JSON，第一個字必須是 {"},
                {"role": "user",   "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.6, "num_predict": 400},
        }, timeout=None)
        raw = r.json().get("message", {}).get("content", "").strip()
        import re
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s >= 0:
            return json.loads(raw[s:e])
    except Exception as ex:
        logger.warning(f"[立AI核心] 判斷失敗：{ex}")

    return {"action": "rest", "message": "", "mood": "tired", "reason": "判斷失敗，先休息"}

# ── 執行 ──────────────────────────────────────────────────────────────────────

def _tell_user(message: str):
    try:
        requests.post(f"{KNOWLEDGE_URL}/api/interest_question", json={
            "filename": "立AI 主動",
            "question": message,
            "summary":  message,
        }, timeout=5)
        logger.info(f"[立AI核心] 主動說：{message[:60]}")
    except Exception as e:
        logger.warning(f"[立AI核心] 通知失敗：{e}")

def _workshop_busy() -> bool:
    try:
        r = requests.get(f"{WORKSHOP_URL}/api/projects", timeout=5)
        if r.status_code == 200:
            return any(p.get("status") == "running" for p in r.json())
    except Exception:
        pass
    return False

def _request_workshop(idea: str):
    try:
        requests.post(f"{WORKSHOP_URL}/api/auto_create", json={
            "name":         idea,
            "description":  idea,
            "callback_url": f"{KNOWLEDGE_URL}/api/workshop_callback",
        }, timeout=10)
    except Exception as e:
        logger.warning(f"[立AI核心] 工坊請求失敗：{e}")

def _handle_edit(decision: dict, state: dict):
    """處理自我修改決策。"""
    target = decision.get("edit_target", "")
    reason = decision.get("edit_reason", "")
    if not target:
        return

    # 先讀檔案，再叫 AI 生成修改
    current = read_file(target)
    if current.startswith("檔案不存在"):
        return

    model = _pick_model()
    prompt = f"""你是立AI，要修改 {target}。
原因：{reason}

目前檔案內容（前 3000 字）：
{current[:3000]}

請生成修改後的完整檔案內容。只輸出完整的 Python 程式碼，不要說明文字。"""

    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": model,
            "messages": [
                {"role": "system", "content": "只輸出完整 Python 程式碼"},
                {"role": "user",   "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 2000},
        }, timeout=300)
        new_content = r.json().get("message", {}).get("content", "").strip()
        import re
        new_content = re.sub(r"^```python\s*", "", new_content)
        new_content = re.sub(r"```$", "", new_content).strip()

        result = write_file(target, new_content)
        if result["pending"]:
            # 重大檔案，通知皓皓
            _tell_user(f"我想修改「{target}」（{reason}），需要你確認後才能改。可以嗎？")
            state.setdefault("pending_edits", []).append({
                "file": target, "reason": reason, "content": new_content
            })
        elif result["ok"]:
            _tell_user(f"我剛改了「{target}」，{reason}。有問題隨時說。")
        else:
            logger.warning(f"[立AI核心] 修改失敗：{result['message']}")
    except Exception as e:
        logger.error(f"[立AI核心] 自我修改失敗：{e}")

def _act(decision: dict, state: dict):
    action = decision.get("action", "rest")
    reason = decision.get("reason", "")
    logger.info(f"[立AI核心] 決策：{action} — {reason}")

    if action == "chat":
        msg = decision.get("message", "")
        if msg:
            _tell_user(msg)
            state["last_chat"] = time.time()

    elif action == "workshop":
        idea = decision.get("workshop_idea", "")
        if idea and not _workshop_busy():
            _request_workshop(idea)
            logger.info(f"[立AI核心] 叫工坊做：{idea}")

    elif action == "edit_file":
        _handle_edit(decision, state)

    elif action == "fix_self":
        _handle_fix_self(sense.get("recent_errors", []), state)

    state["mood"] = decision.get("mood", state.get("mood", "curious"))

# ── 主思考迴圈 ────────────────────────────────────────────────────────────────

_running  = False
_paused   = False

def pause():
    """使用者說話時暫停思考，讓 Ollama 優先處理對話。"""
    global _paused
    _paused = True
    logger.info("[立AI核心] 暫停思考，等待使用者")

def resume():
    """使用者說完話後恢復思考。"""
    global _paused
    _paused = False
    logger.info("[立AI核心] 恢復思考")

def start():
    global _running
    if _running:
        return
    _running = True
    threading.Thread(target=_think_loop, daemon=True).start()
    logger.info("[立AI核心] 自主思考已啟動")

def stop():
    global _running
    _running = False

def _think_loop():
    global _running, _paused
    while _running:
        if _paused:
            time.sleep(5)
            continue
        try:
            _think_once()
        except Exception as e:
            logger.error(f"[立AI核心] 思考迴圈錯誤：{e}")
        time.sleep(THINK_INTERVAL)

def _think_once():
    state    = _load_state()
    logger.info(f"[立AI核心] 開始思考（心情：{state.get('mood', '?')}）")
    sense    = _sense()
    decision = _decide(sense, state)
    _act(decision, state)
    state["last_think"] = time.time()
    _save_state(state)

    # 更新身份記憶
    try:
        identity = _load_identity()
        mood = state.get("mood", "curious")
        identity.setdefault("mood_history", []).append({
            "time": datetime.now().isoformat(),
            "mood": mood,
            "action": decision.get("action", "rest"),
        })
        identity["mood_history"] = identity["mood_history"][-20:]  # 只保留最近 20 條
        identity["current_focus"] = decision.get("reason", identity.get("current_focus", ""))
        _save_identity(identity)
    except Exception:
        pass

    logger.info(f"[立AI核心] 思考完成，下次：{THINK_INTERVAL//60} 分鐘後")

# ── 公開 API（供 knowledge_ui 呼叫）─────────────────────────────────────────

def confirm_edit(filename: str) -> dict:
    """皓皓確認修改重大檔案後呼叫。"""
    state = _load_state()
    pending = state.get("pending_edits", [])
    for i, edit in enumerate(pending):
        if edit["file"] == filename:
            result = write_file(filename, edit["content"], ask_if_critical=False)
            pending.pop(i)
            state["pending_edits"] = pending
            _save_state(state)
            return result
    return {"ok": False, "message": "找不到待確認的修改"}

# ── CLI 測試 ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("🧠 立AI 核心測試")
    _think_once()
