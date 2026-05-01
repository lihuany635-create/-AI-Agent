import sys
import traceback

REQUIRED_KEY = "LOBSTER_CORE_KEY"
SYSTEM_KEY   = "LOBSTER_CORE_KEY"  # agent_basic.py 需要此變數

def verify_key():
    try:
        import config
    except Exception:
        print("❌ 找不到系統鑰匙 config.py")
        sys.exit(1)

    if not hasattr(config, "SYSTEM_KEY"):
        print("❌ config 缺少 SYSTEM_KEY")
        sys.exit(1)

    if config.SYSTEM_KEY != REQUIRED_KEY:
        print("🚫 非法鑰匙，禁止啟動 AI")
        sys.exit(1)

    print("🔑 系統鑰匙驗證成功")
    return config

def start_agent():
    try:
        import agent_basic
        print("🚀 啟動 AI Agent")
        agent_basic.main()
    except Exception:
        print("🔥 Agent 啟動失敗")
        traceback.print_exc()
        sys.exit(1)

def main():
    print("===== LOBSTER SYSTEM BOOT =====")

    verify_key()
    start_agent()

    print("✅ 系統結束")

if __name__ == "__main__":
    main()