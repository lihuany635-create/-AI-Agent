# diagnose.py — 放到 AI-Agent 資料夾執行，找出 Lobster_Core 載入失敗的原因
# 使用方式：python diagnose.py

import sys
import traceback

print("=" * 55)
print("立 AI 系統診斷工具")
print("=" * 55)

results = []

def test(label, fn):
    try:
        fn()
        results.append(("OK", label))
        print(f"  [OK] {label}")
    except Exception as e:
        results.append(("FAIL", label, str(e)))
        print(f"  [FAIL] {label}")
        print(f"         原因：{e}")

# ── 1. 基本依賴 ───────────────────────────────────────────────────────────────
print("\n【第一步：基本套件】")
test("requests",    lambda: __import__("requests"))
test("PyQt6",       lambda: __import__("PyQt6"))
test("psutil",      lambda: __import__("psutil"))

# ── 2. 本地模組 ───────────────────────────────────────────────────────────────
print("\n【第二步：本地模組】")
modules = [
    "config", "agent_logger", "cognition_state_manager",
    "os_controller", "reflex_memory", "episodic_memory",
    "prompt_engine", "learning_engine", "terminal_editor",
    "error_detector", "repair_engine", "reasoning_supervisor",
    "repair_trigger", "repair_loop_controller",
    "reflex_engine", "intent_router",
    "task_capability_registry",
]
for m in modules:
    test(m, lambda m=m: __import__(m))

# ── 3. Lobster_Core 本身 ──────────────────────────────────────────────────────
print("\n【第三步：Lobster_Core】")
try:
    import Lobster_Core
    print("  [OK] Lobster_Core import 成功")
    lc = Lobster_Core.LobsterCore()
    print("  [OK] LobsterCore() 初始化成功")
    results.append(("OK", "Lobster_Core"))
except Exception as e:
    print(f"  [FAIL] Lobster_Core")
    print(f"         原因：{e}")
    traceback.print_exc()
    results.append(("FAIL", "Lobster_Core", str(e)))

# ── 4. Ollama 連線 ────────────────────────────────────────────────────────────
print("\n【第四步：Ollama 連線】")
try:
    import requests
    r = requests.get("http://localhost:11434/api/tags", timeout=3)
    if r.status_code == 200:
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"  [OK] Ollama 在線，模型：{models or '（無模型）'}")
        results.append(("OK", "Ollama"))
    else:
        print(f"  [WARN] Ollama 回應異常：{r.status_code}")
except Exception as e:
    print(f"  [FAIL] Ollama 無法連線：{e}")
    print("         請確認有執行 'ollama serve'")
    results.append(("FAIL", "Ollama", str(e)))

# ── 5. config.py SYSTEM_KEY ───────────────────────────────────────────────────
print("\n【第五步：config.py】")
try:
    import config
    if hasattr(config, "SYSTEM_KEY"):
        print(f"  [OK] SYSTEM_KEY 存在")
    else:
        print(f"  [FAIL] config.py 缺少 SYSTEM_KEY")
        print("         請在 config.py 加上：SYSTEM_KEY = 'LOBSTER_CORE_KEY'")
except Exception as e:
    print(f"  [FAIL] config.py 載入失敗：{e}")

# ── 總結 ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
fails = [r for r in results if r[0] == "FAIL"]
if not fails:
    print("✅ 全部通過！Lobster_Core 應該可以正常載入")
    print("   請重新啟動 desktop_agent.py")
else:
    print(f"❌ 發現 {len(fails)} 個問題：")
    for f in fails:
        print(f"   - {f[1]}: {f[2] if len(f) > 2 else ''}")
    print("\n最可能的修復方式：")
    for f in fails:
        name = f[1]
        if name == "config":
            print("  → config.py：確認檔案存在且沒有 BOM，加上 SYSTEM_KEY = 'LOBSTER_CORE_KEY'")
        elif name == "Ollama":
            print("  → 開啟命令提示字元執行：ollama serve")
        elif name == "requests":
            print("  → pip install requests")
        elif name == "psutil":
            print("  → pip install psutil")
        else:
            print(f"  → {name}：檢查此檔案是否存在於 AI-Agent 資料夾")
print("=" * 55)
