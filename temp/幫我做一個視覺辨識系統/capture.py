import cv2
import numpy as np
import requests


def capture_from_camera(camera_index=0):
    import sys
    api_preference = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(camera_index, api_preference)
    if not cap.isOpened():
        raise ValueError(f"無法開啟攝影機，index={camera_index}")
    try:
        ret, frame = cap.read()
        if not ret or frame is None:
            cap.grab()
            ret, frame = cap.retrieve()
        if not ret or frame is None:
            raise ValueError(f"無法從攝影機 index={camera_index} 讀取影像幀")
        return frame
    finally:
        cap.release()


def capture_from_file(file_path):
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
    import os
    ext = os.path.splitext(file_path)[1].lower()
    if ext in image_exts:
        frame = cv2.imread(file_path)
        if frame is None:
            raise ValueError(f"無法讀取圖片檔案：{file_path}")
        return frame
    else:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise ValueError(f"無法開啟影片檔案：{file_path}")
        try:
            ret, frame = cap.read()
            if not ret or frame is None:
                cap.grab()
                ret, frame = cap.retrieve()
            if not ret or frame is None:
                raise ValueError(f"無法從影片檔案讀取影像幀：{file_path}")
            return frame
        finally:
            cap.release()


def capture_from_url(url):
    cap = cv2.VideoCapture(url)
    if cap.isOpened():
        try:
            ret, frame = cap.read()
            if ret and frame is not None:
                return frame
        finally:
            cap.release()

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = np.frombuffer(response.content, dtype=np.uint8)
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"無法解碼來自 URL 的影像：{url}")
        return frame
    except requests.RequestException as e:
        raise ValueError(f"無法從 URL 下載影像：{url}，錯誤：{e}")


def release_camera(cap):
    if cap is None:
        return
    if cap.isOpened():
        cap.release()