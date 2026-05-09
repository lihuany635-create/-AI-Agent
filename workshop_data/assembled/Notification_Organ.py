"""Windows 通知器官：發送系統彈窗通知和音效提醒。"""
# ── 工坊組裝：Notification Organ ──────────────────────────────────────────

import os
import threading
import time
from datetime import datetime
from typing import Optional


def notify(title: str, message: str, duration_ms: int = 5000, sound_file: str = ""):
    """
    發送桌面通知彈窗。

    範例：
        notify("提醒", "會議即將開始！")
        notify("鬧鐘", "起床了！", sound_file="alarm.mp3")
    """
    # 背景播放音效
    if sound_file and os.path.exists(sound_file):
        threading.Thread(target=_play, args=[sound_file], daemon=True).start()

    # 顯示彈窗
    threading.Thread(
        target=_show_popup,
        args=[title, message, duration_ms],
        daemon=True
    ).start()


def notify_at(trigger_time: datetime, title: str, message: str,
              sound_file: str = "") -> threading.Timer:
    """
    在指定時間發送通知。

    範例：
        from datetime import datetime, timedelta
        notify_at(datetime.now() + timedelta(minutes=30), "提醒", "30分鐘後開會")
    """
    delay = (trigger_time - datetime.now()).total_seconds()
    if delay < 0:
        delay = 0
    timer = threading.Timer(delay, notify,
                            kwargs={"title": title, "message": message,
                                    "sound_file": sound_file})
    timer.daemon = True
    timer.start()
    return timer


def _show_popup(title: str, message: str, duration_ms: int):
    """顯示 tkinter 彈窗。"""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        popup = tk.Toplevel(root)
        popup.title(title)
        popup.attributes('-topmost', True)
        popup.configure(bg='#1a1a2e')

        tk.Label(popup, text=title, bg='#1a1a2e', fg='#e8c547',
                 font=('Microsoft JhengHei UI', 13, 'bold'),
                 padx=16, pady=8).pack(fill='x')
        tk.Label(popup, text=message, bg='#1a1a2e', fg='#e8e6e0',
                 font=('Microsoft JhengHei UI', 11),
                 padx=16, pady=8, wraplength=300, justify='left').pack()

        # 自動關閉
        root.after(duration_ms, root.destroy)
        root.mainloop()
    except Exception as e:
        # fallback：純文字
        print(f"🔔 [{title}] {message}")


def _play(sound_file: str):
    """播放音效。"""
    try:
        from playsound import playsound
        playsound(sound_file, block=True)
    except ImportError:
        try:
            import winsound
            winsound.PlaySound(sound_file, winsound.SND_FILENAME)
        except Exception:
            pass
    except Exception as e:
        print(f"⚠ 音效播放失敗：{e}")


def toast(message: str, duration_ms: int = 3000):
    """簡易 toast 通知（無標題）。"""
    notify("通知", message, duration_ms)


if __name__ == "__main__":
    print("測試通知...")
    notify("測試", "這是一個測試通知！", duration_ms=3000)
    time.sleep(4)
    print("完成")
