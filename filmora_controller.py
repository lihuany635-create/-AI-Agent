"""
filmora_controller.py
整合 filmora_agent + filmora_vision，讓立 AI 操作後自動驗證結果。
"""

import time
import sys
sys.path.insert(0, ".")

from filmora_agent import (
    launch_filmora, focus_filmora, execute_command,
    parse_command, new_project, import_media,
    save_project, split_clip, seek_to, cut_segment,
    delete_selected, export_video, undo, play_pause
)
from filmora_vision import (
    analyze_screen, check_dialog, verify_action,
    get_timeline_status, FilmoraMonitor
)

OLLAMA_URL   = "http://localhost:11434"
OLLAMA_MODEL = "gpt-oss:20b"


# ── 加強版執行（操作後自動驗證）────────────────────────────────────────────────

def execute_with_verify(text: str):
    """執行指令並截圖驗證結果。"""
    print(f"\n📝 指令：{text}")

    # 1. 解析指令
    import requests, json, re
    system = """你是 Filmora 影片編輯控制器。
分析用戶指令，回傳 JSON 操作列表。

可用操作（action）：
- new_project
- open_project: {path}
- import_media: {path}
- save
- play_pause
- seek: {seconds}
- split
- cut_segment: {start, end}
- delete_selected
- export: {output_path, quality}
- undo: {times}
- check_status  （截圖看現在狀態）

只回傳 JSON：{"actions": [{"action": "...", "params": {}, "verify": "驗證說明"}]}"""

    r = requests.post(f"{OLLAMA_URL}/api/chat", json={
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": text},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }, timeout=None)
    raw = r.json().get("message", {}).get("content", "")
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw).strip()

    try:
        result = json.loads(raw)
    except Exception:
        print("⚠ 解析失敗，改用基本執行")
        execute_command(text)
        return

    actions = result.get("actions", [])
    for act in actions:
        action  = act.get("action", "")
        params  = act.get("params", {})
        verify  = act.get("verify", "")

        print(f"  → {action} {params}")

        # 執行操作
        if action == "new_project":           new_project()
        elif action == "open_project":        import sys; exec("from filmora_agent import open_project; open_project(params.get('path',''))")
        elif action == "import_media":        import_media(params.get("path", ""))
        elif action == "save":                save_project()
        elif action == "play_pause":          play_pause()
        elif action == "seek":                seek_to(float(params.get("seconds", 0)))
        elif action == "split":               split_clip()
        elif action == "cut_segment":         cut_segment(float(params.get("start", 0)), float(params.get("end", 0)))
        elif action == "delete_selected":     delete_selected()
        elif action == "export":              export_video(params.get("output_path", ""), params.get("quality", "1080p"))
        elif action == "undo":                undo(int(params.get("times", 1)))
        elif action == "check_status":
            status = analyze_screen("Filmora 目前的狀態？")
            print(f"  📸 {status[:120]}")
            continue

        # 操作後等待 + 截圖驗證
        time.sleep(0.8)

        # 偵測對話框
        dialog = check_dialog()
        if dialog and "沒有" not in dialog and "無" not in dialog:
            print(f"  ⚠ 偵測到對話框：{dialog[:80]}")
            handle_dialog(dialog)

        # 驗證結果
        if verify:
            ok = verify_action(verify)
            if not ok:
                print(f"  ❌ 操作可能未成功，請確認")


def handle_dialog(dialog_desc: str):
    """自動處理常見對話框。"""
    import pyautogui
    desc_lower = dialog_desc.lower()
    if any(w in desc_lower for w in ["確認", "confirm", "yes", "ok"]):
        pyautogui.press("enter")
        print("  ✅ 自動按確認")
    elif any(w in desc_lower for w in ["取消", "cancel", "no"]):
        pyautogui.press("escape")
        print("  ✅ 自動按取消")


# ── 主互動介面 ────────────────────────────────────────────────────────────────

def interactive():
    print("=" * 55)
    print("  🎬 Filmora 立 AI 控制器（視覺增強版）")
    print("  自然語言指令 → 操作 → 截圖驗證")
    print("  輸入 '看' 可截圖查看目前狀態")
    print("  Ctrl+C 退出")
    print("=" * 55)

    if not launch_filmora():
        print("⚠ 請手動開啟 Filmora 後重試")

    # 啟動背景監控
    monitor = FilmoraMonitor(interval=10)
    monitor.start(callback=lambda s: print(f"\n  📡 狀態變化：{s[:60]}"))

    while True:
        try:
            cmd = input("\n🎬 > ").strip()
            if not cmd:
                continue
            if cmd in ("看", "status", "狀態"):
                status = get_timeline_status()
                print(f"  📸 {status}")
            elif cmd in ("ui", "元素"):
                from filmora_vision import capture_ui_elements
                print(f"  📸 {capture_ui_elements()}")
            else:
                execute_with_verify(cmd)
        except KeyboardInterrupt:
            monitor.stop()
            print("\n再見！")
            break


if __name__ == "__main__":
    interactive()
