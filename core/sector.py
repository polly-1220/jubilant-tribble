"""
Визначення сектора макета за ArUco-мітками.
Словник DICT_4X4_50, ID 0..8 відповідають секторам A1..C3 (див. config.SECTOR_NAMES).
Якщо на кадрі кілька міток — беремо ту, що найближча до центру кадру
(бо саме на неї дивиться камера).
"""
import threading

import cv2
import numpy as np

from core import config

_dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
_detector = cv2.aruco.ArucoDetector(_dictionary, cv2.aruco.DetectorParameters())
_lock = threading.Lock()


def detect(frame_bgr):
    """
    Шукає мітки. Повертає (corners, ids) — ids лише з діапазону 0..8.
    corners — список масивів 1x4x2 (координати кутів кожної мітки).
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    with _lock:   # детектор спільний для кількох потоків — по черзі
        corners, ids, _rejected = _detector.detectMarkers(gray)
    if ids is None:
        return [], []
    good_corners, good_ids = [], []
    for c, i in zip(corners, ids.flatten()):
        if 0 <= int(i) < len(config.SECTOR_NAMES):
            good_corners.append(c)
            good_ids.append(int(i))
    return good_corners, good_ids


def find_sector(frame_bgr):
    """
    Повертає словник: name — назва сектора (або None), ids — усі знайдені ID.
    """
    corners, ids = detect(frame_bgr)
    if not ids:
        return {"name": None, "method": None, "aruco_ids": []}
    h, w = frame_bgr.shape[:2]
    center = np.array([w / 2, h / 2])
    # Відстань від центру кожної мітки до центру кадру
    dists = [np.linalg.norm(c.reshape(4, 2).mean(axis=0) - center) for c in corners]
    best = ids[int(np.argmin(dists))]
    return {"name": config.SECTOR_NAMES[best], "method": "ArUco", "aruco_ids": sorted(ids)}


def draw(frame_bgr):
    """Малює знайдені мітки і назви секторів на копії кадру (для попереднього перегляду)."""
    out = frame_bgr.copy()
    corners, ids = detect(out)
    if ids:
        cv2.aruco.drawDetectedMarkers(out, corners, np.array(ids).reshape(-1, 1))
        for c, i in zip(corners, ids):
            x, y = c.reshape(4, 2).mean(axis=0).astype(int)
            cv2.putText(out, config.SECTOR_NAMES[i], (x - 30, y + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 4)
    return out
