import requests

OLLAMA_URL = "http://localhost:11434/api/chat"


def infer(prompt, model="deepseek-r1:1.5b", system=None, timeout=120):

    messages = []

    if system:
        messages.append({
            "role": "system",
            "content": system
        })

    messages.append({
        "role": "user",
        "content": prompt
    })

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.6,
            "num_ctx": 8192
        }
    }

    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()["message"]["content"]

    except Exception as e:
        return f"[LOCAL_INFER_ERROR] {str(e)}"