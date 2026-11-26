"""
Вебкамера у фоновому потоці + автозйомка.

Потік постійно бере кадри з камери і тримає останній кадр у пам'яті.
Якщо увімкнена автозйомка, він також стежить за дроном:
коли «СТАБІЛЬНО» триває 1 с — робить один знімок (не частіше ніж раз на 2 с).
Наступний автознімок буде лише після того, як дрон знову стане нестабільним
і потім знову стабільним (щоб не робити десятки однакових кадрів).
"""
import threading
import time

import cv2

from core import captures, config
from core.drone_reader import get_reader


class CameraReader:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.running = False
        self.index = 0
        self.frame = None          # останній кадр (BGR)
        self.error = None
        self.auto_enabled = False
        self.last_shot_time = 0.0
        self.shot_this_episode = False
        self.last_message = None   # повідомлення про останній знімок
        self.shots_count = 0       # скільки знімків зроблено (щоб оновити галерею)

    def start(self, index=0):
        self.stop()
        self.index = index
        self.error = None
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=3)
            self.thread = None
        with self.lock:
            self.frame = None

    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    # ---------- знімок ----------
    def take_shot(self, source="кнопка"):
        """Зберігає поточний кадр разом з кутами дрона. Повертає опис або None."""
        frame = self.get_frame()
        if frame is None:
            return None
        reader = get_reader()
        meta = captures.save_capture(frame, source, reader.latest_sample())
        with self.lock:
            self.last_shot_time = time.monotonic()
            self.shots_count += 1
            q = "якість добра" if meta["quality"]["ok"] else \
                "перезняти: " + ", ".join(meta["quality"]["reasons"])
            sec = meta["sector"]["name"] or "сектор не визначено"
            self.last_message = f"{time.strftime('%H:%M:%S')} · {source} · {sec} · {q}"
        return meta

    # ---------- фонова робота ----------
    def _loop(self):
        # На macOS використовуємо системний механізм AVFoundation
        cap = cv2.VideoCapture(self.index, cv2.CAP_AVFOUNDATION)
        if not cap.isOpened():
            self.error = (
                f"Не вдалося відкрити камеру №{self.index}. Перевір доступ: "
                "Системні параметри → Конфіденційність і безпека → Камера → "
                "увімкни для «Термінал», потім перезапусти застосунок. "
                "Також закрий інші програми, які використовують камеру (FaceTime, Zoom)."
            )
            self.running = False
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        failures = 0
        while self.running:
            ok, frame = cap.read()
            if not ok or frame is None:
                failures += 1
                if failures > 50:
                    self.error = "Камера перестала надсилати кадри."
                    break
                time.sleep(0.05)
                continue
            failures = 0
            with self.lock:
                self.frame = frame
            if self.auto_enabled:
                self._auto_check()
        cap.release()
        self.running = False

    def _auto_check(self):
        sample = get_reader().latest_sample()
        if sample is None or not sample["stable"]:
            self.shot_this_episode = False   # дрон нестабільний — новий «епізод»
            return
        now = time.monotonic()
        if (sample["stable_for"] >= config.AUTO_SHOT_AFTER_SEC
                and not self.shot_this_episode
                and now - self.last_shot_time >= config.AUTO_SHOT_MIN_INTERVAL):
            self.shot_this_episode = True
            self.take_shot("автозйомка")


_camera = None


def get_camera():
    global _camera
    if _camera is None:
        _camera = CameraReader()
    return _camera
