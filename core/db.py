"""
База даних SQLite: data/rebuild.db

Три головні таблиці:
    surveys  — обстеження (наприклад, «Макет школи, 26 листопада»)
    images   — знімки: файл, час, кути дрона, якість, сектор, дані аналізу
    findings — знахідки AI на знімках: рамка, впевненість, маска, рішення людини, коментар
І маленька таблиця settings — налаштування (яке обстеження зараз активне).

SQLite — це база даних в одному файлі, сервер не потрібен, працює офлайн.
Відкрити файл можна, наприклад, програмою «DB Browser for SQLite».
"""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from core import config

_lock = threading.RLock()   # записуємо в базу по черзі (камера і інтерфейс — різні потоки)

SCHEMA = """
CREATE TABLE IF NOT EXISTS surveys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    notes       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS images (
    id              TEXT PRIMARY KEY,          -- напр. 20261126_153012_345
    survey_id       INTEGER NOT NULL REFERENCES surveys(id),
    file            TEXT NOT NULL,             -- назва файлу в data/raw/
    time            TEXT NOT NULL,
    source          TEXT NOT NULL,             -- автозйомка / кнопка / імпорт
    original_name   TEXT,
    width           INTEGER,
    height          INTEGER,
    -- кути дрона в момент зйомки (NULL, якщо дрона не було)
    roll REAL, pitch REAL, yaw REAL, gx REAL, gy REAL, gz REAL,
    drone_stable    INTEGER,
    drone_demo      INTEGER,
    -- якість кадру
    sharpness       REAL,
    brightness      REAL,
    quality_ok      INTEGER,
    quality_reasons TEXT,                      -- через кому
    -- сектор
    sector          TEXT,
    sector_method   TEXT,                      -- ArUco / вручну
    aruco_ids       TEXT,                      -- через кому
    -- аналіз (NULL, якщо ще не аналізували)
    analyzed_at     TEXT,
    model           TEXT,
    is_stub         INTEGER,
    conf_threshold  REAL,
    analysis_ms     REAL
);

CREATE TABLE IF NOT EXISTS findings (
    image_id    TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    n           INTEGER NOT NULL,              -- номер знахідки на знімку
    x INTEGER, y INTEGER, w INTEGER, h INTEGER,
    confidence  REAL,                          -- впевненість моделі, НЕ оцінка небезпеки
    area_px     INTEGER,
    length_px   REAL,
    mask        TEXT,                          -- файл у data/masks/
    status      TEXT NOT NULL DEFAULT 'очікує',
    comment     TEXT DEFAULT '',
    reviewed_at TEXT,
    PRIMARY KEY (image_id, n)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def connect():
    """
    З'єднання з базою:  with db.connect() as con: ...
    Наприкінці зміни зберігаються (commit), а з'єднання закривається.
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row          # рядки можна читати як словник: row["name"]
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


_initialized = False


def init():
    """Створює таблиці (якщо їх ще немає) і перше обстеження."""
    global _initialized
    if _initialized:
        return
    with _lock, connect() as con:
        con.execute("PRAGMA journal_mode = WAL")   # надійніше при одночасному читанні
        con.executescript(SCHEMA)
        if con.execute("SELECT COUNT(*) FROM surveys").fetchone()[0] == 0:
            con.execute("INSERT INTO surveys (name, created_at) VALUES (?, ?)",
                        ("Перше обстеження", _now()))
    _initialized = True


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- Обстеження ----------
def create_survey(name, notes=""):
    init()
    with _lock, connect() as con:
        cur = con.execute("INSERT INTO surveys (name, created_at, notes) VALUES (?, ?, ?)",
                          (name.strip() or "Без назви", _now(), notes))
        return cur.lastrowid


def list_surveys():
    init()
    with connect() as con:
        rows = con.execute("""
            SELECT s.*, COUNT(i.id) AS images
            FROM surveys s LEFT JOIN images i ON i.survey_id = s.id
            GROUP BY s.id ORDER BY s.id DESC""").fetchall()
    return [dict(r) for r in rows]


def get_survey(survey_id):
    init()
    with connect() as con:
        r = con.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
    return dict(r) if r else None


def get_active_survey_id():
    """Обстеження, у яке зараз зберігаються нові знімки."""
    init()
    with connect() as con:
        r = con.execute("SELECT value FROM settings WHERE key = 'active_survey'").fetchone()
        if r and con.execute("SELECT 1 FROM surveys WHERE id = ?", (int(r[0]),)).fetchone():
            return int(r[0])
        return con.execute("SELECT MAX(id) FROM surveys").fetchone()[0]


def set_active_survey_id(survey_id):
    init()
    with _lock, connect() as con:
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('active_survey', ?)",
                    (str(survey_id),))
