"""
ChatGPT Bridge (Claude-style control, ChatGPT backend)
--------------------------------------------------------
This is a modified version of ClaudeDesktopBridge logic,
but adapted to operate ChatGPT instead of Claude.

Key changes:
- Uses chatgpt.com instead of claude.ai
- Removes OCR, uses clipboard only
- Keeps new-tab clean session behavior
- Keeps stable-read mechanism
"""

import time
import subprocess
import pyautogui
import pyperclip
import pygetwindow as gw

CHATGPT_URL = "https://chatgpt.com"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

WAIT_PAGE_LOAD = 5.0
WAIT_RESPONSE = 120.0
CHECK_INTERVAL = 3.0
MIN_WAIT = 15.0

INPUT_POS = (748, 554) 


class ChatGPTBridgeV2:

    def ask(self, question: str) -> str:
        self._open_chatgpt()
        time.sleep(WAIT_PAGE_LOAD)

        self._type_question(question)
        time.sleep(2)

        answer = self._wait_and_read()
        return answer

    # ─────────────────────

    def _open_chatgpt(self):
        subprocess.Popen([EDGE_EXE, "--new-tab", CHATGPT_URL])
        time.sleep(WAIT_PAGE_LOAD)

        for _ in range(5):
            wins = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]
            if wins:
                win = wins[-1]
                win.restore()
                win.maximize()
                win.activate()
                return
            time.sleep(1)

    # ─────────────────────

    def _type_question(self, question: str):
        full = f"{{立}} 請用純文字回答：{question}"
        pyperclip.copy(full)

        x, y = INPUT_POS
        pyautogui.click(x, y)
        time.sleep(0.5)

        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.5)

        # 驗證貼上成功
        pyautogui.hotkey("ctrl", "a")
        pyautogui.hotkey("ctrl", "c")
        pasted = pyperclip.paste()

        if "{立}" not in pasted:
            raise RuntimeError("輸入失敗")

        pyautogui.press("enter")

    # ─────────────────────

    def _wait_and_read(self) -> str:
        prev = ""
        stable = 0
        elapsed = 0

        time.sleep(MIN_WAIT)
        elapsed += MIN_WAIT

        while elapsed < WAIT_RESPONSE:
            text = self._read_clipboard()

            if len(text) > 50:
                if text == prev:
                    stable += 1
                    if stable >= 3:
                        break
                else:
                    stable = 0
                    prev = text

            time.sleep(CHECK_INTERVAL)
            elapsed += CHECK_INTERVAL

        return self._extract(text)

    # ─────────────────────

    def _read_clipboard(self) -> str:
        pyautogui.click(1000, 500)
        time.sleep(0.3)

        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.5)

        return pyperclip.paste()

    # ─────────────────────

    def _extract(self, text: str) -> str:
        marker = "{立}"
        idx = text.rfind(marker)

        if idx != -1:
            text = text[idx + len(marker):]

        lines = text.splitlines()
        cleaned = []
        skip = True

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if skip:
                skip = False
                continue

            if "ChatGPT" in line or "Send a message" in line:
                continue

            cleaned.append(line)

        return "\n".join(cleaned).strip()


# ─────────────────────

if __name__ == "__main__":
    b = ChatGPTBridgeV2()
    q = input("問什麼：")
    print(b.ask(q))
