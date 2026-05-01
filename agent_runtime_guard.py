import threading
import time
import psutil
import os

_running = True


def _guard_loop():

    print("🛡 Runtime Guard Started")

    process = psutil.Process(os.getpid())

    while _running:

        try:
            cpu = process.cpu_percent(interval=1)
            mem = process.memory_info().rss / (1024 * 1024)

            if cpu > 95:
                print("⚠ CPU OVERLOAD DETECTED")

            if mem > 4000:
                print("⚠ MEMORY OVERLOAD DETECTED")

        except Exception as e:
            print(f"Guard error: {e}")

        time.sleep(2)


def start_runtime_guard():
    t = threading.Thread(target=_guard_loop, daemon=True)
    t.start()


# ⭐ 這行是關鍵（讓 core_boot 可呼叫）
def start():
    start_runtime_guard()