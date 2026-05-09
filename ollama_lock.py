"""
ollama_lock.py — Ollama 使用協調器
確保同一時間只有一個任務在使用 Ollama，高優先級可搶占低優先級。

優先級：
  1 = 最高（使用者直接對話）
  2 = 高（工坊任務執行）
  3 = 中（審查、記憶更新）
  4 = 低（interest_reader 自主閱讀）

用法：
  from ollama_lock import acquire, release

  if acquire("interest_reader", priority=4):
      try:
          # 呼叫 Ollama
      finally:
          release("interest_reader")
"""

import json
import os
import pathlib
import threading
import time
from datetime import datetime

_LOCK_FILE = pathlib.Path(__file__).parent / "workshop_data" / "memory" / "ollama_lock.json"
_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

_local_lock = threading.Lock()  # 同進程內的鎖
_TIMEOUT    = 600               # 最長持有 10 分鐘，超過視為異常自動釋放


def _read() -> dict:
    try:
        if _LOCK_FILE.exists():
            return json.loads(_LOCK_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"owner": None, "priority": 99, "since": 0}


def _write(data: dict):
    try:
        _LOCK_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def acquire(owner: str, priority: int = 4, timeout: int = 120) -> bool:
    """
    嘗試取得 Ollama 使用權。
    owner:    呼叫者名稱（"chat"/"workshop"/"interest_reader" 等）
    priority: 數字越小越優先
    timeout:  最多等幾秒，超過回傳 False
    回傳 True 代表取得使用權。
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        with _local_lock:
            state = _read()
            now   = time.time()

            # 沒有人在用，或鎖超時（異常），直接取得
            if state["owner"] is None or (now - state["since"]) > _TIMEOUT:
                _write({"owner": owner, "priority": priority, "since": now})
                return True

            # 自己已經持有
            if state["owner"] == owner:
                return True

            # 優先級比當前持有者高（數字小），搶占
            if priority < state["priority"]:
                _write({"owner": owner, "priority": priority, "since": now})
                return True

        # 等待後重試
        time.sleep(2)

    return False  # 等待超時


def release(owner: str):
    """釋放 Ollama 使用權。"""
    with _local_lock:
        state = _read()
        if state["owner"] == owner:
            _write({"owner": None, "priority": 99, "since": 0})


def current_owner() -> str | None:
    """查看目前誰在使用 Ollama。"""
    return _read().get("owner")


def is_busy() -> bool:
    """Ollama 是否正在被使用。"""
    state = _read()
    if state["owner"] is None:
        return False
    # 超時視為空閒
    return (time.time() - state["since"]) < _TIMEOUT
