"""我希望他能夠看到我電腦上的畫面"""
# ── 工坊組裝：視覺辨識系統 ──────────────────────────────────────────
# 組裝時間：2026-04-27T15:15:21
# 任務數：6

from PIL import Image
from typing import Tuple
import cv2
import io
import mss
import numpy as np
import socket
import struct
import sys
import time

def capture_screen() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        sct_img = sct.grab(monitor)
        img = Image.frombytes('RGB', sct_img.size, sct_img.rgb)
    return img

if __name__ == '__main__':
    screenshot = capture_screen()
    screenshot.show()

def encode_image(image: Image.Image, fmt: str='JPEG', **params) -> Tuple[bytes, int, int]:
    """
    Encode a PIL Image to bytes in the specified format.

    :param image: PIL Image to encode.
    :param fmt: Target format ("JPEG", "PNG", etc.).
    :param params: Optional format-specific parameters (e.g., quality for JPEG).
    :return: Tuple of (encoded bytes, width, height).
    """
    buf = io.BytesIO()
    image.save(buf, format=fmt, **params)
    return (buf.getvalue(), image.width, image.height)

if __name__ == '__main__':
    import mss
    from PIL import Image

    def capture_screen() -> Image.Image:
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            sct_img = sct.grab(monitor)
            img = Image.frombytes('RGB', sct_img.size, sct_img.rgb)
        return img
    screenshot = capture_screen()
    jpeg_bytes, w, h = encode_image(screenshot, fmt='JPEG', quality=85)
    print(f'JPEG size: {len(jpeg_bytes)} bytes, dimensions: {w}x{h}')
    png_bytes, w, h = encode_image(screenshot, fmt='PNG')
    print(f'PNG size: {len(png_bytes)} bytes, dimensions: {w}x{h}')

def send_image(sock: socket.socket, data: bytes) -> None:
    header = struct.pack('>I', len(data))
    sock.sendall(header + data)

def handle_client(conn: socket.socket, addr):
    print(f'Client connected: {addr}')
    try:
        while True:
            img = capture_screen()
            jpeg_bytes = encode_image(img, fmt='JPEG', quality=85)
            send_image(conn, jpeg_bytes)
            time.sleep(0.1)
    except (BrokenPipeError, ConnectionResetError, OSError):
        print(f'Client disconnected: {addr}')
    finally:
        conn.close()

def run_server(host: str, port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(5)
        print(f'Server listening on {host}:{port}')
        while True:
            try:
                conn, addr = s.accept()
                handle_client(conn, addr)
            except KeyboardInterrupt:
                print('\nServer shutting down.')
                break
            except Exception as e:
                print(f'Error: {e}')

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python server.py <host> <port>')
        sys.exit(1)
    host, port = (sys.argv[1], int(sys.argv[2]))
    run_server(host, port)

def receive_image(sock: socket.socket) -> Image.Image:
    """
    Receive a single image from the socket.
    The image is prefixed with a 4‑byte big‑endian unsigned integer
    indicating the length of the image data.
    """
    header = b''
    while len(header) < 4:
        chunk = sock.recv(4 - len(header))
        if not chunk:
            raise ConnectionError('Connection closed while reading header')
        header += chunk
    length, = struct.unpack('>I', header)
    data = b''
    while len(data) < length:
        chunk = sock.recv(min(4096, length - len(data)))
        if not chunk:
            raise ConnectionError('Connection closed while reading image data')
        data += chunk
    return Image.open(io.BytesIO(data))

def tcp_client(ip: str, port: int):
    """
    Connect to the server and continuously receive images.
    Yields PIL Image objects.
    """
    with socket.create_connection((ip, port)) as sock:
        while True:
            try:
                img = receive_image(sock)
                yield img
            except ConnectionError:
                break

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print('Usage: python client.py <server_ip> <port>')
        sys.exit(1)
    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    for idx, image in enumerate(tcp_client(server_ip, server_port), 1):
        print(f'Received image {idx}: {image.size}')
        image.show()

def main():
    if len(sys.argv) != 3:
        print('Usage: python client.py <server_ip> <port>')
        sys.exit(1)
    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    cv2.namedWindow('Screen', cv2.WINDOW_NORMAL)
    for idx, pil_img in enumerate(tcp_client(server_ip, server_port), 1):
        cv2_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        cv2.imshow('Screen', cv2_img)
        key = cv2.waitKey(1)
        if key == ord('q'):
            break
        if cv2.getWindowProperty('Screen', cv2.WND_PROP_VISIBLE) < 1:
            break
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()

def run_client(server_ip: str, port: int, token: str):
    with socket.create_connection((server_ip, port)) as sock:
        token_bytes = token.encode()
        sock.sendall(struct.pack('>I', len(token_bytes)) + token_bytes)
        result = receive_image(sock)
        if result == b'INVALID_TOKEN':
            print('Token invalid. Connection closed.')
            return
        elif result == b'OK':
            print('Token verified. Starting to receive images.')
        else:
            print('Unexpected response. Connection closed.')
            return
        cv2.namedWindow('Screen', cv2.WINDOW_NORMAL)
        while True:
            try:
                img_bytes = receive_image(sock)
                img = Image.open(io.BytesIO(img_bytes))
                cv2_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                cv2.imshow('Screen', cv2_img)
                if cv2.waitKey(1) & 255 == ord('q'):
                    break
            except ConnectionError:
                break
        cv2.destroyAllWindows()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage:')
        print('  Server: python script.py server <host> <port> <token>')
        print('  Client: python script.py client <server_ip> <port> <token>')
        sys.exit(1)
    mode = sys.argv[1]
    if mode == 'server':
        if len(sys.argv) != 5:
            print('Server usage: python script.py server <host> <port> <token>')
            sys.exit(1)
        host, port, token = (sys.argv[2], int(sys.argv[3]), sys.argv[4])
        run_server(host, port, token)
    elif mode == 'client':
        if len(sys.argv) != 5:
            print('Client usage: python script.py client <server_ip> <port> <token>')
            sys.exit(1)
        server_ip, port, token = (sys.argv[2], int(sys.argv[3]), sys.argv[4])
        run_client(server_ip, port, token)
    else:
        print("Unknown mode. Use 'server' or 'client'.")
        sys.exit(1)