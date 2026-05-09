# floating_ball.py — 立 AI 浮動啟動球（行星軌道版）
# 點大圓 → 小圓沿軌道旋轉展開
# 再點大圓 → 小圓收回
# 使用：python floating_ball.py

import sys, math, subprocess, webbrowser, socket, threading, time, pathlib, json

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QHBoxLayout, QFrame,
    QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont,
    QRadialGradient, QCursor
)

BASE_DIR  = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面\AI-Agent")
BALL_SIZE = 68
ORBT_R    = 110
MINI_SIZE = 48

ACTIONS = [
    ("📚", "知識庫",   "#7eb8f7"),   # 點了展開子圓
    ("🦞", "問立AI",  "#e8c547"),
    ("🤖", "雙AI對話","#c084fc"),
    ("⌨️", "終端機",  "#86efac"),
    ("🖥", "主視窗",  "#f9a8d4"),
    ("🪄", "圓圓",    "#f472b6"),   # VMagicMirror
    ("⚙", "工坊",    "#fb923c"),   # workshop_ui
    ("🎨", "圖片",    "#e879f9"),   # ComfyUI
    ("🎬", "Filmora", "#f87171"),   # Filmora
    ("🧠", "Hermes",  "#a78bfa"),   # Hermes Agent (WSL)
]

VMAGIC_PATH   = r"C:\Program Files (x86)\VMagicMirror\VMagicMirror.exe"
FILMORA_PATH  = r"C:\Users\ACER\AppData\Local\Wondershare\Wondershare Filmora（繁體中文）\Wondershare Filmora Launcher.exe"

# 知識庫子選單（點擊後展開的子圓）
SUB_ACTIONS = [
    ("🏛", "圖書館",     "#7eb8f7"),
    ("📐", "程式碼", "#60a5fa"),
]

# ── 問立AI 工作執行緒 ─────────────────────────────────────────────────────────

OLLAMA_URL   = "http://localhost:11434/api/chat"

# ── 桌面控制 Server ───────────────────────────────────────────────────────────
DESKTOP_API_URL = "http://172.23.48.1:7864"

def _desktop_api(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    import requests as _req_dc
    try:
        if method == "GET":
            r = _req_dc.get(f"{DESKTOP_API_URL}/{endpoint}", timeout=10)
        else:
            r = _req_dc.post(f"{DESKTOP_API_URL}/{endpoint}", json=data or {}, timeout=10)
        return r.json() if r.status_code == 200 else {"ok": False, "error": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _is_desktop_running() -> bool:
    import requests as _req_dc
    try:
        return _req_dc.get(f"{DESKTOP_API_URL}/health", timeout=3).status_code == 200
    except Exception:
        return False

# ── 記憶系統 ──────────────────────────────────────────────────────────────────
try:
    import sys as _sys_mem
    _sys_mem.path.insert(0, str(BASE_DIR))
    from ai_memory import (build_memory_prompt, update_memory_from_conversation,
                        save_conversation, load_recent_conversations)
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False
    def build_memory_prompt(): return ""
    def update_memory_from_conversation(conv, url, model): pass
    def save_conversation(u, r): pass
    def load_recent_conversations(max_turns=10): return []

_conversation_history: list = []
_MAX_HISTORY = 10

# 啟動時載入最近的對話紀錄
try:
    if _HAS_MEMORY:
        _conversation_history = load_recent_conversations(max_turns=_MAX_HISTORY)
except Exception:
    pass
OLLAMA_MODEL = "gpt-oss:20b"
BASE_DIR     = pathlib.Path(__file__).parent
ASSEMBLED_DIR = BASE_DIR / "workshop_data" / "assembled"
SKILLS_DIR    = BASE_DIR / "workshop_data" / "skills"

# ── 技能快取 ──────────────────────────────────────────────────────────────────
_skills_cache: list = []
_skills_cache_mtime: float = 0.0

def _load_skills() -> list[dict]:
    """載入所有技能描述 JSON，使用快取，只有檔案變動才重新載入。"""
    global _skills_cache, _skills_cache_mtime

    # 取得最新修改時間
    latest_mtime = 0.0
    if SKILLS_DIR.exists():
        for f in SKILLS_DIR.glob("*.json"):
            latest_mtime = max(latest_mtime, f.stat().st_mtime)
    if ASSEMBLED_DIR.exists():
        for f in ASSEMBLED_DIR.glob("*.py"):
            latest_mtime = max(latest_mtime, f.stat().st_mtime)

    # 沒有變動 → 直接回傳快取
    if _skills_cache and latest_mtime <= _skills_cache_mtime:
        return _skills_cache

    skills = []

    # 檢查是否有器官沒有對應的 .json 描述
    if ASSEMBLED_DIR.exists() and SKILLS_DIR.exists():
        organ_names = {f.stem for f in ASSEMBLED_DIR.glob("*.py")}
        skill_names = {f.stem for f in SKILLS_DIR.glob("*.json")}
        missing = organ_names - skill_names
        if missing:
            try:
                import sys as _sys
                _sys.path.insert(0, str(BASE_DIR))
                from organ_skill_system import generate_skill_json, _ai_describe_skill
                import json as _json
                SKILLS_DIR.mkdir(parents=True, exist_ok=True)
                for stem in missing:
                    py_path = ASSEMBLED_DIR / f"{stem}.py"
                    if not py_path.exists():
                        continue
                    basic = generate_skill_json(py_path)
                    skill = _ai_describe_skill(py_path, basic)  # AI 產生中文描述
                    json_path = SKILLS_DIR / f"{stem}.json"
                    json_path.write_text(
                        _json.dumps(skill, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
            except Exception:
                pass

    if not SKILLS_DIR.exists():
        return skills
    for f in SKILLS_DIR.glob("*.json"):
        try:
            skills.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass

    # 更新快取
    _skills_cache = skills
    _skills_cache_mtime = latest_mtime
    return skills

def _find_skill(query: str, skills: list[dict]) -> dict | None:
    """用關鍵字找最合適的技能。"""
    q = query.lower()
    for s in skills:
        if q in s.get("name","").lower() or q in s.get("filename","").lower():
            return s
    for s in skills:
        if q in s.get("description","").lower():
            return s
    return None

def _run_skill(skill: dict, args: list = None) -> str:
    """執行器官技能，回傳結果。"""
    import subprocess, sys, os
    path = pathlib.Path(skill.get("path",""))
    if not path.exists():
        path = ASSEMBLED_DIR / skill.get("filename","")
    if not path.exists():
        return f"找不到器官：{skill.get('filename')}"
    try:
        env = os.environ.copy()
        # 把 AI-Agent 資料夾加進 PYTHONPATH，讓器官能 import 系統模組
        env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        cmd = [sys.executable, str(path)] + (args or [])
        r   = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=60, encoding="utf-8", errors="replace",
                             cwd=str(BASE_DIR), env=env)
        out = (r.stdout + r.stderr).strip()
        return out[:600] if out else "（無輸出）"
    except subprocess.TimeoutExpired:
        return "執行超時（60秒）"
    except Exception as e:
        return f"執行錯誤：{e}"

def _run_pipeline(steps: list, initial_input: str = "") -> str:
    """串聯執行多個器官，回傳結果。"""
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR))
        from organ_pipeline import run_pipeline
        result = run_pipeline(steps, initial_input)
        if result["success"]:
            return "✅ 管道執行成功\n最終輸出：" + result["final_output"][:400]
        failed = [s for s in result["steps"] if not s.get("success")]
        organ  = failed[0]["organ"] if failed else "未知"
        err    = failed[0]["error"][:200] if failed else ""
        return "❌ 管道執行失敗\n失敗步驟：" + organ + "\n原因：" + err
    except Exception as e:
        return "管道執行錯誤：" + str(e)

def _skills_summary(skills: list[dict]) -> str:
    if not skills:
        return "（器官庫是空的）"
    return "\n".join(
        f"🔩 {s['name']}：{s.get('description','')[:40]}"
        for s in skills
    )

class AskWorker(QThread):
    result = pyqtSignal(str)

    def __init__(self, msg):
        super().__init__()
        self.msg = msg

    def _filmora_action(self, msg: str, _req) -> str:
        """解析 Filmora 指令並執行，回傳結果說明。"""
        import json, re, subprocess, sys, pathlib

        BASE = pathlib.Path(__file__).parent
        agent_path = BASE / "filmora_agent.py"

        if not agent_path.exists():
            return f"找不到 filmora_agent.py，請確認它在 {BASE}"

        system = """你是 Filmora 影片編輯控制器。
分析用戶指令，回傳 JSON 操作列表。

可用操作：
- new_project / save / play_pause / split / delete_selected
- import_media: {path}
- seek: {seconds}
- cut_segment: {start, end}（秒）
- export: {output_path, quality}
- undo: {times}

只回傳 JSON：{"actions": [{"action": "...", "params": {}}], "summary": "一句話說明"}"""

        try:
            r = _req.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": msg},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 300},
            }, timeout=None)
            raw = r.json().get("message", {}).get("content", "").strip()
            import re as _re2
            raw = _re2.sub(r"^```[a-z]*\n?", "", raw)
            raw = _re2.sub(r"\n?```$", "", raw).strip()
            # 找 JSON 部分
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start == -1:
                return "無法解析 Filmora 指令，請更具體描述（例如：剪掉第 3 到 8 秒）"
            plan = json.loads(raw[start:end])
        except Exception as e:
            return "無法解析 Filmora 指令，請更具體描述（例如：剪掉第 3 到 8 秒）"

        actions = plan.get("actions", [])
        summary = plan.get("summary", "執行 Filmora 操作")

        if not actions:
            return "無法識別 Filmora 操作，請更具體描述（例如：剪掉第 3 到 8 秒）"

        action_script = f"""
import sys
sys.path.insert(0, r'{BASE}')
from filmora_agent import *
import time
actions = {json.dumps(actions)}
for act in actions:
    action = act.get('action','')
    params = act.get('params',{{}})
    if action == 'new_project':       new_project()
    elif action == 'import_media':    import_media(params.get('path',''))
    elif action == 'save':            save_project()
    elif action == 'play_pause':      play_pause()
    elif action == 'seek':            seek_to(float(params.get('seconds',0)))
    elif action == 'split':           split_clip()
    elif action == 'cut_segment':     cut_segment(float(params.get('start',0)), float(params.get('end',0)))
    elif action == 'delete_selected': delete_selected()
    elif action == 'export':          export_video(params.get('output_path',''), params.get('quality','1080p'))
    elif action == 'undo':            undo(int(params.get('times',1)))
    time.sleep(0.5)
print('DONE')
"""
        result = subprocess.run(
            [sys.executable, "-c", action_script],
            capture_output=True, text=True, timeout=30
        )

        if "DONE" in result.stdout:
            steps = "、".join(a.get("action","") for a in actions)
            return f"✅ {summary}\n（執行了：{steps}）"
        else:
            err = (result.stderr or "未知錯誤").strip()[:200]
            return f"⚠ 執行失敗：{err}"

    def run(self):
        global _conversation_history
        try:
            reply = self._process(self.msg)
            self.result.emit(reply)
            _conversation_history.append({"role": "user",      "content": self.msg})
            _conversation_history.append({"role": "assistant", "content": reply})
            _conversation_history = _conversation_history[-_MAX_HISTORY*2:]
            if _HAS_MEMORY:
                # 存入對話紀錄檔
                save_conversation(self.msg, reply)
                # 背景更新長期記憶
                import threading as _th2
                _th2.Thread(
                    target=update_memory_from_conversation,
                    args=(_conversation_history[:],
                          "http://localhost:11434", OLLAMA_MODEL),
                    daemon=True
                ).start()
        except Exception as e:
            self.result.emit(f"錯誤：{e}")

    def _process(self, msg: str) -> str:
        import requests as _req, re as _re
        skills = _load_skills()

        # ── 特殊指令 ──────────────────────────────────────────────────────────
        msg_lower = msg.lower().strip()

        # ── 桌面控制（透過 desktop_control_server）────────────────────────────
        dc_kws = ["截圖", "點擊", "按鍵", "輸入文字", "視窗列表", "辨識螢幕"]
        if any(kw in msg for kw in dc_kws):
            if not _is_desktop_running():
                return "❌ 桌面控制 Server 未啟動，請先在 Windows 執行 desktop_control_server.py"
            if "截圖" in msg:
                r = _desktop_api("screenshot")
                return f"✅ 截圖：{r.get('path','')}" if r.get("ok") else f"❌ {r.get('error','')}"
            if "辨識螢幕" in msg:
                r = _desktop_api("ocr")
                return f"📖 螢幕文字：\n{r.get('text','（無）')}"
            if "視窗列表" in msg:
                r = _desktop_api("windows")
                return "🪟 視窗：\n" + "\n".join(str(w) for w in r.get("windows", [])[:10])
            if "點擊" in msg:
                nums = _re.findall(r"\d+", msg)
                quoted = msg.split("300c")[1].split("300d")[0:1] if "300c" in msg else []
                if len(nums) >= 2:
                    r = _desktop_api("click", "POST", {"x": int(nums[0]), "y": int(nums[1])})
                elif quoted:
                    r = _desktop_api("click", "POST", {"text": quoted[0]})
                else:
                    return "請指定座標或文字，例如：點擊「確定」或點擊 100 200"
                return "✅ 點擊完成" if r.get("ok") else f"❌ {r.get('error','')}"
            if "輸入文字" in msg:
                quoted = msg.split("300c")[1].split("300d")[0:1] if "300c" in msg else []
                text = quoted[0] if quoted else msg.replace("輸入文字", "").strip()
                r = _desktop_api("type", "POST", {"text": text})
                return f"✅ 輸入：{text}" if r.get("ok") else f"❌ {r.get('error','')}"
            if "按鍵" in msg:
                quoted = msg.split("300c")[1].split("300d")[0:1] if "300c" in msg else []
                key = quoted[0] if quoted else msg.replace("按鍵", "").strip()
                r = _desktop_api("key", "POST", {"key": key})
                return f"✅ 按鍵：{key}" if r.get("ok") else f"❌ {r.get('error','')}"

        # ── Filmora 控制指令偵測 ───────────────────────────────────────────────
        filmora_kws = [
            "剪掉","剪輯","裁切","分割","split","cut","trim",
            "匯入","import","素材","影片","media",
            "匯出","export","輸出","render",
            "filmora","時間軸","timeline",
            "跳到","播放","暫停","play","pause","seek",
            "加字幕","字幕","subtitle","caption",
            "加音樂","背景音樂","bgm",
            "還原","undo","重做","redo",
        ]
        if any(kw in msg_lower for kw in filmora_kws):
            return self._filmora_action(msg, _req)

        # 列出技能
        if any(kw in msg_lower for kw in ["有哪些技能","有什麼技能","器官庫","技能列表","有哪些器官"]):
            return f"📦 目前的技能：\n{_skills_summary(skills)}"

        # 執行技能
        run_kws = ["執行","啟動","跑","運行","使用","run"]
        if any(kw in msg_lower for kw in run_kws):
            # 偵測「串聯」需求（提到兩個以上器官或「然後」「接著」「再」）
            pipe_kws = ["然後","接著","再","串聯","依序","pipeline","管道"]
            organ_mentions = [s for s in skills if s.get("name","").lower() in msg_lower]
            if len(organ_mentions) >= 2 or any(kw in msg_lower for kw in pipe_kws):
                # 串聯模式：讓 AI 規劃管道
                pipe_prompt = (
                    "根據需求，從器官庫選出要串聯的器官順序，輸出 JSON：\n"
                    + '[{"organ":"器官名稱","args":[]},{"organ":"器官名稱2","args":["{{prev}}"]}]\n\n'
                    + "需求：" + msg + "\n\n"
                    + "器官庫：\n" + "\n".join(s.get("name","") for s in skills)
                )
                import requests as _req2, json as _json2
                r = _req2.post(OLLAMA_URL, json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": "只輸出 JSON 陣列，第一個字是 ["},
                        {"role": "user",   "content": pipe_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 300},
                }, timeout=None)
                raw = r.json().get("message", {}).get("content", "").strip()
                import re as _re3
                raw = _re3.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
                start, end = raw.find("["), raw.rfind("]") + 1
                if start != -1:
                    steps = _json2.loads(raw[start:end])
                    out = _run_pipeline(steps)
                    return out

            skill = _find_skill(msg, skills)
            if skill:
                if skill.get("needs_args"):
                    return ("🔩 找到技能：" + skill["name"] + "\n"
                            "說明：" + skill.get("description","") + "\n"
                            "這個技能需要參數，請告訴我要傳什麼？")
                out = _run_skill(skill)
                return "✅ 執行 " + skill["name"] + "：\n" + out

        # ── 任務規劃器：分析需求需要哪些器官 ────────────────────────────────
        skills_summary = _skills_summary(skills)
        plan_system = f"""你是 AI 任務規劃師。分析使用者需求，決定需要哪些器官（技能模組）。

現有器官：
{skills_summary if skills_summary != '（器官庫是空的）' else '（無）'}

輸出嚴格 JSON（不要其他文字）：
{{
  "needs_organs": true或false,
  "analysis": "一句話說明需要什麼",
  "required_organs": [
    {{"name": "器官名稱", "description": "這個器官要做什麼", "exists": true或false, "depends_on": []}}
  ],
  "can_answer_directly": true或false,
  "direct_answer": "如果不需要器官，直接回答"
}}

判斷原則：
- 簡單問答（天氣、計算、解釋）→ can_answer_directly: true
- 需要執行程式功能（鬧鐘、截圖、備份）→ needs_organs: true
- exists: true 代表現有器官已能滿足，false 代表需要製作"""

        try:
            # 帶入對話歷史讓規劃器有上下文
            plan_msgs = [{"role": "system", "content": plan_system}]
            for h in _conversation_history[-6:]:
                plan_msgs.append(h)
            plan_msgs.append({"role": "user", "content": msg})
            r = _req.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "messages": plan_msgs,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 600},
            }, timeout=None)
            raw = r.json().get("message", {}).get("content", "").strip()

            import json as _json, re as _re
            raw = _re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            start, end = raw.find("{"), raw.rfind("}") + 1
            plan = _json.loads(raw[start:end]) if start != -1 else {}
        except Exception as e:
            plan = {}

        # ── 直接回答 ──────────────────────────────────────────────────────────
        if plan.get("can_answer_directly") and not plan.get("needs_organs"):
            direct = plan.get("direct_answer", "")
            if direct:
                return direct
            # fallback 到一般 Ollama 回答
            sys_msg = "你是「立」，顏立桓的AI助理，用繁體中文回答，最多5句。"
            hist2 = [{"role": "system", "content": sys_msg}]
            for h in _conversation_history[-6:]:
                hist2.append(h)
            hist2.append({"role": "user", "content": msg})
            r2 = _req.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "messages": hist2,
                "stream": False,
                "options": {"temperature": 0.5, "num_predict": 300},
            }, timeout=None)
            return r2.json().get("message", {}).get("content", "(無回應)").strip()

        # ── 需要器官 ──────────────────────────────────────────────────────────
        required = plan.get("required_organs", [])
        if not required:
            # 規劃失敗，直接回答
            skill_ctx = ("\n\n可用技能：\n" + skills_summary) if skills else ""
            _mem = build_memory_prompt() if _HAS_MEMORY else ""
            sys_msg = "你是「立」，顏立桓的AI助理，用繁體中文回答，最多5句。" + skill_ctx + (("\n\n" + _mem) if _mem else "")
            hist3 = [{"role": "system", "content": sys_msg}]
            for h in _conversation_history[-6:]:
                hist3.append(h)
            hist3.append({"role": "user", "content": msg})
            r3 = _req.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "messages": hist3,
                "stream": False,
                "options": {"temperature": 0.5, "num_predict": 300},
            }, timeout=None)
            return r3.json().get("message", {}).get("content", "(無回應)").strip()

        # 分類：已有 vs 需要製作
        existing  = [o for o in required if o.get("exists")]
        missing   = [o for o in required if not o.get("exists")]

        # 已有的可以直接用
        if existing and not missing:
            skill = _find_skill(required[0]["name"], skills)
            if skill:
                out = _run_skill(skill)
                return f"✅ 使用現有技能「{skill['name']}」：\n{out}"

        # 有缺少的 → 送工坊製作（依依賴順序）
        if missing:
            # 依賴排序：depends_on 為空的先做
            ordered = sorted(missing, key=lambda o: len(o.get("depends_on", [])))

            lines = [f"📋 分析完成，需要製作 {len(ordered)} 個器官："]
            for o in ordered:
                lines.append(f"  🔩 {o['name']}：{o['description']}")

            # 確認工坊在跑，沒開就自動啟動
            import socket as _sk, subprocess as _sp, time as _t, sys as _sys, pathlib as _pl
            with _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM) as _s:
                ws_on = _s.connect_ex(('localhost', 7862)) == 0

            if not ws_on:
                # 工坊沒在跑，用 powershell 開新終端視窗（和手動點相同方式）
                _ws_path = _pl.Path(__file__).parent / "workshop_ui.py"
                if not _ws_path.exists():
                    _ws_path = BASE_DIR / "workshop_ui.py"
                if not _ws_path.exists():
                    lines.append("\n⚠ 找不到 workshop_ui.py，請手動開啟工坊")
                    return "\n".join(lines)
                lines.append("\n🔄 工坊未啟動，自動啟動中...")
                # 寫一個暫時的 .bat 啟動工坊，避免路徑中文/空格引號問題
                _bat_path = _ws_path.parent / "_start_workshop_tmp.bat"
                _bat_path.write_text(
                    f"@echo off\ncd /d \"{_ws_path.parent}\"\npython \"{_ws_path}\"\npause\n",
                    encoding="cp950", errors="replace"
                )
                _sp.Popen(
                    ["cmd", "/c", "start", "", str(_bat_path)],
                    cwd=str(_ws_path.parent),
                    creationflags=_sp.CREATE_NO_WINDOW,
                )
                # 等 /health 回應才算真的 ready
                import urllib.request as _ur, webbrowser as _wb
                for _ in range(40):
                    _t.sleep(1)
                    try:
                        _ur.urlopen("http://localhost:7862/health", timeout=2)
                        ws_on = True
                        _wb.open("http://localhost:7862")
                        break
                    except Exception:
                        pass
                if not ws_on:
                    lines.append("\n⚠ 工坊啟動失敗，請手動點漂浮球的「⚙ 工坊」開啟")
                    return "\n".join(lines)

            # 送工坊依序製作
            lines.append("\n🏭 開始依序製作...")
            results = []
            for o in ordered:
                dep_str = ""
                if o.get("depends_on"):
                    dep_str = f"（依賴：{', '.join(o['depends_on'])}）"
                try:
                    r_ws = _req.post("http://localhost:7862/api/auto_create", json={
                        "name":         o["name"],
                        "requirement":  o["description"],
                        "callback_url": "http://localhost:7861/api/workshop_callback",
                    }, timeout=30)
                    d = r_ws.json()
                    if d.get("ok"):
                        results.append(f"  ✅ 已送出：{o['name']}{dep_str}")
                    else:
                        results.append(f"  ❌ 失敗：{o['name']} — {d.get('error','')}")
                except Exception as e:
                    results.append(f"  ❌ 連線失敗：{o['name']} — {e}")

            lines.extend(results)
            lines.append(f"\n⏳ 工坊製作中，完成後會自動通知你。")
            lines.append(f"原始需求「{msg}」將在器官就緒後執行。")
            return "\n".join(lines)

# ── 問立AI 對話框 ─────────────────────────────────────────────────────────────

class AskDialog(QWidget):
    _reply_signal = pyqtSignal(str)
    def __init__(self):
        super().__init__(None,
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("問立 AI")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 讓視窗在工作列顯示
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.Tool)
        self._worker = None
        self._build()

    def _build(self):
        self.setMinimumWidth(300)
        self.resize(360, 400)  # 預設大小，可拖動調整
        # 右下角大小調整手柄
        from PyQt6.QtWidgets import QSizeGrip
        self._grip = QSizeGrip(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        card = QFrame()
        card.setStyleSheet("QFrame{background:#16161a;border:1px solid #2a2a32;border-radius:14px;}")
        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(28); sh.setColor(QColor(0,0,0,180)); sh.setOffset(0,4)
        card.setGraphicsEffect(sh)
        v = QVBoxLayout(card); v.setContentsMargins(14,12,14,12); v.setSpacing(8)
        h = QHBoxLayout()
        t = QLabel("🦞 問立 AI")
        t.setStyleSheet("color:#e8c547;font-size:13px;font-weight:700;font-family:'Microsoft JhengHei UI';")
        h.addWidget(t); h.addStretch()
        # 收起按鈕（暫時隱藏，保留內容）
        self._min_btn = QPushButton("−"); self._min_btn.setFixedSize(22,22)
        self._min_btn.setStyleSheet("background:none;border:none;color:#888;font-size:15px;font-weight:700;")
        self._min_btn.clicked.connect(self.showMinimized)
        h.addWidget(self._min_btn)
        # 關閉按鈕（隱藏並清空內容）
        cb = QPushButton("✕"); cb.setFixedSize(22,22)
        cb.setStyleSheet("background:none;border:none;color:#555;font-size:13px;")
        cb.clicked.connect(self._close_clear)
        h.addWidget(cb); v.addLayout(h)

        # 可收起的內容區
        self._content = QWidget()
        cv = QVBoxLayout(self._content); cv.setContentsMargins(0,0,0,0); cv.setSpacing(8)

        self.inp = QLineEdit()
        self.inp.setPlaceholderText("輸入問題...")
        self.inp.setStyleSheet("""
            QLineEdit{background:#0e0e0f;border:1px solid #2a2a32;border-radius:8px;
                      padding:8px 12px;color:#e8e6e0;font-size:13px;
                      font-family:'Microsoft JhengHei UI';}
            QLineEdit:focus{border-color:#e8c547;}
        """)
        self.inp.returnPressed.connect(self._ask); cv.addWidget(self.inp)
        self._sb = QPushButton("送出")
        sb = self._sb
        sb.setStyleSheet("""
            QPushButton{background:#e8c547;color:#0e0e0f;border:none;border-radius:8px;
                        padding:8px;font-weight:700;font-family:'Microsoft JhengHei UI';}
            QPushButton:hover{background:#f0d060;}
        """)
        sb.clicked.connect(self._ask); cv.addWidget(sb)
        from PyQt6.QtWidgets import QTextEdit
        self.ans = QTextEdit()
        self.ans.setReadOnly(True)
        self.ans.setPlainText("...")
        self.ans.setStyleSheet("""
            QTextEdit{
                color:#e8e6e0;font-size:12px;font-family:'Microsoft JhengHei UI';
                background:#0e0e0f;border-radius:8px;padding:10px;
                border:none;
            }
        """)
        self.ans.setMinimumHeight(80)
        cv.addWidget(self.ans)
        v.addWidget(self._content)
        outer.addWidget(card)

    def _close_clear(self):
        """關閉並清空內容。"""
        self.inp.clear()
        self.ans.setPlainText("...")
        self.hide()
        self._reply_signal.connect(lambda r: self.ans.setPlainText(r))

    def _ask(self):
        q = self.inp.text().strip()
        if not q: return
        self.inp.clear()

        # 如果是緊急工坊問題的回答
        human_id = getattr(self, "_urgent_human_id", None)
        if human_id:
            self.ans.setPlainText("立AI 正在整理修復方向...")
            self._urgent_human_id = None
            import threading as _th4
            def _send_answer():
                try:
                    import requests as _rq2
                    r = _rq2.post("http://localhost:7861/api/workshop_answer",
                                  json={"human_id": human_id, "answer": q},
                                  timeout=30)
                    data = r.json()
                    hint = data.get("repair_hint", q)
                    # 回到主執行緒更新 UI
                    from PyQt6.QtCore import QMetaObject, Qt
                    self._last_reply = f"✅ 已送出修復方向：\n{hint}\n\n工坊會繼續嘗試修復。"
                    self._reply_signal.emit(self._last_reply)
                    # 停止閃爍
                    ball = self.parent()
                    if ball and hasattr(ball, "_stop_flash"):
                        ball._stop_flash()
                except Exception as e:
                    self._last_reply = f"送出失敗：{e}"
                    from PyQt6.QtCore import QMetaObject, Qt
                    self._reply_signal.emit(self._last_reply)
            _th4.Thread(target=_send_answer, daemon=True).start()
            return

        # 立AI 主動聊天回應
        if getattr(self, "_is_urgent_chat", False):
            self._is_urgent_chat = False
            self.ans.setPlainText("傳送中...")
            import threading as _th5
            def _reply_to_liai():
                try:
                    import requests as _rq3
                    r2 = _rq3.post("http://localhost:7861/api/chat",
                                   json={"message": q}, timeout=60)
                    self._last_reply = r2.json().get("reply", "（無回應）")
                except Exception as e:
                    self._last_reply = f"（連線失敗：{e}）"
                self._reply_signal.emit(self._last_reply)
                try:
                    import requests as _rq4
                    _rq4.post("http://localhost:7861/api/workshop_answer",
                              json={"human_id": "", "answer": q}, timeout=5)
                except Exception:
                    pass
                ball = self.parent()
                if ball:
                    if hasattr(ball, "_stop_flash"):
                        ball._stop_flash()
                    ball._urgent_showing = False
            _th5.Thread(target=_reply_to_liai, daemon=True).start()
            return

        # 一般問題
        self.ans.setPlainText("思考中...")
        self._worker = AskWorker(q)
        self._worker.result.connect(lambda r: self.ans.setPlainText(r))
        self._worker.start()

    def _update_ans_from_thread(self):
        self.ans.setPlainText(getattr(self, "_last_reply", ""))

    @pyqtSlot(str)
    def _update_ans_slot(self, text: str):
        self.ans.setPlainText(text)

    def show_near(self, gpos):
        self.adjustSize()
        sc = QApplication.primaryScreen().availableGeometry()
        x = min(gpos.x() + 80, sc.right() - self.width() - 10)
        y = max(gpos.y() - self.height() - 10, sc.top() + 10)
        self.move(x, y); self.show()
        self.inp.setFocus(); self.inp.clear(); self.ans.setPlainText("...")
        self._urgent_human_id = None

    def show_urgent(self, question: str, human_id: str, context: str):
        self._urgent_human_id = human_id
        self._is_urgent_chat  = (human_id == "")

        # 重新連接送出按鈕
        try: self.inp.returnPressed.disconnect()
        except Exception: pass
        try: self._sb.clicked.disconnect()
        except Exception: pass

        if human_id == "":
            self.ans.setPlainText(question)
            self.inp.setPlaceholderText("回覆立AI...")

            def _send_chat():
                q = self.inp.text().strip()
                if not q: return
                self.inp.clear()
                self.ans.setPlainText("思考中...")
                # 用 AskWorker 一樣的方式，走 knowledge_ui 回應
                import threading as _tc
                def _do():
                    try:
                        import requests as _rc
                        r = _rc.post("http://localhost:7861/api/chat",
                                     json={"message": q}, timeout=None)
                        reply = r.json().get("reply", "（無回應）")
                    except Exception as e:
                        reply = f"連線失敗：{e}"
                    # 清佇列
                    try:
                        import requests as _rc2
                        _rc2.post("http://localhost:7861/api/workshop_answer",
                                  json={"human_id": "", "answer": q}, timeout=5)
                    except Exception: pass
                    # 用 AskWorker 相同的 signal 更新 UI
                    self._worker = None
                    self._reply_signal.emit(reply)
                    ball = self.parent()
                    if ball and hasattr(ball, "_stop_flash"):
                        ball._stop_flash()
                    ball._urgent_showing = False if ball else None
                _tc.Thread(target=_do, daemon=True).start()
            self.inp.returnPressed.connect(_send_chat)
            self._sb.clicked.connect(_send_chat)
        else:
            self.ans.setPlainText(f"⚠ {context}\n\n{question}\n\n（請在上方輸入你的回答）")
            self.inp.setPlaceholderText("輸入你的解釋或修復方向...")
            self.inp.returnPressed.connect(self._ask)
            self._sb.clicked.connect(self._ask)

        self.inp.setFocus()

    EDGE = 8  # 邊框感應範圍

    def _get_edge(self, pos):
        """判斷滑鼠在哪個邊緣，回傳 (left, right, top, bottom)。"""
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        return (x < self.EDGE, x > w - self.EDGE,
                y < self.EDGE, y > h - self.EDGE)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos  = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._resize_edge = self._get_edge(e.position().toPoint())
            self._resize_start_geom = self.geometry()
            self._resize_start_global = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if not e.buttons() == Qt.MouseButton.LeftButton:
            # 更新游標樣式
            edge = self._get_edge(e.position().toPoint())
            l, r, t, b = edge
            if (l and t) or (r and b):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif (r and t) or (l and b):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif l or r:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif t or b:
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if not hasattr(self, '_resize_edge'):
            return

        l, r, t, b = self._resize_edge
        is_resize = any([l, r, t, b])

        if is_resize:
            # 調整大小
            gpos  = e.globalPosition().toPoint()
            delta = gpos - self._resize_start_global
            geom  = self._resize_start_geom
            new_geom = self.geometry()

            if r: new_geom.setRight(geom.right() + delta.x())
            if b: new_geom.setBottom(geom.bottom() + delta.y())
            if l:
                new_geom.setLeft(geom.left() + delta.x())
            if t:
                new_geom.setTop(geom.top() + delta.y())

            if new_geom.width() >= 280 and new_geom.height() >= 200:
                self.setGeometry(new_geom)
        elif hasattr(self, '_drag_pos'):
            # 移動視窗
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if hasattr(self, '_drag_pos'):
            del self._drag_pos
        if hasattr(self, '_resize_edge'):
            del self._resize_edge
        self.setCursor(Qt.CursorShape.ArrowCursor)


# ── 小圓 ─────────────────────────────────────────────────────────────────────

class MiniOrb(QWidget):
    clicked = pyqtSignal()

    def __init__(self, emoji, label, color, parent):
        super().__init__(parent)
        self.emoji = emoji
        self.label = label
        self.color = QColor(color)
        self._alpha = 0
        self._scale = 0.0
        self._hov   = False
        self.setFixedSize(MINI_SIZE, MINI_SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._tip = QLabel(label, parent)
        self._tip.setStyleSheet("""
            background:#16161a;color:#e8e6e0;
            border:1px solid #2a2a32;border-radius:6px;
            padding:3px 8px;font-size:11px;
            font-family:'Microsoft JhengHei UI';
        """)
        self._tip.hide(); self._tip.adjustSize()

    def set_vis(self, alpha, scale):
        self._alpha = alpha; self._scale = scale; self.update()

    def paintEvent(self, e):
        if self._alpha < 2: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._alpha / 255)
        cx = cy = MINI_SIZE // 2
        r = int((MINI_SIZE//2 - 3) * self._scale)
        if r < 1: return
        grad = QRadialGradient(cx - r//3, cy - r//3, r*2)
        grad.setColorAt(0, self.color.lighter(140))
        grad.setColorAt(1, self.color.darker(150))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255,255,255,60), 1))
        p.drawEllipse(cx-r, cy-r, r*2, r*2)
        p.setFont(QFont("Segoe UI Emoji", max(1, int(r*0.85))))
        p.setPen(QColor(255,255,255))
        p.drawText(QRect(0,0,MINI_SIZE,MINI_SIZE), Qt.AlignmentFlag.AlignCenter, self.emoji)

    def enterEvent(self, e):
        self._hov = True
        gp = self.mapToGlobal(QPoint(MINI_SIZE, MINI_SIZE//2 - 10))
        self._tip.move(self.parent().mapFromGlobal(gp))
        self._tip.raise_(); self._tip.show()

    def leaveEvent(self, e):
        self._hov = False; self._tip.hide()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._tip.hide(); self.clicked.emit()

# ── 主浮動球 ──────────────────────────────────────────────────────────────────

class FloatingBall(QWidget):
    _urgent_signal = pyqtSignal(dict)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        total = ORBT_R + MINI_SIZE + 24
        self._ws = total * 2
        self.setFixedSize(self._ws, self._ws)

        sc = QApplication.primaryScreen().availableGeometry()
        self.move(sc.right() - self._ws - 12, sc.bottom() - self._ws - 12)

        self._open   = False
        self._angle  = 0.0
        self._expand = 0.0
        self._pulse  = 0.0
        self._pdir   = 1
        self._drag   = False
        self._dpos   = QPoint()

        self._ask_dlg = AskDialog()
        self._flash_timer = None
        self._original_color = None
        # 背景監聽 knowledge_ui 的緊急問題推送
        self._urgent_signal.connect(self._show_urgent_question)
        self._urgent_showing = False
        import threading as _th3
        _th3.Thread(target=self._listen_urgent, daemon=True).start()

        handlers = [self._do_library, self._do_ask, self._do_dual_ai, self._do_terminal, self._do_main, self._do_vmagic, self._do_workshop, self._do_comfyui, self._do_filmora, self._do_hermes]
        self._orbs = []
        for i, (em, lb, col) in enumerate(ACTIONS):
            orb = MiniOrb(em, lb, col, self)
            orb.set_vis(0, 0.0)
            orb.clicked.connect(handlers[i])
            # index 0（📚 知識庫）點了不關主軌道，其他的關
            if i != 0:
                orb.clicked.connect(lambda: setattr(self, '_open', False))
            self._orbs.append(orb)

        # 子圓（圖書館展開後的兩個選項）
        self._sub_orbs = []
        sub_handlers = [self._do_knowledge, self._do_code_rules]
        for i, (em, lb, col) in enumerate(SUB_ACTIONS):
            orb = MiniOrb(em, lb, col, self)
            orb.set_vis(0, 0.0)
            orb.clicked.connect(sub_handlers[i])
            orb.clicked.connect(lambda: self._close_sub())
            self._sub_orbs.append(orb)

        self._sub_open   = False
        self._sub_expand = 0.0
        self._sub_angle  = 0.0
        self._library_orb_idx = 0  # index of 圖書館 in _orbs

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        self._pulse += 0.025 * self._pdir
        if self._pulse >= 1.0: self._pdir = -1
        elif self._pulse <= 0.0: self._pdir = 1

        if self._open:
            self._angle = (self._angle + 0.5) % 360
            self._expand = min(1.0, self._expand + 0.06)
        else:
            self._expand = max(0.0, self._expand - 0.08)
            if self._expand <= 0.0:
                self._sub_open = False

        n = len(self._orbs)
        for i, orb in enumerate(self._orbs):
            rad = math.radians((360/n)*i + self._angle)
            r   = ORBT_R * self._expand
            cx  = self._ws//2 + r*math.cos(rad) - MINI_SIZE//2
            cy  = self._ws//2 + r*math.sin(rad) - MINI_SIZE//2
            orb.move(int(cx), int(cy))
            orb.set_vis(int(255*self._expand), min(1.0, self._expand*1.5))
            orb.setVisible(self._expand > 0.01)

        # 子圓動畫（圍繞 📚 知識庫小圓展開）
        SUB_R = 75
        if self._sub_open:
            self._sub_expand = min(1.0, self._sub_expand + 0.07)
            self._sub_angle  = (self._sub_angle + 0.3) % 360
        else:
            self._sub_expand = max(0.0, self._sub_expand - 0.10)

        lib_orb = self._orbs[self._library_orb_idx] if self._library_orb_idx < len(self._orbs) else None
        n_sub = len(self._sub_orbs)
        for i, sub in enumerate(self._sub_orbs):
            if self._sub_expand > 0.01 and lib_orb and lib_orb.isVisible():
                lib_cx = lib_orb.x() + MINI_SIZE//2
                lib_cy = lib_orb.y() + MINI_SIZE//2
                base_a = math.radians((360/n_sub)*i + self._sub_angle)
                r = SUB_R * self._sub_expand
                cx = lib_cx + r*math.cos(base_a) - MINI_SIZE//2
                cy = lib_cy + r*math.sin(base_a) - MINI_SIZE//2
                sub.move(int(cx), int(cy))
                sub.set_vis(int(255*self._sub_expand), min(1.0, self._sub_expand*1.5))
                sub.setVisible(True)
                sub.raise_()
            else:
                sub.setVisible(False)

        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 緊急閃爍：覆蓋紅色
        if getattr(self, "_urgent_flash", False):
            cx = cy = BALL_SIZE // 2
            r  = BALL_SIZE // 2 - 4
            grad = QRadialGradient(cx - r//3, cy - r//3, r*2)
            grad.setColorAt(0, QColor(255, 80, 80))
            grad.setColorAt(1, QColor(180, 20, 20))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx-r, cy-r, r*2, r*2)
            p.setFont(QFont("Segoe UI Emoji", r))
            p.setPen(QColor(255,255,255))
            p.drawText(QRect(0,0,BALL_SIZE,BALL_SIZE), Qt.AlignmentFlag.AlignCenter, "❗")
            return
        cx = cy = self._ws // 2
        r  = BALL_SIZE // 2

        # 軌道圈
        if self._expand > 0.01:
            p.setPen(QPen(QColor(255,255,255,int(25*self._expand)), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            orb_r = int(ORBT_R * self._expand)
            p.drawEllipse(cx-orb_r, cy-orb_r, orb_r*2, orb_r*2)

        # 光暈
        glow_a = int(45 + self._pulse*65) if not self._open else 130
        gr = QRadialGradient(cx, cy, r+22)
        gr.setColorAt(0, QColor(232,197,71,glow_a))
        gr.setColorAt(1, QColor(232,197,71,0))
        p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx-r-22, cy-r-22, (r+22)*2, (r+22)*2)

        # 主球
        bg = QRadialGradient(cx-r//3, cy-r//3, r*2)
        if self._open:
            bg.setColorAt(0, QColor(255,230,100)); bg.setColorAt(1, QColor(180,130,20))
        else:
            bg.setColorAt(0, QColor(232,197,71)); bg.setColorAt(1, QColor(150,110,10))
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(255,255,255,50), 1.5))
        p.drawEllipse(cx-r, cy-r, r*2, r*2)

        p.setFont(QFont("Segoe UI Emoji", 22))
        p.setPen(QColor(255,255,255))
        p.drawText(QRect(cx-r, cy-r, r*2, r*2), Qt.AlignmentFlag.AlignCenter, "🦞")

    def _listen_urgent(self):
        """背景輪詢 knowledge_ui，偵測緊急問題推送。"""
        import time
        while True:
            try:
                import requests as _rq
                r = _rq.get("http://localhost:7861/api/urgent_pending", timeout=3)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("has_question") and not getattr(self, "_urgent_showing", False):
                        self._urgent_data    = data
                        self._urgent_showing = True
                        from PyQt6.QtCore import QMetaObject, Qt
                        self._urgent_signal.emit(data)
            except Exception:
                pass
            time.sleep(3)

    @pyqtSlot(dict)
    def _show_urgent_question(self, data: dict = None):
        if data is None:
            data = getattr(self, "_urgent_data", None)
        if not data:
            return
        self._start_flash()
        dlg = self._ask_dlg
        dlg.show_near(self.mapToGlobal(self.rect().center()))
        dlg.show_urgent(
            data.get("question", ""),
            data.get("human_id", ""),
            data.get("context", ""),
        )

    def _start_flash(self):
        from PyQt6.QtCore import QTimer
        self._flash_count = 0
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._do_flash)
        self._flash_timer.start(500)

    def _do_flash(self):
        self._flash_count = getattr(self, "_flash_count", 0) + 1
        self._urgent_flash = (self._flash_count % 2 == 1)
        self.update()
        if self._flash_count > 20:
            self._stop_flash()

    def _stop_flash(self):
        if self._flash_timer:
            self._flash_timer.stop()
            self._flash_timer = None
        self._urgent_flash = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = False
            self._dpos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._dpos)
            self._drag = True

    def mouseReleaseEvent(self, e):
        cx = cy = self._ws // 2
        lp = e.position()
        in_ball = math.hypot(lp.x()-cx, lp.y()-cy) <= BALL_SIZE//2
        if e.button() == Qt.MouseButton.LeftButton and not self._drag and in_ball:
            self._open = not self._open

    # ── 功能 ─────────────────────────────────────────────────────────────────

    def _do_library(self):
        """點擊圖書館小圓：展開/收合子圓"""
        self._sub_open = not self._sub_open

    def _close_sub(self):
        self._sub_open = False
        self._open = False

    def _do_knowledge(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', 7861)) == 0:
                webbrowser.open("http://localhost:7861"); return
        def _go():
            ui = BASE_DIR / "knowledge_ui.py"
            subprocess.Popen(["powershell","-Command",
                f'Start-Process python -ArgumentList "{ui}" -WorkingDirectory "{BASE_DIR}"'],
                creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(3); webbrowser.open("http://localhost:7861")
        threading.Thread(target=_go, daemon=True).start()

    def _do_code_rules(self):
        """開啟知識庫並直接跳到程式碼規範庫"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            running = s.connect_ex(('localhost', 7861)) == 0
        if running:
            webbrowser.open("http://localhost:7861/#code-rules"); return
        def _go():
            ui = BASE_DIR / "knowledge_ui.py"
            subprocess.Popen(["powershell","-Command",
                f'Start-Process python -ArgumentList "{ui}" -WorkingDirectory "{BASE_DIR}"'],
                creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(3)
            webbrowser.open("http://localhost:7861/#code-rules")
        threading.Thread(target=_go, daemon=True).start()

    def _do_ask(self):
        gp = self.mapToGlobal(QPoint(self._ws//2, self._ws//2))
        self._ask_dlg.show_near(gp)

    def _do_terminal(self):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction, QCursor
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background:#1a1a2e; color:#e8e6e0; border:1px solid #333; border-radius:8px; padding:4px; }
            QMenu::item { padding:8px 20px; border-radius:4px; }
            QMenu::item:selected { background:#2a2a3e; }
        """)
        act1 = QAction("🤖 AI Agent (PowerShell)", menu)
        act2 = QAction("🐧 WSL Ubuntu-24.04", menu)
        act1.triggered.connect(self._do_terminal_agent)
        act2.triggered.connect(self._do_terminal_wsl)
        menu.addAction(act1)
        menu.addAction(act2)
        menu.exec(QCursor.pos())

    def _do_terminal_agent(self):
        """開啟 PowerShell 終端機（AI Agent 目錄）。"""
        subprocess.Popen(["powershell", "-Command",
            f'Start-Process powershell -ArgumentList "-NoExit","-Command","cd \'{BASE_DIR}\'"'],
            creationflags=subprocess.CREATE_NO_WINDOW)

    def _do_terminal_wsl(self):
        """開啟 WSL Ubuntu-24.04 終端機。"""
        subprocess.Popen(
            "cmd.exe /k wsl.exe -d Ubuntu-24.04 -u acerli --cd ~",
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )

    def _do_dual_ai(self):
        dual = BASE_DIR / "dual_ai_chat.py"
        subprocess.Popen(["powershell","-Command",
            f'Start-Process python -ArgumentList "{dual}" -WorkingDirectory "{BASE_DIR}"'],
            creationflags=subprocess.CREATE_NO_WINDOW)

    def _do_main(self):
        main = BASE_DIR / "desktop_agent.py"
        subprocess.Popen(["powershell","-Command",
            f'Start-Process python -ArgumentList "{main}" -WorkingDirectory "{BASE_DIR}"'],
            creationflags=subprocess.CREATE_NO_WINDOW)

    def _do_vmagic(self):
        """三段式切換 VMagicMirror：啟動 → 隱藏設定 → 關閉"""
        import psutil
        if not hasattr(self, '_vmagic_state'):
            self._vmagic_state = 0  # 0=關閉 1=開啟 2=隱藏設定

        running = any(
            'VMagicMirror' in (p.info.get('name') or '')
            for p in psutil.process_iter(['name'])
        )

        if not running:
            # 沒在跑 → 啟動 VMagicMirror + 泡泡
            subprocess.Popen([VMAGIC_PATH])
            # 啟動泡泡視窗（不開終端）
            bubble_path = BASE_DIR / "yuanyuan_bubble.py"
            if bubble_path.exists():
                import sys as _sys
                subprocess.Popen(
                    [_sys.executable, str(bubble_path)],
                    cwd=str(BASE_DIR),
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            self._vmagic_state = 1
            if len(self._orbs) > 5:
                self._orbs[5]._tip.setText("隱藏設定")

        elif self._vmagic_state == 1:
            # 第2次 → 隱藏設定視窗
            ps_script = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinHider2 {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc f, IntPtr l);
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr h, int c);
    public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
    public static void Hide() {
        EnumWindows((h, l) => {
            var s = new StringBuilder(256);
            GetWindowText(h, s, 256);
            if (s.ToString().Contains("VMagicMirror v")) ShowWindow(h, 0);
            return true;
        }, IntPtr.Zero);
    }
}
"@
[WinHider2]::Hide()
"""
            subprocess.Popen(
                ["powershell", "-Command", ps_script],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self._vmagic_state = 2
            if len(self._orbs) > 5:
                self._orbs[5]._tip.setText("關閉圓圓")

        else:
            # 第3次 → 關閉
            for p in psutil.process_iter(['name', 'cmdline']):
                try:
                    name = p.info.get('name') or ''
                    cmd  = ' '.join(p.info.get('cmdline') or [])
                    if 'VMagicMirror' in name or 'yuanyuan_bubble' in cmd:
                        p.kill()
                except Exception:
                    pass
            self._vmagic_state = 0
            if len(self._orbs) > 5:
                self._orbs[5]._tip.setText("圓圓")

    def _do_workshop(self):
        """開啟工坊，沒跑先啟動再開瀏覽器"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', 7862)) == 0:
                webbrowser.open("http://localhost:7862"); return
        def _go():
            ws = BASE_DIR / "workshop_ui.py"
            subprocess.Popen(["powershell", "-Command",
                f'Start-Process powershell -ArgumentList "-NoExit","-Command","cd \'{BASE_DIR}\'; python \'{ws}\'"'],
                creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(3); webbrowser.open("http://localhost:7862")
        threading.Thread(target=_go, daemon=True).start()

    def _do_comfyui(self):
        """開啟 ComfyUI，已在跑就直接開瀏覽器"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', 8188)) == 0:
                webbrowser.open("http://localhost:8188"); return
        def _go():
            # 常見 ComfyUI 安裝位置
            candidates = [
                BASE_DIR / "ComfyUI" / "main.py",
                BASE_DIR.parent / "ComfyUI" / "main.py",
                pathlib.Path(r"C:\ComfyUI\main.py"),
                pathlib.Path(r"C:\Users\ACER\ComfyUI\main.py"),
                pathlib.Path(r"C:\Users\ACER\Desktop\ComfyUI\main.py"),
            ]
            comfy = next((p for p in candidates if p.exists()), None)
            if comfy:
                subprocess.Popen(
                    ["powershell", "-Command",
                     f'Start-Process powershell -ArgumentList "-NoExit","-Command",'
                     f'"cd \'{comfy.parent}\'; python \'{comfy}\'"'],
                )
                time.sleep(6)
            webbrowser.open("http://localhost:8188")
        threading.Thread(target=_go, daemon=True).start()

    def _do_hermes(self):
        """開啟 WSL 並啟動 Hermes Agent 和 Telegram Gateway。"""
        import subprocess
        # 確認 desktop_control_server 有在跑
        try:
            import requests as _rq
            _rq.get("http://172.23.48.1:7864/health", timeout=2)
        except Exception:
            _server = BASE_DIR / "desktop_control_server.py"
            if _server.exists():
                subprocess.Popen(
                    [sys.executable, str(_server)],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    cwd=str(BASE_DIR)
                )

        hermes_bin = "/home/acerli/.hermes/hermes-agent/venv/bin/hermes"

        # 背景啟動 gateway（Telegram）
        subprocess.Popen([
            "wsl.exe", "-d", "Ubuntu-24.04", "-u", "acerli",
            "--", "bash", "-c", f"{hermes_bin} gateway"
        ], creationflags=subprocess.CREATE_NO_WINDOW)

        # 前景開啟 Hermes 對話介面
        try:
            subprocess.Popen([
                "cmd.exe", "/k",
                f"wsl.exe -d Ubuntu-24.04 -u acerli -- bash -c \"{hermes_bin}\""
            ], creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Hermes", f"無法開啟 Hermes：{e}")

    def _do_filmora(self):
        """開啟 Filmora 14 並顯示控制面板。"""
        import pathlib, subprocess
        candidates = [
            pathlib.Path(FILMORA_PATH),
            pathlib.Path(r"C:\Users\ACER\AppData\Local\Wondershare\Wondershare Filmora（繁體中文）\Wondershare Filmora Launcher.exe"),
            pathlib.Path(r"C:\Program Files\Wondershare\Filmora14\Filmora.exe"),
        ]
        exe = next((p for p in candidates if p.exists()), None)
        if exe:
            try:
                subprocess.Popen([str(exe)])
            except Exception as err:
                print(f"Filmora 啟動失敗：{err}")
        else:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showwarning("找不到 Filmora",
                f"找不到 Filmora 執行檔。\n請確認安裝路徑：\n{FILMORA_PATH}")
            root.destroy()
            return
        if not hasattr(self, '_filmora_panel') or self._filmora_panel is None:
            self._filmora_panel = FilmoraPanel()
        self._filmora_panel.show()
        self._filmora_panel.raise_()

# ── Filmora 控制面板 ──────────────────────────────────────────────────────────

class FilmoraPanel(QWidget):
    """浮動的 Filmora 控制面板。"""

    def __init__(self):
        super().__init__(None,
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._dragging = False
        self._drag_pos = QPoint()
        self._build()
        # 右下角定位
        sc = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(sc.right() - self.width() - 20, sc.bottom() - self.height() - 200)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #16161a;
                border: 1px solid #2a2a3a;
                border-radius: 14px;
            }
        """)
        vlay = QVBoxLayout(card)
        vlay.setContentsMargins(14, 12, 14, 14)
        vlay.setSpacing(8)

        # 標題列
        title_row = QHBoxLayout()
        title = QLabel("🎬 Filmora 控制")
        title.setStyleSheet("color:#f87171; font-size:13px; font-weight:600;")
        title_row.addWidget(title)
        title_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet("background:transparent;color:#555;border:none;font-size:12px;")
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(close_btn)
        vlay.addLayout(title_row)

        # 快捷按鈕區
        grid_btns = [
            ("▶/⏸", "播放暫停",  self._play_pause),
            ("✂",   "分割片段",  self._split),
            ("🗑",  "刪除選取",  self._delete),
            ("↩",   "還原",      self._undo),
            ("💾",  "儲存",      self._save),
            ("📤",  "匯出",      self._export),
        ]
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (icon, tip, fn) in enumerate(grid_btns):
            btn = QPushButton(icon + "\n" + tip)
            btn.setFixedSize(68, 52)
            btn.setStyleSheet("""
                QPushButton {
                    background: #1e1e2e; color: #ccc;
                    border: 1px solid #2a2a3a; border-radius: 8px;
                    font-size: 11px; line-height: 1.4;
                }
                QPushButton:hover  { background: #2a2a3e; border-color: #f87171; color: #fff; }
                QPushButton:pressed{ background: #f87171; color: #000; }
            """)
            btn.clicked.connect(fn)
            grid.addWidget(btn, i // 3, i % 3)
        vlay.addLayout(grid)

        # 跳轉時間輸入
        seek_row = QHBoxLayout()
        seek_row.setSpacing(6)
        self.seek_inp = QLineEdit()
        self.seek_inp.setPlaceholderText("跳到幾秒...")
        self.seek_inp.setStyleSheet("""
            QLineEdit {
                background:#1e1e2e; color:#ddd;
                border:1px solid #2a2a3a; border-radius:6px;
                padding:4px 8px; font-size:12px;
            }
        """)
        self.seek_inp.returnPressed.connect(self._seek)
        seek_row.addWidget(self.seek_inp)
        seek_btn = QPushButton("跳")
        seek_btn.setFixedWidth(36)
        seek_btn.setStyleSheet("""
            QPushButton {
                background:#f87171; color:#000;
                border:none; border-radius:6px; font-size:12px;
            }
            QPushButton:hover { background:#fca5a5; }
        """)
        seek_btn.clicked.connect(self._seek)
        seek_row.addWidget(seek_btn)
        vlay.addLayout(seek_row)

        # 自然語言輸入
        nl_row = QHBoxLayout()
        nl_row.setSpacing(6)
        self.nl_inp = QLineEdit()
        self.nl_inp.setPlaceholderText("輸入指令（剪掉 3~8 秒）...")
        self.nl_inp.setStyleSheet("""
            QLineEdit {
                background:#1e1e2e; color:#ddd;
                border:1px solid #2a2a3a; border-radius:6px;
                padding:4px 8px; font-size:12px;
            }
        """)
        self.nl_inp.returnPressed.connect(self._nl_exec)
        nl_row.addWidget(self.nl_inp)
        nl_btn = QPushButton("執行")
        nl_btn.setFixedWidth(44)
        nl_btn.setStyleSheet("""
            QPushButton {
                background:#fb923c; color:#000;
                border:none; border-radius:6px; font-size:12px;
            }
            QPushButton:hover { background:#fdba74; }
        """)
        nl_btn.clicked.connect(self._nl_exec)
        nl_row.addWidget(nl_btn)
        vlay.addLayout(nl_row)

        # 狀態列
        self.status = QLabel("就緒")
        self.status.setStyleSheet("color:#555; font-size:11px;")
        vlay.addWidget(self.status)

        outer.addWidget(card)

    # ── 拖曳 ──────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._dragging and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._dragging = False

    def closeEvent(self, e):
        e.ignore()
        self.hide()

    # ── 操作 ──────────────────────────────────────────────────────────────────
    def _run(self, action_code: str, msg: str = ""):
        """在背景執行 filmora_agent 操作。"""
        import pathlib, subprocess, sys, threading
        base = pathlib.Path(__file__).parent
        script = f"import sys; sys.path.insert(0,r'{base}'); from filmora_agent import *; {action_code}"
        self.status.setText(f"⏳ {msg or action_code}...")
        def go():
            r = subprocess.run([sys.executable, "-c", script],
                               capture_output=True, text=True, timeout=15)
            ok = r.returncode == 0
            self.status.setText("✅ 完成" if ok else f"❌ {r.stderr[:60]}")
        threading.Thread(target=go, daemon=True).start()

    def _play_pause(self):  self._run("play_pause()", "播放/暫停")
    def _split(self):       self._run("split_clip()", "分割")
    def _delete(self):      self._run("delete_selected()", "刪除")
    def _undo(self):        self._run("undo(1)", "還原")
    def _save(self):        self._run("save_project()", "儲存")
    def _export(self):      self._run("export_video()", "匯出")

    def _seek(self):
        try:
            sec = float(self.seek_inp.text().strip())
            self._run(f"seek_to({sec})", f"跳到 {sec} 秒")
            self.seek_inp.clear()
        except ValueError:
            self.status.setText("⚠ 請輸入數字（秒）")

    def _nl_exec(self):
        cmd = self.nl_inp.text().strip()
        if not cmd: return
        self.nl_inp.clear()
        self.status.setText(f"⏳ 解析：{cmd[:30]}...")
        import threading
        def go():
            import requests, json, re, subprocess, sys, pathlib
            base = pathlib.Path(__file__).parent
            r = requests.post("http://localhost:11434/api/chat", json={
                "model": "gpt-oss:20b",
                "messages": [
                    {"role": "system", "content": "你是 Filmora 控制器，只回傳 JSON 格式，包含 actions 陣列和 summary 欄位"},
                    {"role": "user",   "content": cmd},
                ],
                "stream": False, "options": {"temperature": 0.1},
            }, timeout=None)
            raw = r.json().get("message",{}).get("content","").strip()
            raw = re.sub(r"^```[a-z]*\n?","",raw); raw = re.sub(r"\n?```$","",raw).strip()
            plan = json.loads(raw)
            actions = plan.get("actions",[])
            if not actions:
                self.status.setText("⚠ 無法解析指令")
                return
            script_lines = ["import sys,time", f"sys.path.insert(0,r'{base}')", "from filmora_agent import *"]
            for act in actions:
                a = act.get("action",""); p = act.get("params",{})
                if a == "seek":            script_lines.append(f"seek_to({p.get('seconds',0)})")
                elif a == "split":         script_lines.append("split_clip()")
                elif a == "cut_segment":   script_lines.append(f"cut_segment({p.get('start',0)},{p.get('end',0)})")
                elif a == "play_pause":    script_lines.append("play_pause()")
                elif a == "import_media":  script_lines.append(f"import_media(r'{p.get('path','')}')")
                elif a == "save":          script_lines.append("save_project()")
                elif a == "export":        script_lines.append(f"export_video(r'{p.get('output_path','')}','{p.get('quality','1080p')}')")
                elif a == "undo":          script_lines.append(f"undo({p.get('times',1)})")
                elif a == "delete_selected": script_lines.append("delete_selected()")
                script_lines.append("time.sleep(0.5)")
            script_lines.append("print('DONE')")
            result = subprocess.run([sys.executable,"-c","\n".join(script_lines)],
                                    capture_output=True, text=True, timeout=30)
            summary = plan.get("summary","完成")
            self.status.setText(f"✅ {summary}" if "DONE" in result.stdout else f"❌ {result.stderr[:60]}")
        threading.Thread(target=go, daemon=True).start()


# ── 啟動 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)

    import subprocess as _sp, socket as _sk, threading as _th_main

    def _bg_start(script_name):
        path = BASE_DIR / script_name
        if not path.exists():
            return
        try:
            _log = open(str(BASE_DIR / (script_name + ".log")), "w", encoding="utf-8")
            _kw = {"cwd": str(BASE_DIR), "stdout": _log, "stderr": _log}
            if hasattr(_sp, "CREATE_NO_WINDOW"):
                _kw["creationflags"] = _sp.CREATE_NO_WINDOW
            _sp.Popen([sys.executable, str(path)], **_kw)
        except Exception as e:
            open(str(BASE_DIR / (script_name + ".log")), "w", encoding="utf-8").write(str(e))

    def _start_services():
        """背景啟動所有服務，不阻塞漂浮球顯示。"""
        import time
        # 啟動 desktop_control_server
        _bg_start("desktop_control_server.py")
        # 啟動 knowledge_ui（立AI 大腦）
        with _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", 7861)) != 0:
                _bg_start("knowledge_ui.py")
                # 等 knowledge_ui 就緒
                for _ in range(30):
                    time.sleep(1)
                    with _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM) as s2:
                        if s2.connect_ex(("localhost", 7861)) == 0:
                            break
        # 啟動 interest_reader
        _bg_start("interest_reader.py")

    # 背景啟動服務，漂浮球立刻出現
    _th_main.Thread(target=_start_services, daemon=True).start()

    app.setQuitOnLastWindowClosed(False)
    ball = FloatingBall()
    ball.show()
    sys.exit(app.exec())
