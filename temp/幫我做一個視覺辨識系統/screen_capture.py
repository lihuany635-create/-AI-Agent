import threading
import time
import numpy as np
try:
    import mss
except ImportError:
    mss = None
try:
    import cv2
except ImportError:
    cv2 = None
_capture_thread: threading.Thread = None
_stop_event: threading.Event = threading.Event()
def capture_screen(region=None) -> np.ndarray:
    if mss is None:
        raise ImportError("mss is required: pip install mss")
    with mss.mss() as sct:
        if region is None:
            monitor = sct.monitors[1]
        else:
            x, y, width, height = region
            monitor = {"top": y, "left": x, "width": width, "height": height}
        screenshot = sct.grab(monitor)
        frame = np.array(screenshot)
        frame = frame[:, :, :3]  # BGRA -> BGR
        return frame
def capture_camera(camera_id: int = 0) -> np.ndarray:
    if cv2 is None:
        raise ImportError("opencv-python is required: pip install opencv-python")
    cap = cv2.VideoCapture(camera_id)
    try:
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera with id {camera_id}")
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Failed to read frame from camera {camera_id}")
        return frame
    finally:
        cap.release()
def capture_video_frame(video_path: str, frame_index: int) -> np.ndarray:
    if cv2 is None:
        raise ImportError("opencv-python is required: pip install opencv-python")
    cap = cv2.VideoCapture(video_path)
    try:
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video file: {video_path}")
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_index < 0 or frame_index >= total_frames:
            raise ValueError(
                f"frame_index {frame_index} out of range [0, {total_frames - 1}]"
            )
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Failed to read frame {frame_index} from {video_path}")
        return frame
    finally:
        cap.release()
def _screen_capture_loop(callback, fps: float, stop_event: threading.Event):
    interval = 1.0 / fps
    while not stop_event.is_set():
        t_start = time.monotonic()
        frame = capture_screen()
        timestamp = time.time()
        callback(frame, timestamp)
        elapsed = time.monotonic() - t_start
        sleep_time = interval - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
def _camera_capture_loop(camera_id: int, callback, fps: float, stop_event: threading.Event):
    if cv2 is None:
        raise ImportError("opencv-python is required: pip install opencv-python")
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera with id {camera_id}")
    interval = 1.0 / fps
    try:
        while not stop_event.is_set():
            t_start = time.monotonic()
            ret, frame = cap.read()
            if ret:
                timestamp = time.time()
                callback(frame, timestamp)
            elapsed = time.monotonic() - t_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    finally:
        cap.release()
def _video_capture_loop(video_path: str, callback, fps: float, stop_event: threading.Event):
    if cv2 is None:
        raise ImportError("opencv-python is required: pip install opencv-python")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video file: {video_path}")
    interval = 1.0 / fps
    try:
        while not stop_event.is_set():
            t_start = time.monotonic()
            ret, frame = cap.read()
            if not ret:
                break  # end of video
            timestamp = time.time()
            callback(frame, timestamp)
            elapsed = time.monotonic() - t_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    finally:
        cap.release()
def start_continuous_capture(source, callback, fps: float = 30):
    global _capture_thread, _stop_event
    if _capture_thread is not None and _capture_thread.is_alive():
        raise RuntimeError(
            "Continuous capture is already running. Call stop_continuous_capture() first."
        )
    _stop_event = threading.Event()
    if source == "screen":
        target = _screen_capture_loop
        args = (callback, fps, _stop_event)
    elif isinstance(source, int):
        target = _camera_capture_loop
        args = (source, callback, fps, _stop_event)
    elif isinstance(source, str):
        target = _video_capture_loop
        args = (source, callback, fps, _stop_event)
    else:
        raise ValueError(
            "source must be 'screen', an int (camera id), or a str (video path)"
        )
    _capture_thread = threading.Thread(target=target, args=args, daemon=True)
    _capture_thread.start()
def stop_continuous_capture():
    global _capture_thread, _stop_event
    if _capture_thread is None or not _capture_thread.is_alive():
        return
    _stop_event.set()
    _capture_thread.join(timeout=5.0)
    _capture_thread = None
def list_available_cameras(max_index: int = 10) -> list:
    if cv2 is None:
        raise ImportError("opencv-python is required: pip install opencv-python")
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            available.append({
                "index": i,
                "readable": ret,
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS),
            })
            cap.release()
        else:
            cap.release()
    return available