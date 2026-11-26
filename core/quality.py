"""
Фільтр якості кадру.

Різкість: «дисперсія Лапласіана». Лапласіан підсвічує краї на зображенні.
У різкому кадрі країв багато і вони контрастні — число велике.
У розмитому кадрі краї «розмазані» — число маленьке.

Яскравість: середнє значення сірого (0 = чорний, 255 = білий).
"""
import cv2

from core import config


class QualitySettings:
    """Пороги якості (змінюються повзунками в інтерфейсі)."""
    sharpness_min = config.SHARPNESS_MIN_DEFAULT
    brightness_min = config.BRIGHTNESS_MIN_DEFAULT
    brightness_max = config.BRIGHTNESS_MAX_DEFAULT


def measure(frame_bgr):
    """Повертає (різкість, яскравість) для кадру."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    # Різкість залежить від розміру кадру, тому міряємо на однаковій ширині 1280
    if gray.shape[1] != 1280:
        scale = 1280 / gray.shape[1]
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    return sharpness, brightness


def check(frame_bgr, settings=QualitySettings):
    """
    Перевіряє кадр. Повертає словник:
      ok — чи кадр хороший; reasons — що не так (українською).
    """
    sharpness, brightness = measure(frame_bgr)
    reasons = []
    if sharpness < settings.sharpness_min:
        reasons.append("розмитий")
    if brightness < settings.brightness_min:
        reasons.append("затемний")
    if brightness > settings.brightness_max:
        reasons.append("пересвічений")
    return {
        "sharpness": round(sharpness, 1),
        "brightness": round(brightness, 1),
        "ok": not reasons,
        "reasons": reasons,
    }
