# ollama_guard.py — Ollama 連線守護層（雙 AI 討論版）
# 兩台各自有獨立 AI，可以互相討論達成共識後回傳結果

import requests
import time
import threading

try:
    from agent_logger import get_logger
    logger = get_logger("ollama_guard")
except ImportError:
    import logging
    logger = logging.getLogger("ollama_guard")

# ── 節點設定 ──────────────────────────────────────────────────────────────────
LOCAL_BASE  = "http://localhost:11434"
REMOTE_BASE = "http://100.91.121.85:11434"
REMOTE_IP   = "100.91.121.85"

# 各節點專屬 model（A電腦=local, B電腦=remote）
LOCAL_MODEL  = "gpt-oss:20b"
REMOTE_MODEL = "deepseek-coder-v2:16b"

NODES = [
    {"name": "local",  "base": LOCAL_BASE,  "model": LOCAL_MODEL,  "online": False, "last_check": 0.0, "fail_count": 0, "busy": False},
    {"name": "remote", "base": REMOTE_BASE, "model": REMOTE_MODEL, "online": False, "last_check": 0.0, "fail_count": 0, "busy": False},
]

CHAT_MODELS = ["gemma:4b", "qwen", "llama", "mistral", "deepseek", "gpt-oss"]

_lock = threading.Lock()

# 討論模式設定
DISCUSS_MAX_ROUNDS    = 5      # 最多討論幾輪
DISCUSS_CONSENSUS_SIM = 0.85   # 相似度超過此值視為達成共識


# ── 節點健康檢查 ──────────────────────────────────────────────────────────────

def _check_node(node: dict, force: bool = False) -> bool:
    with _lock:
        now = time.time()
        interval = 15.0 if node["fail_count"] == 0 else min(30.0, 5.0 * node["fail_count"])
        if not force and (now - node["last_check"]) < interval:
            return node["online"]
    try:
        r = requests.get(f"{node['base']}/api/tags", timeout=5)
        online = r.status_code == 200
    except Exception:
        online = False
    with _lock:
        node["online"] = online
        node["last_check"] = time.time()
        if online:
            node["fail_count"] = 0
        else:
            node["fail_count"] += 1
    return online


def is_online(force: bool = False) -> bool:
    return any(_check_node(n, force) for n in NODES)


# ── 相似度計算 ────────────────────────────────────────────────────────────────

def _similarity(text_a: str, text_b: str) -> float:
    """簡單計算兩段文字的字詞重疊相似度"""
    if not text_a or not text_b:
        return 0.0
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    return len(overlap) / max(len(words_a), len(words_b))


# ── 單節點推論 ────────────────────────────────────────────────────────────────

def _infer_node(node: dict, prompt: str, model: str, system: str = "",
                timeout: int = 180) -> str:
    """對單一節點發送推論請求，優先使用節點專屬 model。"""
    model = node.get("model", model)
    use_chat = any(x in model.lower() for x in CHAT_MODELS)
    if use_chat:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model, "messages": messages, "stream": False,
            "options": {"num_predict": 512, "temperature": 0.6}
        }
        api = "chat"
    else:
        combined = f"[系統指令]\n{system}\n\n{prompt}" if system else prompt
        payload = {
            "model": model, "prompt": combined, "stream": False,
            "options": {"num_predict": 512, "temperature": 0.6, "repeat_penalty": 1.1}
        }
        api = "generate"

    try:
        r = requests.post(f"{node['base']}/api/{api}", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if use_chat:
            return data.get("message", {}).get("content", "")
        return data.get("response", "")
    except Exception as e:
        logger.warning(f"[{node['name']}] 推論失敗：{e}")
        return ""


# ── 討論模式 ──────────────────────────────────────────────────────────────────

def _discuss(prompt: str, model: str, system: str, timeout: int) -> str:
    """
    兩台 AI 互相討論直到達成共識。
    A 台先回答 → B 台針對 A 的答案給意見 → A 台整合 → 重複直到共識或達最大輪數
    """
    local_node  = next((n for n in NODES if n["name"] == "local"),  None)
    remote_node = next((n for n in NODES if n["name"] == "remote"), None)

    local_online  = local_node  and _check_node(local_node)
    remote_online = remote_node and _check_node(remote_node)

    # 只有一台在線，直接單獨推論
    if not local_online or not remote_online:
        node = local_node if local_online else remote_node
        logger.info(f"[Ollama] 只有 {node['name']} 在線，跳過討論")
        return _infer_node(node, prompt, model, system, timeout)

    logger.info("[Ollama] 雙 AI 討論模式開始")
    discuss_system = system or "你是一個專業的 AI 助理，請給出精確且有幫助的回答。"

    # A 台先回答
    a_answer = _infer_node(local_node, prompt, model, discuss_system, timeout)
    logger.info(f"[討論 R0] A台回答（{len(a_answer)}字）")

    for round_num in range(1, DISCUSS_MAX_ROUNDS + 1):
        # B 台針對 A 的答案給意見
        b_prompt = (
            f"原始問題：{prompt}\n\n"
            f"A 的回答：{a_answer}\n\n"
            f"請針對 A 的回答提出補充、修正或不同意見。"
            f"若你完全同意 A 的回答，請直接說「我同意」。"
        )
        b_opinion = _infer_node(remote_node, b_prompt, model, discuss_system, timeout)
        logger.info(f"[討論 R{round_num}] B台意見（{len(b_opinion)}字）")

        # 檢查是否達成共識
        if "我同意" in b_opinion or _similarity(a_answer, b_opinion) >= DISCUSS_CONSENSUS_SIM:
            logger.info(f"[討論 R{round_num}] 達成共識，停止討論")
            break

        # A 台整合 B 的意見
        a_prompt = (
            f"原始問題：{prompt}\n\n"
            f"你之前的回答：{a_answer}\n\n"
            f"B 的意見：{b_opinion}\n\n"
            f"請整合以上意見，給出更完整的最終回答。"
        )
        new_answer = _infer_node(local_node, a_prompt, model, discuss_system, timeout)
        logger.info(f"[討論 R{round_num}] A台整合（{len(new_answer)}字）")

        # 檢查 A 整合後是否收斂
        if _similarity(a_answer, new_answer) >= DISCUSS_CONSENSUS_SIM:
            logger.info(f"[討論 R{round_num}] A台答案收斂，停止討論")
            a_answer = new_answer
            break

        a_answer = new_answer

    logger.info(f"[Ollama] 討論完成，最終答案（{len(a_answer)}字）")
    return a_answer


# ── 主推論入口 ────────────────────────────────────────────────────────────────

def safe_infer(
    prompt: str,
    model: str = "qwen2:7b-instruct-q4_0",
    system: str = "",
    timeout: int = 180,
    max_retries: int = 3,
    fallback: str = None,
    discuss: bool = False,
) -> str:
    """
    主推論函式。
    discuss=True  → 兩台討論模式
    discuss=False → 誰有空誰回答（單台）
    """
    if not is_online():
        logger.warning("Ollama all offline")
        return fallback or _offline_response(prompt)

    if discuss:
        return _discuss(prompt, model, system, timeout)

    # 一般模式：找第一台在線的節點推論
    for node in NODES:
        if _check_node(node):
            logger.info(f"[Ollama] 單節點推論：{node['name']}")
            result = _infer_node(node, prompt, model, system, timeout)
            if result:
                return result

    return fallback or _offline_response(prompt)


# ── 離線回應 ──────────────────────────────────────────────────────────────────

def _offline_response(prompt: str) -> str:
    p = prompt.strip().lower()
    if any(w in p for w in ["你好", "嗨", "hi", "hello"]):
        return "你好。（Ollama 目前離線）"
    if any(w in p for w in ["你是誰", "你叫什麼"]):
        return "我是立。（Ollama 目前離線）"
    return "（Ollama 全部離線，請確認 Ollama 已啟動）"


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def get_available_models() -> list:
    models = set()
    for node in NODES:
        try:
            r = requests.get(f"{node['base']}/api/tags", timeout=5)
            for m in r.json().get("models", []):
                models.add(m["name"])
        except Exception:
            pass
    return list(models)


def get_nodes_status() -> str:
    lines = ["Ollama nodes:"]
    for n in NODES:
        _check_node(n, force=True)
        status = "online" if n["online"] else "offline"
        busy = " (busy)" if n["busy"] else ""
        lines.append(f"  {n['name']:8s} {n['base']:35s} {status}{busy}")
    return "\n".join(lines)


def start_background_monitor(interval: int = 30):
    def _loop():
        while True:
            for n in NODES:
                _check_node(n, force=True)
            online = [n["name"] for n in NODES if n["online"]]
            logger.info(f"[Ollama Monitor] online: {online}")
            time.sleep(interval)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    logger.info(f"Ollama monitor started (every {interval}s)")


if __name__ == "__main__":
    print(get_nodes_status())
    models = get_available_models()
    if models:
        print(f"models: {models}")
        result = safe_infer("你好", model=models[0], discuss=True)
        print(f"response: {result[:200]}")
