# test_bridge.py — claude_desktop_bridge 完整診斷測試
# 執行：python test_bridge.py
# 不需要開 Edge，模擬各環節

import sys
import time
import datetime

_PKG = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

def sep(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")

# ══════════════════════════════════════════════════
# 測試 1：_extract_answer 能否正確清理時間戳和雜訊
# ══════════════════════════════════════════════════
sep("測試 1：_extract_answer 清理效果")

# 模擬 Ctrl+A 複製到的原始剪貼簿文字
fake_clipboard = """{立} 系統設計與架構
下午5:30
以下是系統設計的核心概念：

1. 單體架構（Monolith）
   所有功能集中在一個服務中，部署簡單但難以擴展。

2. 微服務架構（Microservices）
   將功能拆分為獨立服務，可單獨部署和擴展。

3. 負載均衡
   將流量分散到多個伺服器，提升可用性。

Claude is AI and can make mistakes. Please double-check responses.
"""

try:
    from claude_desktop_bridge import ClaudeDesktopBridge
    bridge = ClaudeDesktopBridge.__new__(ClaudeDesktopBridge)
    result = bridge._extract_answer(fake_clipboard)

    print(f"原始長度：{len(fake_clipboard)} 字")
    print(f"清理後長度：{len(result)} 字")
    print(f"清理後內容：\n{result}\n")

    has_timestamp = "下午" in result or "上午" in result
    has_marker    = "{立}" in result
    has_ui_noise  = "Claude is AI" in result
    has_content   = "微服務" in result

    print(f"{FAIL if has_timestamp else PASS} 時間戳過濾：{'失敗，仍有時間戳' if has_timestamp else '正常'}")
    print(f"{FAIL if has_marker    else PASS} {'{立}'} 標記過濾：{'失敗' if has_marker else '正常'}")
    print(f"{FAIL if has_ui_noise  else PASS} UI 雜訊過濾：{'失敗' if has_ui_noise else '正常'}")
    print(f"{FAIL if not has_content else PASS} 正文保留：{'失敗，內容遺失' if not has_content else '正常'}")

    # 測試 startswith("❌") 判斷
    starts_with_error = result.startswith("❌")
    is_empty = not result
    print(f"\n{'🔴' if starts_with_error else PASS} startswith('❌')：{starts_with_error}")
    print(f"{'🔴' if is_empty else PASS} 結果為空：{is_empty}")
    if starts_with_error or is_empty:
        print(f"  → chat_loop 會在此 break！前50字：{repr(result[:50])}")

except Exception as e:
    print(f"{FAIL} 測試 1 失敗：{e}")
    import traceback; traceback.print_exc()

# ══════════════════════════════════════════════════
# 測試 2：_read_via_clipboard 解析邏輯（不實際操作滑鼠）
# ══════════════════════════════════════════════════
sep("測試 2：_read_via_clipboard 解析邏輯")

try:
    import re

    def simulate_read(raw_text):
        """模擬 _read_via_clipboard 的解析邏輯"""
        marker = "{立}"
        idx = raw_text.rfind(marker)
        if idx == -1:
            return raw_text.strip()

        after = raw_text[idx + len(marker):].strip()
        lines = after.splitlines()

        stop_signs = [
            "Claude is AI", "can make mistakes", "double-check",
            "立 AI 收到", "Please double-check",
        ]

        answer_lines = []
        skipped_question = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not skipped_question:
                    continue
                answer_lines.append("")
                continue
            if not skipped_question:
                skipped_question = True
                continue
            cleaned = re.sub(r"(上午|下午|凌晨)\d+:\d+", "", stripped).strip()
            if not cleaned:
                continue
            if any(sign in cleaned for sign in stop_signs):
                break
            answer_lines.append(cleaned)

        return "\n".join(answer_lines).strip()

    result2 = simulate_read(fake_clipboard)
    print(f"解析結果長度：{len(result2)} 字")
    print(f"前100字：{repr(result2[:100])}")
    print(f"\n{FAIL if result2.startswith('❌') else PASS} 不以❌開頭")
    print(f"{FAIL if not result2 else PASS} 結果不為空")
    print(f"{FAIL if '下午' in result2 else PASS} 無時間戳")
    print(f"{FAIL if '微服務' not in result2 else PASS} 正文保留")

except Exception as e:
    print(f"{FAIL} 測試 2 失敗：{e}")

# ══════════════════════════════════════════════════
# 測試 3：ollama_guard.safe_infer 追問生成
# ══════════════════════════════════════════════════
sep("測試 3：safe_infer 追問生成")

try:
    from ollama_guard import safe_infer

    test_q = "系統設計與架構"
    test_a = "微服務架構將功能拆分為獨立服務，可單獨部署和擴展，負載均衡將流量分散到多個伺服器。"

    prompt = (
        "請用繁體中文，根據以下對話生成一個深入的後續問題（只輸出問題本身，不要任何解釋或前綴）：\n\n"
        f"問：{test_q}\n答：{test_a}\n\n繁體中文後續問題："
    )

    print("呼叫 safe_infer 中（最多等 60 秒）...")
    t0 = time.time()
    next_q = safe_infer(prompt, model="qwen2.5:14b", timeout=60)
    elapsed = time.time() - t0

    next_q = next_q.strip().strip("？?。.") if next_q else ""
    print(f"耗時：{elapsed:.1f} 秒")
    print(f"追問結果：{repr(next_q)}")

    invalid = ["Ollama", "離線", "請確認", "ERROR", "failed", "超時", "timeout", "無法"]
    is_valid = next_q and len(next_q) >= 5 and not any(kw in next_q for kw in invalid)

    print(f"\n{PASS if is_valid else FAIL} 追問有效：{is_valid}")
    if not is_valid:
        print(f"  → chat_loop 會在此 break，無法繼續追問")

except ImportError:
    print(f"{FAIL} ollama_guard 未找到，追問功能無法運作")
except Exception as e:
    print(f"{FAIL} safe_infer 失敗：{e}")
    import traceback; traceback.print_exc()

# ══════════════════════════════════════════════════
# 測試 4：模擬完整 chat_loop 邏輯（不開 Edge）
# ══════════════════════════════════════════════════
sep("測試 4：模擬 chat_loop 流程（用假回答）")

try:
    fake_answer = "微服務架構將功能拆分為獨立服務，每個服務可以獨立部署、擴展和維護。"
    question = "系統設計與架構"
    max_rounds = 3
    history = []
    invalid_next = ["Ollama", "離線", "請確認", "ERROR", "failed", "超時", "timeout", "無法"]

    for round_num in range(1, max_rounds + 1):
        print(f"\n第 {round_num} 輪")
        answer = fake_answer  # 模擬 ask() 回傳

        # 關鍵判斷
        if not answer or answer.startswith("❌"):
            print(f"  {FAIL} answer 判斷失敗，會 break")
            break

        print(f"  {PASS} answer 正常（{len(answer)} 字）")
        history.append({"q": question, "a": answer})

        # 追問
        try:
            from ollama_guard import safe_infer
            prompt = (
                "請用繁體中文，根據以下對話生成一個深入的後續問題（只輸出問題本身，不要任何解釋或前綴）：\n\n"
                f"問：{question}\n答：{answer[:300]}\n\n繁體中文後續問題："
            )
            next_q = safe_infer(prompt, model="qwen2.5:14b", timeout=60)
            next_q = next_q.strip().strip("？?。.") if next_q else ""
            is_valid = next_q and len(next_q) >= 5 and not any(kw in next_q for kw in invalid_next)

            if is_valid:
                print(f"  {PASS} 追問成功：{next_q[:50]}")
                question = next_q
            else:
                print(f"  {FAIL} 追問無效，會 break：{repr(next_q[:40])}")
                break
        except Exception as e:
            print(f"  {FAIL} 追問例外，會 break：{e}")
            break

    print(f"\n模擬完成：共 {len(history)} 輪（預期 {max_rounds} 輪）")
    if len(history) < max_rounds:
        print(f"{WARN} 循環提早結束，問題在第 {len(history)+1} 輪")

except Exception as e:
    print(f"{FAIL} 測試 4 失敗：{e}")

# ══════════════════════════════════════════════════
print(f"\n{'═'*50}")
print("  診斷完成，請把以上結果貼回來")
print(f"{'═'*50}\n")
