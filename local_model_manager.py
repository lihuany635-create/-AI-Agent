import requests

OLLAMA_BASE = "http://localhost:11434"


def initialize_local_models():
    """
    確認本地模型服務是否可用
    """

    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)

        if r.status_code != 200:
            raise RuntimeError("Ollama not responding")

        models = [m["name"] for m in r.json().get("models", [])]

        if not models:
            print("⚠ No local models found")
        else:
            print(f"✔ Local models detected: {models}")

    except Exception as e:
        raise RuntimeError(
            f"❌ Local model runtime not available → {str(e)}"
        )


# ⭐ Boot interface 對齊
def preload():
    print("📦 Initializing Local Model Runtime...")
    initialize_local_models()