"""QR scanner client for the Secure QR Flutter identity pass.

Supports keyboard-wedge USB QR scanners (or pasted token) and optional webcam
capture with OpenCV. Backend makes ALL access decisions; offline = DENIED.

Install: py -m pip install requests opencv-python
Example:
  set SCANNER_KEY=<provisioned scanner secret>
  py scanner.py --scanner-id scanner-001 --mode camera

Run only on loopback HTTP for development; production requires HTTPS.
"""
import argparse
import os
import sys
from urllib.parse import urlparse

import requests


def read_camera_qr(camera_index: int = 0) -> str | None:
    try:
        import cv2
    except ImportError:
        print('Install camera support: py -m pip install opencv-python')
        return None
    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        print('Camera unavailable. Check camera permissions and index.')
        return None
    detector = cv2.QRCodeDetector()
    print('Hold Flutter QR in front of camera. Press Q to cancel.')
    try:
        while True:
            ok, image = camera.read()
            if not ok:
                print('Camera read failed.')
                return None
            text, points, _ = detector.detectAndDecode(image)
            if text:
                return text.strip()
            cv2.imshow('Secure QR Scanner (Q to cancel)', image)
            if cv2.waitKey(20) & 0xFF in (ord('q'), 27):
                return None
    finally:
        camera.release()
        cv2.destroyAllWindows()


def safe_base_url(value: str) -> str:
    u = urlparse(value)
    if u.scheme == 'https' and u.netloc and not u.username and not u.password:
        return value.rstrip('/')
    if (u.scheme == 'http' and u.hostname in ('localhost', '127.0.0.1')
            and u.port == 8000 and not u.username and not u.password):
        return value.rstrip('/')
    raise ValueError('Use HTTPS; only loopback http://127.0.0.1:8000 is permitted for development')


def verify_online(session: requests.Session, url: str, scanner_id: str, secret: str, token: str):
    try:
        response = session.post(
            f'{url}/scanner/verify',
            headers={'X-Scanner-ID': scanner_id, 'X-Scanner-Key': secret},
            json={'token': token}, timeout=(3, 8),
        )
        if response.status_code != 200:
            print(f'ACCESS DENIED — Backend HTTP {response.status_code} (no offline grant)')
            return
        data = response.json()
        if data.get('decision') == 'GRANTED':
            print(f"ACCESS GRANTED — room {data.get('room_id', '?')}")
        else:
            print(f"ACCESS DENIED — {data.get('reason', 'Not authorized')}")
    except (requests.RequestException, ValueError) as exc:
        # Never grant access on connection errors, invalid server replies, or timeout.
        print(f'ACCESS DENIED — Verification unavailable ({type(exc).__name__})')


def main():
    parser = argparse.ArgumentParser(description='Secure QR scanner (online / fail closed)')
    parser.add_argument('--scanner-id', default=os.getenv('SCANNER_ID', 'scanner-001'))
    parser.add_argument('--backend', default=os.getenv('QR_API_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--mode', choices=('camera', 'keyboard'), default='keyboard')
    parser.add_argument('--camera-index', type=int, default=0)
    args = parser.parse_args()
    secret = os.getenv('SCANNER_KEY')
    if not secret:
        parser.error('Set the SCANNER_KEY environment variable for this scanner')
    try:
        base_url = safe_base_url(args.backend)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'Scanner {args.scanner_id} ready. All access decisions come from backend.')
    with requests.Session() as session:
        while True:
            if args.mode == 'camera':
                token = read_camera_qr(args.camera_index)
                if token is None:
                    break
            else:
                token = input('Scan QR (or paste JWT, exit to quit): ').strip()
                if token.lower() == 'exit':
                    break
            if not token:
                continue
            verify_online(session, base_url, args.scanner_id, secret, token)


if __name__ == '__main__':
    main()
