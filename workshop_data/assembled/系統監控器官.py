"""新增 **agent_monitor.py**，提供 `start()` 與 `get_status()`。"""
# ── 工坊組裝：系統監控器官 ──────────────────────────────────────────
# 組裝時間：2026-05-03T00:18:12
# 任務數：5

from agent_monitor_module import cli_agent_monitor, get_status
from agent_monitor_module import get_status
import argparse
import psutil
import unittest

def get_status():

    def is_sensitive_process(proc):
        sensitive_processes = {'svchost', 'services'}
        return proc.name() in sensitive_processes
    process_iter = psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_info'])
    status = {'cpu': psutil.cpu_percent(interval=None), 'memory': psutil.virtual_memory().percent, 'processes': [{'pid': proc.info['pid'], 'name': proc.info['name'], 'status': proc.info['status'], 'cpu_percent': proc.info['cpu_percent'], 'mem_percent': proc.info['memory_info'].percent} for proc in process_iter if not is_sensitive_process(proc)]}
    return status

def cli_agent_monitor():
    parser = argparse.ArgumentParser(description='CLI entry point for the agent monitor')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    args = parser.parse_args()
    if args.verbose:
        print('Verbose mode enabled.')
    try:
        BasicAgent.start()
        while True:
            try:
                status = get_status()
                if args.verbose:
                    log_message = f"CPU: {status['cpu']}%, Memory: {status['memory']}%"
                    if not hasattr(cli_agent_monitor, 'logger'):
                        cli_agent_monitor.logger = agent_logger.get_logger()
                    cli_agent_monitor.logger.info(log_message)
                print('Current status:')
                print(status)
                import select
                select.select([], [], [], 1)
            except Exception as e:
                print(f'An error occurred: {e}')
    except Exception as e:
        print(f'Initialization failed: {e}')

if __name__ == '__main__':
    cli_agent_monitor()

class BasicAgent:

    def start(self):
        self.agent_monitor.start()

def get_agent_status(self):
    return self.agent_monitor.get_agent_status()

class AgentRuntimeGuard:

    def __init__(self):
        self.agent = BasicAgent()
        self.cli_agent_monitor = None

    def start(self, interval=5):
        self.agent.start()
        while True:
            try:
                status = get_agent_status(self)
                if hasattr(self.cli_agent_monitor, 'logger'):
                    log_message = f"CPU: {status['cpu']}%, Memory: {status['memory']}%"
                    self.cli_agent_monitor.logger.info(log_message)
                print('Current status:')
                print(status)
                time.sleep(interval)
            except Exception as e:
                print(f'An error occurred: {e}')

class TestAgentMonitor(unittest.TestCase):

    def test_get_status_structure(self):
        status = get_status()
        self.assertIn('cpu', status)
        self.assertIn('memory', status)
        self.assertIn('processes', status)
        for process in status['processes']:
            self.assertIn('pid', process)
            self.assertIn('name', process)
            self.assertIn('status', process)
            self.assertIn('cpu_percent', process)
            self.assertIn('memory_percent', process)
            self.assertIn('disk_usage', process)
            self.assertIn('network_status', process)
            self.assertIn('start_time', process)
            self.assertIn('executable_path', process)

if __name__ == '__main__':
    unittest.main()

class TestCLI(unittest.TestCase):

    def setUp(self):
        self.parser = argparse.ArgumentParser(description='CLI entry point for the agent monitor')
        self.parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')

    def test_cli_logging_and_verbose(self):
        args = self.parser.parse_args(['-v'])
        cli_agent_monitor(args)
        logger = cli_agent_monitor.logger
        self.assertTrue(hasattr(logger, 'debug'))
        self.assertEqual(logger.level, logging.DEBUG)
        self.assertIn('Verbose mode enabled.', logger.handlers[0].formatter._fmt)

    def test_cli_missing_argument(self):
        args = self.parser.parse_args([])
        cli_agent_monitor(args)
        logger = cli_agent_monitor.logger
        self.assertFalse(hasattr(cli_agent_monitor, 'logger'))
        self.assertEqual(logger.level, logging.NOTSET)
        self.assertNotIn('Verbose mode enabled.', logger.handlers[0].formatter._fmt)

    def test_cli_invalid_argument(self):
        args = self.parser.parse_args(['-x'])
        cli_agent_monitor(args)
        logger = cli_agent_monitor.logger
        self.assertFalse(hasattr(cli_agent_monitor, 'logger'))
        self.assertEqual(logger.level, logging.NOTSET)
        self.assertNotIn('Verbose mode enabled.', logger.handlers[0].formatter._fmt)

if __name__ == '__main__':
    unittest.main()