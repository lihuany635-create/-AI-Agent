"""
web_dashboard.py - 網頁控制介面
功能：
  - 瀏覽器開啟 http://localhost:7860 即可使用
  - 即時查看 Agent 狀態、日誌、記憶庫
  - 手動下指令給 Agent
  - 查看修復歷史紀錄
安裝依賴：
    pip install flask
使用方式：
    python web_dashboard.py
    然後打開瀏覽器 → http://localhost:7860
"""

import json
import pathlib
import threading
import datetime
from typing import Optional

try:
    from flask import Flask, jsonify, request, render_template_string
except ImportError:
    print("[錯誤] 請先安裝 Flask：pip install flask")
    raise

try:
    from agent_logger import get_logger
    logger = get_logger("web_dashboard")
except ImportError:
    import logging
    logger = logging.getLogger("web_dashboard")

try:
    from long_term_memory import get_memory
    _memory = get_memory()
except ImportError:
    _memory = None

app = Flask(__name__)

# ── 共享狀態 ────────────────────────────────────────────────────────────────

_state = {
    "status":     "idle",      # idle / running / error
    "last_task":  "",
    "last_result": "",
    "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
}
_state_lock = threading.Lock()
_command_queue: list[str] = []

# ── HTML 介面 ───────────────────────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lobster Core Dashboard</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',sans-serif;background:#0f1117;color:#e0e0e0;padding:20px}
    h1{font-size:1.4rem;color:#7eb8f7;margin-bottom:20px}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .card{background:#1a1d27;border:1px solid #2a2d3a;border-radius:10px;padding:16px}
    .card h2{font-size:.85rem;color:#888;text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px}
    .status{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.8rem;font-weight:600}
    .status.idle{background:#1e3a2f;color:#4caf82}
    .status.running{background:#2a2a00;color:#f0c040;animation:blink 1s infinite}
    .status.error{background:#3a1a1a;color:#f07070}
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.5}}
    #log-box{height:200px;overflow-y:auto;background:#111;border-radius:6px;padding:10px;font-family:monospace;font-size:.78rem;color:#b0ffb0}
    #memory-box{height:180px;overflow-y:auto}
    .mem-item{border-bottom:1px solid #2a2d3a;padding:6px 0;font-size:.82rem}
    .mem-tag{background:#1e2d45;color:#7eb8f7;border-radius:4px;padding:1px 6px;font-size:.72rem;margin-right:4px}
    .imp{color:#f0c040;font-size:.75rem;margin-left:6px}
    textarea{width:100%;background:#111;border:1px solid #2a2d3a;border-radius:6px;color:#e0e0e0;padding:8px;font-family:monospace;font-size:.85rem;resize:vertical}
    button{background:#2563eb;color:#fff;border:none;border-radius:6px;padding:8px 18px;cursor:pointer;font-size:.85rem;margin-top:8px}
    button:hover{background:#1d4ed8}
    .result{margin-top:10px;background:#111;border-radius:6px;padding:10px;font-size:.82rem;min-height:40px;white-space:pre-wrap;color:#a0d0ff}
    .stat{font-size:1.5rem;font-weight:700;color:#7eb8f7}
    .stat-label{font-size:.78rem;color:#888;margin-top:2px}
    .stats-row{display:flex;gap:20px;margin-bottom:8px}
  </style>
</head>
<body>
  <h1>🦞 Lobster Core — Dashboard</h1>
  <div class="grid">

    <!-- 狀態卡 -->
    <div class="card">
      <h2>Agent 狀態</h2>
      <div class="stats-row">
        <div><div class="stat" id="mem-count">-</div><div class="stat-label">記憶筆數</div></div>
        <div><div class="stat" id="uptime">-</div><div class="stat-label">運行時間</div></div>
        <div><span class="status idle" id="status-badge">idle</span></div>
      </div>
      <div style="font-size:.82rem;color:#888;margin-top:8px">上次任務：<span id="last-task" style="color:#ccc">（無）</span></div>
    </div>

    <!-- 下指令 -->
    <div class="card">
      <h2>下指令給 Agent</h2>
      <textarea id="cmd-input" rows="3" placeholder="例如：幫我掃描專案錯誤&#10;修復 repair_engine.py&#10;搜尋記憶：Ollama 設定"></textarea>
      <button onclick="sendCommand()">傳送指令</button>
      <div class="result" id="cmd-result">等待指令...</div>
    </div>

    <!-- 日誌 -->
    <div class="card">
      <h2>即時日誌</h2>
      <div id="log-box">載入中...</div>
      <button onclick="refreshLogs()" style="margin-top:8px;background:#333">重新整理</button>
    </div>

    <!-- 記憶庫 -->
    <div class="card">
      <h2>記憶庫</h2>
      <input id="mem-search" placeholder="搜尋記憶..." style="width:100%;background:#111;border:1px solid #2a2d3a;border-radius:6px;color:#e0e0e0;padding:6px 10px;font-size:.83rem;margin-bottom:8px">
      <div id="memory-box">載入中...</div>
    </div>

  </div>

<script>
const startedAt = new Date("{{ started_at }}");

function updateUptime(){
  const s = Math.floor((Date.now() - startedAt)/1000);
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
  document.getElementById('uptime').textContent =
    (h?h+'h ':'')+m+'m '+sec+'s';
}

async function refreshState(){
  const r = await fetch('/api/state');
  const d = await r.json();
  const badge = document.getElementById('status-badge');
  badge.textContent = d.status;
  badge.className = 'status ' + d.status;
  document.getElementById('last-task').textContent = d.last_task || '（無）';
  document.getElementById('mem-count').textContent = d.memory_count ?? '-';
}

async function refreshLogs(){
  const r = await fetch('/api/logs');
  const d = await r.json();
  const box = document.getElementById('log-box');
  box.innerHTML = d.lines.map(l=>`<div>${escHtml(l)}</div>`).join('');
  box.scrollTop = box.scrollHeight;
}

async function refreshMemory(query=''){
  const url = query ? `/api/memory?q=${encodeURIComponent(query)}` : '/api/memory';
  const r = await fetch(url);
  const d = await r.json();
  const box = document.getElementById('memory-box');
  if(!d.items.length){box.innerHTML='<div style="color:#555;font-size:.82rem">（無記憶）</div>';return;}
  box.innerHTML = d.items.map(m=>`
    <div class="mem-item">
      <span style="color:#ccc">${escHtml(m.content.slice(0,80))}${m.content.length>80?'...':''}</span>
      <span class="imp">${'★'.repeat(Math.min(m.importance,5))}</span>
      <br>${(m.tags||[]).map(t=>`<span class="mem-tag">${escHtml(t)}</span>`).join('')}
    </div>`).join('');
}

async function sendCommand(){
  const cmd = document.getElementById('cmd-input').value.trim();
  if(!cmd) return;
  document.getElementById('cmd-result').textContent = '處理中...';
  const r = await fetch('/api/command', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({command: cmd})
  });
  const d = await r.json();
  document.getElementById('cmd-result').textContent = d.result || '（無回應）';
}

function escHtml(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// 搜尋記憶
document.addEventListener('DOMContentLoaded', ()=>{
  document.getElementById('mem-search').addEventListener('input', e=>{
    refreshMemory(e.target.value);
  });
});

// 自動刷新
refreshState(); refreshLogs(); refreshMemory();
setInterval(()=>{ refreshState(); refreshLogs(); updateUptime(); }, 3000);
setInterval(updateUptime, 1000);
</script>
</body>
</html>
"""

# ── API 路由 ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML, started_at=_state["started_at"])

@app.route("/api/state")
def api_state():
    with _state_lock:
        return jsonify({
            **_state,
            "memory_count": len(_memory._memories) if _memory else 0,
        })

@app.route("/api/logs")
def api_logs():
    """讀取最新日誌（最後 100 行）"""
    log_dir = pathlib.Path("logs")
    lines = []
    if log_dir.exists():
        today = datetime.datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"agent_{today}.log"
        if log_file.exists():
            all_lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            lines = all_lines[-100:]
    if not lines:
        lines = ["（尚無日誌，請先啟動 Agent）"]
    return jsonify({"lines": lines})

@app.route("/api/memory")
def api_memory():
    """搜尋或列出記憶"""
    if _memory is None:
        return jsonify({"items": []})
    q = request.args.get("q", "").strip()
    if q:
        items = _memory.search(q, top_k=20)
    else:
        items = sorted(_memory._memories, key=lambda m: m["accessed_at"], reverse=True)[:30]
    return jsonify({"items": items})

@app.route("/api/command", methods=["POST"])
def api_command():
    """接收前端指令，加入佇列並嘗試即時處理"""
    data = request.get_json(silent=True) or {}
    cmd = str(data.get("command", "")).strip()
    if not cmd:
        return jsonify({"result": "指令不能為空"})

    logger.info(f"[Dashboard] 收到指令：{cmd}")
    _command_queue.append(cmd)

    with _state_lock:
        _state["last_task"] = cmd
        _state["status"] = "running"

    # 嘗試呼叫 Lobster_Core
    result = _try_run_command(cmd)

    with _state_lock:
        _state["status"] = "idle"
        _state["last_result"] = result

    return jsonify({"result": result})

def _try_run_command(cmd: str) -> str:
    """嘗試用 Lobster_Core 執行指令，如果沒有就回傳提示"""
    try:
        from Lobster_Core import LobsterCore
        core = LobsterCore()
        return core.run(cmd)
    except ImportError:
        pass
    except Exception as e:
        return f"[錯誤] {e}"

    # 內建簡易指令
    if cmd.startswith("搜尋記憶：") or cmd.startswith("search:"):
        q = cmd.split("：", 1)[-1].split(":", 1)[-1].strip()
        if _memory:
            results = _memory.search(q)
            if results:
                return "\n".join(f"• {r['content'][:80]}" for r in results)
            return "找不到相關記憶"
        return "記憶系統未啟動"

    if cmd.startswith("記住：") or cmd.startswith("remember:"):
        content = cmd.split("：", 1)[-1].split(":", 1)[-1].strip()
        if _memory:
            _memory.store(content, tags=["manual"], importance=7)
            return f"已記住：{content}"
        return "記憶系統未啟動"

    return f"指令已加入佇列，等待 Agent 處理：{cmd}"


# ── 啟動 ────────────────────────────────────────────────────────────────────

def run_dashboard(host: str = "0.0.0.0", port: int = 7860, debug: bool = False):
    """啟動 Dashboard（可從 core_boot.py 呼叫）"""
    logger.info(f"Dashboard 啟動於 http://localhost:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)

if __name__ == "__main__":
    print("🦞 Lobster Core Dashboard 啟動中...")
    print("   瀏覽器打開 http://localhost:7860")
    run_dashboard(debug=False)

