"""
filmora_agent.py
立 AI 控制 Wondershare Filmora 14 的核心模組。
結合 UI 自動化（pyautogui + 螢幕辨識）實現影片剪輯操作。
"""

import pyautogui
import pygetwindow as gw
import subprocess
import time
import os
import re
from pathlib import Path
from typing import Optional
import requests

# ── 設定 ──────────────────────────────────────────────────────────────────────

FILMORA_EXE  = r"C:\Program Files\Wondershare\Filmora14\Filmora.exe"
OLLAMA_URL   = "http://localhost:11434"
OLLAMA_MODEL = "gpt-oss:20b"

pyautogui.FAILSAFE  = True   # 滑鼠移到左上角緊急停止
pyautogui.PAUSE     = 0.3    # 每次操作間隔

# ── Filmora 視窗管理 ──────────────────────────────────────────────────────────

def get_filmora_window():
    """取得 Filmora 視窗，不存在回傳 None。"""
    wins = gw.getWindowsWithTitle("Filmora")
    return wins[0] if wins else None


def launch_filmora() -> bool:
    """啟動 Filmora，等待就緒。"""
    win = get_filmora_window()
    if win:
        win.activate()
        return True
    if not Path(FILMORA_EXE).exists():
        print(f"找不到 Filmora：{FILMORA_EXE}")
        return False
    subprocess.Popen([FILMORA_EXE])
    print("啟動 Filmora 中...")
    for _ in range(30):
        time.sleep(1)
        if get_filmora_window():
            time.sleep(2)
            return True
    print("Filmora 啟動逾時")
    return False


def focus_filmora():
    """確保 Filmora 在前景。"""
    win = get_filmora_window()
    if win:
        win.activate()
        time.sleep(0.3)
        return True
    return False


def filmora_region():
    """回傳 Filmora 視窗的區域 (x, y, w, h)。"""
    win = get_filmora_window()
    if not win:
        return None
    return (win.left, win.top, win.width, win.height)

# ── 基本操作 ──────────────────────────────────────────────────────────────────

def new_project():
    """建立新專案。"""
    focus_filmora()
    pyautogui.hotkey("ctrl", "n")
    time.sleep(1)
    print("✅ 新建專案")


def open_project(path: str):
    """開啟指定專案檔。"""
    focus_filmora()
    pyautogui.hotkey("ctrl", "o")
    time.sleep(1)
    pyautogui.typewrite(path, interval=0.05)
    pyautogui.press("enter")
    time.sleep(2)
    print(f"✅ 開啟專案：{path}")


def import_media(file_path: str):
    """匯入媒體檔案。"""
    focus_filmora()
    pyautogui.hotkey("ctrl", "i")
    time.sleep(1)
    pyautogui.typewrite(file_path, interval=0.05)
    pyautogui.press("enter")
    time.sleep(1)
    print(f"✅ 匯入媒體：{file_path}")


def save_project():
    """儲存專案。"""
    focus_filmora()
    pyautogui.hotkey("ctrl", "s")
    time.sleep(1)
    print("✅ 已儲存")


def undo(times: int = 1):
    """還原操作。"""
    focus_filmora()
    for _ in range(times):
        pyautogui.hotkey("ctrl", "z")
        time.sleep(0.2)
    print(f"✅ 還原 {times} 次")


# ── 時間軸操作 ────────────────────────────────────────────────────────────────

def play_pause():
    """播放/暫停。"""
    focus_filmora()
    pyautogui.press("space")


def seek_to(seconds: float):
    """跳到指定時間點（秒）。"""
    focus_filmora()
    # Filmora 支援 Ctrl+G 跳到特定時間
    pyautogui.hotkey("ctrl", "g")
    time.sleep(0.5)
    # 格式：HH:MM:SS:FF
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    f = int((seconds % 1) * 30)
    time_str = f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
    pyautogui.typewrite(time_str, interval=0.05)
    pyautogui.press("enter")
    time.sleep(0.3)
    print(f"✅ 跳到 {time_str}")


def split_clip():
    """在當前位置分割片段（Ctrl+B）。"""
    focus_filmora()
    pyautogui.hotkey("ctrl", "b")
    time.sleep(0.3)
    print("✅ 分割片段")


def delete_selected():
    """刪除選取的片段。"""
    focus_filmora()
    pyautogui.press("delete")
    time.sleep(0.3)
    print("✅ 刪除選取")


def cut_segment(start_sec: float, end_sec: float):
    """剪掉指定時間段（跳到開始 → 分割 → 跳到結束 → 分割 → 選取中間 → 刪除）。"""
    seek_to(start_sec)
    split_clip()
    seek_to(end_sec)
    split_clip()
    # 選取中間片段（點擊中間位置）
    mid = (start_sec + end_sec) / 2
    seek_to(mid)
    time.sleep(0.3)
    delete_selected()
    print(f"✅ 剪掉 {start_sec:.1f}s ~ {end_sec:.1f}s")


# ── 匯出 ──────────────────────────────────────────────────────────────────────

def export_video(output_path: str = "", quality: str = "1080p"):
    """匯出影片。"""
    focus_filmora()
    pyautogui.hotkey("ctrl", "e")
    time.sleep(2)
    if output_path:
        # 填入輸出路徑（需要找到輸出欄位）
        pass
    pyautogui.press("enter")   # 確認匯出
    print(f"✅ 開始匯出（{quality}）")


# ── 立 AI 自然語言解析 ────────────────────────────────────────────────────────

def parse_command(text: str) -> dict:
    """
    用 Ollama 解析自然語言指令，回傳結構化操作。
    """
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
- cut_segment: {start, end}  （秒）
- delete_selected
- export: {output_path, quality}
- undo: {times}

只回傳 JSON，格式：
{"actions": [{"action": "...", "params": {...}}]}"""

    try:
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
        import json, re
        raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
        raw = re.sub(r"\n?```$", "", raw).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"解析失敗：{e}")
        return {"actions": []}


def execute_command(text: str):
    """解析並執行自然語言指令。"""
    print(f"\n📝 指令：{text}")
    result = parse_command(text)
    actions = result.get("actions", [])

    if not actions:
        print("⚠ 無法解析指令")
        return

    for act in actions:
        action = act.get("action", "")
        params = act.get("params", {})
        print(f"  → 執行：{action} {params}")

        if action == "new_project":
            new_project()
        elif action == "open_project":
            open_project(params.get("path", ""))
        elif action == "import_media":
            import_media(params.get("path", ""))
        elif action == "save":
            save_project()
        elif action == "play_pause":
            play_pause()
        elif action == "seek":
            seek_to(float(params.get("seconds", 0)))
        elif action == "split":
            split_clip()
        elif action == "cut_segment":
            cut_segment(float(params.get("start", 0)), float(params.get("end", 0)))
        elif action == "delete_selected":
            delete_selected()
        elif action == "export":
            export_video(params.get("output_path", ""), params.get("quality", "1080p"))
        elif action == "undo":
            undo(int(params.get("times", 1)))
        else:
            print(f"  ⚠ 未知操作：{action}")

        time.sleep(0.5)

    print("✅ 完成")


# ── 互動模式 ──────────────────────────────────────────────────────────────────

def interactive():
    """互動式命令列，持續接收指令。"""
    print("=" * 50)
    print("  Filmora 立 AI 控制器")
    print("  輸入自然語言指令，按 Ctrl+C 退出")
    print("=" * 50)

    if not launch_filmora():
        print("⚠ 無法啟動 Filmora，請手動開啟後重試")

    while True:
        try:
            cmd = input("\n🎬 > ").strip()
            if not cmd:
                continue
            execute_command(cmd)
        except KeyboardInterrupt:
            print("\n再見！")
            break


if __name__ == "__main__":
    interactive()
