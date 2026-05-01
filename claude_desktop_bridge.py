# claude_desktop_bridge.py — 立 AI × Claude 桌面橋接
# 流程：立 AI 問題 → 開 Edge 到 claude.ai → 輸入問題 → 等待回答 → OCR 讀取 → 存入記憶庫
# 依賴：pyautogui, pytesseract, Pillow, pygetwindow
# 前提：Edge 已安裝，claude.ai 已登入

import sys as _sys_top
# Python 3.11 路徑（python 指令）
_PKG_311     = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
_PKG_311_W32 = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages\win32"
# Python 3.14 路徑（py 指令）
_PKG_314     = r"C:\Users\ACER\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages"
_PKG_314_W32 = r"C:\Users\ACER\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\win32"
for _p in [_PKG_311, _PKG_311_W32, _PKG_314, _PKG_314_W32]:
    if _p not in _sys_top.path:
        _sys_top.path.insert(0, _p)

# 預先載入 win32gui，確保後續呼叫可用
try:
    import win32gui as _win32gui_preload
    import win32con as _win32con_preload
    _HAS_WIN32 = True
except Exception as _w32e:
    _HAS_WIN32 = False
    import logging as _log_w32
    _log_w32.getLogger("claude_bridge").warning(f"win32gui 預載失敗：{_w32e}")

def _focus_window_by_title(keyword: str) -> bool:
    """用 PowerShell 切換含關鍵字的視窗，不依賴 win32gui"""
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
        import ctypes
        CREATE_NO_WINDOW = 0x08000000
        result = _sp.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="ignore",
            creationflags=CREATE_NO_WINDOW
        )
        output = result.stdout.strip()
        if output.startswith("OK:"):
            return True
        return False
    except Exception:
        return False

import time
import re
import pathlib
import datetime
import subprocess

try:
    from agent_logger import get_logger
    logger = get_logger("claude_bridge")
except ImportError:
    import logging
    logger = logging.getLogger("claude_bridge")

# PC API helper（優先走 API，失敗 fallback pyautogui）
import requests as _pc_req

def _pc(endpoint, data=None, method="post"):
    try:
        if method == "post":
            r = _pc_req.post(f"http://localhost:8899{endpoint}", json=data or {}, timeout=8)
        else:
            r = _pc_req.get(f"http://localhost:8899{endpoint}", timeout=8)
        return r.json()
    except Exception:
        return {"ok": False}

def _pc_available():
    try:
        return _pc_req.get("http://localhost:8899/health", timeout=2).status_code == 200
    except Exception:
        return False

def _click(x, y):
    if _pc_available():
        _pc("/mouse/click", {"x": x, "y": y})
    else:
        import pyautogui
        pyautogui.click(x, y)

def _hotkey(*keys):
    if _pc_available():
        _pc("/keyboard/hotkey", {"keys": list(keys)})
    else:
        import pyautogui
        pyautogui.hotkey(*keys)

def _press(key):
    if _pc_available():
        _pc("/keyboard/hotkey", {"keys": [key]})
    else:
        import pyautogui
        pyautogui.press(key)

def _copy_text(text):
    if _pc_available():
        _pc("/system/clipboard", {"text": text})
    else:
        import pyperclip
        pyperclip.copy(text)

def _paste_text():
    if _pc_available():
        r = _pc("/system/clipboard", method="get")
        return r.get("text", "")
    else:
        import pyperclip
        return pyperclip.paste()

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
    import sys as _sys_ocr
    _PKG_OCR = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    if _PKG_OCR not in _sys_ocr.path:
        _sys_ocr.path.insert(0, _PKG_OCR)
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    from PIL import ImageGrab, Image
    _HAS_OCR = True
except Exception as _e_ocr:
    _HAS_OCR = False
    import logging as _log_ocr
    _log_ocr.getLogger("claude_bridge").warning(f"OCR 載入失敗：{_e_ocr}")

try:
    from long_term_memory import get_memory
    _memory = get_memory()
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

# claude.ai 的 Edge 視窗標題關鍵字
CLAUDE_TITLE_KW  = "Microsoft Edge"  # Edge 視窗標題包含此字串
EDGE_EXE         = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CLAUDE_URL       = "https://claude.ai/chat/1d6095ae-0c04-478f-bc7d-b14d2e16de73"

# OCR 等待時間設定（秒）
WAIT_PAGE_LOAD   = 3.0   # 等網頁載入
WAIT_RESPONSE    = 120.0  # 等 Claude 回答（最長）
WAIT_CHECK_INTERVAL = 3.0  # 每隔幾秒截圖檢查

# 截圖暫存
SCREENSHOT_DIR = pathlib.Path("memory/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class ClaudeDesktopBridge:
    """
    透過桌面自動化讓立 AI 與 Claude 對話並學習
    """

    def __init__(self):
        self._last_question  = ""
        self._last_answer    = ""
        self._ocr_error      = ""
        self._edge_was_open  = False
        self._stop_chat      = False  # 停止對話循環旗標
        self._ensure_ocr()

    def chat_loop(self, initial_question: str, max_rounds: int = 10,
                  notify_fn=None, ui_ref=None) -> str:
        """
        與 Claude 進行多輪對話學習
        - initial_question：起始問題
        - max_rounds：最大輪數
        - notify_fn：每輪完成後的回呼（用於更新 UI）
        - ui_ref：desktop_agent 視窗參考（用於顯示停止按鈕）
        """
        import threading

        self._stop_chat = False
        history = []  # 對話歷史

        # 顯示停止按鈕
        if ui_ref:
            try:
                ui_ref.show_claude_chat_bar(True)
            except Exception:
                pass

        question = initial_question
        results  = []

        for round_num in range(1, max_rounds + 1):
            if self._stop_chat:
                logger.info(f"[ClaudeBridge] 對話循環被停止（第 {round_num} 輪）")
                break

            logger.info(f"[ClaudeBridge] 對話第 {round_num} 輪：{question[:40]}")

            # 問 Claude
            answer = self.ask(question, auto_learn=True)
            if not answer or answer.startswith("❌"):
                logger.warning(f"[ClaudeBridge] 第 {round_num} 輪失敗，停止循環")
                break

            history.append({"q": question, "a": answer})
            results.append("【第 " + str(round_num) + " 輪】\n問：" + question + "\n答：" + answer[:200])

            # 通知 UI
            if notify_fn:
                try:
                    notify_fn(f"[Claude對話 第{round_num}輪] {answer[:100]}")
                except Exception:
                    pass

            if self._stop_chat:
                break

            # 讓立 AI 根據回答生成下一個問題
            try:
                from ollama_guard import safe_infer
                next_q_prompt = (
                    "請用繁體中文，根據以下對話生成一個深入的後續問題。"
                    "只輸出問題本身，不要任何解釋、前綴或標點符號結尾。"
                    "問題必須是「請口頭說明…」或「請解釋…」的形式，不要要求對方製作任何檔案、程式碼或圖表。\n\n"
                    "問：" + question + "\n答：" + answer[:300] + "\n\n繁體中文後續問題："
                )
                next_question = safe_infer(next_q_prompt, model="qwen2.5:14b", timeout=60)
                next_question = next_question.strip().strip("？?。.")
                # 過濾無效的追問（Ollama 錯誤訊息、太短）
                invalid_next = [
                    "Ollama", "離線", "請確認", "ERROR", "failed",
                    "超時", "timeout", "無法",
                ]
                if (not next_question
                        or len(next_question) < 5
                        or any(kw in next_question for kw in invalid_next)):
                    logger.info("[ClaudeBridge] 追問無效，停止循環")
                    break
                question = next_question
            except Exception as e:
                logger.warning(f"[ClaudeBridge] 生成追問失敗：{e}")
                break

        # 隱藏停止按鈕
        if ui_ref:
            try:
                ui_ref.show_claude_chat_bar(False)
            except Exception:
                pass

        summary = f"完成 {len(history)} 輪對話學習，已存入記憶庫"
        return summary

    def _ensure_ocr(self):
        """確保 OCR 可用（直接呼叫 tesseract 執行檔，完全不依賴 PIL）"""
        global _HAS_OCR
        if _HAS_OCR:
            return
        try:
            import subprocess as _sp
            import mss  # 只需要 mss 截圖
            # 測試 tesseract 是否可執行
            result = _sp.run(
                [r"C:\Program Files\Tesseract-OCR\tesseract.exe", "--version"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                _HAS_OCR = True
                self._ocr_error = ""
                logger.info("[ClaudeBridge] OCR 就緒（直接呼叫模式）")
            else:
                self._ocr_error = "tesseract 執行失敗"
        except Exception as e:
            self._ocr_error = str(e)
            logger.warning(f"[ClaudeBridge] OCR 初始化失敗：{e}")

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def _sanitize_question(self, question: str) -> str:
        """
        預處理問題：把會觸發 artifact 的要求改寫成說明形式。
        主要針對程式碼修正任務（由 repair_engine / self_dev_engine 傳入的格式）。
        """
        import re as _re

        # 偵測是否為程式碼修正任務
        code_task_keywords = [
            "輸出修正後的完整", "輸出完整程式碼", "輸出修正後",
            "提供修正後的", "給我完整的程式碼", "輸出完整的",
            "write the complete", "output the complete", "provide the full code",
        ]
        is_code_task = any(kw in question for kw in code_task_keywords)

        if not is_code_task:
            return question

        # 把「輸出/提供完整程式碼」改成「用文字說明修正方式，並逐行列出」
        replacements = [
            (r"輸出修正後的完整\s*Python\s*程式碼", "用純文字逐行說明修正後的程式碼內容"),
            (r"輸出修正後的完整程式碼", "用純文字逐行說明修正後的程式碼內容"),
            (r"輸出完整程式碼", "用純文字逐行說明程式碼內容"),
            (r"輸出修正後", "說明修正方式"),
            (r"提供修正後的.*?程式碼", "說明修正後的程式碼內容"),
            (r"給我完整的程式碼", "用純文字說明完整程式碼"),
            (r"只輸出純文字，不要 markdown，不要提供下載檔案", ""),
        ]
        result = question
        for pattern, replacement in replacements:
            result = _re.sub(pattern, replacement, result)

        # 若任務區塊包含「1. ... 2. ...」格式，把「輸出程式碼」步驟改寫
        result = _re.sub(
            r"(\d+\.\s*)然後輸出修正後的完整\s*Python\s*程式碼",
            r"\1然後用純文字逐行列出修正後的程式碼",
            result
        )

        logger.info("[ClaudeBridge] 問題已預處理（避免 artifact）")
        return result

    def ask(self, question: str, auto_learn: bool = True, raw: bool = False, max_chars: int = 4000) -> str:
        """
        主流程：
        1. 開啟/切換到 claude.ai（Edge）
        2. 輸入問題
        3. 等待並讀取回答
        4. 存入記憶庫（若 auto_learn=True）
        raw=True：不加純文字前綴，適合需要 Claude 輸出 JSON 的場合
        max_chars：回答最大字數（預設4000，0=不限）
        回傳 Claude 的回答文字
        """
        if not _HAS_PYAUTOGUI:
            return "❌ 需要安裝 pyautogui：pip install pyautogui"
        # 嘗試即時載入 OCR（解決 sys.path 問題）
        self._ensure_ocr()
        if not _HAS_OCR:
            return f"❌ OCR 載入失敗：{self._ocr_error}"

        # 預處理問題：把會觸發 artifact 的要求改寫
        question = self._sanitize_question(question)

        logger.info(f"[ClaudeBridge] 開始問 Claude：{question[:50]}")

        # 步驟 1：開啟或切換到 claude.ai
        result = self._open_claude()
        if result != "ok":
            return f"❌ 無法開啟 claude.ai：{result}"

        time.sleep(WAIT_PAGE_LOAD)

        # 步驟 2：找到輸入框並輸入問題
        result = self._type_question(question, raw=raw)
        if result != "ok":
            return f"❌ 輸入失敗：{result}"

        # 步驟 3：確保 Edge 在最前面，然後等待並讀取回答
        time.sleep(2.0)
        self._focus_edge_window()
        time.sleep(1.5)  # 等視窗切換完成
        answer = self._wait_and_read_answer(max_chars=max_chars)
        if not answer:
            return "❌ 無法讀取 Claude 的回答（OCR 失敗或等待超時）"

        self._last_question = question
        self._last_answer   = answer

        logger.info(f"[ClaudeBridge] 取得回答（{len(answer)} 字）")

        # 步驟 4：存入記憶庫
        if auto_learn and _HAS_MEMORY:
            self._learn(question, answer)

        # 步驟 5：關閉這個分頁（每次用完就關，保持乾淨）
        self._close_current_tab()

        return answer

    def learn_correction(self, correction: str) -> str:
        """
        使用者糾正：用正確答案覆蓋記憶庫裡的錯誤回答
        """
        if not self._last_question:
            return "沒有最近的問答記錄可以糾正"

        if _HAS_MEMORY:
            knowledge = f"{self._last_question} → {correction}"
            _memory.store(
                knowledge,
                tags=["claude_corrected", "user_teach"],
                importance=9,
                source="claude_bridge_correction"
            )
            _memory.store(
                correction,
                tags=["claude_corrected", "user_teach"],
                importance=9,
                source="claude_bridge_correction"
            )
            logger.info(f"[ClaudeBridge] 糾正已存入記憶庫：{correction[:50]}")
            return f"✅ 已學習糾正：{correction[:80]}"

        return "記憶庫未載入"

    # ── 開啟 claude.ai ────────────────────────────────────────────────────────

    def _focus_edge_window(self) -> bool:
        """用 pygetwindow 切換到 Claude/Edge 視窗"""
        if not _HAS_GW:
            return False
        try:
            wins = [w for w in gw.getAllWindows()
                    if w.title and ("Claude" in w.title or "Edge" in w.title)]
            if wins:
                wins[0].restore()
                wins[0].maximize()
                wins[0].activate()
                time.sleep(0.5)
                return True
        except Exception:
            pass
        return False

    def _open_claude(self) -> str:
        """
        每次開一個新的 Edge 分頁到 claude.ai/new，
        確保每次都是全新對話，Ctrl+A 只複製這一輪內容。
        """
        import subprocess
        try:
            # 用 Edge 開新分頁（--new-tab 參數）
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                [EDGE_EXE, "--new-tab", "https://claude.ai/new"],
                creationflags=CREATE_NO_WINDOW
            )
            time.sleep(WAIT_PAGE_LOAD + 3.0)

            # 切換到新開的 Claude 分頁
            if _HAS_GW:
                for _ in range(5):
                    wins = [w for w in gw.getAllWindows()
                            if w.title and "Claude" in w.title]
                    if wins:
                        win = wins[-1]  # 最新開的分頁
                        win.restore()
                        win.maximize()
                        win.activate()
                        time.sleep(0.8)
                        logger.info(f"[ClaudeBridge] 已開新分頁：{win.title[:40]}")
                        break
                    time.sleep(1.0)

            # 點擊新分頁的輸入框
            _click(994, 516)
            time.sleep(2.0)
            logger.info("[ClaudeBridge] 已點擊輸入框（994, 516）")

            self._edge_was_open = True
            return "ok"

        except Exception as e:
            logger.warning(f"[ClaudeBridge] 開新分頁失敗：{e}")
            # 降級：切換到現有視窗
            if _HAS_GW:
                wins = [w for w in gw.getAllWindows()
                        if w.title and ("Claude" in w.title or "Edge" in w.title)]
                if wins:
                    wins[0].activate()
                    return "ok"
            return f"開新分頁失敗：{e}"

    def _close_current_tab(self):
        """問完後關掉當前分頁"""
        try:
            self._focus_edge_window()
            time.sleep(0.3)
            _hotkey("ctrl", "w")
            time.sleep(0.5)
            logger.info("[ClaudeBridge] 已關閉 Claude 分頁")
        except Exception as e:
            logger.warning(f"[ClaudeBridge] 關閉分頁失敗：{e}")

    # ── 輸入問題 ──────────────────────────────────────────────────────────────

    def _type_question(self, question: str, raw: bool = False) -> str:
        """在 claude.ai 的輸入框輸入問題並送出"""
        try:
            # 截圖找輸入框位置（用圖像定位或固定座標）
            screen_w, screen_h = pyautogui.size()

            # 根據 Edge 狀態選擇輸入框座標
            import pyperclip
            # 輸入框座標
            candidates = [
                (994, 516),
            ]

            # 要求純文字回答，避免圖表卡片等視覺元素讓 OCR 讀不到
            # raw=True 代表需要結構化輸出（JSON），不加「條列說明」前綴避免干擾
            # ── Prompt 組裝 ────────────────────────────────────────────────
            # 不限制 Claude 輸出格式，讓它自然輸出（程式碼會進 artifact）。
            # 讀取時由 _wait_and_read_answer 自動判斷是否有 artifact 並用正確方式複製。
            if raw:
                full_question = f"{{立}} {question}"
            else:
                full_question = f"{{立}} {question}"
            _copy_text(full_question)

            time.sleep(3.0)  # 等輸入框就緒

            clicked = False
            for input_x, input_y in candidates:
                _click(input_x, input_y)
                time.sleep(0.5)
                _hotkey("ctrl", "v")
                time.sleep(0.5)
                # 檢查剪貼簿內容有沒有貼進去
                _hotkey("ctrl", "a")
                time.sleep(0.2)
                _hotkey("ctrl", "c")
                time.sleep(0.2)
                try:
                    pasted = _paste_text()
                    if "{立}" in pasted:
                        logger.info(f"[ClaudeBridge] 輸入框確認（{input_x},{input_y}）")
                        clicked = True
                        break
                    else:
                        # 清空重試
                        _hotkey("ctrl", "a")
                        _press("delete")
                except Exception:
                    pass

            if not clicked:
                # 備用：直接貼上
                _hotkey("ctrl", "v")
                time.sleep(0.5)

            _press("enter")
            time.sleep(0.5)
            logger.info(f"[ClaudeBridge] 已送出：{question[:30]}")
            return "ok"

        except Exception as e:
            logger.error(f"[ClaudeBridge] 輸入失敗：{e}")
            return str(e)

    # ── 等待並讀取回答 ────────────────────────────────────────────────────────

    # artifact 複製按鈕的固定座標
    ARTIFACT_COPY_BTN = (1744, 169)

    def _has_artifact(self) -> bool:
        """
        判斷目前頁面是否出現 artifact（程式碼側邊欄）。
        方法：截圖右側區域，看剪貼簿是否有程式碼特徵。
        簡易做法：直接嘗試點複製按鈕，若剪貼簿內容有效就算有。
        """
        try:
            import pyperclip
            import pyautogui as _pg
            # 先清空剪貼簿
            _copy_text("")
            time.sleep(0.2)
            _click(*self.ARTIFACT_COPY_BTN)
            time.sleep(0.8)
            content = _paste_text()
            # 有實質內容且含程式碼特徵 → 有 artifact
            code_signs = ["import ", "def ", "class ", "    ", "#!/"]
            if content and len(content) > 30 and any(s in content for s in code_signs):
                logger.info(f"[ClaudeBridge] 偵測到 artifact（{len(content)} 字）")
                return True
        except Exception as e:
            logger.warning(f"[ClaudeBridge] artifact 偵測失敗：{e}")
        return False

    def _read_artifact(self) -> str:
        """
        點擊 artifact 複製按鈕（1744, 169）讀取程式碼內容。
        """
        try:
            import pyperclip
            import pyautogui as _pg
            _copy_text("")
            time.sleep(0.3)
            _click(*self.ARTIFACT_COPY_BTN)
            time.sleep(0.8)
            content = _paste_text()
            logger.info(f"[ClaudeBridge] artifact 複製成功（{len(content)} 字）")
            return content
        except Exception as e:
            logger.error(f"[ClaudeBridge] artifact 複製失敗：{e}")
            return ""

    def _is_claude_done(self) -> bool:
        """
        判斷 Claude 是否回答完成：
        截圖右下角，用 OCR 找「停止」按鈕是否消失，
        或直接找頁面底部的送出按鈕是否重新出現。
        簡易做法：用 pyautogui 找停止按鈕的圖示顏色區域。
        備用：點一下空白處，看剪貼簿有沒有新內容。
        """
        try:
            import mss
            import mss.tools
            # 截圖右下角送出按鈕區域（通常在輸入框右側）
            # 若 Claude 還在回答，送出按鈕會是「停止」狀態（深色方形）
            # 若回答完成，會恢復成「送出」箭頭
            # 用像素顏色判斷（簡易但有效）
            with mss.mss() as sct:
                # 截送出按鈕附近小區塊
                region = {"left": 1100, "top": 910, "width": 60, "height": 40}
                shot = sct.grab(region)
                # 取中心像素 RGB
                w, h = shot.size
                pixel = shot.pixel(w // 2, h // 2)
                r, g, b = pixel[0], pixel[1], pixel[2]
                # 停止按鈕是深色（近黑），送出按鈕是亮色（白或橙）
                is_dark = r < 80 and g < 80 and b < 80
                return not is_dark  # 不是深色 = 送出按鈕 = 回答完成
        except Exception:
            return False

    def _wait_and_read_answer(self, max_chars: int = 4000) -> str:
        """
        等待 Claude 回答完成，完成後直接點 (1744, 169) 複製 artifact 程式碼。
        若沒有 artifact，改用全選讀取純文字。
        """
        import pyperclip

        logger.info("[ClaudeBridge] 等待 Claude 回答...")
        prev_text    = ""
        stable_count = 0
        elapsed      = 0
        min_wait     = 15.0

        while elapsed < WAIT_RESPONSE:
            time.sleep(WAIT_CHECK_INTERVAL)
            elapsed += WAIT_CHECK_INTERVAL
            if elapsed < min_wait:
                continue
            current_text = self._read_via_clipboard()
            if current_text and len(current_text) > 50:
                if current_text == prev_text:
                    stable_count += 1
                    if stable_count >= 3:
                        logger.info(f"[ClaudeBridge] 回答穩定（{elapsed:.0f}秒）")
                        break
                else:
                    stable_count = 0
                    prev_text = current_text
            else:
                stable_count = 0

        # 不管穩定與否，直接點 artifact 複製按鈕
        # ★ 截圖判斷側欄狀態，決定按鈕 X 座標
        artifact_btn_x, artifact_btn_y = self.ARTIFACT_COPY_BTN
        try:
            from screenshot_copy_strategy import confirm_screen_stable, has_artifact, delete_screenshots
            logger.info("[ClaudeBridge] 截圖判斷 artifact 狀態...")
            first_img, last_img, saved_paths = confirm_screen_stable()
            if has_artifact(first_img, last_img):
                artifact_btn_x -= 260
                logger.info(f"[ClaudeBridge] 側欄展開，按鈕調整至 ({artifact_btn_x}, {artifact_btn_y})")
            else:
                logger.info(f"[ClaudeBridge] 側欄收起，使用原始座標 ({artifact_btn_x}, {artifact_btn_y})")
            delete_screenshots(saved_paths)
        except Exception as _sce:
            logger.warning(f"[ClaudeBridge] 截圖判斷失敗，使用預設座標：{_sce}")

        # retry 最多 3 次
        import pyautogui as _pg
        code_signs = ["import ", "def ", "class ", "#!/", "if __name__"]
        artifact_text = ""
        for _retry in range(3):
            try:
                _copy_text("")
                _click(artifact_btn_x, artifact_btn_y)
                time.sleep(3.0)
                artifact_text = _paste_text()
                if artifact_text and len(artifact_text) > 30 and any(s in artifact_text for s in code_signs):
                    logger.info(f"[ClaudeBridge] artifact 複製成功（{len(artifact_text)} 字，第 {_retry+1} 次）")
                    return artifact_text
                else:
                    logger.warning(f"[ClaudeBridge] artifact 第 {_retry+1} 次複製為空，重試...")
                    time.sleep(2.0)
            except Exception as _ae:
                logger.warning(f"[ClaudeBridge] artifact 點擊失敗（第 {_retry+1} 次）：{_ae}")
                time.sleep(2.0)
        logger.warning("[ClaudeBridge] artifact 3 次皆失敗，改用純文字")

        # 沒有 artifact，用全選讀純文字
        if not prev_text:
            return ""
        return self._extract_answer(prev_text, max_chars=max_chars)

    def _read_via_clipboard(self) -> str:
        """
        讀取最新一則 Claude 回答：
        先全選複製，再從文字裡找 {立} 標記，取其後的內容
        """
        try:
            import pyperclip
            import pyautogui

            time.sleep(0.3)

            # ★ 截圖判斷側欄狀態，決定 artifact 按鈕座標
            artifact_btn_x, artifact_btn_y = self.ARTIFACT_COPY_BTN
            try:
                from screenshot_copy_strategy import confirm_screen_stable, has_artifact, delete_screenshots
                logger.info("[ClaudeBridge] 截圖判斷 artifact 狀態...")
                first_img, last_img, saved_paths = confirm_screen_stable()
                sidebar_open = has_artifact(first_img, last_img)
                if sidebar_open:
                    # 側欄展開：artifact 按鈕往左移（側欄約佔 260px）
                    artifact_btn_x = artifact_btn_x - 260
                    logger.info(f"[ClaudeBridge] 側欄展開，artifact 按鈕調整至 ({artifact_btn_x}, {artifact_btn_y})")
                else:
                    logger.info(f"[ClaudeBridge] 側欄收起，使用原始座標 ({artifact_btn_x}, {artifact_btn_y})")
                delete_screenshots(saved_paths)
            except Exception as _sce:
                logger.warning(f"[ClaudeBridge] 截圖判斷失敗，使用預設座標：{_sce}")

            # 用 artifact 按鈕複製（截圖只判斷座標，複製走 artifact）
            _copy_text("")
            time.sleep(0.3)
            _click(artifact_btn_x, artifact_btn_y)
            time.sleep(0.8)
            text = _paste_text()
            logger.info(f"[ClaudeBridge] artifact 複製完成（{len(text)} 字）")
            if not text:
                return ""

            # 找最後一個 {立} 標記，取其後的內容（就是 Claude 的最新回答）
            marker = "{立}"
            idx = text.rfind(marker)
            if idx != -1:
                after = text[idx + len(marker):].strip()
                lines = after.splitlines()

                # 跳過問題行（第一個非空行）
                answer_lines = []
                found_answer = False
                for line in lines:
                    stripped = line.strip()

                    # 跳過問題行
                    if not found_answer:
                        if stripped:
                            found_answer = True
                        continue

                    # 遇到頁面底部標記就停止
                    stop_signs = [
                        "Claude is AI", "can make mistakes", "double-check",
                        "立 AI 收到", "告訴我它顯示", "Please double-check",
                        "立 AI 這次", "顯示了什麼", "告訴我",
                    ]
                    # 過濾時間戳（上午/下午 + 數字）
                    import re as _re_ts
                    stripped = _re_ts.sub(r"(上午|下午|凌晨)\d+:\d+", "", stripped).strip()
                    if not stripped:
                        continue
                    if any(sign in stripped for sign in stop_signs):
                        break

                    answer_lines.append(line)

                return "\n".join(answer_lines).strip()
            else:
                return text.strip()

        except Exception as e:
            logger.error(f"[ClaudeBridge] 剪貼簿讀取失敗：{e}")
            return ""

    def _ocr_screen(self) -> str:
        """截圖並 OCR 讀取文字（mss 截圖 + 直接呼叫 tesseract，不依賴 PIL）"""
        try:
            import mss
            import subprocess as _sp

            screen_w, screen_h = pyautogui.size()
            left   = int(screen_w * 0.15)
            top    = int(screen_h * 0.25)   # 跳過頁首
            right  = int(screen_w * 0.85)
            bottom = int(screen_h * 0.78)   # 跳過輸入框區域

            # 截圖存檔（mss 可直接存 PNG，不需要 PIL）
            ts   = datetime.datetime.now().strftime("%H%M%S")
            path = SCREENSHOT_DIR / f"claude_bridge_{ts}.png"
            with mss.mss() as sct:
                monitor = {"left": left, "top": top,
                           "width": right - left, "height": bottom - top}
                shot = sct.grab(monitor)
                mss.tools.to_png(shot.rgb, shot.size, output=str(path))

            # 直接呼叫 tesseract 執行檔做 OCR
            result = _sp.run(
                [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 str(path), "stdout", "-l", "chi_tra_vert+eng"],
                capture_output=True, text=True,
                timeout=30, encoding="utf-8", errors="ignore"
            )
            return result.stdout.strip()

        except Exception as e:
            logger.error(f"[ClaudeBridge] OCR 失敗：{e}")
            return ""

    def _extract_answer(self, full_text: str, max_chars: int = 4000) -> str:
        """
        從剪貼簿文字中擷取 Claude 的回答
        去除問題本身和頁面 UI 文字，只保留回答
        max_chars：最大字數（0=不限）
        """
        import re as _re

        # 移除「{立}」開頭的問題行
        lines = full_text.splitlines()
        cleaned = []
        skip_question = True

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 跳過問題行（{立} 開頭）
            if "{立}" in line or "｛立｝" in line:
                skip_question = False  # 問題行之後開始收集
                continue

            # 跳過 UI 雜訊
            ui_noise = [
                "Claude is AI", "double-check", "Send a message",
                "New chat", "claude.ai", "How can I help",
                "Good morning", "Good afternoon", "Good evening",
                "Connect your tools", "Sonnet", "Artifacts",
                "立 AI 收到", "告訴我它顯示", "Please double-check",
                "can make mistakes", "Claude is trained",
            ]
            if any(noise.lower() in line.lower() for noise in ui_noise):
                continue

            if not skip_question:
                cleaned.append(line)

        result = "\n".join(cleaned).strip()

        # 如果沒有找到問題分隔，就把全文當回答（去掉 UI）
        if not result:
            result = full_text

        # ── 程式碼回答優化：若回答包含 python/def/import，優先找最完整的程式碼區塊 ──
        # 避免因為對話頁面太長導致只取到最後幾行
        import re as _re2
        _code_indicators = ["import ", "def ", "class ", "# ", "if __name__"]
        _looks_like_code = any(ind in result for ind in _code_indicators)
        if _looks_like_code and len(result) < 200:
            # 回答太短但應該是程式碼，嘗試從全文重新提取
            # 找最後一個 {立} 之後、最後一個程式碼區塊
            full_lines = full_text.splitlines()
            # 從後往前找第一個像程式碼的行
            code_lines = []
            in_code = False
            for line in reversed(full_lines):
                stripped = line.strip()
                if any(stripped.startswith(ind) for ind in _code_indicators):
                    in_code = True
                if in_code:
                    code_lines.insert(0, line)
                # 遇到 {立} 標記就停止（不往前取問題內容）
                if "{立}" in line or "｛立｝" in line:
                    break
            if code_lines and len("\n".join(code_lines)) > len(result):
                result = "\n".join(code_lines).strip()
                logger.info(f"[ClaudeBridge] 從全文重新提取程式碼（{len(result)} 字）")

        if max_chars > 0 and len(result) > max_chars:
            result = result[:max_chars] + "...（已截斷）"

        return result

    # ── 記憶學習 ──────────────────────────────────────────────────────────────

    def _learn(self, question: str, answer: str):
        """將 Claude 的回答分段存入記憶庫（只存有效回答）"""
        if not _HAS_MEMORY:
            return

        # 有效回答判斷：太短或包含錯誤訊息就不存
        invalid_signs = [
            "{立}", "OCR", "載入失敗", "無法讀取", "超時",
            "Good evening", "Good morning", "Good afternoon",
            "How can I help", "Connect your tools",
        ]
        if len(answer.strip()) < 10:
            logger.warning("[ClaudeBridge] 回答太短，不存入記憶庫")
            return
        if any(sign in answer for sign in invalid_signs):
            logger.warning("[ClaudeBridge] 回答包含無效內容，不存入記憶庫")
            return

        # 先刪除同一個問題的舊記憶（覆蓋更新）
        try:
            old_mems = [m for m in _memory._memories
                        if m.get("source") == "claude_bridge"
                        and question[:30] in m.get("content", "")]
            for m in old_mems:
                _memory.forget(m["id"])
            if old_mems:
                logger.info(f"[ClaudeBridge] 覆蓋舊記憶 {len(old_mems)} 筆")
        except Exception:
            pass

        # 存入新的問答對到立 AI 記憶庫
        knowledge = "問：" + question + "\n答：" + answer[:500]
        _memory.store(
            knowledge,
            tags=["claude_answer", "auto_learn"],
            importance=8,
            source="claude_bridge"
        )

        # 同時存入 Claude 知識庫（獨立分類）
        try:
            from claude_knowledge import get_knowledge
            get_knowledge().store(question, answer, source="claude_bridge")
        except Exception as _ke:
            logger.warning(f"[ClaudeBridge] Claude 知識庫存入失敗：{_ke}")

        # 拆段存入（過濾純程式碼段落）
        paragraphs = re.split(r'\n{2,}', answer)
        count = 0
        for para in paragraphs:
            para = para.strip()
            if len(para) < 15:
                continue
            if len(para) > 500:
                para = para[:500]
            # 判斷是否為純程式碼（80% 以上是程式碼行）
            lines = para.splitlines()
            code_lines = sum(1 for l in lines if l.strip().startswith(
                ("def ", "class ", "import ", "from ", "    ", "if ", "for ", "return ", "#")
            ))
            if lines and code_lines / len(lines) > 0.8:
                continue  # 跳過純程式碼段落
            _memory.store(
                para,
                tags=["claude_answer", "auto_learn"],
                importance=7,
                source="claude_bridge"
            )
            count += 1

        logger.info(f"[ClaudeBridge] 已存入記憶庫（{count} 段）")


# ── 模組層級單例 ──────────────────────────────────────────────────────────────
_bridge = None

def get_bridge() -> ClaudeDesktopBridge:
    global _bridge
    if _bridge is None:
        _bridge = ClaudeDesktopBridge()
    return _bridge


if __name__ == "__main__":
    bridge = ClaudeDesktopBridge()
    q = input("要問 Claude 什麼？").strip()
    answer = bridge.ask(q)
    print(f"\nClaude 的回答：\n{answer}")

