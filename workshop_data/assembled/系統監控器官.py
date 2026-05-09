"""新增 agent_monitor.py，提供 start() 與 get_status()，監控系統 CPU、記憶體、行程狀態。"""
# ── 工坊組裝：系統監控器官 ──────────────────────────────────────────

import argparse
import psutil
import threading
import time
import unittest


def get_status() -> dict:
    """取得目前系統狀態，包含 CPU、記憶體、行程列表。"""
    sensitive = {'svchost', 'services', 'System', 'Registry'}
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent']):
        try:
            if proc.info['name'] not in sensitive:
                processes.append({
                    'pid':            proc.info['pid'],
                    'name':           proc.info['name'],
                    'status':         proc.info['status'],
                    'cpu_percent':    proc.info['cpu_percent'],
                    'memory_percent': proc.info['memory_percent'],
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return {
        'cpu':       psutil.cpu_percent(interval=1),
        'memory':    psutil.virtual_memory().percent,
        'disk':      psutil.disk_usage('/').percent,
        'processes': processes[:20],  # 最多顯示 20 個
    }


class AgentMonitor:
    """背景執行的系統監控器。"""

    def __init__(self, interval: float = 5.0):
        self.interval   = interval
        self._running   = False
        self._thread    = None
        self._last_status = {}

    def start(self):
        """開始背景監控。"""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("✅ 系統監控已啟動")

    def stop(self):
        """停止背景監控。"""
        self._running = False

    def _loop(self):
        while self._running:
            self._last_status = get_status()
            time.sleep(self.interval)

    def get_agent_status(self) -> dict:
        return self._last_status or get_status()


_monitor = AgentMonitor()


def start(interval: float = 5.0):
    """啟動系統監控。"""
    _monitor.interval = interval
    _monitor.start()


def cli_agent_monitor():
    """命令列入口。"""
    parser = argparse.ArgumentParser(description='系統監控器')
    parser.add_argument('-v', '--verbose', action='store_true', help='詳細輸出')
    parser.add_argument('-i', '--interval', type=float, default=5.0, help='更新間隔（秒）')
    args = parser.parse_args()

    start(args.interval)
    try:
        while True:
            status = get_status()
            if args.verbose:
                print(f"CPU: {status['cpu']}%  記憶體: {status['memory']}%  磁碟: {status['disk']}%")
            else:
                print(status)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n監控停止")


class TestAgentMonitor(unittest.TestCase):

    def test_get_status_structure(self):
        status = get_status()
        self.assertIn('cpu', status)
        self.assertIn('memory', status)
        self.assertIn('processes', status)

    def test_monitor_start_stop(self):
        m = AgentMonitor(interval=1)
        m.start()
        time.sleep(0.5)
        m.stop()


if __name__ == '__main__':
    cli_agent_monitor()
