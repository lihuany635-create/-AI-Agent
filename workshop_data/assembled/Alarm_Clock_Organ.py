"""鬧鐘系統：支援設定、取消、列出鬧鐘，時間到時播放音效並顯示通知。"""
# ── 工坊組裝：Alarm Clock Organ ──────────────────────────────────────────

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ── 1. 資料模型 ───────────────────────────────────────────────────────────────
@dataclass
class Alarm:
    """鬧鐘資料模型。"""
    id:          str
    time:        datetime
    message:     str
    sound_file:  str = ""
    retries_left: int = field(default=3)

    def __post_init__(self):
        if isinstance(self.time, str):
            self.time = datetime.fromisoformat(self.time)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Alarm":
        return cls(
            id=data["id"],
            time=datetime.fromisoformat(data.get("time", datetime.now().isoformat())),
            message=data["message"],
            sound_file=data.get("sound_file", ""),
            retries_left=data.get("retries_left", 3),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":           self.id,
            "time":         self.time.isoformat(),
            "message":      self.message,
            "sound_file":   self.sound_file,
            "retries_left": self.retries_left,
        }


# ── 2. 音效播放 ───────────────────────────────────────────────────────────────
def play_sound(sound_file: str) -> bool:
    """播放音效，回傳是否成功。"""
    if not sound_file or not os.path.exists(sound_file):
        print(f"⚠ 音效檔案不存在：{sound_file}")
        return False
    try:
        from playsound import playsound
        playsound(sound_file, block=False)
        return True
    except Exception as e:
        print(f"⚠ 播放失敗：{e}")
        return False


# ── 3. 通知彈窗 ───────────────────────────────────────────────────────────────
def show_notification(title: str, message: str):
    """顯示系統通知彈窗。"""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        popup = tk.Toplevel(root)
        popup.title(title)
        popup.attributes('-topmost', True)
        tk.Label(popup, text=message, padx=20, pady=20,
                 font=('Microsoft JhengHei UI', 12)).pack()
        popup.after(8000, popup.destroy)
        root.after(8100, root.destroy)
        root.mainloop()
    except Exception as e:
        print(f"🔔 {title}：{message}")


# ── 4. 鬧鐘排程器 ────────────────────────────────────────────────────────────
class AlarmScheduler:
    """管理所有鬧鐘的排程器。"""

    def __init__(self):
        self._alarms:  Dict[str, Alarm]           = {}
        self._timers:  Dict[str, threading.Timer] = {}
        self._lock     = threading.Lock()

    def add(self, alarm: Alarm) -> bool:
        """新增鬧鐘。"""
        with self._lock:
            if alarm.id in self._alarms:
                return False
            delay = (alarm.time - datetime.now()).total_seconds()
            if delay < 0:
                print(f"⚠ 鬧鐘時間已過：{alarm.time}")
                return False
            self._alarms[alarm.id] = alarm
            timer = threading.Timer(delay, self._trigger, args=[alarm])
            timer.daemon = True
            timer.start()
            self._timers[alarm.id] = timer
            return True

    def cancel(self, alarm_id: str) -> bool:
        """取消鬧鐘。"""
        with self._lock:
            if alarm_id not in self._alarms:
                return False
            self._timers[alarm_id].cancel()
            del self._alarms[alarm_id]
            del self._timers[alarm_id]
            return True

    def list_alarms(self) -> List[Dict[str, Any]]:
        """列出所有鬧鐘。"""
        with self._lock:
            return [a.to_dict() for a in self._alarms.values()]

    def _trigger(self, alarm: Alarm):
        """鬧鐘觸發。"""
        print(f"🔔 鬧鐘觸發：{alarm.message}")
        threading.Thread(target=show_notification,
                         args=["鬧鐘", alarm.message], daemon=True).start()
        if alarm.sound_file:
            play_sound(alarm.sound_file)
        with self._lock:
            self._alarms.pop(alarm.id, None)
            self._timers.pop(alarm.id, None)


# ── 全域排程器 ────────────────────────────────────────────────────────────────
_scheduler = AlarmScheduler()


def set_alarm(trigger_time: datetime, message: str, sound_file: str = "") -> str:
    """
    設定鬧鐘。
    回傳鬧鐘 ID，失敗回傳空字串。

    範例：
        alarm_id = set_alarm(datetime(2026, 5, 3, 8, 0), "早安！")
    """
    alarm = Alarm(
        id=str(uuid.uuid4())[:8],
        time=trigger_time,
        message=message,
        sound_file=sound_file,
    )
    if _scheduler.add(alarm):
        print(f"✅ 鬧鐘已設定：{message} @ {trigger_time.strftime('%H:%M')}")
        return alarm.id
    return ""


def cancel_alarm(alarm_id: str) -> bool:
    """取消指定 ID 的鬧鐘。"""
    return _scheduler.cancel(alarm_id)


def list_alarms() -> List[Dict[str, Any]]:
    """列出所有待觸發的鬧鐘。"""
    return _scheduler.list_alarms()


if __name__ == "__main__":
    from datetime import timedelta
    aid = set_alarm(datetime.now() + timedelta(seconds=5), "測試鬧鐘！")
    print(f"鬧鐘 ID：{aid}")
    print("等待 6 秒...")
    time.sleep(6)
