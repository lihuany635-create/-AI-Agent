# lobster_workflow.py — 立 AI 工作流程引擎（含 AI 設定編輯）
# 安裝：pip install fastapi uvicorn requests
# 啟動：python lobster_workflow.py
# 開啟：http://localhost:9998

import sys, json, datetime, uuid, requests, threading, ast, shutil, re
_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

import pathlib
LOBSTER_DIR = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面")
BACKUP_DIR = LOBSTER_DIR / "_backups"
BACKUP_DIR.mkdir(exist_ok=True)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="立 AI 工作流程引擎")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FLOW_DIR = pathlib.Path("workflows")
FLOW_DIR.mkdir(exist_ok=True)

def save_flow(flow_id, data):
    (FLOW_DIR / f"{flow_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_flow(flow_id):
    p = FLOW_DIR / f"{flow_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def list_flows():
    return [{"id": p.stem, "name": json.loads(p.read_text(encoding="utf-8")).get("name","未命名")} for p in FLOW_DIR.glob("*.json")]

def get_models():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except:
        return []

def ollama_chat(model, prompt, system=""):
    try:
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=120)
        return r.json().get("response", "無回應")
    except Exception as e:
        return f"❌ Ollama 錯誤：{e}"

def backup_file(filepath):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{filepath.stem}_{ts}{filepath.suffix}"
    shutil.copy2(filepath, dest)
    return str(dest)

# ── 檔案 API ──────────────────────────────────────────────────────────────────
@app.get("/api/files")
def api_list_files():
    try:
        files = []
        for p in sorted(LOBSTER_DIR.glob("*.py")):
            s = p.stat()
            files.append({
                "name": p.name,
                "size_str": f"{s.st_size/1024:.1f} KB",
                "modified": datetime.datetime.fromtimestamp(s.st_mtime).strftime("%m/%d %H:%M")
            })
        return {"files": files, "dir": str(LOBSTER_DIR)}
    except Exception as e:
        return {"files": [], "error": str(e)}

@app.get("/api/files/{filename}")
def api_read_file(filename: str):
    try:
        p = LOBSTER_DIR / filename
        if not p.exists():
            return {"ok": False, "error": "檔案不存在"}
        return {"ok": True, "content": p.read_text(encoding="utf-8-sig"), "filename": filename}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/files/{filename}")
def api_write_file(filename: str, body: dict):
    try:
        content = body.get("content", "")
        p = LOBSTER_DIR / filename
        try:
            ast.parse(content)
        except SyntaxError as e:
            return {"ok": False, "error": f"語法錯誤：第 {e.lineno} 行 — {e.msg}"}
        backup_path = backup_file(p) if p.exists() else ""
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "backup": backup_path}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Lobster 設定 API ──────────────────────────────────────────────────────────
_cfg = {"model": "gemma4:latest", "system_prompt": "你是立 AI，一個有用的繁體中文 AI 助理。"}

@app.get("/api/lobster/config")
def api_get_config():
    try:
        core = (LOBSTER_DIR / "Lobster_Core.py").read_text(encoding="utf-8-sig")
        m = re.search(r'model\s*=\s*["\']([^"\']+)["\']', core)
        if m: _cfg["model"] = m.group(1)
    except: pass
    try:
        cfg_file = LOBSTER_DIR / "lobster_config.json"
        if cfg_file.exists():
            saved = json.loads(cfg_file.read_text(encoding="utf-8"))
            _cfg["system_prompt"] = saved.get("system_prompt", _cfg["system_prompt"])
    except: pass
    return _cfg

@app.post("/api/lobster/config")
def api_set_config(body: dict):
    try:
        if "model" in body:
            _cfg["model"] = body["model"]
            p = LOBSTER_DIR / "Lobster_Core.py"
            if p.exists():
                backup_file(p)
                content = p.read_text(encoding="utf-8-sig")
                content = re.sub(
                    r'(def __init__\(self,\s*model\s*=\s*)["\'][^"\']+["\']',
                    f'\\g<1>"{body["model"]}"', content
                )
                p.write_text(content, encoding="utf-8")
        if "system_prompt" in body:
            _cfg["system_prompt"] = body["system_prompt"]
            cfg_file = LOBSTER_DIR / "lobster_config.json"
            existing = {}
            if cfg_file.exists():
                try: existing = json.loads(cfg_file.read_text(encoding="utf-8"))
                except: pass
            existing["system_prompt"] = body["system_prompt"]
            cfg_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── 流程執行 ──────────────────────────────────────────────────────────────────
class FlowExecutor:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, node_id, status, output=""):
        await self.ws.send_json({"type":"node_update","node_id":node_id,"status":status,"output":output,"time":datetime.datetime.now().strftime("%H:%M:%S")})

    async def execute(self, flow, user_input=""):
        nodes = {n["id"]: n for n in flow.get("nodes", [])}
        edges = flow.get("edges", [])
        in_degree = {nid: 0 for nid in nodes}
        children = {nid: [] for nid in nodes}
        for e in edges:
            children[e["from"]].append(e["to"])
            in_degree[e["to"]] += 1
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        outputs = {}
        await self.ws.send_json({"type":"flow_start","message":"🚀 流程開始執行"})
        while queue:
            nid = queue.pop(0)
            node = nodes[nid]
            await self.send(nid, "running")
            try:
                out = await self._run_node(node, outputs, user_input)
                outputs[nid] = out
                await self.send(nid, "done", out[:300])
            except Exception as e:
                await self.send(nid, "error", str(e))
                outputs[nid] = f"❌ {e}"
            for child in children[nid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        final = [nid for nid in nodes if not children[nid]]
        final_out = outputs.get(final[0], "完成") if final else "完成"
        await self.ws.send_json({"type":"flow_done","output":final_out,"message":"✅ 完成"})

    async def _run_node(self, node, outputs, user_input):
        ntype = node.get("type","llm")
        cfg = node.get("config",{})
        upstream = "\n".join(outputs.values()) if outputs else ""
        if ntype == "input": return user_input or cfg.get("default","")
        elif ntype == "llm":
            model = cfg.get("model", _cfg["model"])
            system = cfg.get("system", _cfg["system_prompt"])
            prompt = cfg.get("prompt","{input}").replace("{input}", upstream or user_input)
            return ollama_chat(model, prompt, system)
        elif ntype == "prompt": return cfg.get("template","{input}").replace("{input}", upstream or user_input)
        elif ntype == "condition":
            kw = cfg.get("keyword","")
            return (f"✅ 條件成立（{kw}）\n{upstream}" if kw.lower() in upstream.lower() else f"❌ 條件不成立（{kw}）\n{upstream}")
        elif ntype == "output": return upstream or "（無輸出）"
        return f"未知節點：{ntype}"

@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            if data.get("action") == "run_flow":
                await FlowExecutor(ws).execute(data.get("flow",{}), data.get("input",""))
    except WebSocketDisconnect:
        pass

@app.get("/api/models")
def api_models():
    return {"models": get_models(), "current": _cfg["model"]}

@app.get("/api/flows")
def api_list_flows():
    return {"flows": list_flows()}

@app.post("/api/flows/{flow_id}")
def api_save_flow(flow_id: str, body: dict):
    save_flow(flow_id, body); return {"ok": True}

@app.get("/api/flows/{flow_id}")
def api_load_flow(flow_id: str):
    return load_flow(flow_id)

@app.delete("/api/flows/{flow_id}")
def api_delete_flow(flow_id: str):
    p = FLOW_DIR / f"{flow_id}.json"
    if p.exists(): p.unlink()
    return {"ok": True}

@app.get("/api/status")
def api_status():
    return {"ollama": len(get_models()) > 0, "model": _cfg["model"], "time": datetime.datetime.now().strftime("%H:%M:%S")}

@app.get("/", response_class=HTMLResponse)
def root():
    ui = pathlib.Path("lobster_workflow_ui.html")
    return ui.read_text(encoding="utf-8") if ui.exists() else "<h1>請放置 lobster_workflow_ui.html</h1>"

if __name__ == "__main__":
    print("🦞 立 AI 工作流程引擎")
    print(f"   Lobster 路徑：{LOBSTER_DIR}")
    print(f"   備份路徑：{BACKUP_DIR}")
    print("   開啟：http://localhost:9998")
    uvicorn.run(app, host="0.0.0.0", port=9998)
