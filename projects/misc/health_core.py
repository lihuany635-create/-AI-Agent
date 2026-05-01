# health_core.py
# 健康檢查核心模組:負責確認 Ollama 服務與模型的運行狀態
# 提供帶快取機制的狀態查詢,供 vision_router.py 做路由決策使用
import time
try:
    import requests
except ImportError:
    raise ImportError("缺少必要套件:requests,請執行 pip install requests")
# ────────────────────────────────────────────
# 常數設定
# ────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 2.5          # 單位:秒
DEFAULT_MODEL   = "gemma3:4b"
CACHE_TTL       = 8.0          # 快取有效期,單位:秒
# ────────────────────────────────────────────
# 基本檢查函式
# ────────────────────────────────────────────
def check_ollama() -> dict:
    """
    打 Ollama 根路徑確認服務是否存活.
    回傳 dict 結構:
        status  : "ok" | "timeout" | "unreachable" | "error"
        message : 人類可讀的說明字串
        latency_ms : 回應延遲(毫秒),服務不通時為 None
    """
    url = OLLAMA_BASE_URL
    start = time.monotonic()
    try:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        if resp.status_code == 200:
            return {
                "status": "ok",
                "message": "Ollama 服務正常運行",
                "latency_ms": latency_ms,
            }
        else:
            return {
                "status": "error",
                "message": f"Ollama 回傳非預期狀態碼:{resp.status_code}",
                "latency_ms": latency_ms,
            }
    except requests.exceptions.Timeout:
        return {
            "status": "timeout",
            "message": f"Ollama 服務回應逾時(>{DEFAULT_TIMEOUT}s),服務可能過載",
            "latency_ms": None,
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "unreachable",
            "message": "無法連線 Ollama,服務可能尚未啟動",
            "latency_ms": None,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"未預期錯誤:{exc}",
            "latency_ms": None,
        }
def check_ollama_model(model_name: str = DEFAULT_MODEL) -> dict:
    """
    打 /api/tags 確認指定模型是否已載入至 Ollama.
    參數:
        model_name : 要確認的模型名稱,預設為 gemma3:4b
    回傳 dict 結構:
        status       : "ok" | "not_found" | "unreachable" | "error"
        message      : 說明字串
        loaded_models: 已載入模型名稱清單(服務不通時為空清單)
    """
    url = f"{OLLAMA_BASE_URL}/api/tags"
    try:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # /api/tags 回傳格式:{"models": [{"name": "...", ...}, ...]}
        loaded_models = [m.get("name", "") for m in data.get("models", [])]
        # 模型名稱可能含 tag,例如 "gemma3:4b",做前綴比對以增加相容性
        matched = any(
            m == model_name or m.startswith(model_name.split(":")[0])
            for m in loaded_models
        )
        if matched:
            return {
                "status": "ok",
                "message": f"模型 {model_name} 已載入",
                "loaded_models": loaded_models,
            }
        else:
            return {
                "status": "not_found",
                "message": f"模型 {model_name} 未在 Ollama 中找到,請先執行 ollama pull {model_name}",
                "loaded_models": loaded_models,
            }
    except requests.exceptions.Timeout:
        return {
            "status": "unreachable",
            "message": "查詢模型清單逾時",
            "loaded_models": [],
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "unreachable",
            "message": "無法連線 Ollama,服務可能尚未啟動",
            "loaded_models": [],
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"查詢模型清單時發生錯誤:{exc}",
            "loaded_models": [],
        }
def get_ollama_status(model_name: str = DEFAULT_MODEL) -> dict:
    """
    整合服務健康與模型載入狀態,回傳完整資訊供 vision_router.py 使用.
    回傳 dict 結構:
        service_ok   : bool,服務是否存活
        model_ok     : bool,指定模型是否已載入
        ready        : bool,service_ok AND model_ok(可直接用於路由判斷)
        service      : check_ollama() 的完整結果
        model        : check_ollama_model() 的完整結果
    """
    service_result = check_ollama()
    service_ok = service_result["status"] == "ok"
    # 服務不通時跳過模型檢查,節省等待時間
    if service_ok:
        model_result = check_ollama_model(model_name)
        model_ok = model_result["status"] == "ok"
    else:
        model_result = {
            "status": "skipped",
            "message": "服務未啟動,跳過模型檢查",
            "loaded_models": [],
        }
        model_ok = False
    return {
        "service_ok": service_ok,
        "model_ok":   model_ok,
        "ready":      service_ok and model_ok,
        "service":    service_result,
        "model":      model_result,
    }
# ────────────────────────────────────────────
# 帶 TTL 快取的健康狀態查詢類別
# ────────────────────────────────────────────
class OllamaHealthCache:
    """
    封裝帶 TTL 快取的 Ollama 健康狀態查詢.
    避免 vision_router.py 每次路由前都發送 HTTP 請求造成延遲.
    使用方式:
        cache = OllamaHealthCache()
        status = cache.get_status()   # 第一次發請求
        status = cache.get_status()   # TTL 內直接回傳快取
    """
    def __init__(self, model_name: str = DEFAULT_MODEL, ttl: float = CACHE_TTL):
        self._model_name  = model_name
        self._ttl         = ttl
        self._cached      = None      # 上次查詢結果
        self._cached_at   = 0.0       # 上次查詢的時間戳
    def _is_expired(self) -> bool:
        """判斷快取是否已過期."""
        return (time.monotonic() - self._cached_at) > self._ttl
    def get_status(self, force_refresh: bool = False) -> dict:
        """
        取得 Ollama 完整健康狀態.
        TTL 內直接回傳快取結果;超過 TTL 或強制刷新時重新查詢.
        參數:
            force_refresh : 設為 True 強制繞過快取立即重新查詢
        """
        if force_refresh or self._cached is None or self._is_expired():
            self._cached    = get_ollama_status(self._model_name)
            self._cached_at = time.monotonic()
        # 在結果中附上快取資訊,方便除錯
        result = dict(self._cached)
        result["from_cache"]   = not (force_refresh or self._cached is None)
        result["cache_age_ms"] = round((time.monotonic() - self._cached_at) * 1000, 1)
        return result
    def invalidate(self):
        """手動清除快取,下次呼叫 get_status() 時強制重新查詢."""
        self._cached    = None
        self._cached_at = 0.0
# ────────────────────────────────────────────
# 模組測試入口
# ────────────────────────────────────────────
if __name__ == "__main__":
    import json
    print("=" * 50)
    print("【1】測試 check_ollama()")
    result = check_ollama()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n" + "=" * 50)
    print(f"【2】測試 check_ollama_model('{DEFAULT_MODEL}')")
    result = check_ollama_model(DEFAULT_MODEL)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n" + "=" * 50)
    print("【3】測試 get_ollama_status()")
    result = get_ollama_status(DEFAULT_MODEL)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n" + "=" * 50)
    print("【4】測試 OllamaHealthCache(連續兩次,第二次應命中快取)")
    cache = OllamaHealthCache()
    first = cache.get_status()
    print(f"第一次 from_cache={first['from_cache']},ready={first['ready']}")
    second = cache.get_status()
    print(f"第二次 from_cache={second['from_cache']},cache_age_ms={second['cache_age_ms']}")
    print("\n強制刷新:")
    forced = cache.get_status(force_refresh=True)
    print(f"強制刷新 from_cache={forced['from_cache']},ready={forced['ready']}")