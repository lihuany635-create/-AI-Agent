import cv2
import numpy as np
from typing import Callable, Optional, Union


def open_camera(source: Union[int, str] = 0) -> Optional[cv2.VideoCapture]:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return None
    return cap


def read_frame(cap: cv2.VideoCapture) -> Optional[np.ndarray]:
    if cap is None:
        return None
    ret, frame = cap.read()
    if not ret or frame is None:
        return None
    return frame


def release_camera(cap: Optional[cv2.VideoCapture]) -> None:
    if cap is not None and cap.isOpened():
        cap.release()


def capture_loop(
    source: Union[int, str],
    callback: Callable[[np.ndarray], bool]
) -> None:
    cap = open_camera(source)
    if cap is None:
        raise RuntimeError(f"無法開啟攝影機或串流來源：{source}")
    try:
        while True:
            frame = read_frame(cap)
            if frame is None:
                continue
            should_continue = callback(frame)
            if should_continue is False:
                break
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        pass
    finally:
        release_camera(cap)
        cv2.destroyAllWindows()