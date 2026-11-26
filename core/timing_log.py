"""
Лог для тестування: скільки часу займає аналіз кадру і формування звіту.
Записується в logs/timing.csv (відкривається в Excel / Numbers).
"""
import csv
from datetime import datetime

from core import config

LOG_PATH = config.LOGS_DIR / "timing.csv"


def log(event, ms, item="", note=""):
    """event — що сталося («аналіз кадру», «PDF-звіт»), ms — тривалість у мілісекундах."""
    config.LOGS_DIR.mkdir(exist_ok=True)
    new_file = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["час", "подія", "об'єкт", "мс", "примітка"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), event, item, round(ms, 1), note])


def read_rows():
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))
