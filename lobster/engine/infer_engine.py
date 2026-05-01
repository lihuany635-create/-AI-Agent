# lobster/engine/infer_engine.py
import threading
import requests

try:
    from ollama_guard import safe_infer
    _USE_GUARD = True
except ImportError:
    _USE_GUARD = False

try:
    from agent_logger import get_logger
    logger = get_logger("lobster.engine.infer")
except ImportError:
    import logging
    logger = logging.getLogger("lobster.engine.infer")

try:
    from youtube_bridge import handle_youtube_input, extract_youtube_url
    _USE_YOUTUBE = True
except ImportError:
    _USE_YOUTUBE = False

try:
    from claude_desktop_bridge import get_bridge as get_claude_bridge
    _USE_CLAUDE_BRIDGE = True
except ImportError:
    _USE_CLAUDE_BRIDGE = False

try:
    from model_selector import get_selector
    _USE_SELECTOR = True
except ImportError:
    _USE_SELECTOR = False

from lobster.utils.identity import build_identity
from lobster.tools.file_tool import try_read_file
from lobster.integration.push import push_to_phone


def infer(model: str, url: str, prompt_engine, prompt: str, system: str = "") -> str:
    sys_prompt = system or build_identity(prompt_engine)
    if _USE_GUARD:
        return safe_infer(prompt=prompt, model=model, system=sys_prompt, timeout=180, max_retries=3)
    try:
        r = requests.post(url, json={
            "model": model, "prompt": prompt,
            "system": sys_prompt, "stream": False,
        }, timeout=180)
        r.raise_for_status()
        return r.json().get("response", "")
    except Exception as e:
        return "[LLM ERROR] " + str(e)


def think(core, text: str) -> str:
    if _USE_YOUTUBE and extract_youtube_url(text):
        def _infer_fn(prompt): return infer(core.model, core.url, core.prompt_engine, prompt)
        result = handle_youtube_input(text, _infer_fn)
        if result:
            push_to_phone(text, result)
            return result

    recent = core.episodic.search_recent(10)
    for ep in reversed(recent):
        if ep["input"].strip() == text.strip() and ep.get("response"):
            resp = ep["response"]
            if "[LLM ERROR]" not in resp and len(resp) > 5:
                logger.info(f"[think] 快取命中：{text[:30]}")
                return resp

    file_content = try_read_file(text)
    system = build_identity(core.prompt_engine)
    prompt = core.prompt_engine.build_prompt(text, core.episodic)

    if file_content:
        prompt = f"[檔案內容]（使用者問的檔案，根據這個內容回答）\n{file_content}\n\n{prompt}"

    if _USE_SELECTOR:
        selected = get_selector().select(text)
        if selected != core.model:
            logger.info(f"[think] 切換模型：{core.model} → {selected}")
            core.model = selected

    logger.info(f"[think] 推論（{core.model}）：{text[:40]}")
    result = infer(core.model, core.url, core.prompt_engine, prompt, system)

    if result and "[LLM ERROR]" not in result:
        push_to_phone(text, result)

    return result
