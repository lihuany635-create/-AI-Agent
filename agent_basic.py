import logging
import config

from Lobster_Core import LobsterCore

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("Lobster-Agent")


class BasicAgent:

    def __init__(self):
        # 🔑 系統 KEY 驗證（生命層）
        if not hasattr(config, "SYSTEM_KEY"):
            raise RuntimeError("config.py 缺少 SYSTEM_KEY")

        self.system_key = config.SYSTEM_KEY
        logger.info("🔑 Agent 已取得系統生命 Key")

        # 🧠 建立核心認知
        self.core = LobsterCore()

    def start(self):
        logger.info("🧠 Agent 認知核心啟動")
        return self.core


def start():
    agent = BasicAgent()
    return agent.start()