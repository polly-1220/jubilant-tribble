"""
Збереження знімків.

Картинка лежить у data/raw/<id>.jpg, а її опис (час, джерело, кути дрона, якість,
сектор, результати аналізу і знахідки) — у базі даних SQLite (див. core/db.py).

Для решти програми опис знімка — це звичайний словник (meta):
    {"id", "survey_id", "file", "time", "source", "original_name", "width", "height",
     "drone": {...} або None, "quality": {...}, "sector": {...},
     "analysis": {..., "findings": [...]}  — лише якщо знімок уже аналізували}
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

import cv2

from core import config, db, quality, sector

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}

FINDING_COLS = ["n", "x", "y", "w", "h", "confidence", "area_px", "length_px",
                "mask", "status", "comment", "reviewed_at"]


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
    Зберігає кадр і його опис у поточне обстеження.
    source: «автозйомка», «кнопка» або «імпорт». Повертає словник-опис знімка.
    """
    cap_id = _new_id()
    img_path = config.RAW_DIR / f"{cap_id}.jpg"
    cv2.imwrite(str(img_path), frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])

    meta = {
        "id": cap_id,
        "survey_id": db.get_active_survey_id(),
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


# ---------- Перетворення: словник <-> рядок бази ----------
def _write_meta(meta, con=None):
    """Записує опис знімка (і його знахідки) в базу."""
    d = meta.get("drone") or {}
    q = meta["quality"]
    s = meta["sector"]
    a = meta.get("analysis")
    row = {
        "id": meta["id"], "survey_id": meta["survey_id"], "file": meta["file"],
        "time": meta["time"], "source": meta["source"],
        "original_name": meta.get("original_name"),
        "width": meta.get("width"), "height": meta.get("height"),
        "roll": d.get("roll"), "pitch": d.get("pitch"), "yaw": d.get("yaw"),
        "gx": d.get("gx"), "gy": d.get("gy"), "gz": d.get("gz"),
        "drone_stable": int(d["stable"]) if d else None,
        "drone_demo": int(d.get("demo", False)) if d else None,
        "sharpness": q["sharpness"], "brightness": q["brightness"],
        "quality_ok": int(q["ok"]), "quality_reasons": ",".join(q["reasons"]),
        "sector": s.get("name"), "sector_method": s.get("method"),
        "aruco_ids": ",".join(str(i) for i in s.get("aruco_ids", [])),
        "analyzed_at": a["time"] if a else None,
        "model": a["model"] if a else None,
        "is_stub": int(a["is_stub"]) if a else None,
        "conf_threshold": a["conf_threshold"] if a else None,
        "analysis_ms": a["ms"] if a else None,
    }
    cols = ", ".join(row)
    marks = ", ".join(f":{k}" for k in row)

    def write(c):
        c.execute(f"INSERT OR REPLACE INTO images ({cols}) VALUES ({marks})", row)
        c.execute("DELETE FROM findings WHERE image_id = ?", (meta["id"],))
        for f in (a or {}).get("findings", []):
            x, y, w, h = f["bbox"]
            c.execute(f"""INSERT INTO findings (image_id, {", ".join(FINDING_COLS)})
                          VALUES (?, {", ".join("?" * len(FINDING_COLS))})""",
                      (meta["id"], f["n"], x, y, w, h, f["confidence"], f["area_px"],
                       f["length_px"], f["mask"], f["status"], f.get("comment", ""),
                       f.get("reviewed_at")))

    db.init()
    with db._lock:
        if con is not None:
            write(con)
        else:
            with db.connect() as c:
                write(c)


def _row_to_meta(r, findings):
    has_drone = r["roll"] is not None
    meta = {
        "id": r["id"], "survey_id": r["survey_id"], "file": r["file"], "time": r["time"],
        "source": r["source"], "original_name": r["original_name"],
        "width": r["width"], "height": r["height"],
        "drone": {
            "roll": r["roll"], "pitch": r["pitch"], "yaw": r["yaw"],
            "gx": r["gx"], "gy": r["gy"], "gz": r["gz"],
            "stable": bool(r["drone_stable"]), "demo": bool(r["drone_demo"]),
        } if has_drone else None,
        "quality": {
            "sharpness": r["sharpness"], "brightness": r["brightness"],
            "ok": bool(r["quality_ok"]),
            "reasons": [x for x in (r["quality_reasons"] or "").split(",") if x],
        },
        "sector": {
            "name": r["sector"], "method": r["sector_method"],
            "aruco_ids": [int(x) for x in (r["aruco_ids"] or "").split(",") if x],
        },
    }
    if r["analyzed_at"]:
        meta["analysis"] = {
            "time": r["analyzed_at"], "model": r["model"], "is_stub": bool(r["is_stub"]),
            "conf_threshold": r["conf_threshold"], "ms": r["analysis_ms"],
            "findings": [{
                "n": f["n"], "bbox": [f["x"], f["y"], f["w"], f["h"]],
                "confidence": f["confidence"], "area_px": f["area_px"],
                "length_px": f["length_px"], "mask": f["mask"], "status": f["status"],
                "comment": f["comment"] or "", "reviewed_at": f["reviewed_at"],
            } for f in findings],
        }
    return meta


# ---------- Читання ----------
def load(cap_id):
    db.init()
    with db.connect() as con:
        r = con.execute("SELECT * FROM images WHERE id = ?", (cap_id,)).fetchone()
        if r is None:
            raise KeyError(f"Знімок {cap_id} не знайдено в базі")
        f = con.execute("SELECT * FROM findings WHERE image_id = ? ORDER BY n",
                        (cap_id,)).fetchall()
    return _row_to_meta(r, f)


def list_captures(survey_id=None):
    """Знімки обстеження (за замовчуванням — активного), від найновішого."""
    db.init()
    _migrate_old_json()
    if survey_id is None:
        survey_id = db.get_active_survey_id()
    with db.connect() as con:
        rows = con.execute("SELECT * FROM images WHERE survey_id = ? ORDER BY id DESC",
                           (survey_id,)).fetchall()
        allf = con.execute("""SELECT f.* FROM findings f JOIN images i ON i.id = f.image_id
                              WHERE i.survey_id = ? ORDER BY f.image_id, f.n""",
                           (survey_id,)).fetchall()
    by_image = {}
    for f in allf:
        by_image.setdefault(f["image_id"], []).append(f)
    return [_row_to_meta(r, by_image.get(r["id"], [])) for r in rows]


# ---------- Зміни ----------
def update(cap_id, change):
    """
    Безпечно змінює опис знімка: читає, викликає change(meta), записує.
    Замок не дає двом потокам (камера і інтерфейс) писати одночасно.
    """
    with db._lock:
        meta = load(cap_id)
        change(meta)
        _write_meta(meta)
        return meta


def set_sector_manual(cap_id, name):
    """Вибір сектора вручну (якщо мітку не знайдено або визначено неправильно)."""
    def change(meta):
        if name is None:
            meta["sector"].update({"name": None, "method": None})
        else:
            meta["sector"].update({"name": name, "method": "вручну"})
    update(cap_id, change)


def delete_capture(cap_id):
    """Видаляє знімок з бази разом з файлами: картинка, маски, розмічена копія."""
    with db._lock, db.connect() as con:
        con.execute("DELETE FROM findings WHERE image_id = ?", (cap_id,))
        con.execute("DELETE FROM images WHERE id = ?", (cap_id,))
    files = [config.RAW_DIR / f"{cap_id}.jpg", config.ANNOTATED_DIR / f"{cap_id}.jpg"]
    files += list(config.MASKS_DIR.glob(f"{cap_id}_*.png"))
    for p in files:
        p.unlink(missing_ok=True)


# ---------- Перенесення старих описів (.json з етапів 3–4) у базу ----------
def _migrate_old_json():
    old = sorted(config.RAW_DIR.glob("*.json"))
    if not old:
        return
    archive = config.RAW_DIR / "_старі_json"
    archive.mkdir(exist_ok=True)
    survey_id = db.get_active_survey_id()
    for p in old:
        try:
            with open(p, encoding="utf-8") as f:
                meta = json.load(f)
            meta.setdefault("survey_id", survey_id)
            _write_meta(meta)
            shutil.move(str(p), str(archive / p.name))
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(f"Не вдалося перенести {p.name}: {e}")


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
