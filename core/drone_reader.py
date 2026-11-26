"""
Фонове читання дрона.

Streamlit перезапускає скрипт app.py при кожному кліку, тому сам зв'язок з дроном
живе в окремому «фоновому потоці» (thread). Він ~20 разів на секунду питає дрона
про кути і гіроскоп і зберігає останні значення. Інтерфейс лише читає ці значення.

Демо-режим: якщо дрона немає під рукою, потік генерує «несправжні» дані
(по черзі «трясемо» і «тримаємо рівно»), щоб перевірити інтерфейс.
"""
import math
import random
import threading
import time
from collections import deque

from core import config
from core.msp import DroneError, MSPClient
from core.stability import StabilityDetector

HISTORY_SEC = 10  # скільки секунд показувати на графіку


class DroneReader:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.running = False
        self.demo = False

        self.status = "не підключено"   # короткий стан для інтерфейсу
        self.error = None               # зрозуміле повідомлення про помилку
        self.port = None
        self.fc_info = ""

        self.latest = None              # останні дані (словник)
        # запас ×2, а зайве відрізаємо за часом при малюванні графіка
        self.history = deque(maxlen=HISTORY_SEC * config.MSP_RATE_HZ * 2)
        self.detector = StabilityDetector()

    # ---------- керування ----------
    def start(self, demo=False):
        """Запускає фоновий потік (якщо вже працює — перезапускає)."""
        self.stop()
        self.demo = demo
        self.running = True
        self.error = None
        self.history.clear()
        self.detector.reset()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None
        with self.lock:
            self.status = "не підключено"
            self.latest = None

    def set_threshold(self, value):
        self.detector.threshold = float(value)

    def latest_sample(self):
        """Лише останні дані (швидко, без історії). None — якщо даних немає."""
        with self.lock:
            if not self.running or self.latest is None:
                return None
            return dict(self.latest)

    def snapshot(self):
        """Копія поточних даних — щоб інтерфейс читав їх безпечно."""
        with self.lock:
            return {
                "running": self.running,
                "demo": self.demo,
                "status": self.status,
                "error": self.error,
                "port": self.port,
                "fc_info": self.fc_info,
                "latest": dict(self.latest) if self.latest else None,
                "history": list(self.history),
            }

    # ---------- фонова робота ----------
    def _loop(self):
        period = 1.0 / config.MSP_RATE_HZ
        client = None
        t_start = time.monotonic()

        while self.running:
            t0 = time.monotonic()

            if self.demo:
                roll, pitch, yaw, gyro = self._demo_sample(t0 - t_start)
                with self.lock:
                    self.status = "демо-режим (без дрона)"
                    self.port, self.fc_info, self.error = None, "", None
            else:
                # 1) Якщо ще не підключені — пробуємо підключитися
                if client is None:
                    client = MSPClient()
                    try:
                        client.open()
                        info = client.read_fc_info()
                        with self.lock:
                            self.status = "підключено"
                            self.port, self.fc_info, self.error = client.port, info, None
                    except (DroneError, TimeoutError, OSError) as e:
                        client.close()
                        client = None
                        with self.lock:
                            self.status = "немає зв'язку"
                            self.error = str(e)
                            self.latest = None
                        self._sleep(2.0)   # повторна спроба через 2 с
                        continue
                # 2) Читаємо кути і гіроскоп
                try:
                    roll, pitch, yaw = client.read_attitude()
                    _acc, gyro = client.read_raw_imu()
                except TimeoutError:
                    continue   # одна загублена відповідь — не страшно
                except (DroneError, OSError) as e:
                    client.close()
                    client = None
                    with self.lock:
                        self.status = "зв'язок втрачено"
                        self.error = f"Зв'язок з дроном втрачено (кабель від'єднано?). {e}"
                        self.latest = None
                    continue

            # 3) Оновлюємо стабільність і історію для графіка
            now = time.monotonic()
            stable = self.detector.update(gyro, now)
            sample = {
                "t": now,
                "roll": roll, "pitch": pitch, "yaw": yaw,
                "gx": gyro[0], "gy": gyro[1], "gz": gyro[2],
                "stable": stable,
                "stable_for": self.detector.stable_for(now),
            }
            with self.lock:
                self.latest = sample
                self.history.append(sample)

            # 4) Чекаємо до наступного опитування (~20 разів на секунду)
            self._sleep(period - (time.monotonic() - t0))

        if client is not None:
            client.close()

    def _sleep(self, seconds):
        """Сон, який швидко переривається, якщо натиснули «Від'єднати»."""
        end = time.monotonic() + max(0.0, seconds)
        while self.running and time.monotonic() < end:
            time.sleep(0.01)

    @staticmethod
    def _demo_sample(t):
        """Несправжні дані: 3 с «трясемо», 4 с «тримаємо рівно», по колу."""
        shaking = (t % 7.0) < 3.0
        amp = 60.0 if shaking else 2.0
        gyro = tuple(amp * math.sin(t * f) + random.uniform(-1, 1) for f in (7.0, 5.0, 3.0))
        roll = 8 * math.sin(t * 1.3) if shaking else 1.5 * math.sin(t * 0.5)
        pitch = 6 * math.sin(t * 1.7) if shaking else 1.0 * math.sin(t * 0.4)
        yaw = (t * 5) % 360
        return roll, pitch, yaw, gyro


# Один спільний «читач» на весь застосунок (порт можна відкрити лише один раз)
_reader = None


def get_reader():
    global _reader
    if _reader is None:
        _reader = DroneReader()
    return _reader
