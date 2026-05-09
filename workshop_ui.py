# workshop_ui.py — 自我生產軟體流程工坊
# 依賴：pip install flask flask-socketio
# 使用：python workshop_ui.py
# 瀏覽器：http://localhost:7862

from flask import Flask, request, jsonify, render_template_string, Response, stream_with_context
from flask_socketio import SocketIO, emit
import pathlib, json, os, re, sqlite3, datetime, logging, traceback, subprocess, sys, threading, uuid
import requests as req

# ── 系統地圖 ──────────────────────────────────────────────────────────────────
try:
    from system_map import get_system_context
    _HAS_SYSTEM_MAP = True
except ImportError:
    _HAS_SYSTEM_MAP = False
    def get_system_context(max_chars=2000): return ""

# ── LobsterCore 整合（找不到就降級用直連 Ollama）─────────────────────────────
try:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from Lobster_Core import LobsterCore
    _lobster = LobsterCore()
    _USE_LOBSTER = True
    logging.getLogger("workshop").info("✅ LobsterCore 載入成功")
except Exception as _le:
    _lobster = None
    _USE_LOBSTER = False
    logging.getLogger("workshop").warning(f"⚠ LobsterCore 未載入，使用直連 Ollama：{_le}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("workshop")

app    = Flask(__name__)
app.config["SECRET_KEY"] = "workshop-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", allow_upgrades=True, ping_timeout=60, ping_interval=25)

# ── 資料夾 ────────────────────────────────────────────────────────────────────
WORKSHOP_DIR = pathlib.Path("workshop_data")
PROJECTS_DIR = WORKSHOP_DIR / "projects"
WORKSHOP_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# ── DB ────────────────────────────────────────────────────────────────────────
DB_PATH = WORKSHOP_DIR / "workshop.db"

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT,
            status      TEXT DEFAULT 'planning',
            created_at  TEXT,
            updated_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id                  TEXT PRIMARY KEY,
            project_id          TEXT NOT NULL,
            seq                 INTEGER,
            title               TEXT NOT NULL,
            description         TEXT,
            status              TEXT DEFAULT 'pending',
            code                TEXT,
            error               TEXT,
            repair_count        INTEGER DEFAULT 0,
            review_passed       INTEGER,
            review_report       TEXT,
            review_issues       TEXT,
            review_suggestions  TEXT,
            created_at          TEXT,
            updated_at          TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT,
            task_id    TEXT,
            level      TEXT,
            message    TEXT,
            created_at TEXT
        );
        """)

_init_db()

def _migrate_db():
    """自動補齊新欄位（舊 DB 升級用）。"""
    new_columns = [
        ("tasks", "review_passed",      "INTEGER"),
        ("tasks", "review_report",       "TEXT"),
        ("tasks", "review_issues",       "TEXT"),
        ("tasks", "review_suggestions",  "TEXT"),
    ]
    with _db() as c:
        for table, col, col_type in new_columns:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                logger.info(f"[DB] 新增欄位：{table}.{col}")
            except Exception:
                pass  # 欄位已存在，忽略

_migrate_db()

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434"
PLANNER_MODELS  = ["gpt-oss:20b", "qwen2.5:14b", "qwen2.5:7b", "gemma3:4b"]   # 規劃用大模型
CODER_MODELS    = ["deepseek-coder:6.7b-instruct-q4_K_M", "qwen2.5:14b", "gemma3:4b"]  # 程式碼生成
REVIEWER_MODELS = ["qwen2.5:14b", "qwen2.5:7b", "gemma3:4b", "gpt-oss:20b"]  # 本機審查備用模型

# ── 審查Agent 設定 ─────────────────────────────────────────────────────────────
# True = 啟用；False = 跳過
REVIEW_ENABLED = True
REVIEWER_MODE  = "remote"   # "remote" = 另一台的 reviewer_agent.py
REVIEWER_URL   = "http://100.91.121.85:7863"   # 另一台的 Tailscale IP

# 工坊自己的 callback 地址（審查完後回傳到這裡）
# 請填入本機的 Tailscale IP
WORKSHOP_CALLBACK_BASE = "http://100.91.148.59:7862"  # 主電腦 Tailscale IP

REVIEWER_MODE = "remote"   # "local" = 本機, "remote" = 遠端 Agent

def _get_models():
    try:
        r = req.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except:
        return []

def _pick(candidates):
    available = _get_models()
    for c in candidates:
        for a in available:
            if a == c or a.startswith(c.split(":")[0]):
                return a
    return candidates[-1]

# 全域 Ollama session，強制中斷時關閉
_ollama_sessions: dict = {}

def _ollama_stream(model, system, prompt, temperature=0.4, pid: str = "", num_predict: int = 2000):
    """Streaming generator，yield token strings。支援強制中斷。"""
    _lock_acquired = False
    try:
        from ollama_lock import acquire as _acq_ws
        if _acq_ws("workshop_stream", priority=2, timeout=300):
            _lock_acquired = True
    except Exception:
        pass
    session = __import__('requests').Session()
    if pid:
        _ollama_sessions[pid] = session
    try:
        with session.post(f"{OLLAMA_URL}/api/generate", json={
            "model": model, "system": system, "prompt": prompt,
            "stream": True, "options": {"temperature": temperature, "num_predict": num_predict}
        }, stream=True, timeout=None) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line: continue
                try:
                    chunk = __import__('json').loads(line)
                    tok = chunk.get("response", "")
                    if tok: yield tok
                    if chunk.get("done"): break
                except: continue
    except Exception as _e:
        yield f"__OLLAMA_ERROR__:{_e}"
        return
    finally:
        if pid and pid in _ollama_sessions:
            _ollama_sessions.pop(pid, None)
        if _lock_acquired:
            try:
                from ollama_lock import release as _rel_ws
                _rel_ws("workshop_stream")
            except Exception:
                pass

def _wait_model_loaded(model: str, timeout: int = 60) -> bool:
    """
    等待 Ollama 真的把指定模型載入完成。
    用一個小請求確認模型可用，最多等 timeout 秒。
    回傳 True 代表載入成功。
    """
    import time as _t
    start = _t.time()
    while _t.time() - start < timeout:
        try:
            r = req.post(f"{OLLAMA_URL}/api/generate", json={
                "model": model,
                "prompt": "hi",
                "stream": False,
                "options": {"num_predict": 1}
            }, timeout=10)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        _t.sleep(2)
    return False


def _unload_model(model: str) -> bool:
    """用 keep_alive:0 讓 Ollama 立刻從記憶體卸載指定模型。"""
    try:
        r = req.post(f"{OLLAMA_URL}/api/generate", json={
            "model": model, "prompt": "", "keep_alive": 0,
        }, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def _switch_model(pid: str, tid: str, target_model: str) -> bool:
    """用 keep_alive:0 卸載非目標模型，不重啟 daemon。"""
    import time as _t
    _log(pid, f"🔄 切換模型 → {target_model}...", "AI", tid)
    socketio.emit("model_switching", {"project_id": pid, "task_id": tid,
                                      "model": target_model, "status": "stopping"})
    try:
        loaded = [m["name"] for m in req.get(f"{OLLAMA_URL}/api/ps", timeout=5).json().get("models", [])]
    except Exception:
        loaded = []
    target_stem = target_model.split(":")[0]
    for m in loaded:
        if not m.startswith(target_stem):
            _log(pid, f"  ⬇ 卸載 {m}", "INFO", tid)
            _unload_model(m)
    if loaded:
        _t.sleep(1)
    _log(pid, f"⏳ 載入 {target_model}...", "AI", tid)
    socketio.emit("model_switching", {"project_id": pid, "task_id": tid,
                                      "model": target_model, "status": "loading"})
    ok = _wait_model_loaded(target_model, timeout=180)
    if ok:
        _log(pid, f"✅ {target_model} 已就緒", "OK", tid)
        socketio.emit("model_switching", {
            "project_id": pid,
            "task_id":    tid,
            "model":      target_model,
            "status":     "ready",
        })
    else:
        _log(pid, f"⚠ {target_model} 載入逾時，繼續嘗試", "WARN", tid)
    return ok


def _force_stop_ollama(pid: str):
    """強制關閉該專案的 Ollama 連線。"""
    session = _ollama_sessions.pop(pid, None)
    if session:
        try:
            session.close()
            logger.info(f"[{pid[:8]}] 已強制中斷 Ollama 連線")
        except Exception:
            pass

def _ollama_once(model, system, prompt, temperature=0.3, timeout=None):
    """Non-streaming call，回傳完整字串。"""
    _lock_acquired = False
    try:
        from ollama_lock import acquire as _acq_wo, release as _rel_wo
        if _acq_wo("workshop", priority=2, timeout=300):
            _lock_acquired = True
    except Exception:
        pass
    try:
        r = req.post(f"{OLLAMA_URL}/api/generate", json={
            "model": model, "system": system, "prompt": prompt,
            "stream": False, "options": {"temperature": temperature, "num_predict": -1}
        }, timeout=timeout)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    finally:
        if _lock_acquired:
            try:
                from ollama_lock import release as _rel_wo2
                _rel_wo2("workshop")
            except Exception:
                pass

# ── LobsterCore 包裝函式（只保留修復閉環）────────────────────────────────────

def _lobster_plan(requirement: str, kb_context: str = "") -> str:
    """規劃任務 — 直連 Ollama（Lobster 規劃功能暫未啟用）。"""
    sys_ctx     = get_system_context(max_chars=1500) if _HAS_SYSTEM_MAP else ""
    sys_section = f"\n\n{sys_ctx}" if sys_ctx else ""
    prompt = f"把以下需求拆解成 3~8 個獨立可測試的 Python 任務，輸出嚴格 JSON：\n\n{requirement}{kb_context}{sys_section}"
    return _ollama_once(_pick(PLANNER_MODELS),
        "你是資深軟體工程師，只輸出 JSON，第一個字必須是 {", prompt, temperature=0.3)

def _lobster_code_stream(system: str, prompt: str, pid: str = ""):
    """生成程式碼 — 直連 Ollama（限制 1500 tokens 避免超長輸出）。"""
    yield from _ollama_stream(_pick(CODER_MODELS), system, prompt,
                              temperature=0.2, pid=pid)

def _lobster_repair(code: str, error: str, task_desc: str) -> str:
    """
    修復程式碼 — 直連本機 Ollama，不使用 LobsterCore 分散式推論。
    """
    # 確保帶入完整程式碼（不截斷）
    code_section = code if len(code) <= 2000 else code[:2000] + "\n# ...（截斷）"
    prompt = (f"任務：{task_desc}\n\n"
              f"錯誤訊息：\n{error[:300]}\n\n"
              f"以下是完整的有問題程式碼，請修正並輸出完整版本：\n"
              f"```python\n{code_section}\n```\n\n"
              f"輸出修正後的完整 Python 程式碼（不要說明，直接輸出程式碼）：")
    return _ollama_once(
        _pick(CODER_MODELS),
        "你是 Python 程式碼修復機器。規則：1.只輸出純 Python 程式碼 2.不寫任何說明文字 3.不用 markdown 4.輸出必須是完整可執行的程式碼 5.這是 Windows 系統不要用 Linux 指令 6.優先使用現有模組不要重新實作",
        prompt, temperature=0.1
    )

def _lobster_judge(code: str, task_desc: str, run_output: str) -> bool:
    """審查 — 暫未啟用，直接回傳 True。"""
    return True

# ── 審查函式 ──────────────────────────────────────────────────────────────────

def _review_plan(pid: str, tasks: list[dict]) -> dict:
    """審查任務規劃是否合理。"""
    if not REVIEW_ENABLED:
        return {"passed": True, "issues": [], "suggestions": [], "report": ""}

    if REVIEWER_MODE == "remote":
        try:
            r = req.post(f"{REVIEWER_URL}/api/review/plan",
                json={"project_id": pid, "tasks": tasks}, timeout=120)
            return r.json()
        except Exception as e:
            _log(pid, f"⚠ 遠端審查失敗，改用本機：{e}", "WARN")

    # 本機模擬審查：用不同模型
    model = _pick(REVIEWER_MODELS)
    _log(pid, f"🔍 審查規劃中（{model}）...", "AI")

    task_text = "\n".join(
        f"{t['seq']}. {t['title']}：{t['description'] or ''}" for t in tasks
    )
    system = """你是嚴格的技術主管，負責審查 AI 產出的任務規劃。

輸出嚴格 JSON（不要其他文字）：
{
  "passed": true/false,
  "issues": ["問題1", "問題2"],
  "suggestions": ["建議1", "建議2"],
  "report": "總結說明（2-3句）"
}

審查重點：
1. 任務之間是否有依賴關係缺失
2. 任務描述是否夠具體可實作
3. 任務數量和分配是否合理
4. 有沒有遺漏重要步驟
用繁體中文回答。"""

    prompt = "請審查以下任務規劃：\n\n" + task_text

    try:
        raw = _ollama_once(model, system, prompt, temperature=0.2)
        start, end = raw.find("{"), raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        return result
    except Exception as e:
        return {"passed": True, "issues": [], "suggestions": [],
                "report": f"審查解析失敗，自動通過：{e}"}


def _review_code(pid: str, task: dict, code: str, run_output: str) -> dict:
    """
    審查程式碼品質和正確性。
    回傳 {"passed": bool, "issues": [...], "suggestions": [...],
          "fixed_code": str or None, "report": str}
    """
    if REVIEWER_MODE == "remote":
        try:
            r = req.post(f"{REVIEWER_URL}/api/review/code",
                json={"project_id": pid, "task": task,
                      "code": code, "run_output": run_output}, timeout=180)
            return r.json()
        except Exception as e:
            _log(pid, f"⚠ 遠端審查失敗，改用本機：{e}", "WARN")

    model = _pick(REVIEWER_MODELS)
    _log(pid, f"🔍 審查程式碼中（{model}）...", "AI")

    system = """你是嚴格的 Python 程式碼審查員。

輸出嚴格 JSON（不要其他文字）：
{
  "passed": true/false,
  "issues": ["問題1", "問題2"],
  "suggestions": ["優化建議1"],
  "fixed_code": "修正後的完整程式碼（如果有問題的話）或 null",
  "report": "審查總結（2-3句）"
}

審查重點：
1. 程式碼邏輯是否正確
2. 有沒有潛在的 bug 或例外沒處理
3. 執行結果是否符合任務要求
4. 是否有更好的實作方式
用繁體中文回答，fixed_code 用英文（Python 程式碼）。"""

    prompt = f"""任務：{task['title']}
說明：{task['description'] or ''}

程式碼：
```python
{code}
```

執行結果：
{run_output or '（無輸出）'}

請審查："""

    try:
        raw = _ollama_once(model, system, prompt, temperature=0.2)
        start, end = raw.find("{"), raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        return result
    except Exception as e:
        return {"passed": True, "issues": [], "suggestions": [],
                "fixed_code": None, "report": f"審查解析失敗，自動通過：{e}"}

# ── 工具函式 ──────────────────────────────────────────────────────────────────
def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")

def _send_to_reviewer(pid: str, task_id: str, content: str,
                      review_type: str, filename: str,
                      timeout: int = 0) -> dict | None:
    """
    送內容給審查Agent。
    timeout > 0 → 同步等待審查結果（秒），等到才回傳結果 dict。
    timeout = 0 → 非同步，立刻回傳 None。
    """
    if not REVIEW_ENABLED:
        return None
    callback_url = f"{WORKSHOP_CALLBACK_BASE}/api/review_callback"

    # 建立等待 Event（用 task_id 當 key）
    wait_ev = threading.Event()
    _review_events[task_id] = wait_ev
    _review_results.pop(task_id, None)

    payload = {
        "content":      content,
        "filename":     filename,
        "data_type":    "任務規劃" if review_type == "plan" else "Python 程式碼",
        "review_type":  review_type,
        "task_id":      task_id,
        "callback_url": callback_url,
        "source_url":   WORKSHOP_CALLBACK_BASE,
    }
    try:
        r = req.post(f"{REVIEWER_URL}/review", json=payload, timeout=10)
        d = r.json()
        if d.get("success"):
            sid = d.get("session_id", "")
            _log(pid, f"🔍 已送審查Agent（session={sid}，type={review_type}）", "AI")
        else:
            _log(pid, f"⚠ 審查Agent 拒絕：{d.get('error','')}", "WARN")
            _review_events.pop(task_id, None)
            return None
    except Exception as e:
        _log(pid, f"⚠ 審查Agent 連線失敗：{e}，跳過審查", "WARN")
        _review_events.pop(task_id, None)
        return None

    if timeout <= 0:
        return None  # 非同步模式

    # 同步等待 callback
    _log(pid, f"⏳ 等待審查結果（最多 {timeout//60} 分鐘）...", "AI")
    signaled = wait_ev.wait(timeout=timeout)
    _review_events.pop(task_id, None)
    if not signaled:
        _log(pid, "⚠ 審查等待超時，繼續執行", "WARN")
        return None
    result = _review_results.pop(task_id, None)
    _log(pid, "✅ 收到審查結果", "OK")
    return result


def _notify_ai(pid: str, status: str, message: str):
    """通知 knowledge_ui 的立AI，工坊專案狀態更新。"""
    callback_url = _ai_callbacks.get(pid)
    if not callback_url:
        return
    try:
        payload = {
            "project_id": pid,
            "status":     status,   # "done" / "failed" / "paused"
            "message":    message,
        }
        req.post(callback_url, json=payload, timeout=5)
        logger.info(f"[{pid[:8]}] 已通知立AI：{status}")
    except Exception as e:
        logger.warning(f"[{pid[:8]}] 通知立AI 失敗：{e}")


def _broadcast(event, data, project_id=None):
    room = f"project_{project_id}" if project_id else None
    if room:
        socketio.emit(event, data, room=room)
    else:
        socketio.emit(event, data)


def _emit_step(pid, tid, step, status="active", detail=""):
    """發送任務內部步驟進度。status: active|done|error"""
    socketio.emit("task_step", {
        "project_id": pid, "task_id": tid,
        "step": step, "status": status, "detail": detail
    })


def _scan_local_modules(max_chars: int = 2000) -> str:
    """
    掃描 assembled 資料夾，提取每個模組的公開介面（函式、類別、docstring）。
    讓 model 知道有哪些本地模組可以用。
    """
    import ast as _ast
    assembled_dir = WORKSHOP_DIR / "assembled"
    if not assembled_dir.exists():
        return ""

    lines = ["現有系統檔案（可直接 import 使用）："]
    total = 0

    for path in sorted(assembled_dir.glob("*.py"), key=lambda x: x.stat().st_mtime, reverse=True):
        module_name = path.stem
        try:
            code = path.read_text(encoding="utf-8")
            tree = _ast.parse(code)
        except Exception:
            continue

        # 擷取公開介面
        items = []
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    doc = _ast.get_docstring(node) or ""
                    args = [a.arg for a in node.args.args if a.arg != "self"]
                    items.append(f"  def {node.name}({', '.join(args)})" +
                                 (f"  # {doc.split(chr(10))[0]}" if doc else ""))
            elif isinstance(node, _ast.ClassDef):
                if not node.name.startswith("_"):
                    doc = _ast.get_docstring(node) or ""
                    items.append(f"  class {node.name}" +
                                 (f"  # {doc.split(chr(10))[0]}" if doc else ""))

        if items:
            header = f"\n# {module_name}.py"
            entry = header + "\n" + "\n".join(items[:10])
            if total + len(entry) > max_chars:
                break
            lines.append(entry)
            total += len(entry)

    return "\n".join(lines) if len(lines) > 1 else ""


def _validate_assembled(path) -> dict:
    """
    自動檢查組裝好的器官檔案。
    回傳 {"ok": bool, "errors": [...], "warnings": [...]}
    """
    import ast, py_compile, importlib.util, tempfile, os
    result = {"ok": True, "errors": [], "warnings": []}
    code = path.read_text(encoding="utf-8")

    # 1. 語法檢查
    try:
        ast.parse(code)
    except SyntaxError as e:
        result["ok"] = False
        result["errors"].append(f"語法錯誤 第{e.lineno}行：{e.msg}")
        return result   # 語法錯誤直接返回，後續無法繼續

    # 2. 縮排一致性（用 py_compile）
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as tf:
            tf.write(code)
            tmp_path = tf.name
        py_compile.compile(tmp_path, doraise=True)
        os.unlink(tmp_path)
    except py_compile.PyCompileError as e:
        result["ok"] = False
        result["errors"].append(f"編譯錯誤：{e}")
        try: os.unlink(tmp_path)
        except: pass
        return result

    # 3. import 檢查（找出缺少的第三方套件）
    tree = ast.parse(code)
    missing = []
    stdlib = {
        "os","sys","re","json","time","math","random","datetime","pathlib",
        "typing","collections","itertools","functools","threading","subprocess",
        "logging","unittest","io","copy","abc","enum","dataclasses","contextlib",
        "inspect","socket","struct","hashlib","base64","urllib","http","email",
        "csv","sqlite3","pickle","shutil","tempfile","glob","fnmatch","signal",
        "traceback","warnings","weakref","gc","platform","uuid",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod not in stdlib:
                    spec = importlib.util.find_spec(mod)
                    if spec is None:
                        missing.append(mod)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if mod not in stdlib and mod != "":
                    spec = importlib.util.find_spec(mod)
                    if spec is None:
                        missing.append(mod)
    if missing:
        result["warnings"].append(f"找不到套件：{', '.join(set(missing))}（可能需要 pip install）")

    # 4. 檢查是否有可呼叫的函式或類別
    has_callable = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in ast.walk(tree)
    )
    if not has_callable:
        result["warnings"].append("沒有找到可呼叫的函式或類別")

    # 5. 檢查空白器官（只有 import 沒有實作）
    non_import_nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                          ast.Assign, ast.Expr))
    ]
    if len(non_import_nodes) < 2:
        result["warnings"].append("器官內容過少，可能尚未實作")

    return result


def _auto_fix_assembled(path, pid: str, max_rounds: int = 5) -> bool:
    """
    驗證失敗時，自動送給 AI 修正，直到通過或達最大次數。
    回傳 True = 最終通過，False = 無法修正。
    """
    import ast as _ast

    for round_num in range(1, max_rounds + 1):
        val = _validate_assembled(path)
        if val["ok"] and not any("過少" in w or "空殼" in w for w in val.get("warnings", [])):
            _log(pid, f"✅ 自動修正完成（第 {round_num} 輪通過）", "OK")
            return True

        issues = val["errors"] + val.get("warnings", [])
        _log(pid, f"🔧 自動修正第 {round_num} 輪，問題：{'; '.join(issues)}", "WARN")

        code = path.read_text(encoding="utf-8")
        prompt = (
            f"以下 Python 程式碼有問題，請修正並回傳完整修正後的程式碼。\n"
            f"問題：{chr(10).join(issues)}\n\n"
            f"程式碼：\n```python\n{code}\n```\n\n"
            f"只回傳修正後的完整 Python 程式碼，不要任何說明或 markdown。"
        )
        try:
            model = CODER_MODELS[0]
            r = req.post(f"{OLLAMA_URL}/api/generate", json={
                "model":  model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 2000},
            }, timeout=None)
            raw = r.json().get("response", "").strip()
            # 清理 markdown
            import re as _re
            raw = _re.sub(r"^```[a-z]*\n?", "", raw)
            raw = _re.sub(r"\n?```$", "", raw).strip()
            if not raw:
                _log(pid, f"⚠ 第 {round_num} 輪 AI 回應空白", "WARN")
                continue
            # 先語法檢查再存檔
            try:
                _ast.parse(raw)
            except SyntaxError as e:
                _log(pid, f"⚠ 第 {round_num} 輪修正後仍有語法錯誤：{e}", "WARN")
                continue
            path.write_text(raw, encoding="utf-8")
            _log(pid, f"📝 第 {round_num} 輪已套用修正", "OK")
        except Exception as e:
            _log(pid, f"⚠ 第 {round_num} 輪修正失敗：{e}", "ERROR")
            continue

    val = _validate_assembled(path)
    if val["ok"]:
        _log(pid, f"✅ 自動修正完成（{max_rounds} 輪後通過）", "OK")
        return True
    _log(pid, f"❌ 自動修正失敗，已達最大輪數 {max_rounds}，需人工介入", "ERROR")
    return False


def _clean_assembled_code(task_codes: list) -> str:
    """
    清理並合併多個任務的程式碼：
    1. 移除 markdown fences
    2. 去重複函式/類別定義
    3. 合併 import 到頂部
    """
    import re as _re, ast as _ast

    cleaned = []
    for code in task_codes:
        if not code.strip():
            continue
        # 移除 markdown fences
        code = _re.sub(r"```(?:python)?\s*\n?", "", code)
        code = _re.sub(r"\n?```", "", code)
        cleaned.append(code.strip())

    combined = "\n\n".join(cleaned)

    try:
        tree = _ast.parse(combined)
    except SyntaxError:
        return combined

    seen_defs    = set()
    seen_imports = set()
    top_imports  = []
    other_nodes  = []

    for node in tree.body:
        if isinstance(node, (_ast.Import, _ast.ImportFrom)):
            key = _ast.dump(node)
            if key not in seen_imports:
                seen_imports.add(key)
                top_imports.append(_ast.unparse(node))
            continue
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            if node.name in seen_defs:
                continue
            seen_defs.add(node.name)
        other_nodes.append(_ast.unparse(node))

    parts = []
    if top_imports:
        parts.append("\n".join(sorted(set(top_imports))))
    parts.extend(other_nodes)
    return "\n\n".join(parts)


def _auto_assemble(pid: str):
    """專案完成後自動組裝成 .py 器官檔，並通知 desktop_agent。"""
    try:
        with _db() as c:
            p     = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            tasks = c.execute(
                "SELECT * FROM tasks WHERE project_id=? AND status='done' ORDER BY seq", (pid,)
            ).fetchall()
        if not p or not tasks:
            return

        assembled_dir = WORKSHOP_DIR / "assembled"
        assembled_dir.mkdir(exist_ok=True)
        safe_name = p["name"].replace(" ", "_").replace("/", "_")
        out_path  = assembled_dir / f"{safe_name}.py"

        req_lines = [l.strip() for l in (p["description"] or "").splitlines()
                     if l.strip() and not l.strip().startswith("【") and "審查" not in l]
        module_doc = req_lines[0][:120] if req_lines else p["name"]
        header = [
            f'"""{module_doc}"""',
            f"# ── 工坊組裝：{p['name']} ──────────────────────────────────────────",
            f"# 組裝時間：{_now()}",
            f"# 任務數：{len(tasks)}",
            "",
        ]
        task_codes = []
        for t in tasks:
            code = (t["code"] or "").strip()
            if not code:
                continue
            task_codes.append(f"# ── [{t['seq']}] {t['title']}\n{code}")
        cleaned = _clean_assembled_code(task_codes)
        out_path.write_text("\n".join(header) + "\n" + cleaned, encoding="utf-8")
        _log(pid, f"🔩 已自動組裝器官：{out_path.name}", "OK")

        # 自動 import 驗證
        try:
            import subprocess as _spv, sys as _sysv, os as _osv, re as _rev
            _env_v = _osv.environ.copy()
            _env_v["PYTHONPATH"] = str(WORKSHOP_DIR.parent.resolve()) + _osv.pathsep + _env_v.get("PYTHONPATH","")
            _vr = _spv.run(
                [_sysv.executable, "-c",
                 f"import importlib.util; spec=importlib.util.spec_from_file_location('_t',r'{out_path}'); "
                 f"m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK')"],
                capture_output=True, text=True, timeout=15,
                cwd=str(WORKSHOP_DIR.parent.resolve()), env=_env_v
            )
            if "OK" in _vr.stdout:
                _log(pid, f"✅ 器官驗證通過：{out_path.name}", "OK")
            else:
                _missing = _rev.findall(r"No module named '([^']+)'", _vr.stderr)
                if _missing:
                    _log(pid, f"ℹ 器官警告：找不到套件：{', '.join(_missing)}（可能需要 pip install）", "INFO")
                else:
                    _log(pid, f"ℹ 器官載入警告：{_vr.stderr.strip()[:100]}", "INFO")
        except Exception as _ve:
            _log(pid, f"ℹ 器官驗證跳過：{_ve}", "INFO")

        # 自動驗證，失敗則自動修正
        val = _validate_assembled(out_path)
        if not val["ok"] or any("過少" in w or "空殼" in w for w in val.get("warnings", [])):
            _log(pid, f"⚠ 器官驗證失敗，啟動自動修正：{out_path.name}", "WARN")
            threading.Thread(
                target=_auto_fix_assembled, args=(out_path, pid), daemon=True
            ).start()
        else:
            if val["warnings"]:
                for w in val["warnings"]:
                    _log(pid, f"ℹ 器官警告：{w}", "WARN")
            _log(pid, f"✅ 器官驗證通過：{out_path.name}", "OK")

        # 通知前端刷新器官庫
        socketio.emit("organ_assembled", {
            "name":     p["name"],
            "filename": out_path.name,
            "path":     str(out_path),
        })

        # 自動更新技能描述（背景 AI 分析，讓立AI 知道新器官）
        def _update_skills():
            try:
                from organ_skill_system import generate_skill_json, _ai_describe_skill, SKILLS_DIR
                import json as _json
                SKILLS_DIR.mkdir(parents=True, exist_ok=True)
                basic = generate_skill_json(out_path)
                skill = _ai_describe_skill(out_path, basic)
                json_path = SKILLS_DIR / (out_path.stem + ".json")
                json_path.write_text(
                    _json.dumps(skill, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                logger.info(f"[AutoAssemble] 技能描述已更新：{json_path.name}")
            except Exception as se:
                logger.warning(f"[AutoAssemble] 技能描述更新失敗：{se}")
        threading.Thread(target=_update_skills, daemon=True).start()

        # ── Git 自動 commit ────────────────────────────────────────────────
        def _git_commit():
            try:
                import subprocess as _sp
                git_dir = WORKSHOP_DIR.parent.resolve()  # AI-Agent/ 資料夾
                # 確認是 git repo
                result = _sp.run(
                    ["git", "rev-parse", "--is-inside-work-tree"],
                    capture_output=True, cwd=str(git_dir),
                    creationflags=_sp.CREATE_NO_WINDOW
                )
                if result.returncode != 0:
                    return

                # git add 組裝的器官和技能描述
                _sp.run(["git", "add",
                         str(out_path),
                         str(WORKSHOP_DIR / "skills"),
                         ], capture_output=True, cwd=str(git_dir),
                        creationflags=_sp.CREATE_NO_WINDOW)

                commit_msg = f"器官：{p['name']} — 自動組裝 {_now()[:16]}"
                result = _sp.run(
                    ["git", "commit", "-m", commit_msg],
                    capture_output=True, text=True, cwd=str(git_dir),
                    creationflags=_sp.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    _log(pid, f"📦 Git commit：{commit_msg}", "OK")
                else:
                    # 沒有變動也不算錯
                    if "nothing to commit" not in result.stdout:
                        _log(pid, f"⚠ Git commit 失敗：{result.stderr[:100]}", "WARN")
            except Exception as ge:
                _log(pid, f"⚠ Git 自動 commit 失敗：{ge}", "WARN")
        threading.Thread(target=_git_commit, daemon=True).start()
    except Exception as e:
        logger.warning(f"[AutoAssemble] 組裝失敗（不影響主流程）：{e}")


def _save_project_to_knowledge(pid: str):
    """專案完成後自動存進 knowledge_ui（port 7861）。"""
    import socket as _sock
    with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', 7861)) != 0:
            logger.info(f"[{pid[:8]}] knowledge_ui 未運行，跳過自動存檔")
            return
    try:
        with _db() as c:
            p     = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            tasks = c.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY seq", (pid,)).fetchall()
        if not p:
            return
        # 組成知識庫內容
        lines = [f"需求：{p['description'] or '（無）'}\n"]
        for t in tasks:
            status_icon = "✅" if t["status"] == "done" else "❌"
            lines.append(f"{status_icon} [{t['seq']}] {t['title']}")
            if t["description"]:
                lines.append(f"   說明：{t['description']}")
            if t["code"]:
                lines.append(f"   程式碼：\n```python\n{t['code'][:500]}\n```")
        content = "\n".join(lines)
        title   = f"【工坊】{p['name']}"
        payload = {
            "title":      title,
            "content":    content,
            "importance": 8,
            "tags":       ["工坊產出", "程式碼", p["name"]],
        }
        r = req.post("http://localhost:7861/api/add/text",
                     json=payload, timeout=10)
        if r.status_code == 200:
            logger.info(f"[{pid[:8]}] 已自動存進知識庫：{title}")
        else:
            logger.warning(f"[{pid[:8]}] 存進知識庫失敗：{r.status_code}")
    except Exception as e:
        logger.warning(f"[{pid[:8]}] 存進知識庫例外：{e}")

def _log(project_id, message, level="INFO", task_id=None):
    with _db() as c:
        c.execute("INSERT INTO logs (project_id,task_id,level,message,created_at) VALUES (?,?,?,?,?)",
                  (project_id, task_id, level, message, _now()))
    _broadcast("log", {"project_id": project_id, "task_id": task_id,
                       "level": level, "message": message, "ts": _now()}, project_id)
    logger.info(f"[{project_id[:8]}] {message}")

def _is_server_code(code: str) -> bool:
    """
    判斷程式碼是否應跳過直接執行，改做語法檢查。
    涵蓋：長駐服務、需要命令列參數、本地模組依賴、GUI、硬體、網路監聽等情況。
    """
    patterns = [
        # ── 確定會佔用 port 或永久阻塞的長駐服務 ──────────────────
        "app.run(", "socketio.run(", "uvicorn.run(",
        "server.serve_forever", "serve_forever", "run_forever",
        "socket.bind(", "TCPServer", "HTTPServer", "ThreadingTCPServer",
        "BaseServer", "start_server", "grpc.server", "zmq.Context",

        # ── 本地自訂模組 import（相對 import 或已知同專案模組）─────
        "from . import", "from ..",
        "import AlarmScheduler", "from AlarmScheduler",
        "import audio_player", "from audio_player",

        # ── GUI 框架（需要視覺環境，無法在 subprocess 執行）────────
        "PyQt", "PySide", "wx.App", "kivy",
        "QApplication", "gtk.main", "Gtk.main",

        # ── 硬體 / 音訊（需要實體裝置）────────────────────────────
        "playsound", "pygame.mixer", "sounddevice", "pyaudio",
        "serial.Serial", "smbus", "RPi.GPIO",
        "picamera", "pynput", "keyboard.on_press",

        # ── 需要外部服務的資料庫連線 ───────────────────────────────
        "psycopg2.connect", "pymysql.connect", "cx_Oracle",
        "MongoClient(", "redis.Redis(", "elasticsearch",

        # ── 測試框架（需要特定執行環境）───────────────────────────
        "unittest.main()", "pytest.main(", "nose.run(",
    ]
    code_lower = code.lower()
    if any(p.lower() in code_lower for p in patterns):
        return True

    # 額外偵測：import 非標準函式庫的本地模組
    # 例如 from XxxYyy import ... 其中 XxxYyy 不像標準套件命名
    import re
    local_imports = re.findall(r"^from\s+([A-Z][A-Za-z0-9_]+)\s+import", code, re.MULTILINE)
    if local_imports:
        stdlib = {
            "os", "sys", "re", "json", "time", "math", "random", "datetime",
            "pathlib", "typing", "collections", "itertools", "functools",
            "threading", "subprocess", "logging", "unittest", "io", "copy",
            "abc", "enum", "dataclasses", "contextlib", "inspect",
        }
        for mod in local_imports:
            if mod not in stdlib:
                return True

    return False

def _run_code(code: str, project_id: str, stop_ev=None) -> tuple[bool, str]:
    """
    執行 Python code，回傳 (success, output)。
    如果偵測到長駐服務類型的程式碼，改用語法檢查代替執行。
    """
    import os as _os
    tmp = WORKSHOP_DIR / f"tmp_{project_id[:8]}.py"
    tmp.write_text(code, encoding="utf-8")

    # 設定 PYTHONPATH 讓器官能找到系統模組
    env = _os.environ.copy()
    base_dir = str(WORKSHOP_DIR.parent.resolve())
    env["PYTHONPATH"] = base_dir + _os.pathsep + env.get("PYTHONPATH", "")

    try:
        # 長駐服務類：只做語法檢查，不實際執行
        if _is_server_code(code):
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(tmp)],
                capture_output=True, text=True, timeout=10,
                cwd=base_dir, env=env
            )
            if result.returncode == 0:
                return True, "（伺服器/服務類程式碼，語法檢查通過，跳過實際執行）"
            else:
                return False, result.stderr.strip()

             # 一般程式碼：Popen 執行，支援 stop_ev 中斷
        import time as _time
        proc = subprocess.Popen(
            [sys.executable, str(tmp)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=base_dir, env=env
        )
        deadline = 30.0; elapsed = 0.0
        while proc.poll() is None:
            if stop_ev and stop_ev.is_set():
                proc.kill(); return False, "__PAUSED__"
            _time.sleep(0.1); elapsed += 0.1
            if elapsed >= deadline:
                proc.kill()
                return False, "執行超時（30秒），程式可能需要外部資源或是服務類程式碼"
        stdout, stderr = proc.communicate()
        output = (stdout + stderr).strip()
        success = proc.returncode == 0
        return success, output
    except subprocess.TimeoutExpired:
        return False, "執行超時（30秒），程式可能需要外部資源或是服務類程式碼"
    except Exception as e:
        return False, str(e)
    finally:
        tmp.unlink(missing_ok=True)

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>⚙ 工坊</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Noto+Sans+TC:wght@300;400;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.min.js"></script>
<style>
:root {
  --bg:       #0a0b0d;
  --surface:  #111316;
  --panel:    #161a1f;
  --border:   #1e2530;
  --border2:  #2a3340;
  --text:     #c8d0db;
  --muted:    #556070;
  --accent:   #00d4ff;
  --accent2:  #ff6b35;
  --success:  #00e676;
  --warning:  #ffb300;
  --danger:   #ff3d57;
  --planning: #7c5cbf;
  --running:  #00d4ff;
  --done:     #00e676;
  --failed:   #ff3d57;
  --pending:  #556070;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; background: var(--bg); color: var(--text);
  font-family: 'Noto Sans TC', sans-serif; font-size: 14px; overflow: hidden; }

/* ── 格線背景 ── */
body::before {
  content: '';
  position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    linear-gradient(rgba(0,212,255,.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,212,255,.03) 1px, transparent 1px);
  background-size: 40px 40px;
}

/* ── 頂部 bar ── */
#topbar {
  position: fixed; top: 0; left: 0; right: 0; height: 48px; z-index: 100;
  background: rgba(10,11,13,.95); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 16px; padding: 0 20px;
  backdrop-filter: blur(8px);
}
#topbar .logo {
  font-family: 'Space Mono', monospace; font-size: .9rem; color: var(--accent);
  letter-spacing: .12em; white-space: nowrap;
}
#topbar .logo span { color: var(--accent2); }
#model-badge {
  font-family: 'Space Mono', monospace; font-size: .65rem;
  color: var(--muted); border: 1px solid var(--border2);
  padding: 2px 8px; border-radius: 3px;
}
#topbar .spacer { flex: 1; }
#new-project-btn {
  background: var(--accent); color: #000; border: none; border-radius: 4px;
  padding: 6px 16px; font-size: .8rem; font-weight: 700; cursor: pointer;
  font-family: 'Space Mono', monospace; letter-spacing: .05em;
  transition: all .15s;
}
#new-project-btn:hover { background: #33ddff; transform: translateY(-1px); }

/* ── 主佈局 ── */
#layout {
  position: fixed; top: 48px; left: 0; right: 0; bottom: 0;
  display: grid; grid-template-columns: 260px 1fr 320px; z-index: 1;
}

/* ── 左側專案列表 ── */
#sidebar {
  background: var(--surface); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
#sidebar-header {
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  font-family: 'Space Mono', monospace; font-size: .7rem;
  color: var(--muted); letter-spacing: .12em;
}
#projects-list { flex: 1; overflow-y: auto; padding: 8px; }
.proj-item {
  padding: 10px 12px; border-radius: 6px; cursor: pointer;
  border: 1px solid transparent; margin-bottom: 4px;
  transition: all .15s;
}
.proj-item:hover { background: var(--panel); border-color: var(--border2); }
.proj-item.active { background: rgba(0,212,255,.06); border-color: rgba(0,212,255,.25); }
.proj-item .proj-name {
  font-size: .82rem; font-weight: 700; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.proj-item .proj-meta {
  font-family: 'Space Mono', monospace; font-size: .62rem;
  color: var(--muted); margin-top: 3px; display: flex; gap: 8px; align-items: center;
}
.status-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  display: inline-block;
}
.status-planning { background: var(--planning); }
.status-running  { background: var(--running); animation: pulse 1.2s infinite; }
.status-done     { background: var(--done); }
.status-failed   { background: var(--failed); }
.status-pending  { background: var(--pending); }
.status-paused   { background: var(--warning); }

@keyframes pulse {
  0%,100% { opacity: 1; } 50% { opacity: .3; }
}

/* ── 中央工作區 ── */
#workspace {
  background: var(--bg); display: flex; flex-direction: column; overflow-y: auto;
}
#workspace-header {
  padding: 16px 24px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 12px; flex-shrink: 0;
}
#workspace-title {
  font-family: 'Space Mono', monospace; font-size: .95rem; color: var(--text);
}
#workspace-status {
  font-family: 'Space Mono', monospace; font-size: .65rem;
  padding: 3px 10px; border-radius: 3px; letter-spacing: .08em;
}
#workspace-actions { margin-left: auto; display: flex; gap: 8px; }

/* 需求輸入區 */
#requirement-area {
  padding: 24px; flex-shrink: 0; border-bottom: 1px solid var(--border);
}
#req-label {
  font-family: 'Space Mono', monospace; font-size: .65rem;
  color: var(--muted); letter-spacing: .12em; margin-bottom: 8px;
}
#req-input {
  width: 100%; background: var(--panel); border: 1px solid var(--border2);
  border-radius: 6px; color: var(--text); padding: 12px 16px;
  font-family: 'Noto Sans TC', sans-serif; font-size: .88rem;
  line-height: 1.6; resize: vertical; min-height: 80px; max-height: 200px;
  transition: border-color .15s;
}
#req-input:focus { outline: none; border-color: var(--accent); }
#req-input::placeholder { color: var(--muted); }
#req-actions { margin-top: 10px; display: flex; gap: 8px; align-items: center; }
.btn {
  border: none; border-radius: 4px; padding: 7px 16px; cursor: pointer;
  font-size: .78rem; font-weight: 700; transition: all .15s;
  font-family: 'Space Mono', monospace; letter-spacing: .04em;
}
.btn-primary { background: var(--accent); color: #000; }
.btn-primary:hover { background: #33ddff; }
.btn-primary:disabled { opacity: .4; cursor: not-allowed; }
.btn-ghost {
  background: transparent; color: var(--muted);
  border: 1px solid var(--border2);
}
.btn-ghost:hover { color: var(--text); border-color: var(--border2); }
.btn-danger { background: rgba(255,61,87,.15); color: var(--danger); border: 1px solid rgba(255,61,87,.3); }
.btn-success { background: rgba(0,230,118,.15); color: var(--success); border: 1px solid rgba(0,230,118,.3); }
.btn-warn { background: rgba(255,179,0,.15); color: var(--warning); border: 1px solid rgba(255,179,0,.3); }

/* 任務列表 */
#tasks-area { flex: 1; overflow-y: auto; padding: 16px 24px; }
#project-detail { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
#tasks-label {
  font-family: 'Space Mono', monospace; font-size: .65rem;
  color: var(--muted); letter-spacing: .12em; margin-bottom: 12px;
}
.task-card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; margin-bottom: 10px; overflow: hidden;
  transition: border-color .15s;
}
.task-card.active  { border-color: var(--accent); }
.task-card.done    { border-color: rgba(0,230,118,.3); }
.task-card.failed  { border-color: rgba(255,61,87,.3); }
.task-card.paused  { border-color: rgba(255,179,0,.4); }
.task-header {
  padding: 12px 16px; display: flex; align-items: center; gap: 10px; cursor: pointer;
}
.task-seq {
  font-family: 'Space Mono', monospace; font-size: .65rem;
  color: var(--muted); width: 28px; flex-shrink: 0;
}
.task-title { font-size: .85rem; font-weight: 700; flex: 1; }
.task-status-label {
  font-family: 'Space Mono', monospace; font-size: .6rem;
  padding: 2px 8px; border-radius: 3px; letter-spacing: .06em;
}
.label-pending  { background: rgba(85,96,112,.2);  color: var(--muted); }
.label-running  { background: rgba(0,212,255,.15); color: var(--accent); }
.label-done     { background: rgba(0,230,118,.15); color: var(--success); }
.label-failed   { background: rgba(255,61,87,.15); color: var(--danger); }
.label-paused   { background: rgba(255,179,0,.15); color: var(--warning); }
.label-skipped  { background: rgba(85,96,112,.15); color: var(--muted); }

.task-body {
  padding: 0 16px 14px; display: none; border-top: 1px solid var(--border);
}
.task-body.open { display: block; }
.task-desc { font-size: .8rem; color: var(--muted); line-height: 1.6; padding: 10px 0 8px; }

/* code block */
.code-block {
  background: #080a0c; border: 1px solid var(--border);
  border-radius: 6px; padding: 14px; margin: 8px 0;
  font-family: 'Space Mono', monospace; font-size: .72rem;
  line-height: 1.65; color: #a8d8a8; overflow-x: auto;
  max-height: 320px; overflow-y: auto; white-space: pre-wrap;
  word-break: break-all;
}
.error-block {
  background: rgba(255,61,87,.05); border: 1px solid rgba(255,61,87,.2);
  border-radius: 6px; padding: 12px; margin: 8px 0;
  font-family: 'Space Mono', monospace; font-size: .7rem;
  color: var(--danger); line-height: 1.5; white-space: pre-wrap;
}
.task-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }

/* 空狀態 */
#empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; color: var(--muted); text-align: center; gap: 12px;
}
#empty-state .big { font-size: 3rem; }
#empty-state .hint { font-size: .82rem; line-height: 1.7; max-width: 320px; }

/* ── 右側 log ── */
#log-panel {
  background: var(--surface); border-left: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
#log-header {
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
  font-family: 'Space Mono', monospace; font-size: .7rem; color: var(--muted);
  letter-spacing: .1em; flex-shrink: 0;
}
#log-clear { margin-left: auto; font-size: .65rem; cursor: pointer; color: var(--muted); }
#log-clear:hover { color: var(--text); }
#log-body { flex: 1; overflow-y: auto; padding: 8px; font-family: 'Space Mono', monospace; font-size: .65rem; }
.log-line {
  padding: 3px 8px; border-radius: 3px; margin-bottom: 2px;
  line-height: 1.5; word-break: break-all;
}
.log-INFO  { color: var(--muted); }
.log-OK    { color: var(--success); }
.log-WARN  { color: var(--warning); }
.log-ERROR { color: var(--danger); background: rgba(255,61,87,.05); }
.log-AI    { color: var(--accent); }
.log-ts    { opacity: .5; margin-right: 6px; }

/* ── Confirm modal ── */
#confirm-modal {
  position: fixed; inset: 0; background: rgba(0,0,0,.8);
  z-index: 200; display: none; align-items: center; justify-content: center;
}
#confirm-modal.open { display: flex; }
#confirm-box {
  background: var(--panel); border: 1px solid var(--border2);
  border-radius: 12px; padding: 28px; max-width: 540px; width: 90%;
  box-shadow: 0 24px 60px rgba(0,0,0,.6);
}
#confirm-title {
  font-family: 'Space Mono', monospace; font-size: .85rem;
  color: var(--accent); margin-bottom: 12px;
}
#confirm-body { font-size: .85rem; line-height: 1.7; color: var(--text); margin-bottom: 20px; }
#confirm-actions { display: flex; gap: 8px; justify-content: flex-end; }

/* ── New project modal ── */
#newproj-modal {
  position: fixed; inset: 0; background: rgba(0,0,0,.8);
  z-index: 200; display: none; align-items: center; justify-content: center;
}
#newproj-modal.open { display: flex; }
#newproj-box {
  background: var(--panel); border: 1px solid var(--border2);
  border-radius: 12px; padding: 28px; width: 480px;
}
#newproj-box h2 { font-family:'Space Mono',monospace; font-size:.85rem; color:var(--accent); margin-bottom:16px; }
#newproj-name {
  width:100%; background:var(--surface); border:1px solid var(--border2);
  border-radius:6px; color:var(--text); padding:10px 14px;
  font-family:'Noto Sans TC',sans-serif; font-size:.88rem; margin-bottom:10px;
}
#newproj-name:focus { outline:none; border-color:var(--accent); }
#newproj-actions { display:flex; gap:8px; justify-content:flex-end; margin-top:16px; }

/* 摺疊區塊 */
.collapsible-block { margin: 6px 0; border-radius: 6px; overflow: hidden; border: 1px solid var(--border); }
.collapsible-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px; cursor: pointer; user-select: none;
  background: #0d1117; font-family: 'Space Mono',monospace; font-size: .65rem;
  color: var(--muted); transition: background .15s;
}
.collapsible-header:hover { background: #161b22; }
.collapsible-header .ch-label { display: flex; align-items: center; gap: 6px; }
.collapsible-header .ch-arrow { transition: transform .2s; font-size: 10px; }
.collapsible-header.open .ch-arrow { transform: rotate(90deg); }
.collapsible-content {
  display: none; padding: 10px 12px;
  background: #080a0c; font-size: .72rem; line-height: 1.65;
  font-family: 'Space Mono',monospace; white-space: pre-wrap;
  overflow-x: auto; max-height: 320px; overflow-y: auto;
}
.collapsible-content.open { display: block; }
.collapsible-content.code-content { color: var(--accent); }
.collapsible-content.error-content { color: var(--danger); }
.collapsible-content.plan-content  { color: #8b949e; }
.collapsible-content.review-content { color: var(--text); }

/* 施工計畫 */
#build-plan {
  background: #0d1117; border: 1px solid #1e1e2e;
  border-radius: 8px; padding: 12px 16px; margin: 10px 0;
  display: none;
}
#build-plan .bp-title {
  font-size: 11px; color: #555; letter-spacing: .08em;
  text-transform: uppercase; margin-bottom: 10px;
}
.bp-step {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 0; border-bottom: 1px solid #1a1a1a;
  font-size: 12.5px; color: #666; transition: color .2s;
}
.bp-step:last-child { border-bottom: none; }
.bp-step.bp-done  { color: #3fb950; }
.bp-step.bp-current { color: #e3b341; font-weight: 600; }
.bp-step.bp-failed  { color: #f85149; }
.bp-step .bp-icon { font-size: 13px; width: 18px; flex-shrink: 0; }
.bp-step .bp-num  { color: #444; font-size: 11px; width: 24px; flex-shrink: 0; }

/* stream output */
#stream-output {
  background: #080a0c; border: 1px solid var(--border);
  border-radius: 6px; padding: 14px; margin: 12px 0;
  font-family: 'Space Mono', monospace; font-size: .72rem;
  line-height: 1.65; color: var(--accent); overflow-x: auto;
  max-height: 260px; overflow-y: auto; white-space: pre-wrap;
  display: none;
}

/* 即時狀態列 */
#live-status-bar {
  display: none;
  position: fixed; top: 0; left: 0; right: 0; z-index: 9000;
  background: #0d1117; border-bottom: 1px solid #238636;
  padding: 6px 16px; font-size: 12px; font-family: monospace;
  color: #3fb950; gap: 10px; align-items: center;
}
#live-status-bar .live-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #3fb950; animation: blink 1s infinite;
  flex-shrink: 0;
}
#live-status-bar .live-task { color: #8b949e; margin-right: 8px; }
#live-status-bar .live-code {
  flex: 1; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; color: #3fb950;
}
#live-status-bar .live-counter { color: #8b949e; flex-shrink: 0; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
@keyframes spin   { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
</style>
</head>
<body>

<!-- 即時狀態列 -->
<div id="live-status-bar">
  <div class="live-dot"></div>
  <span class="live-task" id="live-task-name">生成中...</span>
  <span class="live-code" id="live-code-preview"></span>
  <span class="live-counter" id="live-char-count">0 字元</span>
</div>

<!-- 頂部 -->
<div id="topbar">
  <div class="logo">⚙ 工<span>坊</span></div>
  <div id="model-badge">MODEL: --</div>
  <div class="spacer"></div>
  <button id="new-project-btn" onclick="openNewProject()">+ 新專案</button>
</div>

<!-- 主佈局 -->
<div id="layout">

  <!-- 左：專案列表 -->
  <div id="sidebar">
    <div id="sidebar-header">PROJECTS</div>
    <div id="projects-list"></div>
  </div>

  <!-- 中：工作區 -->
  <div id="workspace">
    <div id="workspace-header">
      <div id="workspace-title" style="color:var(--muted)">選擇或建立一個專案</div>
      <div id="workspace-status" style="display:none"></div>
      <div id="workspace-actions"></div>
    </div>

    <div id="stream-output" style="display:none"></div>

    <div id="tasks-area">
      <div id="empty-state">
        <div class="big">⚙</div>
        <div class="hint">建立新專案，描述你要做什麼<br>立AI 會幫你拆解任務並逐一執行</div>
      </div>
      <div id="tasks-label" style="display:none">TASKS</div>
      <div id="tasks-container"></div>
    </div>
  </div>

  <!-- 右：Log -->
  <div id="log-panel">
    <div id="log-header">
      <span style="color:var(--accent)">●</span> CONSOLE
      <span id="log-clear" onclick="clearLog()">CLR</span>
    </div>
    <div id="log-body"></div>
  </div>

</div>

<!-- New project modal -->
<div id="newproj-modal">
  <div id="newproj-box">
    <h2>// 新專案</h2>
    <input id="newproj-name" placeholder="專案名稱" maxlength="60">
    <div id="newproj-actions">
      <button class="btn btn-ghost" onclick="closeNewProject()">取消</button>
      <button class="btn btn-primary" onclick="createProject()">建立</button>
    </div>
  </div>
</div>

<!-- Confirm modal -->
<div id="confirm-modal">
  <div id="confirm-box">
    <div id="confirm-title"></div>
    <div id="confirm-body"></div>
    <div id="confirm-actions"></div>
  </div>
</div>

<script>
const socket = io({
  transports: ['websocket'],
  reconnectionDelay: 3000,
  reconnectionDelayMax: 10000,
  reconnectionAttempts: 10,
});
let _currentProject = null;
let _projects = [];

// ── Socket ────────────────────────────────────────────────────────────────────
socket.on('connect', () => {
  appendLog('SYSTEM', '已連線', 'OK');
  loadProjects();
  loadModel();
  if (_currentProject) socket.emit('join_project', { project_id: _currentProject.id });
});
socket.on('log', d => {
  if (!_currentProject || d.project_id === _currentProject.id) {
    appendLog(d.level, d.message, d.level);
  }
});
socket.on('project_updated', d => {
  if (d.status === 'running') return;
  // 只刷新受影響的專案，不重新載入全部清單
  if (_currentProject && d.id === _currentProject.id) {
    loadProject(_currentProject.id);
  }
  // 更新左側清單的狀態點（不重新渲染整個清單）
  _updateProjectBadge(d.id, d.status);
});

function _updateProjectBadge(id, status) {
  const el = document.querySelector(`[data-project-id="${id}"] .project-status`);
  if (el && status) el.className = `project-status ${status}`;
}
// 全域累積字串（跨任務）
let _liveBuffer = '';
let _liveTaskId = null;

socket.on('model_switching', d => {
  if (!_currentProject || d.project_id !== _currentProject.id) return;
  const bar = document.getElementById('live-status-bar');
  const icon = d.status === 'stopping' ? '🔄' : d.status === 'loading' ? '⏳' : '✅';
  const msg  = d.status === 'stopping' ? '關閉舊模型...'
             : d.status === 'loading'  ? `載入 ${d.model}...`
             : `${d.model} 就緒`;
  bar.style.display = 'flex';
  document.getElementById('live-task-name').textContent  = `模型切換`;
  document.getElementById('live-code-preview').textContent = `${icon} ${msg}`;
  document.getElementById('live-char-count').textContent = '';
  if (d.status === 'ready') {
    setTimeout(() => {
      if (bar.style.display !== 'none')
        document.getElementById('live-code-preview').textContent = `✅ ${d.model} 生成中...`;
    }, 500);
  }
});

socket.on('stream_token', d => {
  // 頂部狀態列
  const bar = document.getElementById('live-status-bar');
  if (d.task_id !== _liveTaskId) {
    _liveBuffer = '';
    _liveTaskId = d.task_id;
  }
  _liveBuffer += d.token;
  bar.style.display = 'flex';
  document.getElementById('live-char-count').textContent = _liveBuffer.length + ' 字元';
  if (_currentProject) {
    const taskEl = document.getElementById('task-' + d.task_id);
    const titleEl = taskEl ? taskEl.querySelector('.task-title') : null;
    document.getElementById('live-task-name').textContent =
      titleEl ? titleEl.textContent : '生成中...';
  }
  const lines = _liveBuffer.split('\n').filter(l => l.trim());
  document.getElementById('live-code-preview').textContent =
    lines.length ? lines[lines.length - 1].trim() : '';

  // 寫進任務卡片的 stream box
  if (!_currentProject || d.project_id !== _currentProject.id) return;

  const taskCard = document.getElementById('task-' + d.task_id);
  if (!taskCard) {
    // 任務卡片還不存在，先刷新再試
    if (_currentProject) {
      loadProject(_currentProject.id).then(() => {
        const tc = document.getElementById('task-' + d.task_id);
        if (tc) {
          const tb = document.getElementById('tbody-' + d.task_id);
          if (tb && !tb.classList.contains('open')) tb.classList.add('open');
        }
      });
    }
    return;
  }

  // 自動展開任務卡片
  const tbody = document.getElementById('tbody-' + d.task_id);
  if (tbody && !tbody.classList.contains('open')) {
    tbody.classList.add('open');
  }

  // 找或建立 stream box
  let streamBox = taskCard.querySelector('.task-stream-box');
  if (!streamBox) {
    streamBox = document.createElement('div');
    streamBox.className = 'task-stream-box';
    streamBox.style.cssText = `
      background:#080a0c;border:1px solid #21262d;border-radius:6px;
      padding:10px 12px;margin:8px 0;font-family:'Space Mono',monospace;
      font-size:.68rem;line-height:1.6;color:#58a6ff;
      max-height:200px;overflow-y:auto;white-space:pre-wrap;`;
    tbody.insertBefore(streamBox, tbody.firstChild);
  }
  if (d.task_id !== streamBox.dataset.taskId) {
    streamBox.textContent = '';
    streamBox.dataset.taskId = d.task_id;
  }
  streamBox.textContent += d.token;
  streamBox.scrollTop = streamBox.scrollHeight;

  // stream-output 不同步程式碼（避免重複顯示）
});

socket.on('task_updated', d => {
  if (d.status && (d.status === 'done' || d.status === 'failed' || d.status === 'paused')) {
    document.getElementById('live-status-bar').style.display = 'none';
    _liveBuffer = '';
    // 清除任務卡片的 stream box
    const taskCard = document.getElementById('task-' + d.task_id);
    if (taskCard) {
      const sb = taskCard.querySelector('.task-stream-box');
      if (sb) sb.remove();
    }
  }
  if (!_currentProject || d.project_id !== _currentProject.id) return;
  if (d.status === 'running') {
    // running 時也刷新，讓任務卡片出現，然後自動展開
    loadProject(_currentProject.id).then(() => {
      const tbody = document.getElementById('tbody-' + d.task_id);
      if (tbody && !tbody.classList.contains('open')) {
        tbody.classList.add('open');
      }
    });
  } else {
    loadProject(_currentProject.id);
  }
});
// 施工計畫
socket.on('analyzed', d => {
  const status = document.getElementById('req-status');
  if (status) {
    status.innerHTML = '<span style="color:#e8c547">📋 需求分析：</span>' + esc(d.text);
  }
});

socket.on('build_plan', d => {
  if (!_currentProject || d.project_id !== _currentProject.id) return;
  const panel = document.getElementById('build-plan');
  const steps = document.getElementById('bp-steps');
  panel.style.display = 'block';
  const icons = { done:'✅', running:'⚡', pending:'○', failed:'❌', paused:'⏸' };
  steps.innerHTML = d.tasks.map(t => {
    const cls = t.id === d.current_id ? 'bp-current' :
                t.status === 'done'    ? 'bp-done'    :
                t.status === 'failed'  ? 'bp-failed'  : '';
    const icon = t.id === d.current_id ? '▶' : (icons[t.status] || '○');
    return `<div class="bp-step ${cls}" id="bp-${t.id}">
      <span class="bp-icon">${icon}</span>
      <span class="bp-num">#${String(t.seq).padStart(2,'0')}</span>
      <span>${t.title}</span>
    </div>`;
  }).join('');
});

socket.on('task_plan_token', d => {
  if (!_currentProject || d.project_id !== _currentProject.id) return;

  let planBox = document.getElementById('task-plan-box');
  if (planBox && planBox._taskId && planBox._taskId !== d.task_id) {
    planBox._text = '';
    planBox._taskId = d.task_id;
    while (planBox.firstChild) planBox.removeChild(planBox.firstChild);
  }
  if (planBox && planBox._taskId && planBox._taskId !== d.task_id) {
    planBox._text = '';
    planBox._taskId = d.task_id;
    while (planBox.firstChild) planBox.removeChild(planBox.firstChild);
  }
  if (!planBox) {
    // 建立摺疊容器
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'margin-bottom:10px;border:1px solid #1e3a1e;border-radius:6px;overflow:hidden;';

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:7px 12px;background:#0d1117;cursor:pointer;user-select:none;';
    header.innerHTML = '<span style="font-size:11px;color:#3fb950;letter-spacing:.06em;">📋 施工計畫</span><span id="plan-toggle-icon" style="font-size:10px;color:#555;transition:transform .2s;">▼</span>';

    planBox = document.createElement('div');
    planBox.id = 'task-plan-box';
    planBox.style.cssText = [
      'background:#0a0e14',
      'padding:10px 14px',
      'font-size:12px',
      'color:#3fb950',
      'white-space:pre-wrap',
      'line-height:1.6',
      'max-height:300px',
      'overflow-y:auto',
    ].join(';');

    // 點 header 收納/展開
    let _planOpen = true;
    header.onclick = () => {
      _planOpen = !_planOpen;
      planBox.style.display = _planOpen ? 'block' : 'none';
      document.getElementById('plan-toggle-icon').style.transform = _planOpen ? 'rotate(0deg)' : 'rotate(-90deg)';
    };

    wrapper.appendChild(header);
    wrapper.appendChild(planBox);
    const so = document.getElementById('stream-output');
    so.parentNode.insertBefore(wrapper, so);
  }

  // 累積 token 顯示
  if (!planBox._taskId) planBox._taskId = d.task_id;
  if (!planBox._taskId) planBox._taskId = d.task_id;
  if (!planBox._text) planBox._text = '';
  planBox._text += d.token;
  // 更新顯示（label 之後的文字）
  const label = planBox.querySelector('div');
  if (label) {
    label.nextSibling
      ? label.nextSibling.textContent = planBox._text
      : planBox.appendChild(document.createTextNode(planBox._text));
  }
  planBox.scrollTop = planBox.scrollHeight;
});

socket.on('task_step', d => {
  if (!_currentProject || d.project_id !== _currentProject.id) return;

  // 在 stream-output 上方顯示步驟進度
  let stepBox = document.getElementById('task-step-box');
  if (!stepBox) {
    stepBox = document.createElement('div');
    stepBox.id = 'task-step-box';
    stepBox.style.cssText = 'margin-bottom:8px;font-size:12px;';
    const so = document.getElementById('stream-output');
    so.parentNode.insertBefore(stepBox, so);
  }

  // 找或建立這個步驟的元素
  const stepId = 'step-' + d.task_id + '-' + d.step.replace(/\s/g,'_');
  let el = document.getElementById(stepId);
  if (!el) {
    el = document.createElement('div');
    el.id = stepId;
    el.style.cssText = 'padding:3px 0;display:flex;align-items:center;gap:8px;border-bottom:1px solid #1a1a1a;';
    stepBox.appendChild(el);
  }

  const icons = { active:'⚡', done:'✅', error:'❌' };
  const colors = { active:'#e3b341', done:'#3fb950', error:'#f85149' };
  el.innerHTML = `<span style="color:${colors[d.status]||'#888'}">${icons[d.status]||'○'}</span>
    <span style="color:${colors[d.status]||'#888'}">${d.step}</span>
    ${d.detail ? `<span style="color:#555;font-size:11px;margin-left:auto">${d.detail}</span>` : ''}`;
});

socket.on('build_plan_step', d => {
  if (!_currentProject || d.project_id !== _currentProject.id) return;
  // 更新所有步驟的樣式
  document.querySelectorAll('.bp-step').forEach(el => {
    el.classList.remove('bp-current');
    const icon = el.querySelector('.bp-icon');
    if (icon && icon.textContent === '▶') icon.textContent = '○';
  });
  const cur = document.getElementById('bp-' + d.current_id);
  if (cur) {
    cur.classList.add('bp-current');
    const icon = cur.querySelector('.bp-icon');
    if (icon) icon.textContent = '▶';
    cur.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
});

socket.on('confirm_request', d => {
  if (!_currentProject || d.project_id !== _currentProject.id) return;
  showConfirm(d);
});
socket.on('human_assist_request', d => {
  if (!_currentProject || d.project_id !== _currentProject.id) return;
  showHumanAssist(d);
});

function showHumanAssist(d) {
  document.getElementById('human-assist-overlay')?.remove();
  const ov = document.createElement('div');
  ov.id = 'human-assist-overlay';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9999;display:flex;align-items:center;justify-content:center;';
  ov.innerHTML = `
    <div style="background:#161b22;border:2px solid #e24b4a;border-radius:12px;padding:28px;max-width:620px;width:92%;box-shadow:0 20px 60px rgba(0,0,0,.6);">
      <div style="color:#e24b4a;font-size:15px;font-weight:700;margin-bottom:10px;">🆘 需要人工協助</div>
      <div style="color:#c9d1d9;font-size:13px;margin-bottom:8px;">任務 #${d.task_seq}「${d.task_title}」自動修復 3 次失敗</div>
      <div style="background:#0d1117;border-radius:8px;padding:12px;margin-bottom:14px;font-family:monospace;font-size:11.5px;color:#fca5a5;max-height:140px;overflow-y:auto;white-space:pre-wrap;">${(d.error||'').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
      <div style="color:#8b949e;font-size:12px;margin-bottom:8px;">📋 請把上面的錯誤貼給 Claude，然後把解答貼到下方：</div>
      <textarea id="human-solution-input" style="width:100%;height:120px;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#c9d1d9;padding:10px;font-size:12px;resize:vertical;" placeholder="貼上 Claude 的解答..."></textarea>
      <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end;">
        <button onclick="submitHumanAssist('${d.human_id}')" style="background:#2563eb;color:#fff;border:none;border-radius:8px;padding:8px 20px;cursor:pointer;font-size:13px;">✅ 送出解答</button>
        <button onclick="document.getElementById('human-assist-overlay').remove()" style="background:#21262d;color:#8b949e;border:1px solid #30363d;border-radius:8px;padding:8px 20px;cursor:pointer;font-size:13px;">⏭ 跳過</button>
      </div>
    </div>`;
  document.body.appendChild(ov);
  setTimeout(() => document.getElementById('human-solution-input')?.focus(), 100);
}

async function submitHumanAssist(humanId) {
  const solution = document.getElementById('human-solution-input')?.value?.trim();
  if (!solution) { alert('請貼上 Claude 的解答'); return; }
  await fetch(`/api/human_assist/${humanId}`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({solution})
  });
  document.getElementById('human-assist-overlay')?.remove();
  appendLog('OK', '✅ 解答已送出，繼續修復...');
}
socket.on('review_result', d => {
  if (!_currentProject || d.project_id !== _currentProject.id) return;
  showReviewBanner(d);
});

// ── 模型 ──────────────────────────────────────────────────────────────────────
async function loadModel() {
  try {
    const r = await fetch('/api/models');
    const d = await r.json();
    const m = (d.planner || '--').split(':')[0].toUpperCase();
    const rv = (d.reviewer || '--').split(':')[0].toUpperCase();
    const mode = d.mode === 'remote' ? '🌐' : '🖥';
    const lb = d.lobster ? '🦞' : '';
    document.getElementById('model-badge').textContent =
      d.lobster ? `${lb} LOBSTER  ${mode}REV:${rv}` : `GEN:${m}  ${mode}REV:${rv}`;
  } catch {}
}

// ── 專案列表 ──────────────────────────────────────────────────────────────────
async function loadProjects() {
  const r = await fetch('/api/projects');
  _projects = await r.json();
  const el = document.getElementById('projects-list');
  if (!_projects.length) {
    el.innerHTML = '<div style="padding:20px 12px;font-size:.75rem;color:var(--muted);text-align:center">還沒有專案<br>點右上角「+ 新專案」</div>';
    return;
  }
  el.innerHTML = _projects.map(p => `
    <div class="proj-item ${_currentProject?.id === p.id ? 'active' : ''}"
         onclick="loadProject('${p.id}')">
      <div class="proj-name">${esc(p.name)}</div>
      <div class="proj-meta">
        <span class="status-dot status-${p.status}"></span>
        <span>${p.status}</span>
        <span style="margin-left:auto">${p.task_count||0} 任務</span>
      </div>
    </div>
  `).join('');
}

async function loadProject(id) {
  const r = await fetch(`/api/projects/${id}`);
  _currentProject = await r.json();
  socket.emit('join_project', { project_id: id });
  renderWorkspace();
  // 不在這裡呼叫 loadProjects，避免每次 task_updated 都重新載入清單
}

function renderWorkspace() {
  const p = _currentProject;
  if (!p) return;
  // 渲染完後把焦點移走，避免按鈕被意外觸發
  document.activeElement?.blur();

  // Header
  document.getElementById('workspace-title').textContent = p.name;
  document.getElementById('workspace-title').style.color = 'var(--text)';

  const statusEl = document.getElementById('workspace-status');
  statusEl.style.display = '';
  const colorMap = { planning:'var(--planning)', running:'var(--running)',
                     done:'var(--done)', failed:'var(--danger)', paused:'var(--warning)' };
  statusEl.style.background = `rgba(${hexToRgb(colorMap[p.status] || '#556070')},.15)`;
  statusEl.style.color = colorMap[p.status] || 'var(--muted)';
  statusEl.style.border = `1px solid rgba(${hexToRgb(colorMap[p.status] || '#556070')},.3)`;
  statusEl.textContent = p.status.toUpperCase();

  // Actions
  const acts = document.getElementById('workspace-actions');
  acts.innerHTML = '';
  if (p.status === 'planning') {
    const hasTasks = (p.tasks || []).length > 0;
    acts.innerHTML = hasTasks
      ? `<span style="font-family:'Space Mono',monospace;font-size:.75rem;color:var(--planning);animation:blink 1.2s infinite;">⏳ 規劃完成，自動執行中...</span>
         <button class="btn btn-danger" onclick="deleteProject('${p.id}')">🗑 刪除</button>`
      : `<span style="font-family:'Space Mono',monospace;font-size:.75rem;color:var(--planning);animation:blink 1.2s infinite;">⏳ AI 規劃中，請稍候...</span>
         <button class="btn btn-danger" onclick="deleteProject('${p.id}')">🗑 刪除</button>`;
  } else if (p.status === 'running') {
    acts.innerHTML = `
      <button class="btn btn-warn" onclick="pauseProject('${p.id}')">⏸ 暫停</button>
      <button class="btn btn-danger" onclick="deleteProject('${p.id}')">🗑 刪除</button>`;
  } else if (p.status === 'paused') {
    acts.innerHTML = `
      <button class="btn btn-success" onclick="resumeProject()">▶ 繼續</button>
      <button class="btn btn-danger"  onclick="deleteProject('${p.id}')">🗑 刪除</button>`;
  } else if (p.status === 'done' || p.status === 'failed') {
    const pending = (p.tasks || []).filter(t => ['pending','failed','paused'].includes(t.status)).length;
    const assembleBtn = p.assembled
      ? `<button class="btn btn-ghost" style="color:var(--success);border-color:rgba(0,230,118,.3);" onclick="assembleProject('${p.id}')">🔄 重新組裝</button>`
      : `<button class="btn btn-success" onclick="assembleProject('${p.id}')">🔩 組裝器官</button>`;
    acts.innerHTML = `
      ${pending ? `<button class="btn btn-primary" tabindex="-1" onclick="resumeProject()">▶ 繼續未完成(${pending})</button>` : ''}
      ${assembleBtn}
      ${p.assembled ? `<button class="btn btn-ghost" style="color:#f59e0b;border-color:rgba(245,158,11,.3);" onclick="repairAssembled('${p.assembled_filename || ''}')">🔧 修正器官</button>` : ''}
      <button class="btn btn-ghost"    onclick="rerunProject('${p.id}')">🔄 全部重跑</button>
      <button class="btn btn-ghost"    style="opacity:.7;font-size:11px;" onclick="cleanupParts('${p.id}')">🗑 清除錯誤子任務</button>
      <button class="btn btn-ghost"    onclick="exportProject('${p.id}')">⬇ 匯出</button>
      <button class="btn btn-danger"   onclick="deleteProject('${p.id}')">🗑</button>`;
  }

  // requirement-area 已移除

  // Tasks
  const tasks = p.tasks || [];
  const emptyEl = document.getElementById('empty-state');
  const labelEl = document.getElementById('tasks-label');
  const container = document.getElementById('tasks-container');

  if (!tasks.length) {
    emptyEl.style.display = p.status === 'planning' ? '' : 'flex';
    emptyEl.innerHTML = p.status === 'planning'
      ? '<div class="big" style="animation:spin 2s linear infinite;display:inline-block;">⚙</div><div class="hint" style="color:var(--planning);">AI 規劃中，請稍候...</div>'
      : '<div class="big">⚙</div><div class="hint">等待立AI 下單...</div>';
    labelEl.style.display = 'none';
    container.innerHTML = '';
  } else {
    emptyEl.style.display = 'none';
    labelEl.style.display = '';
    container.innerHTML = tasks.map(t => renderTask(t, p)).join('');
  }

  // stream output
  document.getElementById('stream-output').style.display = 'none';
  document.getElementById('stream-output').textContent = '';
}

function renderTask(t, p) {
  const labelClass = { pending:'label-pending', running:'label-running',
    done:'label-done', failed:'label-failed', paused:'label-paused', skipped:'label-skipped' };
  const cardClass  = { running:'active', done:'done', failed:'failed', paused:'paused' };

  let body = `<div class="task-desc">${esc(t.description || '')}</div>`;

  if (t.code) {
    const lineCount = (t.code.match(/\n/g) || []).length + 1;
    body += makeCollapsible(
      `📄 程式碼輸出 <span style="color:#444;margin-left:6px;">${lineCount} 行</span>`,
      esc(t.code), 'code-content', false
    );
  }
  if (t.error) {
    body += makeCollapsible(
      `❌ 錯誤訊息 <span style="color:#444;margin-left:6px;">修復 ${t.repair_count}/3</span>`,
      esc(t.error), 'error-content', true
    );
  }
  if (t.review_report) {
    const rvIcon = t.review_passed ? '✅' : '⚠';
    const rvLabel = t.review_passed ? '審查通過' : '審查意見';
    const rvContent = esc(t.review_report)
      + (t.review_issues     ? '\n\n問題：' + esc(t.review_issues) : '')
      + (t.review_suggestions ? '\n建議：'  + esc(t.review_suggestions) : '');
    body += makeCollapsible(
      `${rvIcon} ${rvLabel}`,
      rvContent, 'review-content', !t.review_passed
    );
  }

  // 動作按鈕
  let taskActions = '';
  const isPartTask = t.title && t.title.match(/\(Part \d+\/\d+\)/);
  const deleteBtn = `<button class="btn btn-danger" style="opacity:.6;font-size:11px;" onclick="deleteTask('${t.id}')">🗑 刪除</button>`;

  if (t.status === 'paused') {
    taskActions = `
      <button class="btn btn-success" onclick="approveTask('${t.id}')">✓ 確認，繼續</button>
      <button class="btn btn-warn"    onclick="editTask('${t.id}', \`${esc(t.description)}\`)">✎ 修改再試</button>
      <button class="btn btn-danger"  onclick="skipTask('${t.id}')">⊘ 跳過</button>
      ${deleteBtn}`;
  } else if (t.status === 'pending') {
    taskActions = `
      <button class="btn btn-ghost" onclick="editTask('${t.id}', \`${esc(t.description)}\`)">✎ 編輯描述</button>
      <button class="btn btn-danger" style="opacity:.7;" onclick="skipTask('${t.id}')">⊘ 跳過</button>
      ${deleteBtn}
      ${p.status === 'paused' ? `<button class="btn btn-ghost" onclick="runSingleTask('${t.id}')">▶ 單獨執行</button>` : ''}`;
  } else if (t.status === 'done') {
    taskActions = `<button class="btn btn-ghost" style="opacity:.6;font-size:11px;" onclick="retryTask('${t.id}')">🔄 重新執行</button>${deleteBtn}`;
  } else if (t.status === 'failed') {
    taskActions = `
      <button class="btn btn-ghost" onclick="retryTask('${t.id}')">🔄 重試</button>
      <button class="btn btn-warn"  onclick="editTask('${t.id}', \`${esc(t.description)}\`)">✎ 修改描述</button>
      ${deleteBtn}`;
  } else if (t.status === 'skipped') {
    taskActions = `
      <button class="btn btn-ghost" onclick="retryTask('${t.id}')">🔄 重試</button>
      ${deleteBtn}`;
  }

  if (taskActions) body += `<div class="task-actions">${taskActions}</div>`;

  return `
    <div class="task-card ${cardClass[t.status] || ''}" id="task-${t.id}">
      <div class="task-header" onclick="toggleTask('${t.id}')">
        <div class="task-seq">#${String(t.seq).padStart(2,'0')}</div>
        <div class="task-title">${esc(t.title)}</div>
        <div class="task-status-label ${labelClass[t.status] || 'label-pending'}">${t.status.toUpperCase()}</div>
      </div>
      <div class="task-body" id="tbody-${t.id}">${body}</div>
    </div>`;
}

function toggleTask(id) {
  const el = document.getElementById(`tbody-${id}`);
  el.classList.toggle('open');
}

function toggleCollapsible(headerId) {
  const header  = document.getElementById(headerId);
  const content = document.getElementById(headerId + '-content');
  if (!header || !content) return;
  header.classList.toggle('open');
  content.classList.toggle('open');
}

function makeCollapsible(label, innerHtml, colorClass, defaultOpen) {
  const id = 'col-' + Math.random().toString(36).slice(2, 8);
  const openCls = defaultOpen ? ' open' : '';
  return `
    <div class="collapsible-block">
      <div class="collapsible-header${openCls}" id="${id}" onclick="toggleCollapsible('${id}')">
        <span class="ch-label">${label}</span>
        <span class="ch-arrow">▶</span>
      </div>
      <div class="collapsible-content ${colorClass}${openCls}" id="${id}-content">${innerHtml}</div>
    </div>`;
}

// ── 規劃 ──────────────────────────────────────────────────────────────────────
async function expandRequirement() {
  const req_text = document.getElementById('req-input').value.trim();
  if (!req_text) { alert('請先輸入簡單的需求描述'); return; }

  const btn    = document.getElementById('expand-btn');
  const status = document.getElementById('req-status');
  btn.disabled = true;
  btn.textContent = '⏳ 擴展中...';
  status.textContent = 'AI 分析需求中...';

  try {
    const r = await fetch('/api/expand_requirement', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({requirement: req_text})
    });
    const d = await r.json();
    if (d.expanded) {
      document.getElementById('req-input').value = d.expanded;
      status.textContent = '✅ 需求已擴展，確認後點「開始規劃」';
    } else {
      status.textContent = '❌ 擴展失敗：' + (d.error || '未知錯誤');
    }
  } catch(e) {
    status.textContent = '❌ 錯誤：' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ 擴展需求';
  }
}

async function startPlanning() {
  const req_text = document.getElementById('req-input').value.trim();
  if (!req_text) return;
  if (!_currentProject) return;

  const btn = document.getElementById('plan-btn');
  btn.disabled = true;
  document.getElementById('req-status').textContent = '規劃中...';
  document.getElementById('stream-output').textContent = '';
  document.getElementById('stream-output').style.display = 'block';

  const r = await fetch(`/api/projects/${_currentProject.id}/plan`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ requirement: req_text })
  });

  // SSE stream
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      let ev; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
      if (ev.type === 'token') {
        document.getElementById('stream-output').textContent += ev.text;
        document.getElementById('stream-output').scrollTop = 999999;
      } else if (ev.type === 'review') {
        const rv = ev.review;
        const icon = rv.passed ? '✅' : '⚠';
        const msg = `${icon} 審查：${rv.report || ''}`;
        appendLog('AI', msg, rv.passed ? 'OK' : 'WARN');
        // 顯示審查 banner
        const so = document.getElementById('stream-output');
        so.style.display = 'block';
        so.textContent += '\n\n' + msg;
        if (rv.issues?.length)      so.textContent += '\n問題：' + rv.issues.join('、');
        if (rv.suggestions?.length) so.textContent += '\n建議：' + rv.suggestions.join('、');
      } else if (ev.type === 'done') {
        document.getElementById('req-status').textContent = `✅ 規劃完成，${ev.task_count} 個任務`;
        document.getElementById('stream-output').style.display = 'none';
        await loadProject(_currentProject.id);
        // 問是否開始執行
        showConfirmDialog(
          '// 確認任務清單',
          `立AI 規劃了 ${ev.task_count} 個任務，確認後開始逐一執行。`,
          [{ label: '▶ 開始執行', cls: 'btn-primary', action: 'start' },
           { label: '先看看', cls: 'btn-ghost', action: 'cancel' }],
          async (action) => { if (action === 'start') await startExecution(); }
        );
      } else if (ev.type === 'error') {
        document.getElementById('req-status').textContent = '❌ ' + ev.error;
      }
    }
  }
  btn.disabled = false;
}

async function startExecution() {
  if (!_currentProject) return;
  await fetch(`/api/projects/${_currentProject.id}/run`, { method: 'POST' });
  await loadProject(_currentProject.id);
}

async function resumeProject() {
  if (!_currentProject) return;
  await fetch(`/api/projects/${_currentProject.id}/resume`, { method: 'POST' });
}

async function pauseProject(id) {
  await fetch(`/api/projects/${id}/pause`, { method: 'POST' });
  await loadProject(id);
}

async function deleteTask(taskId) {
  if (!confirm('確定刪除這個任務？')) return;
  const r = await fetch(`/api/tasks/${taskId}/delete`, {method:'POST'});
  const d = await r.json();
  if (d.ok) {
    appendLog('OK', '🗑 任務已刪除');
    if (_currentProject) loadProject(_currentProject.id);
  }
}

async function cleanupParts(pid) {
  const r = await fetch(`/api/projects/${pid}/cleanup_parts`, {method:'POST'});
  const d = await r.json();
  appendLog('OK', `🗑 已清除 ${d.deleted} 個錯誤子任務`);
  loadProject(pid);
}

async function rerunProject(id) {
  showConfirmDialog('// 全部重跑', '將所有任務重設為 pending 並重新執行，確定嗎？',
    [{ label: '🔄 確定重跑', cls: 'btn-primary', action: 'ok' },
     { label: '取消', cls: 'btn-ghost', action: 'cancel' }],
    async (action) => {
      if (action !== 'ok') return;
      await fetch(`/api/projects/${id}/rerun`, { method: 'POST' });
      await loadProject(id);
    }
  );
}

async function approveTask(taskId) {
  await fetch(`/api/tasks/${taskId}/approve`, { method: 'POST' });
}

async function skipTask(taskId) {
  await fetch(`/api/tasks/${taskId}/skip`, { method: 'POST' });
}

async function editTask(taskId, currentDesc) {
  showConfirmDialog(
    '// 編輯任務描述',
    `<div style="color:var(--muted);font-size:.75rem;margin-bottom:6px;">修改後任務會重設為 pending 重新執行：</div>
     <textarea id="edit-desc" style="width:100%;background:var(--surface);border:1px solid var(--border2);border-radius:6px;color:var(--text);padding:10px;font-family:'Microsoft JhengHei UI',sans-serif;font-size:.85rem;resize:vertical;min-height:120px;">${currentDesc || ''}</textarea>`,
    [{ label: '✅ 儲存並重新執行', cls: 'btn-primary', action: 'save' },
     { label: '💾 只儲存', cls: 'btn-ghost', action: 'save_only' },
     { label: '取消', cls: 'btn-ghost', action: 'cancel' }],
    async (action) => {
      if (action === 'cancel') return;
      const newDesc = document.getElementById('edit-desc')?.value?.trim() || '';
      const r = await fetch(`/api/tasks/${taskId}/edit_desc`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ description: newDesc, rerun: action === 'save' })
      });
      const d = await r.json();
      if (d.ok) appendLog('OK', action === 'save' ? '✅ 描述已更新，重新執行中...' : '✅ 描述已儲存');
    }
  );
}

async function runSingleTask(taskId) {
  await fetch(`/api/tasks/${taskId}/run`, { method: 'POST' });
}

async function retryTask(taskId) {
  // 先把任務重設為 pending 再執行
  await fetch(`/api/tasks/${taskId}/reset`, { method: 'POST' });
  await fetch(`/api/tasks/${taskId}/run`,   { method: 'POST' });
}

// ── 專案管理 ──────────────────────────────────────────────────────────────────
function openNewProject() {
  document.getElementById('newproj-modal').classList.add('open');
  document.getElementById('newproj-name').focus();
}
function closeNewProject() {
  document.getElementById('newproj-modal').classList.remove('open');
  document.getElementById('newproj-name').value = '';
}
async function createProject() {
  const name = document.getElementById('newproj-name').value.trim();
  if (!name) return;
  const r = await fetch('/api/projects', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name })
  });
  const d = await r.json();
  closeNewProject();
  await loadProjects();
  await loadProject(d.id);
}

async function deleteProject(id) {
  showConfirmDialog('// 刪除專案', '確定刪除這個專案及所有任務？',
    [{ label: '刪除', cls: 'btn-danger', action: 'del' },
     { label: '取消', cls: 'btn-ghost', action: 'cancel' }],
    async (action) => {
      if (action !== 'del') return;
      await fetch(`/api/projects/${id}`, { method: 'DELETE' });
      _currentProject = null;
      document.getElementById('workspace-title').textContent = '選擇或建立一個專案';
      document.getElementById('workspace-title').style.color = 'var(--muted)';
      document.getElementById('workspace-status').style.display = 'none';
      document.getElementById('requirement-area').style.display = 'none';
      document.getElementById('workspace-actions').innerHTML = '';
      document.getElementById('tasks-container').innerHTML = '';
      document.getElementById('empty-state').style.display = 'flex';
      document.getElementById('tasks-label').style.display = 'none';
      await loadProjects();
    }
  );
}

async function repairAssembled(filename) {
  _notify("🔧 開始修正器官：" + (filename || "全部"));
  try {
    const r = await fetch("/api/repair_assembled", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({filename: filename || ""})
    });
    const d = await r.json();
    if (!d.ok) _notify("⚠ 修正請求失敗");
  } catch(e) {
    _notify("⚠ 修正請求失敗：" + e);
  }
}

function _notify(msg) {
  // 顯示在頁面頂部的簡易通知
  let n = document.getElementById("_repair_notify");
  if (!n) {
    n = document.createElement("div");
    n.id = "_repair_notify";
    n.style.cssText = "position:fixed;top:10px;left:50%;transform:translateX(-50%);background:#1e1e2e;color:#ddd;border:1px solid #444;border-radius:8px;padding:8px 18px;font-size:13px;z-index:9999;max-width:500px;text-align:center;";
    document.body.appendChild(n);
  }
  n.textContent = msg;
  n.style.display = "block";
  clearTimeout(n._t);
  n._t = setTimeout(() => { n.style.display = "none"; }, 4000);
}

socket.on("repair_progress", function(data) {
  if (data.status === "done") {
    _notify("🎉 器官修正完成");
    if (_currentProject) loadProject(_currentProject.id);
  } else if (data.filename) {
    const icons = {ok:"✅", fixing:"🔧", fixed:"✅", failed:"❌", not_found:"⚠"};
    const icon  = icons[data.status] || "ℹ";
    _notify(icon + " " + data.filename + "：" + data.message);
  }
});

async function assembleProject(id) {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '⏳ 組裝中...';
  const r = await fetch(`/api/projects/${id}/assemble`, { method: 'POST' });
  const d = await r.json();
  if (d.ok) {
    btn.textContent = '✅ 已組裝';
    btn.style.background = 'rgba(0,230,118,.2)';
    appendLog('OK', `🔩 組裝完成：${d.name}（${d.tasks} 個任務，${d.size} bytes）`);
    appendLog('AI', `路徑：${d.path}`);
  } else {
    btn.disabled = false;
    btn.textContent = '🔩 組裝器官';
    appendLog('ERROR', `組裝失敗：${d.error}`);
  }
}

async function exportProject(id) {
  window.open(`/api/projects/${id}/export`, '_blank');
}

// ── Confirm dialog ─────────────────────────────────────────────────────────────
function showReviewBanner(d) {
  // 在 log 顯示審查結果，並在 confirm modal 前預覽
  const rv = d.review;
  const icon = rv.passed ? '✅' : '⚠';
  appendLog('AI', `${icon} 任務#${d.task_seq}「${d.task_title}」審查完成`, rv.passed ? 'OK' : 'WARN');
  if (rv.report)       appendLog('AI', `報告：${rv.report}`, 'AI');
  if (rv.issues?.length)      appendLog('AI', `問題：${rv.issues.join('、')}`, 'WARN');
  if (rv.suggestions?.length) appendLog('AI', `建議：${rv.suggestions.join('、')}`, 'AI');
}

function showConfirmDialog(title, body, buttons, callback) {
  const modal = document.getElementById('confirm-modal');
  document.getElementById('confirm-title').textContent = title;
  document.getElementById('confirm-body').innerHTML = body;
  const acts = document.getElementById('confirm-actions');
  acts.innerHTML = '';
  for (const btn of buttons) {
    const el = document.createElement('button');
    el.className = `btn ${btn.cls}`;
    el.textContent = btn.label;
    el.onclick = async () => {
      modal.classList.remove('open');
      await callback(btn.action);
    };
    acts.appendChild(el);
  }
  modal.classList.add('open');
}

function showConfirm(d) {
  showConfirmDialog(
    d.title || '// 需要你決策',
    d.body  || '',
    d.buttons || [{ label: '確認', cls: 'btn-primary', action: 'ok' }],
    async (action) => {
      await fetch(`/api/confirm/${d.confirm_id}`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ action })
      });
    }
  );
}

// ── Log ───────────────────────────────────────────────────────────────────────
function appendLog(level, msg, cls) {
  const el = document.getElementById('log-body');
  const div = document.createElement('div');
  div.className = `log-line log-${cls || level}`;
  const ts = new Date().toTimeString().slice(0,8);
  div.innerHTML = `<span class="log-ts">${ts}</span>${esc(msg)}`;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
  // 最多保留 200 行
  while (el.children.length > 200) el.removeChild(el.firstChild);
}
function clearLog() { document.getElementById('log-body').innerHTML = ''; }

// ── 工具 ──────────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function hexToRgb(cssVar) {
  const map = {
    'var(--planning)':'124,92,191', 'var(--running)':'0,212,255',
    'var(--done)':'0,230,118',      'var(--danger)':'255,61,87',
    'var(--warning)':'255,179,0',   'var(--muted)':'85,96,112',
  };
  return map[cssVar] || '85,96,112';
}

// Enter 建立專案
document.getElementById('newproj-name').addEventListener('keydown', e => {
  if (e.key === 'Enter') createProject();
});

// socketio join room

</script>
</body>
</html>
"""

# ── Socket events ─────────────────────────────────────────────────────────────
@socketio.on("join_project")
def on_join(data):
    from flask_socketio import join_room
    room = f"project_{data.get('project_id','')}"
    join_room(room)

# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/review_callback", methods=["POST"])
def api_review_callback():
    """審查Agent 審查完後回傳結果到這裡，自動更新工坊任務。"""
    data = request.get_json(silent=True) or {}
    task_id     = data.get("task_id", "")
    review_type = data.get("review_type", "code")
    fixed_code  = data.get("fixed_code")
    plan        = data.get("plan", "")
    issues      = data.get("issues", "")
    session_id  = data.get("session_id", "")

    logger.info(f"[ReviewCallback] 收到審查結果：task={task_id} type={review_type} session={session_id}")

    # 解除等待中的 Event
    if task_id in _review_events:
        _review_results[task_id] = data
        _review_events[task_id].set()

    if not task_id:
        return jsonify({"ok": False, "error": "缺少 task_id"}), 400

    with _db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()

    if not task:
        # task_id 可能是 project_id（規劃審查）
        with _db() as c:
            proj = c.execute("SELECT * FROM projects WHERE id=?", (task_id,)).fetchone()
        if proj and review_type == "plan" and plan:
            # 把審查建議附加到專案描述
            review_note = f"\n\n【規劃審查建議】\n{plan}"
            if issues:
                review_note += f"\n\n問題清單：\n{issues}"
            with _db() as c:
                c.execute("UPDATE projects SET description=?,updated_at=? WHERE id=?",
                          (proj["description"] + review_note, _now(), task_id))
            _log(task_id, f"✅ 規劃審查完成，已更新描述", "OK")
            socketio.emit("project_updated", {"id": task_id})
        return jsonify({"ok": True})

    pid = task["project_id"]

    if review_type == "code" and fixed_code:
        # 用審查後的程式碼更新任務
        with _db() as c:
            c.execute("UPDATE tasks SET code=?,review_report=?,updated_at=? WHERE id=?",
                      (fixed_code, issues[:500] if issues else "", _now(), task_id))
        _log(pid, f"✅ 任務 #{task['seq']}「{task['title']}」審查完成，程式碼已更新", "OK", task_id)
        socketio.emit("task_updated", {"project_id": pid, "task_id": task_id})
    elif review_type == "code" and not fixed_code:
        # 審查通過，無修改
        _log(pid, f"✅ 任務 #{task['seq']}「{task['title']}」審查通過，無需修改", "OK", task_id)

    return jsonify({"ok": True})


@app.route("/health")
def health():
    return "ok", 200


@app.route("/api/module_context", methods=["GET"])
def api_module_context():
    """供審查 Agent 主動來拉的模組摘要 endpoint。"""
    import ast as _ast_mc
    _base = WORKSHOP_DIR.parent
    _mods = []
    for _mp in sorted(_base.glob("*.py"))[:30]:
        try:
            _src  = _mp.read_text(encoding="utf-8", errors="replace")
            _tree = _ast_mc.parse(_src)
            _doc  = _ast_mc.get_docstring(_tree) or ""
            _fns  = []
            for _n in _ast_mc.walk(_tree):
                if isinstance(_n, (_ast_mc.FunctionDef, _ast_mc.AsyncFunctionDef)):
                    if _n.name.startswith("_"):
                        continue
                    _fns.append({"name": _n.name, "args": ", ".join(a.arg for a in _n.args.args), "doc": ""})
            if _fns:
                _mods.append({"module": _mp.stem, "description": _doc.splitlines()[0] if _doc else "", "functions": _fns[:8]})
        except Exception:
            pass
    return jsonify({"ok": True, "modules": _mods, "count": len(_mods)})


@app.route("/api/auto_create", methods=["POST"])
def api_auto_create():
    """
    立AI 呼叫此端點，自動創建專案、規劃、執行，完成後 callback。
    body: {name, requirement, callback_url}
    """
    data        = request.get_json(silent=True) or {}
    name        = str(data.get("name", "AI自動任務")).strip()
    requirement = str(data.get("requirement", "")).strip()
    callback_url = str(data.get("callback_url", "")).strip()

    if not requirement:
        return jsonify({"error": "需求不能為空"}), 400

    final_req = requirement  # 分析在背景執行


    # 建立專案
    pid = str(__import__('uuid').uuid4())
    now = _now()
    with _db() as c:
        c.execute("INSERT INTO projects (id,name,description,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                  (pid, name, final_req, "planning", now, now))

    # 標記為自動模式
    _auto_projects.add(pid)
    if callback_url:
        _ai_callbacks[pid] = callback_url

    socketio.emit("project_updated", {"id": pid})
    _log(pid, f"🤖 立AI 自動建立專案：{name}", "AI")

    # 背景執行規劃 + 執行
    def _auto_run():
        import json as _json, re as _re
        try:
            _auto_run_inner()
        except Exception as _e:
            import traceback
            _log(pid, f"[auto_run 崩潰] {_e}\n{traceback.format_exc()}", "ERROR")
            _notify_ai(pid, "failed", f"自動執行崩潰：{_e}")

    def _auto_run_inner():
        import json as _json, re as _re
        _log(pid, "▶ _auto_run 開始", "INFO")
        # ── 需求分析（整合現有模組）────────────────────────────────────
        _base_scan = WORKSHOP_DIR.parent
        _mod_summary = []
        try:
            import ast as _ast_req2
            for _mp in sorted(_base_scan.glob("*.py"))[:20]:
                try:
                    _src = _mp.read_text(encoding="utf-8", errors="replace")
                    _tree = _ast_req2.parse(_src)
                    _doc = _ast_req2.get_docstring(_tree) or ""
                    _fns = [n.name for n in _tree.body
                            if isinstance(n, (_ast_req2.FunctionDef, _ast_req2.AsyncFunctionDef, _ast_req2.ClassDef))]
                    if _fns:
                        _mod_summary.append(f"{_mp.name}：{_doc[:60] or ', '.join(_fns[:5])}")
                except Exception:
                    pass
        except Exception:
            pass
        _mod_list = "\n".join(_mod_summary) if _mod_summary else "（無）"
        _aprmt = f"使用者需求：{requirement}\n\n現有系統模組：\n{_mod_list}\n\n請用繁體中文100字以內輸出完整需求說明，包含要用哪些現有模組。直接輸出，不要標題。"
        _analyzed_req = requirement
        try:
            _log(pid, f"⏳ 需求分析中，使用模型：{_pick(PLANNER_MODELS)}...", "INFO")
            _ar = _ollama_once(_pick(PLANNER_MODELS), "你是需求分析師，整合現有模組輸出完整需求說明。", _aprmt, temperature=0.2)
            if _ar and len(_ar) > 10:
                _analyzed_req = _ar
                _log(pid, f"📋 需求分析完成：{_ar[:100]}...", "AI")
                with _db() as c:
                    c.execute("UPDATE projects SET description=?,updated_at=? WHERE id=?", (_analyzed_req, _now(), pid))
        except Exception as _ae:
            _log(pid, f"⚠ 需求分析失敗：{_ae}", "WARN")

        # 規劃
        _log(pid, "⏳ 開始規劃任務...", "INFO")
        sys_c = get_system_context(max_chars=1500) if _HAS_SYSTEM_MAP else ""
        plan_raw = _lobster_plan(_analyzed_req, ("\n\n" + sys_c) if sys_c else "")
        _log(pid, f"⏳ 規劃原始輸出（{len(plan_raw)} 字元），解析中...", "INFO")

        # 解析任務
        try:
            cleaned = _re.sub(r"```(?:json)?\s*", "", plan_raw).strip().rstrip("`")
            start, end = cleaned.find("{"), cleaned.rfind("}") + 1
            parsed = _json.loads(cleaned[start:end])
            tasks  = parsed.get("tasks", [])
        except Exception as e:
            _log(pid, f"規劃解析失敗：{e}", "ERROR")
            _notify_ai(pid, "failed", f"規劃解析失敗：{e}")
            return

        # 正規化
        normalized = []
        for i, t in enumerate(tasks):
            import re as _re2
            seq = t.get("seq") or t.get("id") or i + 1
            if isinstance(seq, str):
                m = _re2.search(r'\d+', seq)
                seq = int(m.group()) if m else i + 1
            normalized.append({
                "seq":         seq,
                "title":       t.get("title") or t.get("name") or f"任務{seq}",
                "description": t["description"] or "",
            })

        now2 = _now()
        with _db() as c:
            for t in normalized:
                tid2 = str(__import__('uuid').uuid4())
                c.execute("""INSERT INTO tasks
                    (id,project_id,seq,title,description,status,repair_count,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (tid2, pid, t["seq"], t["title"], t["description"],
                     "pending", 0, now2, now2))
            c.execute("UPDATE projects SET status='planning',updated_at=? WHERE id=?", (now2, pid))

        socketio.emit("project_updated", {"id": pid})
        _log(pid, f"規劃完成：{len(normalized)} 個任務", "OK")

        # 如果有規劃審查，先等完成再執行
        if REVIEW_ENABLED:
            _log(pid, "🔍 送審查Agent審查規劃...", "AI")
            _plan_text = "\n".join(
                f"{t['seq']}. {t['title']}：{t['description'] or ''}"
                for t in normalized
            )
            _rv = _send_to_reviewer(
                pid=pid, task_id=pid + "_plan",
                content=_plan_text,
                review_type="plan",
                filename=f"{pid[:8]}_plan.txt",
                timeout=3600,
            )
            if _rv:
                _pn = _rv.get("plan",""); _is = _rv.get("issues","")
                if _pn or _is:
                    _note = f"\n\n【規劃審查建議】\n{_pn}"
                    if _is: _note += f"\n問題：\n{_is}"
                    with _db() as c:
                        req0 = c.execute("SELECT description FROM projects WHERE id=?", (pid,)).fetchone()
                        _orig = req0["description"] if req0 else ""
                        c.execute("UPDATE projects SET description=?,updated_at=? WHERE id=?",
                                  (_orig + _note, _now(), pid))
                    _log(pid, "✅ 規劃審查完成，已更新描述", "OK")
                else:
                    _log(pid, "✅ 規劃審查完成，無需修改", "OK")

        # 審查完成後才執行，標記規劃審查已做過讓 _run_project 跳過
        _review_results[pid + "_plan"] = _rv or {"skipped": True}
        _log(pid, "▶ 開始自動執行任務", "OK")
        _run_project(pid)

    threading.Thread(target=_auto_run, daemon=True).start()

    return jsonify({
        "ok":         True,
        "project_id": pid,
        "name":       name,
        "message":    "已開始自動製作器官，完成後會通知你",
    })


@app.route("/api/expand_requirement", methods=["POST"])
def api_expand_requirement():
    """
    把使用者的模糊需求擴展成清楚的工程需求描述。
    使用系統地圖讓 AI 知道可以對接哪些現有模組。
    """
    data = request.get_json(silent=True) or {}
    raw  = str(data.get("requirement", "")).strip()
    if not raw:
        return jsonify({"error": "需求不能為空"}), 400

    sys_ctx = get_system_context(max_chars=1500) if _HAS_SYSTEM_MAP else ""

    system = """你是資深軟體架構師，幫使用者把模糊的需求擴展成清楚的工程需求文件。

輸出格式：
【功能說明】
（2-3句說明這個功能是什麼）

【輸入】
（輸入什麼資料或觸發條件）

【輸出】
（產出什麼結果）

【可對接的現有模組】
（從系統地圖中找出可以直接使用的模組）

【建議實作方式】
（具體的技術方向，1-3點）

用繁體中文，簡潔清楚。"""

    prompt = f"使用者的需求：{raw}\n\n{sys_ctx}"

    try:
        result = _ollama_once(
            _pick(PLANNER_MODELS), system, prompt,
            temperature=0.4
        )
        return jsonify({"expanded": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/models")
def api_models():
    models = _get_models()
    return jsonify({
        "available": models,
        "planner":   "LobsterCore" if _USE_LOBSTER else _pick(PLANNER_MODELS),
        "coder":     "LobsterCore" if _USE_LOBSTER else _pick(CODER_MODELS),
        "reviewer":  _pick(REVIEWER_MODELS),
        "mode":      REVIEWER_MODE,
        "lobster":   _USE_LOBSTER,
    })

# ── 專案 CRUD ──────────────────────────────────────────────────────────────────
@app.route("/api/projects")
def api_list_projects():
    with _db() as c:
        rows = c.execute("""
            SELECT p.*, COUNT(t.id) as task_count
            FROM projects p LEFT JOIN tasks t ON t.project_id = p.id
            GROUP BY p.id ORDER BY p.created_at DESC
        """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/projects", methods=["POST"])
def api_create_project():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name","")).strip()
    if not name:
        return jsonify({"error": "名稱不能為空"}), 400
    pid = str(uuid.uuid4())
    now = _now()
    with _db() as c:
        c.execute("INSERT INTO projects (id,name,status,created_at,updated_at) VALUES (?,?,?,?,?)",
                  (pid, name, "planning", now, now))
    socketio.emit("project_updated", {"id": pid})
    return jsonify({"id": pid, "name": name})

@app.route("/api/projects/<pid>")
def api_get_project(pid):
    with _db() as c:
        p = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not p: return jsonify({"error":"找不到"}), 404
        tasks = c.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY seq", (pid,)).fetchall()
    d = dict(p)
    d["tasks"] = [dict(t) for t in tasks]
    # 檢查是否已組裝
    safe_name = p["name"].replace(" ", "_").replace("/", "_")
    assembled_path = WORKSHOP_DIR / "assembled" / f"{safe_name}.py"
    d["assembled"] = assembled_path.exists()
    d["assembled_filename"] = f"{safe_name}.py" if d["assembled"] else None
    return jsonify(d)

@app.route("/api/projects/<pid>", methods=["DELETE"])
def api_delete_project(pid):
    with _db() as c:
        c.execute("DELETE FROM tasks WHERE project_id=?", (pid,))
        c.execute("DELETE FROM logs  WHERE project_id=?", (pid,))
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
    socketio.emit("project_updated", {"id": pid})
    return jsonify({"ok": True})

# ── 規劃 (SSE) ────────────────────────────────────────────────────────────────
@app.route("/api/projects/<pid>/plan", methods=["POST"])
def api_plan(pid):
    data = request.get_json(silent=True) or {}
    requirement = str(data.get("requirement","")).strip()
    if not requirement:
        return jsonify({"error":"需求不能為空"}), 400

    # 存需求到專案
    with _db() as c:
        c.execute("UPDATE projects SET description=?,updated_at=? WHERE id=?",
                  (requirement, _now(), pid))
        # 清舊任務
        c.execute("DELETE FROM tasks WHERE project_id=?", (pid,))

    engine_name = "LobsterCore" if _USE_LOBSTER else _pick(PLANNER_MODELS)
    _log(pid, f"開始規劃，使用 {engine_name}", "AI")

    # 從知識庫查相關背景（如果 knowledge_ui 有在跑）
    kb_context = ""
    try:
        import socket as _sock
        with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', 7861)) == 0:
                r = req.post("http://localhost:7861/api/search",
                             json={"query": requirement, "limit": 5}, timeout=5)
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    if results:
                        kb_context = "\n\n【知識庫規則 - 規劃任務時必須遵守，並寫入每個任務的描述中】\n"
                        for item in results:
                            kb_context += f"- {item.get('title','')}：{item.get('content','')}\n"
                        _log(pid, f"📚 從知識庫找到 {len(results)} 筆規則，已注入規劃 prompt", "AI")
    except Exception:
        pass

    # ── 規劃前掃描現有模組 API（不靠知識庫，直接看系統有什麼）──────────────
    module_api_ctx = ""
    try:
        import ast as _ast_plan
        _base = WORKSHOP_DIR.parent
        _api_parts = []
        for _mpath in sorted(_base.glob("*.py")):
            try:
                _src = _mpath.read_text(encoding="utf-8", errors="replace")
                _tree = _ast_plan.parse(_src)
                # 取 module docstring
                _mod_doc = _ast_plan.get_docstring(_tree) or ""
                # 取所有函式和類別簽名
                _sigs = []
                for _node in _tree.body:
                    if isinstance(_node, (_ast_plan.FunctionDef, _ast_plan.AsyncFunctionDef)):
                        _args = [a.arg for a in _node.args.args if a.arg != "self"]
                        _doc  = _ast_plan.get_docstring(_node) or ""
                        _sigs.append(f"  def {_node.name}({', '.join(_args)}){': ' + _doc[:60] if _doc else ''}")
                    elif isinstance(_node, _ast_plan.ClassDef):
                        _sigs.append(f"  class {_node.name}")
                        for _cn in _node.body:
                            if isinstance(_cn, (_ast_plan.FunctionDef, _ast_plan.AsyncFunctionDef)):
                                _ca = [a.arg for a in _cn.args.args if a.arg != "self"]
                                _sigs.append(f"    def {_cn.name}({', '.join(_ca)})")
                if _sigs:
                    _api_parts.append(
                        f"【{_mpath.name}】{(' - ' + _mod_doc[:100]) if _mod_doc else ''}\n" +
                        "\n".join(_sigs[:12])
                    )
            except Exception:
                pass
        if _api_parts:
            module_api_ctx = "\n\n【現有系統模組 API - 規劃時優先使用這些，不要重新實作】\n" + "\n\n".join(_api_parts)
            _log(pid, f"🔍 已掃描 {len(_api_parts)} 個現有模組 API 注入規劃", "AI")
    except Exception as _me:
        _log(pid, f"⚠ 模組掃描失敗：{_me}", "WARN")

    system = """你是一個資深軟體工程師，負責把使用者需求拆解成具體可執行的程式任務。

只輸出 JSON，不要任何其他文字、不要 markdown、不要說明、不要 ```：
{"tasks": [
  {"seq": 1, "title": "任務標題", "description": "具體說明要做什麼，包含輸入輸出"},
  {"seq": 2, "title": "...", "description": "..."}
]}

規則：
- 每個任務都是獨立可測試的 Python 程式碼單元
- 每個任務的程式碼預期在 30~60 行以內
- 如果某個功能需要超過 60 行，必須拆成多個任務
- 測試類任務每個只測一個功能模組（不要寫一個大測試檔測所有東西）
- 任務數量 3~8 個（寧可多拆也不要太大）
- title 簡短清楚（10字以內）
- description 必須包含：要用哪些現有模組、禁止用哪些、函式名稱和參數
- 如果知識庫規則有指定使用某個模組，description 必須明確寫出 import 方式
- 只輸出 JSON，第一個字必須是 {"""

    sys_ctx     = get_system_context(max_chars=1500) if _HAS_SYSTEM_MAP else ""
    sys_section = f"\n\n{sys_ctx}" if sys_ctx else ""
    prompt = f"請把以下需求拆解成任務清單：\n\n{requirement}{kb_context}{module_api_ctx}{sys_section}"

    def sse_gen():
        full = []
        # 先顯示需求分析結果
        if final_req != requirement:
            yield f"data: {json.dumps({'type':'analyzed','text': final_req})}\n\n"
        yield f"data: {json.dumps({'type':'token','text':''})}\n\n"
        try:
            raw = _lobster_plan(final_req, kb_context + module_api_ctx)
            for i in range(0, len(raw), 15):
                tok = raw[i:i+15]
                full.append(tok)
                yield f"data: {json.dumps({'type':'token','text':tok})}\n\n"

            raw = "".join(full).strip()
            logger.info(f"[{pid[:8]}] 模型原始輸出（前300字）：{raw[:300]}")

            # 抽出 JSON：多重策略
            parsed = None

            # 策略1：移除 markdown fences 後直接解析
            cleaned = raw
            if "```" in cleaned:
                import re
                cleaned = re.sub(r'```(?:json)?\s*', '', cleaned).strip()

            # 策略2：找 {"tasks": 開頭
            for candidate in [cleaned, raw]:
                idx = candidate.find('{"tasks"')
                if idx == -1:
                    idx = candidate.find('{ "tasks"')
                if idx != -1:
                    end = candidate.rfind("}") + 1
                    try:
                        parsed = json.loads(candidate[idx:end])
                        break
                    except:
                        pass

            # 策略3：找最外層 { }
            if not parsed:
                for candidate in [cleaned, raw]:
                    start = candidate.find("{")
                    end   = candidate.rfind("}") + 1
                    if start != -1 and end > start:
                        try:
                            parsed = json.loads(candidate[start:end])
                            break
                        except:
                            pass

            if not parsed:
                logger.error(f"[{pid[:8]}] 無法解析 JSON，原始輸出：{raw}")
                yield f"data: {json.dumps({'type':'error','error':f'模型輸出無法解析為 JSON，請重試。原始：{raw[:200]}'})}\n\n"
                return

            tasks = parsed.get("tasks", [])

            # ── 正規化任務格式（相容多種模型輸出格式）────────────────────
            normalized = []
            for i, t in enumerate(tasks):
                # 有 seq + title → 標準格式
                # 有 name 沒有 title → 用 name 當 title
                # 有 id 沒有 seq → 用 id 序號
                seq   = t.get("seq") or t.get("id") or i + 1
                # 嘗試把 seq 轉成整數（T1 → 1）
                if isinstance(seq, str):
                    import re as _re
                    m = _re.search(r'\d+', seq)
                    seq = int(m.group()) if m else i + 1
                title = t.get("title") or t.get("name") or f"任務 {seq}"
                normalized.append({
                    "seq":         seq,
                    "title":       title,
                    "description": t["description"] or "" or t["description"] or "",
                })
            tasks = normalized

            now = _now()
            with _db() as c:
                for t in tasks:
                    tid = str(uuid.uuid4())
                    c.execute("""INSERT INTO tasks
                        (id,project_id,seq,title,description,status,repair_count,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (tid, pid, t["seq"], t["title"], t["description"] or "",
                         "pending", 0, now, now))
                c.execute("UPDATE projects SET status='planning',updated_at=? WHERE id=?", (now, pid))

            _log(pid, f"規劃完成：{len(tasks)} 個任務", "OK")
            socketio.emit("project_updated", {"id": pid})

            # 規劃審查統一由 _run_project 開始前處理，避免與程式碼審查同時進行
            yield f"data: {json.dumps({'type':'done','task_count':len(tasks)})}\n\n"

        except Exception as e:
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type':'error','error':str(e)})}\n\n"

    return Response(stream_with_context(sse_gen()), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ── 執行 ──────────────────────────────────────────────────────────────────────
# 每個專案一個執行執行緒
_running_projects: dict[str, threading.Thread] = {}
_stop_events:      dict[str, threading.Event]  = {}  # 每個專案一個停止信號
_confirm_events:   dict[str, threading.Event]  = {}
_confirm_results:  dict[str, str]              = {}
_review_events:    dict[str, threading.Event]  = {}  # 等待審查callback
_review_results:   dict[str, dict]             = {}  # 審查callback結果
_auto_projects:    set                         = set()  # 自動模式的專案ID
_ai_callbacks:     dict[str, str]              = {}  # 完成後通知的 callback URL
_human_events:     dict                        = {}  # 等待人工輸入的 Event
_human_answers:    dict                        = {}  # 人工貼入的解答

def _run_project(pid: str):
    """背景執行緒：依序執行所有 pending 任務。"""
    stop_ev = threading.Event()
    _stop_events[pid] = stop_ev

    # ── 規劃審查（只做一次，確保在任何程式碼審查之前完成）──────────────
    _plan_key = pid + "_plan"
    if REVIEW_ENABLED and _plan_key not in _review_results:
        _review_results[_plan_key] = True  # 先標記，避免重複
        with _db() as c:
            _tlist = c.execute(
                "SELECT seq,title,description FROM tasks WHERE project_id=? ORDER BY seq", (pid,)
            ).fetchall()
        if _tlist:
            _log(pid, "🔍 送審查Agent審查規劃...", "AI")
            _ptxt = "\n".join(
                f"{t['seq']}. {t['title']}：{t['description'] or ''}" for t in _tlist
            )
            _prv = _send_to_reviewer(
                pid=pid, task_id=_plan_key,
                content=_ptxt, review_type="plan",
                filename=f"{pid[:8]}_plan.txt", timeout=3600,
            )
            if _prv:
                _pn = _prv.get("plan",""); _pi = _prv.get("issues","")
                if _pn or _pi:
                    with _db() as c:
                        _req0 = c.execute("SELECT description FROM projects WHERE id=?", (pid,)).fetchone()
                        _note = f"\n\n【規劃審查建議】\n{_pn}"
                        if _pi: _note += f"\n問題：\n{_pi}"
                        c.execute("UPDATE projects SET description=?,updated_at=? WHERE id=?",
                                  ((_req0["description"] if _req0 else "") + _note, _now(), pid))
                    _log(pid, "✅ 規劃審查完成，已更新描述", "OK")
                else:
                    _log(pid, "✅ 規劃審查完成，無需修改", "OK")

    with _db() as c:
        # 清掉上次殘留的 running 狀態（執行緒中斷沒清乾淨的）
        c.execute("UPDATE tasks SET status='pending',updated_at=? WHERE project_id=? AND status='running'",
                  (_now(), pid))
        c.execute("UPDATE projects SET status='running',updated_at=? WHERE id=?", (_now(), pid))
    socketio.emit("project_updated", {"id": pid})

    with _db() as c:
        # 取所有未完成任務，按 seq 排序
        incomplete = c.execute(
            "SELECT * FROM tasks WHERE project_id=? AND status IN ('pending','running') ORDER BY seq", (pid,)
        ).fetchall()

        # 同時取所有任務（含已完成）用於顯示完整計畫
        all_tasks = c.execute(
            "SELECT id, seq, title, status FROM tasks WHERE project_id=? ORDER BY seq", (pid,)
        ).fetchall()

        done_seqs = set(row["seq"] for row in c.execute(
            "SELECT seq FROM tasks WHERE project_id=? AND status='done'", (pid,)
        ).fetchall())

    # emit 施工計畫（所有任務的列表與狀態）
    socketio.emit("build_plan", {
        "project_id": pid,
        "tasks": [{"id": t["id"], "seq": t["seq"], "title": t["title"], "status": t["status"]}
                  for t in all_tasks],
        "current_id": None,
    })

    def _progress(task):
        """這個任務之前有幾個已完成 = 完成度。"""
        return sum(1 for s in done_seqs if s < task["seq"])

    tasks = sorted(incomplete, key=_progress, reverse=True)

    for task in tasks:
        if stop_ev.is_set():
            _log(pid, "⏸ 收到暫停信號，停止執行", "WARN")
            return

        tid = task["id"]
        # 標註當前執行中的任務
        socketio.emit("build_plan_step", {"project_id": pid, "current_id": tid})
        _log(pid, f"▶ [{task['seq']}] {task['title']}", "AI", tid)
        result = _execute_task(pid, dict(task), stop_ev)

        if stop_ev.is_set() or result == "paused":
            return

        with _db() as c:
            p = c.execute("SELECT status FROM projects WHERE id=?", (pid,)).fetchone()
        if p and p["status"] == "paused":
            return

    _stop_events.pop(pid, None)

    with _db() as c:
        fail_count    = c.execute(
            "SELECT COUNT(*) FROM tasks WHERE project_id=? AND status='failed'", (pid,)
        ).fetchone()[0]
        skipped_count = c.execute(
            "SELECT COUNT(*) FROM tasks WHERE project_id=? AND status='skipped'", (pid,)
        ).fetchone()[0]
    final = "failed" if fail_count else "done"
    with _db() as c:
        c.execute("UPDATE projects SET status=?,updated_at=? WHERE id=?", (final, _now(), pid))
    skip_note = f"（{skipped_count} 個跳過）" if skipped_count else ""
    _log(pid, f"{'✅ 全部完成' if final=='done' else '⚠ 完成（有失敗任務）'}{skip_note}", "OK")
    socketio.emit("project_updated", {"id": pid})

    # ── 自動存進知識庫 ────────────────────────────────────────────────────────
    if final == "done":
        _save_project_to_knowledge(pid)
        _auto_assemble(pid)
        if pid in _auto_projects:
            _auto_projects.discard(pid)
            with _db() as c:
                p_name = c.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()
            _notify_ai(pid, "done",
                       f"器官「{p_name['name'] if p_name else pid[:8]}」已製作完成並組裝，可以使用了")

def _estimate_tokens(text: str) -> int:
    """估算 token 數（約 1 token = 3 中文字 or 4 英文字元）。"""
    chinese = sum(1 for c in text if '一' <= c <= '鿿')
    others  = len(text) - chinese
    return chinese // 3 + others // 4

TOKEN_LIMIT   = 10000  # 超過就拆分
SPLIT_EVERY   = 10000  # 每 10000 token 拆一個

def _split_task_if_needed(pid: str, task: dict, system: str, prompt: str) -> list[dict]:
    """
    估算 system + prompt 的 token 數，超過 TOKEN_LIMIT 就把任務拆成多個子任務。
    回傳子任務列表（沒超過就回傳原本的 [task]）。
    """
    total_tokens = _estimate_tokens(system + prompt)
    if total_tokens <= TOKEN_LIMIT:
        return [task]

    # 需要拆分
    n_parts = max(2, (total_tokens + SPLIT_EVERY - 1) // SPLIT_EVERY)
    _log(pid, f"⚠ 任務「{task['title']}」估計 {total_tokens} tokens，自動拆成 {n_parts} 個子任務", "AI")

    # 用 Ollama 規劃拆分方式
    split_prompt = f"""任務太複雜，需要拆成 {n_parts} 個獨立的子任務。

原任務：{task['title']}
說明：{task['description'] or ''}

請輸出嚴格 JSON（不要其他文字）：
{{"subtasks": [
  {{"title": "子任務1標題", "description": "具體說明，100字以內"}},
  {{"title": "子任務2標題", "description": "具體說明，100字以內"}}
]}}

規則：
- 每個子任務獨立可執行
- 合起來完成原任務的所有功能
- 標題簡短（10字以內）"""

    try:
        raw = _ollama_once(_pick(PLANNER_MODELS),
            "你是資深軟體工程師，只輸出 JSON，第一個字必須是 {",
            split_prompt, temperature=0.3)
        import re as _re
        raw = _re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        start, end = raw.find("{"), raw.rfind("}") + 1
        parsed = json.loads(raw[start:end])
        subtasks = parsed.get("subtasks", [])
    except Exception as e:
        _log(pid, f"⚠ 拆分規劃失敗（{e}），改用簡單拆分", "WARN")
        # 簡單拆分：把描述切成幾段
        desc = task["description"] or ""
        chunk_size = len(desc) // n_parts or 1
        subtasks = []
        for i in range(n_parts):
            subtasks.append({
                "title": f"{task['title']} (Part {i+1}/{n_parts})",
                "description": desc[i*chunk_size:(i+1)*chunk_size],
            })

    if not subtasks:
        return [task]

    # 建立子任務（插入 DB）
    now = _now()
    base_seq = task["seq"]
    new_tasks = []
    with _db() as c:
        # 把原任務 seq 後面的任務往後移
        c.execute("UPDATE tasks SET seq = seq + ? WHERE project_id=? AND seq > ?",
                  (len(subtasks) - 1, pid, base_seq))
        # 更新原任務為第一個子任務
        c.execute("UPDATE tasks SET title=?,description=?,updated_at=? WHERE id=?",
                  (subtasks[0]["title"], subtasks[0].get("description",""), now, task["id"]))
        new_tasks.append({**task, "title": subtasks[0]["title"],
                          "description": subtasks[0].get("description","")})
        # 插入其餘子任務
        for i, st in enumerate(subtasks[1:], 1):
            tid_new = str(uuid.uuid4())
            new_seq  = base_seq + i
            c.execute("""INSERT INTO tasks
                (id,project_id,seq,title,description,status,repair_count,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (tid_new, pid, new_seq, st["title"], st["description"] or "",
                 "pending", 0, now, now))
            new_tasks.append({"id": tid_new, "seq": new_seq,
                               "title": st["title"],
                               "description": st["description"] or ""})

    socketio.emit("project_updated", {"id": pid})
    _log(pid, f"✅ 已拆成 {len(new_tasks)} 個子任務", "OK")
    return new_tasks


def _execute_task(pid: str, task: dict, stop_ev: threading.Event = None):
    """執行單一任務，含自動修復最多 3 次。"""
    tid = task["id"]
    engine_name = "LobsterCore" if _USE_LOBSTER else _pick(CODER_MODELS)

    with _db() as c:
        proj = c.execute("SELECT description FROM projects WHERE id=?", (pid,)).fetchone()
    project_req = proj["description"] if proj else ""

    # 取得前面已完成任務的 code 作 context
    with _db() as c:
        done_tasks = c.execute(
            "SELECT title,code FROM tasks WHERE project_id=? AND status='done' ORDER BY seq", (pid,)
        ).fetchall()
    import ast as _ast_ctx
    context = ""
    if done_tasks:
        context = "\n【已完成任務的可用函式/類別，不要重複定義】\n"
        for dt in done_tasks:
            code = dt["code"] or ""
            sigs = []
            try:
                tree = _ast_ctx.parse(code)
                for node in tree.body:
                    if isinstance(node, (_ast_ctx.FunctionDef, _ast_ctx.AsyncFunctionDef)):
                        args = [a.arg for a in node.args.args]
                        sigs.append(f"def {node.name}({', '.join(args)})")
                    elif isinstance(node, _ast_ctx.ClassDef):
                        sigs.append(f"class {node.name}")
            except Exception:
                pass
            if sigs:
                context += f"# {dt['title']}：{', '.join(sigs)}\n"

    plan_text = ""
    for attempt in range(4):  # 0=初次, 1~3=修復
        is_repair = attempt > 0
        action = "修復" if is_repair else "生成"

        with _db() as c:
            err = c.execute("SELECT error FROM tasks WHERE id=?", (tid,)).fetchone()
        prev_error = err["error"] if err else ""

        _log(pid, f"{'🔧 修復' if is_repair else '⚙ 生成'} [{task['seq']}] {task['title']} (attempt {attempt+1})", "AI", tid)

        sys_ctx      = get_system_context(max_chars=400) if _HAS_SYSTEM_MAP else ""
        sys_section  = f"\n\n可用模組：{sys_ctx}" if sys_ctx else ""
        local_mods   = _scan_local_modules(max_chars=300)
        local_section = f"\n\n本地模組：{local_mods}" if local_mods else ""
        # ── 查詢知識庫規則 ────────────────────────────────────────────────
        _kb_rules = ""
        try:
            import socket as _sk2
            with _sk2.socket(_sk2.AF_INET, _sk2.SOCK_STREAM) as _s2:
                if _s2.connect_ex(('localhost', 7861)) == 0:
                    _kr = req.post("http://localhost:7861/api/search",
                                   json={"query": task['title'] + " " + task['description'] or ''[:100],
                                         "limit": 3}, timeout=5)
                    if _kr.status_code == 200:
                        _kr_results = _kr.json().get("results", [])
                        if _kr_results:
                            _kb_rules = "\n\n【知識庫規則 - 必須遵守】\n"
                            for _kr_item in _kr_results:
                                _kb_rules += f"- {_kr_item.get('title','')}：{_kr_item.get('content','')}\n"
                            _log(pid, f"📚 知識庫規則已載入（{len(_kr_results)} 條）", "AI", tid)
        except Exception:
            pass

        system = f"""你是資深 Python 工程師。只輸出可直接執行的 Python 程式碼，不要任何說明文字或 markdown。

【輸出規則 - 嚴格遵守】
1. 所有函式必須有完整實作，嚴禁輸出 pass、# TODO、...、raise NotImplementedError 等佔位符
2. 程式碼控制在 120 行以內；若功能超過 120 行，在最後一行加上注釋：# SPLIT_NEEDED: <建議的拆分方式>，然後只實作核心部分
3. 這是 Windows 系統，不要使用 Linux 指令（xdotool、scrot、xrandr 等）
4. 優先使用上方「現有系統檔案」中列出的模組，不要重新實作已有的功能
5. 不要使用未在現有模組中出現的第三方套件，除非任務明確要求

【輸出格式範例】
import os
import json

def load_config(path: str) -> dict:
    \"\"\"載入設定檔，找不到則回傳空字典。\"\"\"
    if not os.path.exists(path):
        return {{}}
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def save_config(path: str, data: dict) -> bool:
    \"\"\"儲存設定檔，成功回傳 True。\"\"\"
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"儲存失敗：{{e}}")
        return False

if __name__ == '__main__':
    cfg = load_config('config.json')
    cfg['version'] = '1.0'
    save_config('config.json', cfg)

專案需求：{project_req}
{context}{sys_section}{local_section}{_kb_rules}"""

        # ── 先估算是否需要拆分（在建 prompt 之前）─────────────────────────
        if not is_repair:
            task_desc = task['description'] or ''
            estimated = _estimate_tokens(system + task_desc + task['title'] or '')
            if estimated > TOKEN_LIMIT:
                # 建一個暫時的 prompt 來估算
                temp_prompt = f"任務：{task['title']}\n說明：{task_desc}\n\n請輸出完整的 Python 程式碼："
                subtasks = _split_task_if_needed(pid, task, system, temp_prompt)
                if len(subtasks) > 1:
                    task  = subtasks[0]
                    tid   = task["id"]
                    _log(pid, f"🔀 已拆分，執行子任務：{task['title']}", "AI", tid)

        plan_text = "" if is_repair else plan_text if attempt == 0 and 'plan_text' in locals() else ""
        if is_repair:
            prompt = f"""任務：{task['title']}
說明：{task['description'] or ''}

上次的程式碼執行出錯：
{prev_error}

請修復並輸出完整的修正後程式碼："""
        else:
            # 把施工計畫和已完成任務的函式簽名帶進 prompt
            plan_section   = f"\n\n施工計畫（完整規格，照此實作）：\n{plan_text}" if plan_text else ""
            context_section = f"\n\n{context}" if context else ""
            prompt = f"""任務：{task['title']}
說明：{task['description'] or ''}{plan_section}{context_section}

請根據以上計畫輸出完整的 Python 程式碼（最多 120 行，超過就精簡）："""

            # ── 施工計畫（首次生成才做）────────────────────────────────────
        if not is_repair:
            try:
                _planner_stem = _pick(PLANNER_MODELS).split(":")[0]
                for _lm in [m["name"] for m in req.get(f"{OLLAMA_URL}/api/ps", timeout=5).json().get("models", [])]:
                    if not _lm.startswith(_planner_stem):
                        _log(pid, f"  ⬇ 施工計畫前卸載 {_lm}", "INFO", tid)
                        _unload_model(_lm)
            except Exception:
                pass
            # ── Step 0：查詢相關模組 API ──────────────────────────────────
            _emit_step(pid, tid, "查詢相關模組", "active")
            _module_api_ctx = ""
            try:
                # 讓模型說「我需要參考哪些現有模組」
                _ref_prompt = (
                    f"任務：{task['title']}\n說明：{task['description'] or ''}\n\n"
                    f"現有系統模組：{local_section[:300]}\n\n"
                    f"請列出這個任務需要參考的現有模組名稱（只列檔名，用逗號分隔，最多3個）："
                )
                _ref_raw = _ollama_once(
                    _pick(PLANNER_MODELS),
                    "只列出檔名，不要說明。格式：module1.py, module2.py",
                    _ref_prompt, temperature=0.1
                )
                # 解析模組名稱並讀取 docstring
                import re as _re_mod
                _ref_names = [n.strip().replace(".py","") for n in _re_mod.split(r"[,\n\s]+", _ref_raw) if n.strip() and ".py" in n or n.strip() in [
                    p.stem for p in WORKSHOP_DIR.parent.glob("*.py")
                ]][:3]

                _base = WORKSHOP_DIR.parent
                _api_parts = []
                for _mname in _ref_names:
                    _mpath = _base / f"{_mname}.py"
                    if not _mpath.exists():
                        continue
                    try:
                        import ast as _ast_ref
                        _src = _mpath.read_text(encoding="utf-8", errors="replace")
                        _tree = _ast_ref.parse(_src)
                        # 取 module docstring + 所有函式/類別簽名
                        _mod_doc = _ast_ref.get_docstring(_tree) or ""
                        _sigs = []
                        for _node in _tree.body:
                            if isinstance(_node, (_ast_ref.FunctionDef, _ast_ref.AsyncFunctionDef)):
                                _args = [a.arg for a in _node.args.args]
                                _doc  = _ast_ref.get_docstring(_node) or ""
                                _sigs.append(f"  def {_node.name}({', '.join(_args)}): {_doc[:80]}")
                            elif isinstance(_node, _ast_ref.ClassDef):
                                _sigs.append(f"  class {_node.name}")
                                for _cn in _node.body:
                                    if isinstance(_cn, (_ast_ref.FunctionDef, _ast_ref.AsyncFunctionDef)):
                                        _ca = [a.arg for a in _cn.args.args]
                                        _sigs.append(f"    def {_cn.name}({', '.join(_ca)})")
                        _api_parts.append(
                            f"【{_mname}.py】\n{_mod_doc[:200]}\n" + "\n".join(_sigs[:15])
                        )
                    except Exception:
                        pass

                if _api_parts:
                    _module_api_ctx = "\n\n【可參考的現有模組 API】\n" + "\n\n".join(_api_parts)
                    _log(pid, f"📚 已載入模組 API：{', '.join(_ref_names)}", "AI", tid)

            except Exception as _me:
                _log(pid, f"⚠ 模組查詢失敗（繼續）：{_me}", "WARN", tid)
            _emit_step(pid, tid, "查詢相關模組", "done",
                       f"{len(_module_api_ctx)} 字")

            _emit_step(pid, tid, "分析施工計畫", "active")
            plan_prompt = f"""任務：{task['title']}
說明：{task['description']}
{context}{_module_api_ctx}
請用以下結構說明施工計畫（繁體中文，不要輸出程式碼）：

【平台確認】Windows 系統，使用 Python 套件，禁用 xdotool/scrot/Linux 指令

【Import 清單】只列出真正需要的模組，優先使用現有系統模組

【函式設計】列出要實作的函式名稱和參數，例如：
  - execute_command(command: str) -> str

【實作步驟】3-5 個步驟

【注意】不要重複定義已有函式"""
            plan_parts = []
            for tok in _ollama_stream(
                _pick(CODER_MODELS),
                "你是資深 Python 工程師，請用繁體中文簡短說明施工計畫。",
                plan_prompt,
                temperature=0.3,
                pid=pid,
            ):
                plan_parts.append(tok)
                socketio.emit("task_plan_token", {"project_id": pid, "task_id": tid, "token": tok})
            plan_text = "".join(plan_parts).strip()
            _emit_step(pid, tid, "分析施工計畫", "done", f"{len(plan_text)} 字")
            _log(pid, f"📋 施工計畫：{plan_text[:100]}...", "INFO", tid)

            # ── 切換到程式碼生成模型 ──────────────────────────────────────────
            _switch_model(pid, tid, CODER_MODELS[0])

        with _db() as c:
            c.execute("UPDATE tasks SET status='running',updated_at=? WHERE id=?", (_now(), tid))
        socketio.emit("task_updated", {"project_id": pid, "task_id": tid, "status": "running"})

        # 生成 / 修復 code
        code_parts = []
        _auto_simplified = threading.Event()


        # 動態估算生成時間（字元數估算）
        def _estimate_duration(title: str, desc: str) -> int:
            return max(2, min(15, len(desc) // 150 + 3))

        if not is_repair:
            estimated_minutes = _estimate_duration(task['title'] or '', task['description'] or '')
            _log(pid, f"⏱ 預估生成時間：{estimated_minutes} 分鐘", "AI", tid)
        else:
            estimated_minutes = 5

        # 心跳執行緒：動態監控是否卡住
        _hb_stop = threading.Event()
        def _heartbeat():
            count = 0
            last_len = 0
            stuck_count = 0
            while not _hb_stop.wait(60):
                count += 1
                current_len = len(code_parts)
                if count < estimated_minutes:
                    _log(pid, f"⏳ 生成中（{count}/{estimated_minutes} 分鐘，{current_len} tokens）... [{task['title']}]", "INFO", tid)
                else:
                    if current_len == last_len:
                        stuck_count += 1
                        if stuck_count >= 2 and not _auto_simplified.is_set() and not is_repair:
                            # 先確認 Ollama 是否在線，斷線不算卡住
                            try:
                                import requests as _rq2
                                _rq2.get("http://localhost:11434/api/tags", timeout=3)
                                ollama_ok = True
                            except Exception:
                                ollama_ok = False

                            if ollama_ok:
                                _auto_simplified.set()
                                _log(pid, f"🔍 確認卡住（{count} 分鐘無新輸出），自動精簡描述重試", "WARN", tid)
                                _force_stop_ollama(pid)
                            else:
                                _log(pid, f"⚠ Ollama 離線，等待重連（不拆分任務）...", "WARN", tid)
                        else:
                            _log(pid, f"🔍 超過預估時間，觀察中（{count} 分鐘，tokens 未增加）...", "WARN", tid)
                    else:
                        stuck_count = 0
                        _log(pid, f"⏳ 仍在生成（{count} 分鐘，{current_len} tokens，預估還需 {max(1, estimated_minutes - count)} 分鐘）... [{task['title']}]", "INFO", tid)
                last_len = current_len
        _hb_thread = threading.Thread(target=_heartbeat, daemon=True)
        _hb_thread.start()

        if is_repair:
            raw_code = _lobster_repair(
                code="",
                error=prev_error,
                task_desc=f"{task['title']}：{task['description'] or ''}"
            )
            for i in range(0, len(raw_code), 20):
                tok = raw_code[i:i+20]
                code_parts.append(tok)
                socketio.emit("stream_token", {"project_id": pid, "task_id": tid, "token": tok})
        else:
            for tok in _lobster_code_stream(system, prompt, pid=pid):
                stop = _stop_events.get(pid)
                if stop and stop.is_set():
                    _force_stop_ollama(pid)
                    return "paused"
                code_parts.append(tok)
                socketio.emit("stream_token", {"project_id": pid, "task_id": tid, "token": tok})

        code = "".join(code_parts).strip()

        _hb_stop.set()   # 停止心跳

        # 若心跳執行緒觸發了自動精簡 → 精簡描述重試
        if _auto_simplified.is_set() and not is_repair:
            _log(pid, "🔄 自動精簡描述，重新生成...", "AI", tid)
            try:
                simple_prompt = (f"把以下任務描述精簡成 2-3 句重點，不超過 80 字：\n\n{task['description'] or ''}")
                simplified = _ollama_once(
                    _pick(CODER_MODELS),
                    "只輸出精簡後的描述，不要說明。",
                    simple_prompt, temperature=0.2
                )
                if simplified and simplified.strip():
                    new_desc = simplified.strip()
                    with _db() as c:
                        c.execute("UPDATE tasks SET description=?,updated_at=? WHERE id=?",
                                  (new_desc, _now(), tid))
                    task = dict(task)
                    task["description"] = new_desc
                    prompt = f"任務：{task['title']}\n說明：{new_desc}\n\n請輸出完整的 Python 程式碼（最多 120 行）："
                    _log(pid, f"📝 新描述：{new_desc[:80]}", "AI", tid)
                    # 重新生成
                    code_parts = []
                    for tok in _lobster_code_stream(system, prompt, pid=pid):
                        code_parts.append(tok)
                        socketio.emit("stream_token", {"project_id": pid, "task_id": tid, "token": tok})
            except Exception as e:
                _log(pid, f"⚠ 自動精簡失敗：{e}", "WARN", tid)

        # 檢查 Ollama 連線失敗
        if code.startswith("__OLLAMA_ERROR__:"):
            err_msg = code.replace("__OLLAMA_ERROR__:", "")
            _log(pid, f"❌ Ollama 連線失敗，任務中止：{err_msg}", "ERROR", tid)
            with _db() as c:
                c.execute("UPDATE tasks SET status='failed',error=?,updated_at=? WHERE id=?",
                          (f"Ollama 離線：{err_msg}", _now(), tid))
            socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
            return "failed"

        # 移除可能的 markdown fences 和說明文字
        import re as _re_clean
        code = _re_clean.sub(r"```(?:python)?\s*", "", code).strip().rstrip("`")

        # 黑名單指令掃描
        _blacklist = ["xdotool", "scrot", "xrandr", "wmctrl", "xwininfo"]
        _found_bl  = [b for b in _blacklist if b in code]
        if _found_bl:
            _log(pid, f"⚠ 偵測到不相容 Linux 指令：{_found_bl}，重新修復", "WARN", tid)
            # 強制帶入修復提示
            code = "# 錯誤：包含 Windows 不支援的指令，請用 pyautogui/desktop_control 替代\n" + code
        # 過濾說明文字：移除夾在程式碼中的中文說明行
        _code_line = re.compile(
            r'^\s*($|#|import |from |def |class |if |else:|elif |try:|except|finally:|'
            r'with |return |raise |pass|break|continue|[a-zA-Z_][\w\.]*\s*[=(\[{]|'
            r'"""|\'\'\'|[\-+*/]|@|async |await |yield |lambda )',
            re.MULTILINE
        )
        lines = code.split("\n")
        # 找第一行程式碼
        start_idx = 0
        for i, line in enumerate(lines):
            if _code_line.match(line):
                start_idx = i
                break
        # 過濾中間的純中文說明行（不在字串內的）
        cleaned = []
        in_string = False
        for line in lines[start_idx:]:
            stripped = line.strip()
            # 偵測多行字串邊界
            if stripped.count('"""') % 2 == 1 or stripped.count("'''") % 2 == 1:
                in_string = not in_string
            if in_string:
                cleaned.append(line)
                continue
            # 純中文說明行特徵：以中文字開頭、不含 Python 語法符號
            is_chinese_desc = (
                stripped and
                '\u4e00' <= stripped[0] <= '\u9fff' and
                not stripped.startswith('#') and
                '=' not in stripped and
                '(' not in stripped and
                ':' not in stripped
            )
            if not is_chinese_desc:
                cleaned.append(line)
            else:
                _log(pid, f"⚠ 過濾說明文字：{stripped[:40]}", "INFO", tid)
        code = "\n".join(cleaned).strip()

        if not code.strip():
            _log(pid, "❌ 生成的程式碼是空的，任務中止", "ERROR", tid)
            with _db() as c:
                c.execute("UPDATE tasks SET status='failed',error=?,updated_at=? WHERE id=?",
                          ("生成程式碼為空", _now(), tid))
            socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
            return "failed"

        _log(pid, f"程式碼已生成（{len(code)} 字元），執行中...", "INFO", tid)
        _emit_step(pid, tid, "執行程式碼", "active")

        success, output = _run_code(code, pid)
        _emit_step(pid, tid, "執行程式碼",
                   "done" if success else "error",
                   output[:80] if output else "")

        with _db() as c:
            c.execute("UPDATE tasks SET code=?,error=?,repair_count=?,updated_at=? WHERE id=?",
                      (code, None if success else output, attempt, _now(), tid))

        if success:
            if REVIEW_ENABLED:
                _log(pid, f"🔍 [{task['seq']}] {task['title']} 執行通過，等待審查...", "AI", tid)
                socketio.emit("stream_token", {"project_id": pid, "task_id": tid,
                                               "token": "\n\n⏳ 等待審查Agent審查..."})
                # 同步等待審查結果
                review_result = _send_to_reviewer(
                    pid=pid, task_id=tid,
                    content=code,
                    review_type="code",
                    filename=f"{task['title'].replace(' ','_')}.py",
                    timeout=3600,  # 等最多 1 小時
                )
                final_code = code
                if review_result and review_result.get("fixed_code"):
                    final_code = review_result["fixed_code"]
                    _log(pid, f"✅ [{task['seq']}] 審查完成，採用修正版程式碼", "OK", tid)
                    review_summary = "\n\n✅ 審查完成，程式碼已依審查意見修正"
                elif review_result:
                    _log(pid, f"✅ [{task['seq']}] 審查完成，程式碼無需修改", "OK", tid)
                    review_summary = "\n\n✅ 審查完成，程式碼無需修改"
                else:
                    _log(pid, f"⚠ [{task['seq']}] 審查逾時或跳過", "WARN", tid)
                    review_summary = "\n\n⚠ 審查逾時，使用原始程式碼"
                with _db() as c:
                    c.execute("UPDATE tasks SET status='done',code=?,updated_at=? WHERE id=?",
                              (final_code, _now(), tid))
                socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
            else:
                # 審查關閉，直接標記完成
                with _db() as c:
                    c.execute("UPDATE tasks SET status='done',code=?,updated_at=? WHERE id=?",
                              (code, _now(), tid))
                socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
                _log(pid, f"✅ [{task['seq']}] {task['title']} 完成", "OK", tid)
                review_summary = ""

            # ── 預設自動繼續，只有按暫停才停 ───────────────────────────────
            _log(pid, f"✅ 任務 #{task['seq']} 完成，自動繼續", "AI", tid)
            return "continue"

        else:
            _log(pid, f"❌ 執行失敗（attempt {attempt+1}）：{output[:120]}", "ERROR", tid)
            socketio.emit("task_updated", {"project_id": pid, "task_id": tid})

            if attempt >= 3:
                # ── 先判斷是否應該自動跳過 ──────────────────────────────────
                skip_patterns = [
                    "No module named",
                    "ModuleNotFoundError",
                    "cannot import name",
                ]
                # 只有真的缺模組才跳過，一般執行錯誤不跳過
                should_auto_skip = (
                    any(p in output for p in skip_patterns)
                    and "ImportError" not in output.split("No module")[0][:50]  # 確認是 import 錯誤
                )

                if should_auto_skip:
                    _log(pid, f"⏭ [{task['seq']}] 自動跳過：缺少依賴模組（{output[:80]}）", "WARN", tid)
                    with _db() as c:
                        c.execute("UPDATE tasks SET status='skipped',error=?,updated_at=? WHERE id=?",
                                  (f"自動跳過：{output[:200]}", _now(), tid))
                    socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
                    return "continue"

                _log(pid, f"⚠ [{task['seq']}] 修復 3 次仍失敗，等待人工協助", "WARN", tid)

                # 加入字典（確保有定義）
                if "_human_events" not in dir():
                    pass  # 已在全域定義

                human_id = str(uuid.uuid4())
                human_ev = threading.Event()
                _human_events[human_id] = human_ev

                socketio.emit("human_assist_request", {
                    "project_id": pid,
                    "task_id":    tid,
                    "human_id":   human_id,
                    "task_seq":   task["seq"],
                    "task_title": task["title"],
                    "error":      output[:500],
                    "code":       "".join(code_parts) if code_parts else "",
                })

                if pid in _auto_projects:
                    _notify_ai(pid, "failed",
                               f"任務 #{task['seq']}「{task['title']}」修復 3 次仍失敗，需要人工介入",
                               extra={
                                   "human_id":   human_id,
                                   "task_id":    tid,
                                   "task_title": task["title"],
                                   "error":      output[:500],
                                   "code":       "".join(code_parts) if code_parts else "",
                               })

                _log(pid, "⏳ 等待人工輸入解答（最多 2 小時）...", "AI", tid)
                signaled = human_ev.wait(timeout=7200)
                _human_events.pop(human_id, None)

                if not signaled:
                    _log(pid, "⌛ 人工輸入逾時，暫停任務", "WARN", tid)
                    with _db() as c:
                        c.execute("UPDATE tasks SET status='paused',updated_at=? WHERE id=?", (_now(), tid))
                        c.execute("UPDATE projects SET status='paused',updated_at=? WHERE id=?", (_now(), pid))
                    socketio.emit("project_updated", {"id": pid})
                    return

                human_solution = _human_answers.pop(human_id, "")
                if not human_solution:
                    return

                _log(pid, "✅ 收到人工解答，繼續修復", "AI", tid)
                import re as _re2
                fix_prompt = (f"任務：{task['title']}\n"
                              f"說明：{task['description'] or ''}\n\n"
                              f"錯誤：{output[:300]}\n\n"
                              f"人工解決方案：\n{human_solution}\n\n"
                              f"請輸出修正後的完整 Python 程式碼：")
                fixed_code = _ollama_once(
                    _pick(CODER_MODELS),
                    "你是資深 Python 工程師，只輸出程式碼，不要說明。",
                    fix_prompt, temperature=0.2
                )
                if fixed_code:
                    fc = _re2.sub(r"```(?:python)?\s*", "", fixed_code).strip().rstrip("`")
                    success2, output2 = _run_code(fc, pid)
                    if success2:
                        _log(pid, "✅ 人工協助修復成功！", "OK", tid)
                        try:
                            from bug_learning_engine import learn_bug
                            learn_bug(
                                project_state={"changed": [task["title"]], "files": []},
                                diagnosis=output[:500],
                                repair_plan=human_solution,
                                result=True,
                            )
                            _log(pid, "📚 已學習此次修復經驗", "AI", tid)
                        except Exception as _le:
                            _log(pid, f"⚠ 學習存入失敗：{_le}", "WARN", tid)
                        with _db() as c:
                            c.execute("UPDATE tasks SET status='done',code=?,updated_at=? WHERE id=?",
                                      (fc, _now(), tid))
                        socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
                        break

                with _db() as c:
                    c.execute("UPDATE tasks SET status='paused',updated_at=? WHERE id=?", (_now(), tid))
                    c.execute("UPDATE projects SET status='paused',updated_at=? WHERE id=?", (_now(), pid))
                socketio.emit("project_updated", {"id": pid})
                return

@app.route("/api/projects/<pid>/run", methods=["POST"])
def api_run_project(pid):
    if pid in _running_projects and _running_projects[pid].is_alive():
        return jsonify({"error": "已在執行中"}), 400
    with _db() as c:
        c.execute("UPDATE projects SET status='running',updated_at=? WHERE id=?", (_now(), pid))
    t = threading.Thread(target=_run_project, args=(pid,), daemon=True)
    _running_projects[pid] = t
    t.start()
    return jsonify({"ok": True})

_resume_lock: dict = {}   # 防止重複 resume

@app.route("/api/projects/<pid>/resume", methods=["POST"])
def api_resume_project(pid):
    import time as _t
    now = _t.time()
    last = _resume_lock.get(pid, 0)
    if now - last < 3:   # 3 秒內不重複執行
        return jsonify({"ok": True, "skipped": True})
    _resume_lock[pid] = now

    # 如果已經在跑了就跳過
    if pid in _running_projects and _running_projects[pid].is_alive():
        return jsonify({"ok": True, "skipped": True})

    with _db() as c:
        c.execute("UPDATE tasks SET status='pending',error=NULL,updated_at=? WHERE project_id=? AND status IN ('paused','running')",
                  (_now(), pid))
        c.execute("UPDATE projects SET status='running',updated_at=? WHERE id=?", (_now(), pid))
    socketio.emit("project_updated", {"id": pid})
    t = threading.Thread(target=_run_project, args=(pid,), daemon=True)
    _running_projects[pid] = t
    t.start()
    return jsonify({"ok": True})

@app.route("/api/projects/<pid>/pause", methods=["POST"])
def api_pause_project(pid):
    # 1. 設置停止信號
    if pid in _stop_events:
        _stop_events[pid].set()

    # 2. 關閉 requests session（中斷 streaming）
    _force_stop_ollama(pid)

    # 3. 用 taskkill 強制中斷 Ollama（確保生成真的停止）
    try:
        import subprocess as _sp
        _sp.run(["taskkill", "/F", "/IM", "ollama.exe"],
                capture_output=True, creationflags=_sp.CREATE_NO_WINDOW)
        import time as _t; _t.sleep(1)
        _sp.Popen(["ollama", "serve"],
                  creationflags=_sp.CREATE_NO_WINDOW)
        _log(pid, "🔄 Ollama 已重啟", "WARN")
    except Exception as _e:
        _log(pid, f"⚠ Ollama 重啟失敗：{_e}", "WARN")

    with _db() as c:
        c.execute("UPDATE projects SET status='paused',updated_at=? WHERE id=?", (_now(), pid))
        c.execute("UPDATE tasks SET status='pending',updated_at=? WHERE project_id=? AND status='running'",
                  (_now(), pid))
    socketio.emit("project_updated", {"id": pid})
    _log(pid, "⏸ 已暫停，Ollama 已中斷", "WARN")
    return jsonify({"ok": True})

@app.route("/api/projects/<pid>/rerun", methods=["POST"])
def api_rerun_project(pid):
    with _db() as c:
        c.execute("""UPDATE tasks SET status='pending', code=NULL, error=NULL,
                     repair_count=0, review_passed=NULL, review_report=NULL,
                     review_issues=NULL, review_suggestions=NULL, updated_at=?
                     WHERE project_id=?""", (_now(), pid))
        c.execute("UPDATE projects SET status='running',updated_at=? WHERE id=?", (_now(), pid))
    socketio.emit("project_updated", {"id": pid})
    _log(pid, "🔄 全部重跑", "AI")
    t = threading.Thread(target=_run_project, args=(pid,), daemon=True)
    _running_projects[pid] = t
    t.start()
    return jsonify({"ok": True})

# ── 任務操作 ──────────────────────────────────────────────────────────────────
@app.route("/api/tasks/<tid>/approve", methods=["POST"])
def api_approve_task(tid):
    with _db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task: return jsonify({"error":"找不到"}), 404
        c.execute("UPDATE tasks SET status='done',updated_at=? WHERE id=?", (_now(), tid))
        c.execute("UPDATE projects SET status='running',updated_at=? WHERE id=?", (_now(), task["project_id"]))
    pid = task["project_id"]
    socketio.emit("project_updated", {"id": pid})
    socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
    t = threading.Thread(target=_run_project, args=(pid,), daemon=True)
    _running_projects[pid] = t
    t.start()
    return jsonify({"ok": True})

@app.route("/api/projects/<pid>/cleanup_parts", methods=["POST"])
def api_cleanup_parts(pid):
    """刪除因 Ollama 斷線誤判產生的 Part X/Y 子任務（所有狀態）。"""
    with _db() as c:
        tasks = c.execute(
            "SELECT * FROM tasks WHERE project_id=? AND (title LIKE '% (Part %/%)')",
            (pid,)
        ).fetchall()
        deleted = 0
        for t in tasks:
            c.execute("DELETE FROM tasks WHERE id=?", (t["id"],))
            deleted += 1
        # 重新排序剩餘任務的 seq
        remaining = c.execute(
            "SELECT id FROM tasks WHERE project_id=? ORDER BY seq", (pid,)
        ).fetchall()
        for i, r in enumerate(remaining, 1):
            c.execute("UPDATE tasks SET seq=? WHERE id=?", (i, r["id"]))
    socketio.emit("project_updated", {"id": pid})
    _log(pid, f"🗑 已清除 {deleted} 個因斷線誤判產生的子任務", "OK")
    return jsonify({"ok": True, "deleted": deleted})


@app.route("/api/tasks/<tid>/delete", methods=["POST"])
def api_delete_task(tid):
    """刪除單一任務。"""
    with _db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task:
            return jsonify({"error": "找不到"}), 404
        pid = task["project_id"]
        c.execute("DELETE FROM tasks WHERE id=?", (tid,))
        # 重新排序 seq
        remaining = c.execute("SELECT id FROM tasks WHERE project_id=? ORDER BY seq", (pid,)).fetchall()
        for i, r in enumerate(remaining, 1):
            c.execute("UPDATE tasks SET seq=? WHERE id=?", (i, r["id"]))
    socketio.emit("project_updated", {"id": pid})
    return jsonify({"ok": True})


@app.route("/api/tasks/<tid>/skip", methods=["POST"])
def api_skip_task(tid):
    with _db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task: return jsonify({"error":"找不到"}), 404
        c.execute("UPDATE tasks SET status='skipped',updated_at=? WHERE id=?", (_now(), tid))
    pid = task["project_id"]
    socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
    return jsonify({"ok": True})

@app.route("/api/tasks/<tid>/edit_desc", methods=["POST"])
def api_edit_task_desc(tid):
    """直接修改任務描述，可選擇是否重新執行。"""
    data        = request.get_json(silent=True) or {}
    new_desc    = str(data.get("description", "")).strip()
    rerun       = bool(data.get("rerun", False))
    if not new_desc:
        return jsonify({"error": "描述不能為空"}), 400
    with _db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task: return jsonify({"error": "找不到"}), 404
        if rerun:
            c.execute("""UPDATE tasks SET description=?,status='pending',
                         code=NULL,error=NULL,repair_count=0,updated_at=? WHERE id=?""",
                      (new_desc, _now(), tid))
        else:
            c.execute("UPDATE tasks SET description=?,updated_at=? WHERE id=?",
                      (new_desc, _now(), tid))
    pid = task["project_id"]
    socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
    if rerun:
        with _db() as c:
            c.execute("UPDATE projects SET status='running',updated_at=? WHERE id=?", (_now(), pid))
        t = threading.Thread(target=_run_project, args=(pid,), daemon=True)
        _running_projects[pid] = t
        t.start()
    return jsonify({"ok": True})


@app.route("/api/tasks/<tid>/edit", methods=["POST"])
def api_edit_task(tid):
    data = request.get_json(silent=True) or {}
    instruction = str(data.get("instruction","")).strip()
    with _db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task: return jsonify({"error":"找不到"}), 404
        new_desc = task["description"] + (f"\n\n修改意見：{instruction}" if instruction else "")
        c.execute("UPDATE tasks SET description=?,status='pending',error=NULL,repair_count=0,updated_at=? WHERE id=?",
                  (new_desc, _now(), tid))
        c.execute("UPDATE projects SET status='running',updated_at=? WHERE id=?", (_now(), task["project_id"]))
    pid = task["project_id"]
    socketio.emit("task_updated", {"project_id": pid, "task_id": tid})
    t = threading.Thread(target=_run_project, args=(pid,), daemon=True)
    _running_projects[pid] = t
    t.start()
    return jsonify({"ok": True})

@app.route("/api/tasks/<tid>/reset", methods=["POST"])
def api_reset_task(tid):
    """把單一任務重設為 pending。"""
    with _db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task: return jsonify({"error": "找不到"}), 404
        c.execute("UPDATE tasks SET status='pending',code=NULL,error=NULL,repair_count=0,updated_at=? WHERE id=?",
                  (_now(), tid))
        c.execute("UPDATE projects SET status='paused',updated_at=? WHERE id=?",
                  (_now(), task["project_id"]))
    socketio.emit("project_updated", {"id": task["project_id"]})
    socketio.emit("task_updated", {"project_id": task["project_id"], "task_id": tid})
    return jsonify({"ok": True})


@app.route("/api/tasks/<tid>/run", methods=["POST"])
def api_run_task(tid):
    with _db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task: return jsonify({"error":"找不到"}), 404
        task = dict(task)
    t = threading.Thread(target=_execute_task, args=(task["project_id"], task), daemon=True)
    t.start()
    return jsonify({"ok": True})

# ── Confirm ────────────────────────────────────────────────────────────────────
@app.route("/api/human_assist/<human_id>", methods=["POST"])
def api_human_assist(human_id):
    """接收人工貼入的解答，喚醒等待中的修復執行緒。"""
    data     = request.get_json(silent=True) or {}
    solution = str(data.get("solution", "")).strip()
    if not solution:
        return jsonify({"error": "解答不能為空"}), 400
    _human_answers[human_id] = solution
    if human_id in _human_events:
        _human_events[human_id].set()
    return jsonify({"ok": True})


@app.route("/api/confirm/<confirm_id>", methods=["POST"])
def api_confirm(confirm_id):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action","continue"))
    _confirm_results[confirm_id] = action
    if confirm_id in _confirm_events:
        _confirm_events[confirm_id].set()
    return jsonify({"ok": True})

# ── 匯出 ──────────────────────────────────────────────────────────────────────
@app.route("/api/projects/<pid>/export")
def api_export(pid):
    with _db() as c:
        p = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        tasks = c.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY seq", (pid,)).fetchall()
    if not p: return jsonify({"error":"找不到"}), 404

    lines = [f"# {p['name']}", f"## 需求", p['description'] or '', "", "## 任務"]
    for t in tasks:
        lines += [f"\n### [{t['seq']}] {t['title']}", t['description'] or '', ""]
        if t['code']:
            lines += ["```python", t['code'], "```"]
    export_dir = WORKSHOP_DIR / "exports"
    export_dir.mkdir(exist_ok=True)
    out = export_dir / f"{p['name'].replace(' ','_')}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    from flask import send_file
    return send_file(str(out), as_attachment=True, download_name=out.name)

@app.route("/api/projects/<pid>/assemble", methods=["POST"])
def api_assemble(pid):
    """
    把專案所有完成任務的程式碼組合成單一 .py 檔。
    存到 workshop_data/assembled/<專案名>.py
    供 desktop_agent 直接載入執行。
    """
    with _db() as c:
        p     = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        tasks = c.execute(
            "SELECT * FROM tasks WHERE project_id=? AND status='done' ORDER BY seq", (pid,)
        ).fetchall()
    if not p:
        return jsonify({"error": "找不到專案"}), 404
    if not tasks:
        return jsonify({"error": "沒有完成的任務"}), 400

    assembled_dir = WORKSHOP_DIR / "assembled"
    assembled_dir.mkdir(exist_ok=True)

    safe_name = p["name"].replace(" ", "_").replace("/", "_")
    out_path  = assembled_dir / f"{safe_name}.py"

    req_lines = [l.strip() for l in (p["description"] or "").splitlines()
                 if l.strip() and not l.strip().startswith("【") and "審查" not in l]
    module_doc = req_lines[0][:120] if req_lines else p["name"]
    header = [
        f'"""{module_doc}"""',
        f"# ── 工坊組裝：{p['name']} ──────────────────────────────────────────",
        f"# 組裝時間：{_now()}",
        f"# 任務數：{len(tasks)}",
        "",
    ]
    task_codes = []
    for t in tasks:
        code = (t["code"] or "").strip()
        if not code:
            continue
        task_codes.append(f"# ── [{t['seq']}] {t['title']}\n{code}")
    cleaned = _clean_assembled_code(task_codes)
    out_path.write_text("\n".join(header) + "\n" + cleaned, encoding="utf-8")
    logger.info(f"[Assemble] 組裝完成：{out_path}")

    # 自動驗證，失敗則自動修正
    val = _validate_assembled(out_path)
    pid_local = str(p["id"]) if "id" in p.keys() else "manual"
    if not val["ok"] or any("過少" in w or "空殼" in w for w in val.get("warnings", [])):
        logger.warning(f"[Assemble] {out_path.name} 驗證失敗，啟動自動修正")
        threading.Thread(
            target=_auto_fix_assembled, args=(out_path, pid_local), daemon=True
        ).start()
    else:
        if val["warnings"]:
            logger.info(f"[Assemble] {out_path.name} 警告：{'; '.join(val['warnings'])}")
        logger.info(f"[Assemble] {out_path.name} 驗證通過")

    return jsonify({
        "ok":        True,
        "path":      str(out_path),
        "name":      p["name"],
        "tasks":     len(tasks),
        "size":      out_path.stat().st_size,
        "validated": val["ok"],
        "errors":    val["errors"],
        "warnings":  val["warnings"],
    })

@app.route("/api/assembled")
def api_list_assembled():
    """列出所有已組裝的模組供 desktop_agent 使用。"""
    assembled_dir = WORKSHOP_DIR / "assembled"
    assembled_dir.mkdir(exist_ok=True)
    files = []
    for f in sorted(assembled_dir.glob("*.py"), key=lambda x: x.stat().st_mtime, reverse=True):
        files.append({
            "name":     f.stem.replace("_", " "),
            "filename": f.name,
            "path":     str(f),
            "size":     f.stat().st_size,
            "mtime":    datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return jsonify(files)

@app.route("/api/assembled/<filename>")
def api_get_assembled(filename):
    """取得單一組裝模組的程式碼內容。"""
    filename = pathlib.Path(filename).name  # 防止路徑穿越
    path = WORKSHOP_DIR / "assembled" / filename
    if not path.exists():
        return jsonify({"error": "找不到"}), 404
    return jsonify({
        "filename": filename,
        "code":     path.read_text(encoding="utf-8"),
        "size":     path.stat().st_size,
    })

# ── 器官修正 API ──────────────────────────────────────────────────────────────

@app.route("/api/repair_assembled", methods=["POST"])
def api_repair_assembled():
    """修正 assembled 資料夾裡有問題的器官。"""
    data     = request.get_json(silent=True) or {}
    filename = data.get("filename", "")   # 空白 = 全部
    results  = []

    assembled_dir = WORKSHOP_DIR / "assembled"
    if filename:
        files = [assembled_dir / pathlib.Path(filename).name]
    else:
        files = sorted(assembled_dir.glob("*.py"), key=lambda x: x.stat().st_mtime, reverse=True)

    def do_repair():
        for path in files:
            if not path.exists():
                socketio.emit("repair_progress", {"filename": str(path.name), "status": "not_found"})
                continue
            val = _validate_assembled(path)
            if val["ok"] and not any("過少" in w or "空殼" in w for w in val.get("warnings", [])):
                socketio.emit("repair_progress", {
                    "filename": path.name, "status": "ok",
                    "message": "驗證通過，無需修正"
                })
                continue
            socketio.emit("repair_progress", {
                "filename": path.name, "status": "fixing",
                "message": f"修正中：{'; '.join(val['errors'] + val.get('warnings', []))}"
            })
            ok = _auto_fix_assembled(path, "repair_api")
            socketio.emit("repair_progress", {
                "filename": path.name,
                "status":   "fixed" if ok else "failed",
                "message":  "修正完成" if ok else "無法自動修正，需人工介入"
            })
        socketio.emit("repair_progress", {"filename": "", "status": "done", "message": "全部完成"})

    threading.Thread(target=do_repair, daemon=True).start()
    return jsonify({"ok": True, "count": len(list(files))})


# ── 啟動 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 強制 stdout 使用 utf-8，避免 Windows cp950 無法顯示特殊字元導致啟動崩潰
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("[workshop] 工坊啟動中...")
    print("   http://localhost:7862")
    try:
        models = _get_models()
        if models:
            print(f"   規劃模型：{_pick(PLANNER_MODELS)}")
            print(f"   生成模型：{_pick(CODER_MODELS)}")
        else:
            print("   [!] Ollama 無回應")
    except:
        print("   [!] 無法連線 Ollama")
    print("   Ctrl+C 停止")
    socketio.run(app, host="0.0.0.0", port=7862, debug=False, allow_unsafe_werkzeug=True)
