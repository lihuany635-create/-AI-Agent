# chatgpt_desktop_bridge.py — 立 AI × ChatGPT 桌面橋接
# 流程：立 AI 問題 → 切換到 ChatGPT → 輸入問題 → 等待回答 → 讀取 → 存入記憶庫
# 依賴：pyautogui, pyperclip, pygetwindow, requests
# 前提：Edge/Chrome 已開啟 chatgpt.com 並登入

import sys as _sys_top
_PKG_311     = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
_PKG_311_W32 = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages\win32"
_PKG_314     = r"C:\Users\ACER\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages"
_PKG_314_W32 = r"C:\Users\ACER\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\win32"
for _p in [_PKG_311, _PKG_311_W32, _PKG_314, _PKG_314_W32]:
    if _p not in _sys_top.path:
        _sys_top.path.insert(0, _p)

try:
    import win32gui as _win32gui_preload
    import win32con as _win32con_preload
    _HAS_WIN32 = True
except Exception as _w32e:
    _HAS_WIN32 = False

def _focus_window_by_title(keyword: str) -> bool:
    try:
        import subprocess as _sp
        ps_script = f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinHelper {{
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmd);
}}
"@
$procs = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{keyword}*' }}
if ($procs) {{
    $hwnd = $procs[0].MainWindowHandle
    [WinHelper]::ShowWindow($hwnd, 3)
    [WinHelper]::SetForegroundWindow($hwnd)
    Write-Output "OK:$($procs[0].MainWindowTitle)"
}} else {{
    Write-Output "NOT_FOUND"
}}
"""
        result = _sp.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="ignore"
        )
        return result.stdout.strip().startswith("OK:")
    except Exception:
        return False

import time
import re
import pathlib
import datetime

try:
    from agent_logger import get_logger
    logger = get_logger("chatgpt_bridge")
except ImportError:
    import logging
    logger = logging.getLogger("chatgpt_bridge")

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.4
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    _HAS_GW = True
except ImportError:
    _HAS_GW = False

try:
    from long_term_memory import get_memory
    _memory = get_memory()
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

# ── 設定 ─────────────────────────────────────────────────────────────────────
CHATGPT_URL      = "https://chatgpt.com"
WAIT_PAGE_LOAD   = 3.0
WAIT_RESPONSE    = 120.0
CHECK_INTERVAL   = 10.0
MIN_WAIT         = 20.0
STABLE_NEEDED    = 3

# 輸入框座標（實測，與 Claude 相同位置）
INPUT_CANDIDATES = [
    (919, 896),
    (960, 896),
]
# 對話區域安全點
SAFE_X = 980
SAFE_Y = 541

# ── 手機通知 ─────────────────────────────────────────────────────────────────
_TG_TOKEN    = "8659848303:AAFVOzNMDvcwg24uGCU_lzTvgjNlEUeVWx0"
_TG_CHAT_IDS = [8443859030]

def _push(msg: str):
    try:
        import requests as _req
        url = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
        for cid in _TG_CHAT_IDS:
            r = _req.post(url, json={"chat_id": cid, "text": f"🔔 {msg}"}, timeout=10)
            if r.status_code == 200:
                logger.info(f"[ChatGPTBridge] 手機通知成功 → {cid}")
            else:
                logger.warning(f"[ChatGPTBridge] 手機通知失敗：{r.status_code}")
    except Exception as _e:
        logger.warning(f"[ChatGPTBridge] 手機通知例外：{_e}")


# ── 主類別 ───────────────────────────────────────────────────────────────────

class ChatGPTDesktopBridge:
    """透過桌面自動化讓立 AI 與 ChatGPT 對話並學習"""

    def __init__(self):
        self._last_question = ""
        self._last_answer   = ""
        self._stop_chat     = False

    def stop_chat(self):
        """外部呼叫此方法以停止 chat_loop 對話循環"""
        self._stop_chat = True
        logger.info("[ChatGPTBridge] 收到停止指令，將在本輪結束後中止")

    def chat_loop(self, initial_question: str, max_rounds: int = 9999,
                  notify_fn=None, ui_ref=None) -> str:
        """與 ChatGPT 進行多輪對話學習"""
        self._stop_chat = False
        history = []

        if ui_ref:
            try:
                ui_ref.show_chatgpt_chat_bar(True)
            except Exception:
                pass

        question = initial_question

        for round_num in range(1, max_rounds + 1):
            if self._stop_chat:
                logger.info(f"[ChatGPTBridge] 對話循環被停止（第 {round_num} 輪）")
                break

            logger.info(f"[ChatGPTBridge] 對話第 {round_num} 輪：{question[:40]}")
            _push(f"📞 第 {round_num} 輪開始呼叫 ask()")

            answer = self.ask(question, auto_learn=True)
            logger.info(f"[ChatGPTBridge] 第 {round_num} 輪 ask() 已回傳（{len(answer) if answer else 0} 字）")

            bridge_errors = ["需要安裝 pyautogui", "無法開啟 ChatGPT", "輸入失敗", "無法讀取 ChatGPT"]
            if not answer or len(answer.strip()) < 10:
                logger.warning(f"[ChatGPTBridge] 第 {round_num} 輪回傳空白，停止循環")
                break
            if any(err in answer for err in bridge_errors):
                logger.warning(f"[ChatGPTBridge] 第 {round_num} 輪橋接失敗：{answer[:60]}")
                break

            history.append({"q": question, "a": answer})

            if notify_fn:
                try:
                    notify_fn(f"[ChatGPT對話 第{round_num}輪] {answer[:100]}")
                except Exception:
                    pass

            _push(f"✅ 第 {round_num} 輪完成\n問：{question[:40]}\n答：{answer[:80]}...")
            logger.info(f"[ChatGPTBridge] 手機通知已發送（第 {round_num} 輪）")

            if self._stop_chat:
                break

            # ── 生成追問 ──────────────────────────────────────────────────
            logger.info(f"[ChatGPTBridge] 等待 Ollama 空閒...")
            _ollama_ready = False
            for _wait in range(18):
                time.sleep(10)
                try:
                    import requests as _rq
                    r = _rq.get("http://localhost:11434/api/tags", timeout=3)
                    if r.status_code == 200:
                        _ollama_ready = True
                        logger.info(f"[ChatGPTBridge] Ollama 空閒（{(_wait+1)*10} 秒）")
                        break
                except Exception:
                    pass
                if self._stop_chat:
                    break

            invalid_next = ["Ollama", "離線", "請確認", "ERROR", "failed", "超時", "timeout", "無法"]
            _result = [None]

            def _infer():
                try:
                    from ollama_guard import safe_infer
                    prompt = (
                        "請用繁體中文，根據以下對話生成一個深入的後續問題（只輸出問題本身，不要任何解釋或前綴）：\n\n"
                        "問：" + question + "\n答：" + answer[:300] + "\n\n繁體中文後續問題："
                    )
                    _result[0] = safe_infer(prompt, model="qwen2.5:14b", timeout=60)
                    logger.info(f"[ChatGPTBridge] safe_infer 回傳：{repr(_result[0][:60]) if _result[0] else 'None'}")
                except Exception as e:
                    logger.warning(f"[ChatGPTBridge] safe_infer 失敗：{e}")

            import threading
            t = threading.Thread(target=_infer, daemon=True)
            t.start()
            t.join(timeout=70)

            def _make_fallback(ans: str, q: str) -> str:
                words = re.findall(r'[\u4e00-\u9fff]{4,8}', ans)
                words = [w for w in words if w not in q]
                seen  = set()
                unique = [w for w in words if not (w in seen or seen.add(w))]
                keyword = unique[round_num % len(unique)] if unique else q[:10]
                angles = [
                    f"{keyword}的底層實作原理是什麼？",
                    f"如何在生產環境中正確使用{keyword}？",
                    f"{keyword}有哪些進階用法？",
                    f"為什麼{keyword}會被設計成現在這樣？",
                    f"{keyword}在不同語言或框架間有何差異？",
                    f"使用{keyword}時最常見的陷阱是什麼？",
                ]
                return angles[round_num % len(angles)]

            if t.is_alive() or not _result[0]:
                next_question = _make_fallback(answer, question)
                logger.info(f"[ChatGPTBridge] 使用備用追問：{next_question}")
            else:
                next_question = _result[0].strip().strip("？?。.")
                if any(kw in next_question for kw in invalid_next) or len(next_question) < 5:
                    next_question = _make_fallback(answer, question)
                    logger.info(f"[ChatGPTBridge] 追問無效，使用備用：{next_question}")

            logger.info(f"[ChatGPTBridge] 追問：{next_question[:60]}")
            question = next_question

        # 隱藏停止按鈕
        if ui_ref:
            try:
                ui_ref.show_chatgpt_chat_bar(False)
            except Exception:
                pass

        summary = f"完成 {len(history)} 輪 ChatGPT 對話學習，已存入記憶庫"

        rounds  = len(history)
        first_q = history[0]["q"][:40] if history else initial_question[:40]
        last_q  = history[-1]["q"][:40] if rounds > 1 else ""
        _push(
            f"🎓 ChatGPT 對話學習完成\n\n"
            f"共完成：{rounds} 輪\n"
            f"起始問題：{first_q}\n"
            + (f"最後問題：{last_q}\n" if rounds > 1 else "")
            + "\n所有回答已存入記憶庫"
        )
        logger.info("[ChatGPTBridge] 已發送完成通知到手機")
        return summary

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def ask(self, question: str, auto_learn: bool = True) -> str:
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui：pip install pyautogui"

        logger.info(f"[ChatGPTBridge] 開始問 ChatGPT：{question[:50]}")

        result = self._open_chatgpt()
        if result != "ok":
            return f"❌ 無法開啟 ChatGPT：{result}"

        time.sleep(WAIT_PAGE_LOAD)

        result = self._type_question(question)
        if result != "ok":
            return f"❌ 輸入失敗：{result}"

        time.sleep(2.0)
        self._focus_window()
        time.sleep(1.5)
        answer = self._wait_and_read_answer()
        if not answer:
            return "❌ 無法讀取 ChatGPT 的回答（等待超時）"

        self._last_question = question
        self._last_answer   = answer

        logger.info(f"[ChatGPTBridge] 取得回答（{len(answer)} 字）前50字：{repr(answer[:50])}")

        if auto_learn and _HAS_MEMORY:
            self._learn(question, answer)

        logger.info("[ChatGPTBridge] ask() 準備 return")
        return answer

    def learn_correction(self, correction: str) -> str:
        if not self._last_question:
            return "沒有最近的問答記錄可以糾正"
        if _HAS_MEMORY:
            knowledge = f"{self._last_question} → {correction}"
            _memory.store(knowledge, tags=["chatgpt_corrected", "user_teach"], importance=9, source="chatgpt_bridge_correction")
            _memory.store(correction, tags=["chatgpt_corrected", "user_teach"], importance=9, source="chatgpt_bridge_correction")
            logger.info(f"[ChatGPTBridge] 糾正已存入記憶庫：{correction[:50]}")
            return f"✅ 已學習糾正：{correction[:80]}"
        return "記憶庫未載入"

    # ── 開啟 ChatGPT ──────────────────────────────────────────────────────────

    def _focus_window(self) -> bool:
        if not _HAS_GW:
            return False
        try:
            wins = [w for w in gw.getAllWindows()
                    if w.title and ("ChatGPT" in w.title or "Edge" in w.title or "Chrome" in w.title)]
            if wins:
                wins[0].restore()
                wins[0].maximize()
                wins[0].activate()
                time.sleep(0.5)
                return True
        except Exception:
            pass
        return False

    def _open_chatgpt(self) -> str:
        """切換到已開啟的 ChatGPT 視窗"""
        if _HAS_GW:
            try:
                wins = [w for w in gw.getAllWindows()
                        if w.title and "ChatGPT" in w.title]
                if not wins:
                    wins = [w for w in gw.getAllWindows()
                            if w.title and ("Edge" in w.title or "Chrome" in w.title)]
                if wins:
                    win = wins[0]
                    win.restore()
                    win.maximize()
                    win.activate()
                    time.sleep(1.0)
                    logger.info(f"[ChatGPTBridge] 已切換到：{win.title[:40]}")
                    return "ok"
            except Exception as e:
                logger.warning(f"[ChatGPTBridge] 視窗切換失敗：{e}")

        import webbrowser
        webbrowser.open(CHATGPT_URL)
        time.sleep(WAIT_PAGE_LOAD + 2)
        logger.info("[ChatGPTBridge] 找不到視窗，開新的")
        return "ok"

    # ── 輸入問題 ──────────────────────────────────────────────────────────────

    def _type_question(self, question: str) -> str:
        try:
            import pyperclip

            plain_text_prefix = "請用純文字回答，不要用互動卡片、表格或圖表，直接條列說明："
            full_question = f"{{立}} {plain_text_prefix}{question}"
            pyperclip.copy(full_question)

            clicked = False
            for input_x, input_y in INPUT_CANDIDATES:
                pyautogui.click(input_x, input_y)
                time.sleep(0.5)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.5)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.2)
                try:
                    pasted = pyperclip.paste()
                    if "{立}" in pasted:
                        logger.info(f"[ChatGPTBridge] 輸入框確認（{input_x},{input_y}）")
                        clicked = True
                        break
                    else:
                        pyautogui.hotkey("ctrl", "a")
                        pyautogui.press("delete")
                except Exception:
                    pass

            if not clicked:
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.5)

            pyautogui.press("enter")
            time.sleep(0.5)
            pyautogui.hotkey("ctrl", "End")
            time.sleep(0.3)
            logger.info(f"[ChatGPTBridge] 已送出：{question[:30]}")
            return "ok"

        except Exception as e:
            logger.error(f"[ChatGPTBridge] 輸入失敗：{e}")
            return str(e)

    # ── 等待並讀取回答 ────────────────────────────────────────────────────────

    def _wait_and_read_answer(self) -> str:
        import pyperclip
        import pyautogui as _pg

        logger.info(f"[ChatGPTBridge] 靜候 {int(MIN_WAIT)} 秒讓 ChatGPT 開始生成...")
        time.sleep(MIN_WAIT)

        prev_text    = ""
        stable_count = 0
        elapsed      = MIN_WAIT

        logger.info("[ChatGPTBridge] 開始每 10 秒檢查一次...")

        while elapsed < WAIT_RESPONSE:
            try:
                _pg.click(SAFE_X, SAFE_Y)
                time.sleep(0.2)
                _pg.hotkey("ctrl", "End")
                time.sleep(0.4)
                _pg.hotkey("ctrl", "a")
                time.sleep(0.3)
                _pg.hotkey("ctrl", "c")
                time.sleep(0.5)
                full_text = pyperclip.paste()

                marker = "{立}"
                idx = full_text.rfind(marker) if full_text else -1
                current_text = full_text[idx:] if idx != -1 else full_text

            except Exception as e:
                logger.warning(f"[ChatGPTBridge] 剪貼簿讀取異常：{e}")
                time.sleep(CHECK_INTERVAL)
                elapsed += CHECK_INTERVAL
                continue

            text_len = len(current_text) if current_text else 0
            logger.info(f"[ChatGPTBridge] 讀取（{elapsed:.0f}秒）：{text_len} 字，前30字：{repr(current_text[:30]) if current_text else 'empty'}")

            if not current_text or text_len < 20:
                stable_count = 0
                time.sleep(CHECK_INTERVAL)
                elapsed += CHECK_INTERVAL
                continue

            if current_text == prev_text:
                stable_count += 1
                logger.info(f"[ChatGPTBridge] 內容無變化 {stable_count}/{STABLE_NEEDED}（{elapsed:.0f}秒）")
                if stable_count >= STABLE_NEEDED:
                    logger.info(f"[ChatGPTBridge] 連續 {STABLE_NEEDED} 次無變化，確認完畢")
                    break
            else:
                if prev_text:
                    logger.info(f"[ChatGPTBridge] 內容仍在變化（{elapsed:.0f}秒，{len(prev_text)}→{text_len} 字）")
                stable_count = 0
                prev_text = current_text

            time.sleep(CHECK_INTERVAL)
            elapsed += CHECK_INTERVAL

        if not prev_text:
            return ""

        return self._extract_answer(prev_text)

    def _extract_answer(self, full_text: str) -> str:
        import re as _re

        ui_noise = [
            "ChatGPT", "Send a message", "New chat",
            "Good morning", "Good afternoon", "Good evening",
            "How can I help", "ChatGPT can make mistakes",
            "立 AI 收到", "Please double-check",
        ]

        marker = "{立}"
        idx = full_text.rfind(marker)
        if idx != -1:
            full_text = full_text[idx + len(marker):]

        lines = full_text.splitlines()
        cleaned = []
        skipped_question = (idx == -1)

        for line in lines:
            stripped = line.strip()
            stripped = _re.sub(r"(上午|下午|凌晨)\d+:\d+", "", stripped).strip()
            if not stripped:
                continue
            if not skipped_question:
                skipped_question = True
                continue
            if any(noise.lower() in stripped.lower() for noise in ui_noise):
                continue
            cleaned.append(stripped)

        result = "\n".join(cleaned).strip()
        if not result:
            result = full_text.strip()
        if len(result) > 2000:
            result = result[:2000] + "...（已截斷）"
        return result

    # ── 記憶學習 ──────────────────────────────────────────────────────────────

    def _learn(self, question: str, answer: str):
        if not _HAS_MEMORY:
            return

        invalid_signs = [
            "{立}", "載入失敗", "無法讀取",
            "Good evening", "Good morning", "How can I help",
        ]
        if len(answer.strip()) < 10:
            logger.warning("[ChatGPTBridge] 回答太短，不存入記憶庫")
            return
        if any(sign in answer for sign in invalid_signs):
            logger.warning("[ChatGPTBridge] 回答包含無效內容，不存入記憶庫")
            return

        # 覆蓋舊記憶
        try:
            old_mems = [m for m in _memory._memories
                        if m.get("source") == "chatgpt_bridge"
                        and question[:30] in m.get("content", "")]
            for m in old_mems:
                _memory.forget(m["id"])
            if old_mems:
                logger.info(f"[ChatGPTBridge] 覆蓋舊記憶 {len(old_mems)} 筆")
        except Exception:
            pass

        # 存入問答對
        knowledge = "問：" + question + "\n答：" + answer[:500]
        _memory.store(knowledge, tags=["chatgpt_answer", "auto_learn"], importance=8, source="chatgpt_bridge")

        # 存入 ChatGPT 知識庫
        try:
            from chatgpt_knowledge import get_knowledge
            get_knowledge().store(question, answer, source="chatgpt_bridge")
        except Exception as _ke:
            logger.warning(f"[ChatGPTBridge] ChatGPT 知識庫存入失敗：{_ke}")

        # 拆段存入
        paragraphs = re.split(r'\n{2,}', answer)
        if len(paragraphs) <= 1:
            paragraphs = answer.splitlines()
        count = 0
        for para in paragraphs:
            para = para.strip()
            if len(para) < 15:
                continue
            if len(para) > 500:
                para = para[:500]
            _memory.store(para, tags=["chatgpt_answer", "auto_learn"], importance=7, source="chatgpt_bridge")
            count += 1

        logger.info(f"[ChatGPTBridge] 已存入記憶庫（{count} 段）")
        _push(f"📥 ChatGPT 已存入記憶庫（{count} 段），準備生成追問...")
        logger.info("[ChatGPTBridge] _learn() 完成，返回 ask()")


# ── 手機通知（用 requests 直接呼叫 Telegram API）────────────────────────────
_TG_TOKEN    = "8659848303:AAFVOzNMDvcwg24uGCU_lzTvgjNlEUeVWx0"
_TG_CHAT_IDS = [8443859030]

# ── 模組層級單例 ──────────────────────────────────────────────────────────────
_bridge = None

def get_bridge() -> ChatGPTDesktopBridge:
    global _bridge
    if _bridge is None:
        _bridge = ChatGPTDesktopBridge()
    return _bridge


if __name__ == "__main__":
    bridge = ChatGPTDesktopBridge()
    q = input("要問 ChatGPT 什麼？").strip()
    answer = bridge.ask(q)
    print(f"\nChatGPT 的回答：\n{answer}")

