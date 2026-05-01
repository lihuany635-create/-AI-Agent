"""**工程需求（200字內）**"""
# ── 工坊組裝：語音辨識系統 ──────────────────────────────────────────
# 組裝時間：2026-05-01T17:44:41
# 任務數：15

from agent_basic import BasicAgent, start as start_agent
from agent_logger import get_logger
from agent_runtime_guard import start_runtime_guard
from ai_bridge import handle_message
from ai_bridge import handle_message, poll_loop, start as start_bridge
from datetime import datetime
from googletrans import Translator, exceptions as gtexceptions
from pathlib import Path
from tenacity import retry, wait_fixed, stop_after_attempt, before_log, after_log
from typing import Generator, Any
from typing import List
import csv
import json
import logging
import openai
import os
import queue
import re
import signal
import sounddevice as sd
import speech_recognition as sr
import subprocess
import sys
import threading
import threading, time, logging
import time

class AudioCapture:

    def __init__(self, samplerate: int=16000, channels: int=1, blocksize: int=1024):
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self._queue: queue.Queue[Any] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._running = False
        self._lock = threading.Lock()

    def _callback(self, indata: Any, frames: int, time: Any, status: sd.CallbackFlags) -> None:
        if status:
            logging.error(f'Error in callback: {status}')
            return
        self._queue.put(indata.copy())

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            try:
                self._stream = sd.InputStream(samplerate=self.samplerate, channels=self.channels, blocksize=self.blocksize, callback=self._callback)
                self._stream.start()
                self._running = True
            except Exception as e:
                logging.error(f'Error starting stream: {e}')

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            try:
                self._stream.stop()
                self._stream.close()
                self._stream = None
                self._running = False
            except Exception as e:
                logging.error(f'Error stopping stream: {e}')

    def get_stream(self) -> Generator[Any, None, None]:
        while self._running or not self._queue.empty():
            try:
                yield from self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        if exc:
            return False
        else:
            return True

class SpeechToText:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__init__(*args, **kwargs)
        return cls._instance

    def __init__(self, language='zh-TW', sample_rate=16000):
        self.language = language
        self.sample_rate = sample_rate
        self.audio_queue = queue.Queue()
        self._running = False
        self._thread = None
        self._callback = None
        if not hasattr(self, '_rec'):
            self._rec = sr.Recognizer()
        self._logger = get_logger('SpeechToText')

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
            self._thread = None

    def on_text(self, callback):
        self._callback = callback

    def set_language(self, lang):
        self.language = lang

    def _run(self):
        buffer = bytearray()
        audio_data = None
        raw = None
        try:
            with sr.Microphone(sample_rate=self.sample_rate) as source:
                self._rec.adjust_for_ambient_noise(source)
                while self._running:
                    audio_data = self._rec.listen(source, timeout=1, phrase_time_limit=5)
                    raw = audio_data.get_raw_data()
                    buffer.extend(raw)
                    if len(buffer) >= self.sample_rate * 2:
                        audio = sr.AudioData(bytes(buffer), self.sample_rate, 2)
                        try:
                            text = self._rec.recognize_google(audio, language=self.language)
                            self._logger.info(f'Recognized: {text}')
                            if self._callback:
                                self._callback(text)
                            handle_message(text)
                        except sr.UnknownValueError:
                            self._logger.warning('Could not understand audio')
                        except sr.RequestError as e:
                            self._logger.error(f'Recognition error: {e}')
                        buffer.clear()
        except Exception as e:
            self._logger.error(f'Runtime error: {e}')
            time.sleep(1)
            if self._running:
                self._run()

def run_recognizer(stop_event):
    stt = SpeechToText()
    stt.on_text(lambda txt: logging.info(f'Callback received: {txt}'))
    stt.start()
    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        stt.stop()

def main():
    stop_event = threading.Event()

    def guard_func():
        run_recognizer(stop_event)
    try:
        start_runtime_guard(guard_func)
    except KeyboardInterrupt:
        stop_event.set()
        logging.info('Shutting down')

if __name__ == '__main__':
    main()

if __name__ == '__main__':
    main()

def get_logger(name: str=__name__, level: int=logging.INFO) -> logging.Logger:
    """建立或取得 logger。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger = get_logger('speech_ai_demo')

@retry(wait=wait_fixed(2), stop=stop_after_attempt(3), before_log=before_log(logger, logging.INFO), after_log=after_log(logger, logging.WARN))
def record_audio(duration: int=5, language: str='en-US') -> str:
    """使用麥克風錄音並轉成文字。"""
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        logger.info(f'請說話（{duration} 秒）...')
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source, timeout=duration + 2)
    try:
        text = recognizer.recognize_google(audio, language=language)
        logger.info(f'語音辨識結果: {text}')
        return text
    except sr.UnknownValueError:
        logger.warning('無法辨識語音。')
        raise Exception('无法识别语音')
    except sr.RequestError as e:
        logger.error(f'語音辨識服務錯誤: {e}')
        raise Exception('语音识别服务错误')
    except sr.WaitTimeoutError:
        logger.warning('錄音超時，請嘗試重新錄音。')
        raise Exception('录音超时')

@retry(wait=wait_fixed(2), stop=stop_after_attempt(3), before_log=before_log(logger, logging.INFO), after_log=after_log(logger, logging.WARN))
def translate_text(text: str, dest_lang: str='zh-tw') -> str:
    """將文字翻譯成目標語言。"""
    translator = Translator()
    try:
        result = translator.translate(text, dest=dest_lang)
        logger.info(f'翻譯結果 ({dest_lang}): {result.text}')
        return result.text
    except gtexceptions.TranslatableError as e:
        logger.error(f'翻譯失敗: {e}')
        raise Exception('翻译失败')

@retry(wait=wait_fixed(2), stop=stop_after_attempt(3), before_log=before_log(logger, logging.INFO), after_log=after_log(logger, logging.WARN))
def ask_openai(prompt: str, model: str='gpt-3.5-turbo') -> str:
    """呼叫 OpenAI API 取得回覆。"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.error('請設定環境變數 OPENAI_API_KEY')
        raise Exception('未设置OpenAI API Key')
    try:
        openai.api_key = api_key
        response = openai.ChatCompletion.create(model=model, messages=[{'role': 'user', 'content': prompt}], temperature=0.7, max_tokens=150)
        reply = response.choices[0].message.content.strip()
        logger.info(f'AI 回覆: {reply}')
        return reply
    except Exception as e:
        logger.error(f'OpenAI API 呼叫失敗: {e}')
        raise Exception('OpenAI API 调用失败')

def format_message(original: str, translated: str, reply: str) -> str:
    """格式化輸出訊息。"""
    return f'=== 原始語音文字 ===\n{original}\n\n=== 翻譯成繁體中文 ===\n{{translated}}\n\n=== AI 回覆 ===\n{{reply}}\n'.format(original=original, translated=translated, reply=reply)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info('程式中斷，結束。')

MAX_RESTARTS = 3

RESTART_DELAY = 2

restart_count = 0

running = True

def signal_handler(signum, frame):
    global running
    running = False
    print('\nReceived termination signal, shutting down...')

signal.signal(signal.SIGINT, signal_handler)

signal.signal(signal.SIGTERM, signal_handler)

def run_child():
    """
    Starts a child process that sleeps for 1 second and then exits with code 1
    to simulate a crash.
    """
    return subprocess.Popen([sys.executable, '-c', 'import os; time.sleep(1); os._exit(1)'])

while running:
    try:
        child = run_child()
        print(f'Started child PID {child.pid}')
        while True:
            if not running:
                child.terminate()
                child.wait()
                print('Parent exiting.')
                sys.exit(0)
            ret = child.poll()
            if ret is not None:
                print(f'Child exited with code {ret}')
                break
            time.sleep(0.1)
    except Exception as e:
        print(f'An error occurred while starting or monitoring the child process: {e}')
        pass
    restart_count += 1
    if restart_count > MAX_RESTARTS:
        print(f'Exceeded max restarts ({MAX_RESTARTS}). Exiting.')
        break
    print(f'Restarting child in {RESTART_DELAY}s (restart #{restart_count})')
    time.sleep(RESTART_DELAY)

print('Daemon finished.')

'\n異常捕獲測試：模擬網路斷線、資源耗盡等異常，驗證程式能正確捕獲並處理。\n'

log = get_logger('exception_test', logging.INFO)

def simulate_network_disconnect() -> None:
    """模擬網路斷線：嘗試連線失敗，拋出連線錯誤。"""
    raise ConnectionError('Simulated network disconnection')

def simulate_resource_exhaustion() -> None:
    """模擬資源耗盡：嘗試分配適量的記憶體，拋出 MemoryError。"""
    try:
        _ = [0] * 10 ** 6
    except MemoryError as me:
        raise MemoryError(f'Simulated memory exhaustion: {me}') from me

TIMESTAMP_RE = re.compile('\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}')

ERROR_RE = re.compile('ERROR|Exception|Traceback', re.IGNORECASE)

def verify_log_file(log_path: Path) -> bool:
    if not isinstance(log_path, str):
        raise TypeError('log_path must be a string')
    log_path = Path(log_path)
    try:
        if not log_path.is_file():
            print(f'Log file not found: {log_path}')
            return False
    except Exception as e:
        print(f'An error occurred while checking the log file path: {e}')
        return False
    all_ok = True
    with log_path.open('r', encoding='utf-8', errors='replace') as f:
        for line_no, line in enumerate(f, 1):
            if TIMESTAMP_RE.search(line) and ERROR_RE.search(line):
                continue
            else:
                print(f'[{log_path}] Line {line_no} missing timestamp or error keyword: {line}')
                all_ok = False
    return all_ok

if __name__ == '__main__':
    main()

'\n时间戳完整性检查：扫描日志文件，确认每条记录均包含合法时间戳，且时间顺序不乱。\n'

log = get_logger('timestamp_checker', logging.INFO)

TIMESTAMP_RE = re.compile('\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}')

def parse_ts(line: str):
    """返回 datetime 对象或 None"""
    m = TIMESTAMP_RE.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(), '%Y-%m-%d %H:%M:%S')
    except ValueError:
        log.error(f'Invalid timestamp format in line: {line.strip()}')
        return None

def check_order(ts_list):
    """检查时间戳是否非递减"""
    for i in range(1, len(ts_list)):
        if ts_list[i] < ts_list[i - 1]:
            return (False, i + 1)
    return (True, None)

if __name__ == '__main__':
    main()

'\n错误码比对：将系统日志中的错误码与预定义列表逐一比对，标记已匹配的条目。\n'

log = get_logger('error_code_checker', level=logging.INFO)

PREDEFINED_CODES = {'ERR001': 'Invalid input format', 'ERR002': 'Connection timeout', 'ERR003': 'Resource not found', 'ERR004': 'Permission denied', 'ERR005': 'Internal server error'}

ERRCODE_RE = re.compile('ERR\\d{3}')

def extract_error_code(line: str):
    """返回错误码字符串或 None"""
    m = ERRCODE_RE.search(line)
    return m.group() if m else None

def process_log_file(log_path: Path):
    if not log_path.is_file():
        log.error(f'Log file not found: {log_path}')
        sys.exit(1)
    matched = set()
    output_lines = []
    with log_path.open('r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            code = extract_error_code(line)
            if code is not None:
                if code in PREDEFINED_CODES:
                    matched.add(code)
                    output_lines.append(f'{line.rstrip()} [MATCHED]\n')
                else:
                    output_lines.append(line)
            else:
                log.warning(f"Line {line_no}: No error code found in line '{line.rstrip()}'")
                output_lines.append(line)
    out_path = log_path.with_name(log_path.stem + '_checked' + log_path.suffix)
    with out_path.open('w', encoding='utf-8') as f:
        f.writelines(output_lines)
    log.info(f"已匹配错误码: {(', '.join(sorted(matched)) if matched else '无')}")
    log.info(f'检查结果已写入: {out_path}')

if __name__ == '__main__':
    main()

logging.basicConfig(level=logging.ERROR)

ERRCODE_RE = re.compile('ERR\\d+')

def read_error_codes(file_path: str, output_file_path: str):
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            error_codes = [extract_error_code(line) for line in lines]
            valid_codes = [code for code in error_codes if code is not None]
            with open(output_file_path, 'w') as output_file:
                for code in valid_codes:
                    output_file.write(code + '\n')
        return True
    except FileNotFoundError:
        logging.error(f'文件 {file_path} 不存在。')
        return False

'\n生成缺失报告：读取缺失项列表，生成 JSON 报告并打印统计信息。\n'

log = get_logger('missing_reporter', level=logging.DEBUG)

def read_missing_items(file_path: Path):
    if not file_path.is_file():
        log.error(f'文件不存在: {file_path}')
        return []
    block_size = 1024 * 8
    items = []
    with file_path.open('r', encoding='utf-8', errors='replace') as f:
        while True:
            lines = f.readlines(block_size)
            if not lines:
                break
            for line in lines:
                if line.strip():
                    items.append(line.strip())
    return items

def generate_json_report(items, out_path: Path):
    report = {'missing_items': items, 'count': len(items)}
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    log.info(f'JSON 报告已写入: {out_path}')
    return report

def generate_csv_report(items, out_path: Path):
    with out_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['missing_item'])
        for item in items:
            writer.writerow([item])
    log.info(f'CSV 报告已写入: {out_path}')
    return {'missing_items': items, 'count': len(items)}

if __name__ == '__main__':
    main()