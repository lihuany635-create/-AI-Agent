"""**工程需求（≤200字）**"""
# ── 工坊組裝：Integration Test Organ ──────────────────────────────────────────
# 組裝時間：2026-04-27T22:30:12
# 任務數：5

from pathlib import Path
from urllib.parse import quote, unquote
import datetime
import importlib.util
import json
import logging
import os
import pathlib
import requests
import sys

logging.basicConfig(level=os.getenv('LOG_LEVEL', logging.INFO).upper(), format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

EXPECTED_FUNCS = {'start', 'analyze', 'run_auto_tests', 'main', 'init'}

def import_module_from_path(module_path: Path):
    """Dynamically import a module from a file path."""
    module_name = module_path.stem
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if not spec:
            raise ImportError(f'Cannot find module {module_name} in path.')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error(f'Failed to import {module_name}: {e}')
        return None
    return module

def main():
    root = Path(__file__).parent.resolve()
    py_files = list(root.glob('*.py'))
    if not py_files:
        logger.warning('No .py files found in the project root.')
        return
    imported_modules = {}
    for py_file in py_files:
        module_name = py_file.stem
        if module_name in imported_modules:
            module = imported_modules[module_name]
        else:
            module = import_module_from_path(py_file)
            if module is not None:
                imported_modules[module_name] = module
        if module is None:
            continue
        logger.info(f'Imported module: {module_name}')
        found_funcs = [func for func in EXPECTED_FUNCS if hasattr(module, func)]
        if found_funcs:
            logger.info(f"Module '{module_name}' exposes: {', '.join(found_funcs)}")
        else:
            logger.warning(f"Module '{module_name}' does NOT expose any expected main functions.")

if __name__ == '__main__':
    main()

def add(a, b):
    """Simple addition function."""
    return a + b

def subtract(a, b):
    """Simple subtraction function."""
    return a - b

def test_add():
    """Test the add function."""
    assert add(2, 3) == 5, f'add(2, 3) should be 5, got {add(2, 3)}'

def test_subtract():
    """Test the subtract function."""
    assert subtract(5, 3) == 2, f'subtract(5, 3) should be 2, got {subtract(5, 3)}'

def run_auto_tests():
    """
    Execute all test cases and report detailed pass/fail status.
    Returns a list of tuples: (test_name, passed, message).
    """
    results = []
    test_functions = [test_add, test_subtract]
    for test_func in test_functions:
        try:
            test_func()
            results.append((test_func.__name__, True, ''))
        except AssertionError as e:
            results.append((test_func.__name__, False, str(e)))
        except Exception as e:
            results.append((test_func.__name__, False, f'Unexpected error: {e}'))
    print('\nTest Summary:')
    for name, passed, msg in results:
        status = 'PASS' if passed else 'FAIL'
        print(f'  {name:15} : {status} {msg}')
    return results

if __name__ == '__main__':
    run_auto_tests()

try:
    import auto_test_engine
except ImportError:

    class auto_test_engine:

        @staticmethod
        def get_test_results():
            return [{'name': 'test_case_1', 'status': 'passed', 'execution_time': 0.123, 'error_message': None}, {'name': 'test_case_2', 'status': 'failed', 'execution_time': 0.456, 'error_message': 'AssertionError: expected 1 but got 0'}, {'name': 'test_case_3', 'status': 'skipped', 'execution_time': 0.0, 'error_message': None}]

def generate_report(results, output_path):
    """Generate a JSON report from test results."""
    report = {'generated_at': datetime.datetime.utcnow().isoformat() + 'Z', 'test_cases': []}
    test_cases = report['test_cases']
    for case in results:
        test_case = {'name': case.get('name'), 'status': case.get('status'), 'execution_time': case.get('execution_time'), 'error_message': case.get('error_message')}
        test_cases.append(test_case)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)

if __name__ == '__main__':
    main()

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

def send_slack(message: str):
    webhook = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook:
        return
    try:
        import requests
    except ImportError:
        logging.error('requests module not available; cannot send Slack notification.')
        return
    payload = {'text': message}
    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logging.error(f'Failed to send Slack notification: {e}')

def load_report():
    try:
        with open('report.json', 'r') as f:
            report = json.load(f)
        return report
    except FileNotFoundError:
        logging.error('Report file not found.')
        return None
    except json.JSONDecodeError:
        logging.error('Failed to decode JSON from report file.')
        return None

yaml_content = 'name: CI\n\non:\n  push:\n    branches:\n      - main\n\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v3\n\n      - name: Set up Python\n        uses: actions/setup-python@v4\n        with:\n          python-version: \'3.10\'\n\n      - name: Install dependencies\n        run: |\n          python -m pip install --upgrade pip\n          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi\n\n      - name: Run T1 - build_and_test.py\n        run: python build_and_test.py\n\n      - name: Check for auto_test_engine module\n        id: check_module\n        run: |\n          if ! python -c "import auto_test_engine" 2>/dev/null; then\n            echo "auto_test_engine module not found, skipping test."\n            exit 0\n          fi\n\n      - name: Run T2 - auto_test_engine.run_auto_tests\n        run: python -c "import auto_test_engine; auto_test_engine.run_auto_tests()"\n\n      - name: Run T3 - generate_report.py\n        run: python generate_report.py\n\n      - name: Run T4 - notify_on_failure.py\n        run: python notify_on_failure.py\n'

if __name__ == '__main__':
    main()