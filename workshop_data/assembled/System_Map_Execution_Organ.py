"""請開發一個可執行的 **system_map.py**，啟動時自動掃描專案根目錄下所有 Python 檔案，解析 `import` 依賴並生成完整依賴圖；若發現未安裝的第三方模組或缺失的內部模組，將其列入報告；報告以 Markdown/JS"""
# ── 工坊組裝：System Map Execution Organ ──────────────────────────────────────────
# 組裝時間：2026-05-03T02:08:31
# 任務數：6

from pathlib import Path
import glob
import importlib.util
import os
import pathlib
import sys

def initialize_logger():
    logger = logging.getLogger('application_logger')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

def scan_python_files(directory):
    directory_path = pathlib.Path(directory)
    try:
        for file in directory_path.rglob('*.py'):
            print(f'Scanning: {file}')
    except FileNotFoundError:
        print('The specified directory does not exist.')
    except Exception as e:
        print(f'An error occurred: {e}')

scan_python_files('path/to/your/project')

def parse_imports(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            import_statements = [line for line in content.split('\n') if line.strip().startswith('from') or line.strip().startswith('import')]
            return {file_path: import_statements}
    except Exception as e:
        print(f'Error reading {file_path}: {e}')
        return {}

def detect_missing_modules(file_list):
    """
    檢測指定的模塊是否缺失。

    參數:
        file_list (list of str): 需要檢測的模塊列表。

    返回:
        list of str: 缺失的模塊列表。
    """
    missing_modules = []
    spec_cache = {file: importlib.util.find_spec(file) for file in file_list}
    for file, spec in spec_cache.items():
        if spec is None:
            missing_modules.append(file)
        try:
            pass
        except (ImportError, ModuleNotFoundError) as e:
            print(f'Error importing {file}: {e}')
    return missing_modules

file_list = ['module1.py', 'module2.py']

missing_modules = detect_missing_modules(file_list)

print(missing_modules)

def save_markdown_report(report_data):
    report_path = Path('reports/system_map_report.md')
    if not report_path.parent.exists():
        os.makedirs(report_path.parent)
    try:
        with open(report_path, 'w', encoding='utf-8') as file:
            for key in sorted(report_data.keys()):
                line = f'## {key}\n'
                for item in report_data[key]:
                    line += f'- `{item}`\n'
                file.write(line)
    except Exception as e:
        print(f'Failed to write markdown report: {e}')

report_data = {'system_map': [['module1.py', 'import sys'], ['module2.py', 'from module3 import function']]}

save_markdown_report(report_data)

def system_map_main():
    """
    主函式，用於檢查並列印所有預設模組是否已安裝成功，以及系統的基本資訊。
    """
    try:
        import requests
        import json
        import datetime
        import numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        import seaborn as sns
        print('所有預設模組已安裝成功')
    except (ImportError, ModuleNotFoundError) as e:
        print(f'發生錯誤: {e}')
    os_info = {'os_name': os.name, 'os_version': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}', 'python_version': f'{sys.version_info.major}.{sys.version_info.minor}'}
    print('\n系統資訊:')
    for key, value in os_info.items():
        print(f'{key}: {value}')

system_map_main()