"""
Детектор стабільності.
Дрон вважається «СТАБІЛЬНИМ», якщо кутова швидкість (гіроскоп) по всіх трьох осях
нижча за поріг безперервно протягом hold_sec секунд (за замовчуванням 0.3 с).
"""
from core import config


class StabilityDetector:
    def __init__(self, threshold=config.GYRO_THRESHOLD_DEFAULT,
                 hold_sec=config.STABLE_HOLD_SEC):
        self.threshold = threshold   # градусів за секунду
        self.hold_sec = hold_sec
        self.calm_since = None       # з якого моменту гіроскоп нижче порогу
        self.stable = False

    def update(self, gyro, t):
        """
        gyro — три числа (°/с), t — поточний час у секундах.
        Повертає True, якщо зараз «СТАБІЛЬНО».
        """
        calm = all(abs(g) < self.threshold for g in gyro)
        if calm:
            if self.calm_since is None:
                self.calm_since = t
            self.stable = (t - self.calm_since) >= self.hold_sec
        else:
            self.calm_since = None
            self.stable = False
        return self.stable

    def stable_for(self, t):
        """Скільки секунд поспіль триває «СТАБІЛЬНО» (0, якщо зараз нестабільно)."""
        if not self.stable or self.calm_since is None:
            return 0.0
        return t - self.calm_since - self.hold_sec

    def reset(self):
        self.calm_since = None
        self.stable = False
