# liai_api.py — 立AI 獨立 HTTP API
# 啟動方式：python liai_api.py
# 監聽 port 7777，供 NOVA App 呼叫

import threading
import logging
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("liai_api")

REPLY_MODEL = "gemma3:4b"
PORT = 7777


def _infer(prompt: str) -> str:
    """直接用本地 Ollama 推論"""
    try:
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": REPLY_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_predict": 512, "temperature": 0.8}
            },
            timeout=180
        )
        result = r.json().get("message", {}).get("content", "").strip()
        if result:
            logger.info(f"[API] 推論完成（{len(result)}字）")
            return result
    except Exception as e:
        logger.warning(f"[API] 推論失敗：{e}")
    return "抱歉，我現在無法回應，請稍後再試。"


class APIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                message = data.get("message", "")
                logger.info(f"[API] 收到訊息：{message[:60]}")
                reply = _infer(
                    f"你是立AI，認真有點幽默的AI助理。"
                    f"使用者說：「{message}」"
                    f"請用繁體中文回應，100字以內。"
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"reply": reply}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                logger.error(f"[API] 錯誤：{e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        logger.info(f"[HTTP] {format % args}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), APIHandler)
    logger.info(f"[API] 立AI HTTP API 啟動於 port {PORT}")
    logger.info(f"[API] 測試網址：http://localhost:{PORT}/chat")
    server.serve_forever()
