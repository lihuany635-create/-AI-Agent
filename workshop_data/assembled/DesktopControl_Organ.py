"""**工程需求說明（200字以內）**"""
# ── 工坊組裝：DesktopControl Organ ──────────────────────────────────────────
# 組裝時間：2026-05-03T16:54:32
# 任務數：6

from agent_basic import BasicAgent
from win32gui import GetForegroundWindow, SetForegroundWindow
import asyncio
import os
import pygetwindow as gw
import subprocess
import time

class DesktopController(BasicAgent):

    def __init__(self, pid=None, title=None, window_type=None):
        super().__init__()
        self.pid = pid
        self.title = title
        self.window_type = window_type

    async def capture_screen(self, region=None, format='png'):
        if not self.pid:
            raise ValueError('PID must be provided for screen capture.')
        try:
            import subprocess
            cmd = ['import', '-window', 'root' if region is None else f'{region}']
            output = subprocess.check_output(cmd, text=True)
            return output
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f'Failed to capture screen: {e}') from e

    async def send_key(self, keys, delay=0.05):
        if not self.pid:
            raise ValueError('PID must be provided for key press.')
        try:
            import time
            for key in keys:
                os.system(f'xdotool key {key}')
                await asyncio.sleep(delay)
        except Exception as e:
            raise RuntimeError(f'Failed to send key: {e}') from e

    async def move_mouse(self, x, y, duration=0.1):
        if not self.pid:
            raise ValueError('PID must be provided for mouse movement.')
        try:
            import subprocess
            cmd = ['xdotool', 'mousemove', str(x), str(y)]
            subprocess.run(cmd)
        except Exception as e:
            raise RuntimeError(f'Failed to move mouse: {e}') from e

    async def click_button(self, button='left', times=1):
        if not self.pid:
            raise ValueError('PID must be provided for button click.')
        try:
            import time
            for _ in range(times):
                os.system(f'xdotool click {button}')
                await asyncio.sleep(0.1)
        except Exception as e:
            raise RuntimeError(f'Failed to click button: {e}') from e

asyncio.run(agent.send_key('keys', 'ABC'))

def list_windows():
    windows = []
    for i, title in enumerate(gw.getAllTitles()):
        window = gw.getWindowByTitle(title)
        if window:
            windows.append(window)
    return windows

def activate_window(handle):
    win = gw.getWindowById(handle)
    if win:
        SetForegroundWindow(win.handle)

def resize_window(handle, width, height):
    win = gw.getWindowById(handle)
    if win:
        setattr(win, 'width', width)
        setattr(win, 'height', height)

def move_window(handle, x, y):
    win = gw.getWindowById(handle)
    if win:
        setattr(win, 'x', x)
        setattr(win, 'y', y)

class ScreenCaptureError(Exception):
    pass

class KeySendingError(Exception):
    pass

class MouseMovementError(Exception):
    pass

class ButtonClickingError(Exception):
    pass

class WindowNotFoundError(Exception):
    pass

class MouseWheelError(Exception):
    pass