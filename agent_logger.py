"""
agent_logger.py - 統一日誌系統
功能：
  - 分級日誌（DEBUG / INFO / WARNING / ERROR / CRITICAL）
  - 同時輸出到終端機 + 寫入檔案
  - 每天自動換新日誌檔
  - 支援模組名稱標記，方便追蹤是哪個模組發出的訊息
使用方式：
    from agent_logger import get_logger
    logger = get_logger("repair_engine")
    logger.info("開始修復...")
    logger.error("修復失敗", exc_info=True)
"""

import logging
import logging.handlers
import pathlib
import sys
from datetime import datetime

# 日誌存放目錄
LOG_DIR = pathlib.Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# 日誌格式
CONSOLE_FORMAT = "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s"
FILE_FORMAT    = "[%(asctime)s] %(levelname)-8s [%(name)s] %(filename)s:%(lineno)d - %(message)s"
DATE_FORMAT    = "%H:%M:%S"

# 顏色（終端機用）
COLORS = {
    "DEBUG":    "\033[36m",   # 青色
    "INFO":     "\033[32m",   # 綠色
    "WARNING":  "\033[33m",   # 黃色
    "ERROR":    "\033[31m",   # 紅色
    "CRITICAL": "\033[35m",   # 紫色
    "RESET":    "\033[0m",
}

class ColorFormatter(logging.Formatter):
    """終端機彩色輸出"""
    def format(self, record):
        color = COLORS.get(record.levelname, COLORS["RESET"])
        reset = COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)

class AgentLogger:
    """集中管理所有模組的 logger"""
    _loggers: dict = {}
    _initialized: bool = False
    _root_logger: logging.Logger = None

    @classmethod
    def _init_root(cls):
        if cls._initialized:
            return
        root = logging.getLogger("Agent")
        root.setLevel(logging.DEBUG)

        # 終端機 handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(ColorFormatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT))

        # 檔案 handler（每天換檔，保留 7 天）
        log_file = LOG_DIR / f"agent_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file, when="midnight", backupCount=7, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))

        # 錯誤單獨存一份
        error_file = LOG_DIR / "agent_errors.log"
        error_handler = logging.FileHandler(error_file, encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))

        root.addHandler(console_handler)
        root.addHandler(file_handler)
        root.addHandler(error_handler)

        cls._root_logger = root
        cls._initialized = True

    @classmethod
    def get(cls, module_name: str) -> logging.Logger:
        """取得指定模組的 logger"""
        cls._init_root()
        if module_name not in cls._loggers:
            logger = logging.getLogger(f"Agent.{module_name}")
            cls._loggers[module_name] = logger
        return cls._loggers[module_name]


def get_logger(module_name: str) -> logging.Logger:
    """快速取得 logger 的捷徑函式"""
    return AgentLogger.get(module_name)


# ── 使用範例 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger = get_logger("test")
    logger.debug("這是 DEBUG 訊息（只寫入檔案，不顯示在終端機）")
    logger.info("Agent 系統啟動")
    logger.warning("記憶體用量偏高")
    logger.error("修復引擎發生錯誤")
    logger.critical("核心模組崩潰！")
    print("\n日誌已寫入 logs/ 資料夾")
