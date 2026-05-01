# pc_api_client.py — 立AI 電腦控制 API 客戶端
import requests
import logging
import re
import os
import json

try:
    from agent_logger import get_logger
    logger = get_logger("pc_api_client")
except ImportError:
    logger = logging.getLogger("pc_api_client")

PC_API_BASE  = "http://localhost:8899"
OLLAMA_BASE  = "http://localhost:11434"
TIMEOUT      = 10


def _post(endpoint: str, data: dict) -> dict:
    try:
        r = requests.post(f"{PC_API_BASE}{endpoint}", json=data, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"[PCClient] {endpoint} 失敗：{e}")
        return {"ok": False, "error": str(e)}


def _get(endpoint: str, params: dict = None) -> dict:
    try:
        r = requests.get(f"{PC_API_BASE}{endpoint}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"[PCClient] {endpoint} 失敗：{e}")
        return {"ok": False, "error": str(e)}


# ── 滑鼠 ──────────────────────────────────────────────────────────────────────

def click(x, y, button="left", clicks=1):
    result = _post("/mouse/click", {"x": x, "y": y, "button": button, "clicks": clicks})
    logger.info(f"[PCClient] 點擊 ({x}, {y})")
    return result.get("ok", False)

def move(x, y):
    return _post("/mouse/move", {"x": x, "y": y, "duration": 0.2}).get("ok", False)

def scroll(x, y, amount):
    return _post("/mouse/scroll", {"x": x, "y": y, "amount": amount}).get("ok", False)

def get_mouse_position():
    result = _get("/mouse/position")
    return result.get("x", 0), result.get("y", 0)


# ── 鍵盤 ──────────────────────────────────────────────────────────────────────

def type_text(text):
    result = _post("/keyboard/type", {"text": text, "interval": 0.05})
    logger.info(f"[PCClient] 輸入：{text[:30]}")
    return result.get("ok", False)

def hotkey(*keys):
    result = _post("/keyboard/hotkey", {"keys": list(keys)})
    logger.info(f"[PCClient] 快捷鍵：{'+'.join(keys)}")
    return result.get("ok", False)


# ── 截圖與視覺 ────────────────────────────────────────────────────────────────

def capture_screen(scale=0.5):
    return _get("/screen/capture", {"scale": scale}).get("image", "")

def ask_screen(question):
    result = _post("/screen/ask", {"question": question})
    answer = result.get("answer", "")
    logger.info(f"[PCClient] 視覺：{answer[:60]}")
    return answer

def get_screen_size():
    result = _get("/screen/size")
    return result.get("width", 1920), result.get("height", 1080)


# ── 系統 ──────────────────────────────────────────────────────────────────────

def run_command(command, wait=False):
    return _post("/system/run", {"command": command, "wait": wait, "timeout": 30})

def open_file(path):
    return _post("/system/open", {"path": path}).get("ok", False)

def get_clipboard():
    return _get("/system/clipboard").get("text", "")

def set_clipboard(text):
    return _post("/system/clipboard", {"text": text}).get("ok", False)


# ── 健康檢查 ──────────────────────────────────────────────────────────────────

def is_available():
    try:
        r = requests.get(f"{PC_API_BASE}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ── 路徑工具 ──────────────────────────────────────────────────────────────────

def _expand_path(path: str) -> str:
    desktop   = os.path.join(os.path.expanduser("~"), "Desktop")
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    documents = os.path.join(os.path.expanduser("~"), "Documents")
    path = path.replace("桌面", desktop)
    path = path.replace("下載", downloads)
    path = path.replace("文件", documents)
    return path


# ── Ollama 意圖理解 ───────────────────────────────────────────────────────────

_INTENT_PROMPT = """你是一個電腦控制 AI，負責把用戶的自然語言指令轉換成 API 呼叫。

可用的 action 清單：
- screenshot: 截圖並描述畫面
- click: 點擊畫面上的元素，需要 target（描述要點什麼）
- type: 輸入文字，需要 text
- hotkey: 按快捷鍵，需要 keys（陣列）
- file_write: 建立或寫入檔案，需要 path 和 content
- file_read: 讀取檔案，需要 path
- file_copy: 複製檔案，需要 src 和 dst
- file_delete: 刪除檔案，需要 path（會要求確認）
- file_search: 搜尋檔案，需要 directory 和 pattern
- file_list: 列出資料夾，需要 directory
- window_list: 列出所有視窗
- window_focus: 切換視窗，需要 title
- window_maximize: 最大化視窗，需要 title
- window_close: 關閉視窗，需要 title
- run: 執行系統指令，需要 command
- open: 開啟檔案或程式，需要 path
- download: 下載檔案，需要 url 和 save_path
- notify: 發送桌面通知，需要 message
- volume_get: 取得目前音量
- volume_set: 設定音量，需要 level（0-100）
- brightness_set: 設定亮度，需要 level（0-100）
- record_start: 開始錄影，需要 duration（秒）和 save_path
- record_stop: 停止錄影
- clipboard_get: 讀取剪貼簿
- clipboard_set: 寫入剪貼簿，需要 text
- ask_screen: 截圖後問 AI 問題，需要 question

用戶說：「{user_input}」

請輸出 JSON，格式：
{{"action": "動作名稱", "params": {{...參數...}}, "reason": "為什麼這樣判斷"}}

只輸出 JSON，不要其他文字。"""


def _understand_intent(text: str) -> dict:
    """用 Ollama 理解用戶意圖，回傳 action 和 params"""
    try:
        prompt = _INTENT_PROMPT.replace("{user_input}", text)
        r = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": "gemma4:latest", "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.1, "num_predict": 256}},
            timeout=60
        )
        response = r.json().get("response", "").strip()
        # 清除 markdown
        response = re.sub(r'```json|```', '', response).strip()
        # 找 JSON
        start = response.find("{")
        end   = response.rfind("}") + 1
        if start != -1 and end > start:
            result = json.loads(response[start:end])
            logger.info(f"[PCClient] 意圖：{result.get('action')} — {result.get('reason', '')}")
            return result
    except Exception as e:
        logger.warning(f"[PCClient] 意圖理解失敗：{e}")
    return {"action": "ask_screen", "params": {"question": text}}


# ── 執行 action ───────────────────────────────────────────────────────────────

def _execute_action(action: str, params: dict) -> str:
    p = params or {}

    if action == "screenshot":
        return ask_screen("請用繁體中文描述這個畫面上有什麼")

    elif action == "ask_screen":
        return ask_screen(p.get("question", "描述畫面"))

    elif action == "click":
        target = p.get("target", "")
        answer = ask_screen(f"畫面上的「{target}」在哪裡？請只回答座標 x,y（純數字）")
        try:
            parts = [s.strip() for s in answer.replace("，", ",").split(",")]
            x, y = int(parts[0]), int(parts[1])
            click(x, y)
            return f"已點擊「{target}」({x}, {y})"
        except Exception:
            return f"無法定位「{target}」：{answer}"

    elif action == "type":
        text = p.get("text", "")
        type_text(text)
        return f"已輸入：{text}"

    elif action == "hotkey":
        keys = p.get("keys", [])
        hotkey(*keys)
        return f"已按下：{'+'.join(keys)}"

    elif action == "file_write":
        path = _expand_path(p.get("path", ""))
        content = p.get("content", "")
        result = _post("/file/write", {"path": path, "content": content})
        return f"已建立：{path}" if result.get("ok") else f"失敗：{result.get('error')}"

    elif action == "file_read":
        path = _expand_path(p.get("path", ""))
        result = _post("/file/read", {"path": path})
        return result.get("content", "讀取失敗")[:1000]

    elif action == "file_copy":
        src = _expand_path(p.get("src", ""))
        dst = _expand_path(p.get("dst", ""))
        result = _post("/file/copy", {"src": src, "dst": dst})
        return f"已複製：{src} → {dst}" if result.get("ok") else "複製失敗"

    elif action == "file_delete":
        path = _expand_path(p.get("path", ""))
        # 先回傳確認請求，不直接刪
        result = _post("/file/delete", {"path": path, "confirm": False})
        return result.get("message", "需要確認才能刪除")

    elif action == "file_search":
        directory = _expand_path(p.get("directory", "."))
        pattern   = p.get("pattern", "*")
        result = _post("/file/search", {"directory": directory, "pattern": pattern})
        files = result.get("results", [])
        return f"找到 {len(files)} 個：\n" + "\n".join(files[:20])

    elif action == "file_list":
        directory = _expand_path(p.get("directory", "."))
        result = _get("/file/list", {"directory": directory})
        items = result.get("items", [])
        return "\n".join(f"{'📁' if i['type']=='dir' else '📄'} {i['name']}" for i in items)

    elif action == "window_list":
        result = _get("/window/list")
        wins = result.get("windows", [])
        return "目前視窗：\n" + "\n".join(f"- {w['title']}" for w in wins)

    elif action == "window_focus":
        title = p.get("title", "")
        result = _post("/window/focus", {"title": title})
        return f"已切換到：{title}" if result.get("ok") else f"找不到視窗：{title}"

    elif action == "window_maximize":
        title = p.get("title", "")
        _post("/window/maximize", {"title": title})
        return f"已最大化：{title}"

    elif action == "window_close":
        title = p.get("title", "")
        _post("/window/close", {"title": title})
        return f"已關閉視窗：{title}"

    elif action == "run":
        command = p.get("command", "")
        result = run_command(command, wait=True)
        return result.get("stdout", "") or result.get("error", "執行完成")

    elif action == "open":
        path = _expand_path(p.get("path", ""))
        open_file(path)
        return f"已開啟：{path}"

    elif action == "download":
        url  = p.get("url", "")
        path = _expand_path(p.get("save_path", "download"))
        result = _post("/network/download", {"url": url, "save_path": path})
        return f"下載完成：{result.get('path')}" if result.get("ok") else "下載失敗"

    elif action == "notify":
        msg = p.get("message", "")
        _post("/notify", {"title": "立 AI", "message": msg, "duration": 5})
        return f"已通知：{msg}"

    elif action == "volume_get":
        result = _get("/system/volume")
        return f"目前音量：{result.get('level')}%"

    elif action == "volume_set":
        level = p.get("level", 50)
        _post("/system/volume", {"level": level})
        return f"已設定音量：{level}%"

    elif action == "brightness_set":
        level = p.get("level", 50)
        _post("/system/brightness", level)
        return f"已設定亮度：{level}%"

    elif action == "record_start":
        duration  = p.get("duration", 30)
        save_path = _expand_path(p.get("save_path", "record.mp4"))
        _post("/record/start", {"duration": duration, "save_path": save_path})
        return f"開始錄製（{duration}秒）→ {save_path}"

    elif action == "record_stop":
        _post("/record/stop", {})
        return "已停止錄製"

    elif action == "clipboard_get":
        return f"剪貼簿：{get_clipboard()[:300]}"

    elif action == "clipboard_set":
        text = p.get("text", "")
        set_clipboard(text)
        return f"已寫入剪貼簿：{text}"

    return f"未知動作：{action}"


# ── 主要對外介面 ──────────────────────────────────────────────────────────────

def smart_execute(text: str) -> str:
    """
    用自然語言指令控制電腦。
    先讓 Ollama 理解意圖，再執行對應 API。
    """
    if not is_available():
        return "（PC API 未啟動，請先執行 python pc_api.py）"

    logger.info(f"[PCClient] 指令：{text[:60]}")
    intent = _understand_intent(text)
    action = intent.get("action", "ask_screen")
    params = intent.get("params", {})

    return _execute_action(action, params)
