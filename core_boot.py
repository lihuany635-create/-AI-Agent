import time, threading, subprocess, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="ignore") if hasattr(sys.stdout, "reconfigure") else None

print("AI Runtime Booting...")

# 0. Ollama 連線守護
try:
    from ollama_guard import is_online, start_background_monitor, get_available_models
    online = is_online(force=True)
    print(f"Ollama: {'在線' if online else '離線（將以離線模式運行）'}")
    if online:
        print(f"   可用模型: {get_available_models()}")
    start_background_monitor(interval=30)
except Exception as e:
    print(f"[BOOT] OllamaGuard failed: {e}")

# 1. 系統健康檢查
try:
    import system_health_guard
    system_health_guard.run_health_guard()
    print("HealthGuard OK")
except Exception as e:
    print(f"[BOOT] HealthGuard skipped: {e}")

# 2. Runtime Guard
try:
    import agent_runtime_guard
    agent_runtime_guard.start()
    print("Runtime Guard Online")
except Exception as e:
    print(f"[BOOT] RuntimeGuard skipped: {e}")

# 3. 記憶系統
try:
    import memory_engine
    import cognition_state_manager
    print("Memory Systems OK")
except Exception as e:
    print(f"[BOOT] Memory skipped: {e}")

# 4. 向量庫
try:
    import local_vector_store
    print("Vector Store OK")
except Exception as e:
    print(f"[BOOT] VectorStore skipped: {e}")

# 5. 模型管理器
try:
    import local_model_manager
    local_model_manager.preload()
    print("Model Manager OK")
except Exception as e:
    print(f"[BOOT] ModelManager skipped: {e}")

# 6. UI（主程式）
print("Starting Desktop Agent UI...")
subprocess.Popen(["py", "desktop_agent.py"],
    cwd=os.path.dirname(os.path.abspath(__file__)))

# 7. Telegram Bot
try:
    from telegram_bot import start_bot
    print("Starting Telegram Bot...")
    start_bot(background=True)
except Exception as e:
    print(f"[BOOT] TelegramBot skipped: {e}")

# 8. 自我診斷排程
try:
    from self_healer import get_healer
    get_healer().start_auto_heal(interval_hours=24)
    print("Self Healer scheduled (every 24h)")
except Exception as e:
    print(f"[BOOT] SelfHealer skipped: {e}")

print("AI Runtime Online")
