"""
Збереження знімків.

Кожен знімок — це два файли в data/raw/:
    20261126_153012_345.jpg   — сама картинка
    20261126_153012_345.json  — опис: час, джерело, кути дрона, якість, сектор
(На етапі 5 ці описи також потраплять у базу даних SQLite.)
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

import cv2

from core import config, quality, sector

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def _new_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _drone_info(drone_sample, demo):
    """Кути дрона в момент зйомки (або None, якщо дрона немає)."""
    if not drone_sample:
        return None
    keys = ["roll", "pitch", "yaw", "gx", "gy", "gz", "stable"]
    info = {k: (round(drone_sample[k], 2) if isinstance(drone_sample[k], float)
                else drone_sample[k]) for k in keys}
    info["demo"] = bool(demo)
    return info


def save_capture(frame_bgr, source, drone_sample=None, demo=False, original_name=None):
    """
    Зберігає кадр і його опис. source: «автозйомка», «кнопка» або «імпорт».
    Повертає словник-опис знімка.
    """
    cap_id = _new_id()
    img_path = config.RAW_DIR / f"{cap_id}.jpg"
    cv2.imwrite(str(img_path), frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])

    meta = {
        "id": cap_id,
        "file": img_path.name,
        "time": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "original_name": original_name,
        "width": int(frame_bgr.shape[1]),
        "height": int(frame_bgr.shape[0]),
        "drone": _drone_info(drone_sample, demo),
        "quality": quality.check(frame_bgr),
        "sector": sector.find_sector(frame_bgr),
    }
    _write_meta(meta)
    return meta


def _meta_path(cap_id):
    return config.RAW_DIR / f"{cap_id}.json"


def _write_meta(meta):
    with open(_meta_path(meta["id"]), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def load(cap_id):
    with open(_meta_path(cap_id), encoding="utf-8") as f:
        return json.load(f)


def list_captures():
    """Усі знімки, від найновішого до найстарішого."""
    metas = []
    for p in sorted(config.RAW_DIR.glob("*.json"), reverse=True):
        try:
            with open(p, encoding="utf-8") as f:
                metas.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass   # пошкоджений файл — пропускаємо
    return metas


def set_sector_manual(cap_id, name):
    """Вибір сектора вручну (якщо мітку не знайдено або визначено неправильно)."""
    meta = load(cap_id)
    if name is None:
        meta["sector"].update({"name": None, "method": None})
    else:
        meta["sector"].update({"name": name, "method": "вручну"})
    _write_meta(meta)


def delete_capture(cap_id):
    for p in [config.RAW_DIR / f"{cap_id}.jpg", _meta_path(cap_id)]:
        p.unlink(missing_ok=True)


# ---------- Імпорт фото ----------
def import_bytes(data, name):
    """Імпорт одного файлу (наприклад, з кнопки завантаження). Повертає опис або текст помилки."""
    import numpy as np
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return f"{name}: не вдалося відкрити (формат HEIC з iPhone не підтримується — збережи як JPEG)"
    return save_capture(frame, "імпорт", original_name=name)


def import_folder(folder):
    """Імпортує всі фото з папки. Повертає (кількість, список помилок)."""
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        return 0, [f"Папку не знайдено: {folder}"]
    count, errors = 0, []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() == ".heic":
            errors.append(f"{p.name}: HEIC не підтримується — збережи фото як JPEG")
            continue
        if p.suffix.lower() not in IMAGE_EXT:
            continue
        frame = cv2.imread(str(p))
        if frame is None:
            errors.append(f"{p.name}: не вдалося відкрити")
            continue
        save_capture(frame, "імпорт", original_name=p.name)
        # Переносимо оброблене фото в підпапку, щоб не імпортувати двічі
        done = folder / "імпортовано"
        done.mkdir(exist_ok=True)
        shutil.move(str(p), str(done / p.name))
        count += 1
    return count, errors
