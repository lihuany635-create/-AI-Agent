"""
dev_brain.py — 立AI大腦接入層
把 LobsterCore 接入 dev_tool 的 BrainInterface。

使用方式：
    from dev_brain import LobsterBrain, setup_dev_tool
    setup_dev_tool(lobster_core, bot, allowed_ids)
"""

from dev_tool import BrainInterface, TelegramNotifier, get_tool, set_brain

try:
    from agent_logger import get_logger
    logger = get_logger("dev_brain")
except ImportError:
    import logging
    logger = logging.getLogger("dev_brain")


class LobsterBrain(BrainInterface):
    """
    立AI大腦接入實作。
    - raw=False：用 Ollama 本地推論（_infer）
    - raw=True：需要結構化輸出，用 claude_desktop_bridge 問 Claude
    """

    def __init__(self, lobster_core):
        self.core = lobster_core

    def is_available(self) -> bool:
        try:
            from ollama_guard import is_online
            return is_online()
        except Exception:
            return True  # 假設可用，讓推論自己回傳錯誤

    def ask(self, prompt: str, raw: bool = False) -> str:
        if raw:
            return self._ask_claude(prompt)
        else:
            return self._ask_local(prompt)

    def _ask_local(self, prompt: str) -> str:
        """用 Ollama 本地推論，離線時嘗試喚醒"""
        # 先確認 Ollama 是否在線，不在線就嘗試啟動
        try:
            from ollama_guard import is_online, start_background_monitor
            if not is_online(force=True):
                logger.warning("[DevBrain] Ollama 離線，嘗試啟動...")
                self._try_start_ollama()
                import time
                # 等最多 30 秒讓 Ollama 上線
                for _ in range(10):
                    time.sleep(3)
                    if is_online(force=True):
                        logger.info("[DevBrain] Ollama 已上線")
                        break
                else:
                    logger.warning("[DevBrain] Ollama 啟動超時，改用 Claude")
                    return self._ask_claude(prompt)
        except Exception:
            pass
        try:
            result = self.core._infer(prompt)
            logger.info(f"[DevBrain] 本地推論完成（{len(result)} 字）")
            return result
        except Exception as e:
            logger.warning(f"[DevBrain] 本地推論失敗：{e}，改用 Claude")
            return self._ask_claude(prompt)

    def _try_start_ollama(self):
        """嘗試啟動 Ollama"""
        import subprocess, pathlib
        pass  # 分散式推論已移除
        try:
            # 直接啟動 ollama serve
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("[DevBrain] 已嘗試啟動 ollama serve")
        except Exception as e:
            logger.warning(f"[DevBrain] 無法啟動 Ollama：{e}")

    def _ask_claude(self, prompt: str) -> str:
        """用 claude_desktop_bridge 問 Claude（需要結構化輸出時）"""
        try:
            from claude_desktop_bridge import get_bridge
            bridge = get_bridge()
            result = bridge.ask(prompt, auto_learn=False, raw=True, max_chars=0)
            if not result or result.startswith("❌"):
                logger.warning("[DevBrain] Claude 橋接失敗，改用本地推論")
                return self._ask_local(prompt)
            logger.info(f"[DevBrain] Claude 回答完成（{len(result)} 字）")
            return result
        except Exception as e:
            logger.warning(f"[DevBrain] Claude 橋接失敗：{e}，改用本地推論")
            return self._ask_local(prompt)


def setup_dev_tool(lobster_core, bot=None, allowed_ids: list = None,
                   output_dir: str = "projects/output") -> object:
    """
    一次完成接入：設定大腦 + 通知器 + 回傳 tool 實例。

    用法：
        tool = setup_dev_tool(lobster_core, bot, allowed_ids)
        tool.start("幫我做一個視覺辨識系統")
    """
    brain = LobsterBrain(lobster_core)
    set_brain(brain)

    tool = get_tool()

    if bot and allowed_ids:
        tool.set_notifier(TelegramNotifier(bot, allowed_ids))
        logger.info("[DevBrain] TelegramNotifier 已設定")
    else:
        from dev_tool import PrintNotifier
        tool.set_notifier(PrintNotifier())
        logger.info("[DevBrain] PrintNotifier 已設定（測試模式）")

    logger.info(f"[DevBrain] dev_tool 接入完成，AI可用：{brain.is_available()}")
    return tool
