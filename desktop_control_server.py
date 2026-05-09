"""
desktop_control_server.py — 桌面控制 HTTP API Server
讓 Hermes (WSL) 可以透過 HTTP 控制 Windows 桌面

啟動：python desktop_control_server.py
端口：7863（或自訂）
"""

from flask import Flask, request, jsonify
import sys
import pathlib

# 加入 AI-Agent 路徑
sys.path.insert(0, str(pathlib.Path(__file__).parent))

try:
    from desktop_control import get_control
    ctrl = get_control()
    HAS_CTRL = True
except Exception as e:
    HAS_CTRL = False
    print(f"警告：desktop_control 載入失敗：{e}")

app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({"ok": True, "has_control": HAS_CTRL})

@app.route("/screenshot", methods=["POST", "GET"])
def screenshot():
    try:
        path = ctrl.screenshot()
        return jsonify({"ok": True, "path": str(path)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/click", methods=["POST"])
def click():
    data = request.json or {}
    try:
        if "text" in data:
            ctrl.click_text(data["text"])
        else:
            ctrl.click(int(data.get("x", 0)), int(data.get("y", 0)),
                      data.get("button", "left"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/type", methods=["POST"])
def type_text():
    data = request.json or {}
    text = data.get("text", "")
    try:
        if any(ord(c) > 127 for c in text):
            ctrl.type_chinese(text)
        else:
            ctrl.type_text(text)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/key", methods=["POST"])
def press_key():
    data = request.json or {}
    try:
        ctrl.press_key(data.get("key", ""))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/windows", methods=["GET"])
def list_windows():
    try:
        wins = ctrl.list_windows()
        return jsonify({"ok": True, "windows": wins})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/ocr", methods=["GET"])
def ocr():
    try:
        text = ctrl.ocr_screen()
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/scroll", methods=["POST"])
def scroll():
    data = request.json or {}
    try:
        ctrl.scroll(data.get("clicks", 3), data.get("direction", "down"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/mouse_pos", methods=["GET"])
def mouse_pos():
    try:
        pos = ctrl.get_mouse_pos()
        return jsonify({"ok": True, "position": pos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7864
    print(f"🖥 桌面控制 Server 啟動在 port {port}")
    print(f"   Hermes 可以用 http://172.23.48.1:{port} 連接")
    app.run(host="0.0.0.0", port=port, debug=False)
