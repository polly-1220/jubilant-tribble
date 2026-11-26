"""
Усі налаштування проєкту в одному місці.
Якщо треба щось змінити (папку, поріг) — міняємо тут.
"""
from pathlib import Path

# Головна папка проєкту (там, де лежить app.py)
ROOT = Path(__file__).resolve().parent.parent

# Папки для даних
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"              # оригінальні знімки
ANNOTATED_DIR = DATA_DIR / "annotated"  # знімки з намальованими знахідками
MASKS_DIR = DATA_DIR / "masks"          # маски тріщин
DB_PATH = DATA_DIR / "rebuild.db"       # база даних SQLite

MODELS_DIR = ROOT / "models"
CRACK_MODEL_PATH = MODELS_DIR / "crack_seg.onnx"  # AI-модель тріщин
MAKET_MODEL_PATH = MODELS_DIR / "maket.glb"       # 3D-модель макета
SECTORS_JSON = ROOT / "sectors.json"              # розмітка секторів на 3D

REPORTS_DIR = ROOT / "reports"
SNAPSHOT_3D = DATA_DIR / "3d_snapshot.png"  # знімок 3D-моделі для звіту (етап 6)
LOGS_DIR = ROOT / "logs"
STATIC_DIR = ROOT / "static"

# Сектори макета: ArUco ID 0..8 -> назва сектора
SECTOR_NAMES = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"]

# Стабільність дрона (етап 2)
GYRO_THRESHOLD_DEFAULT = 15.0   # градусів за секунду — поріг "рівно"
STABLE_HOLD_SEC = 0.3           # скільки часу треба бути нижче порогу
MSP_RATE_HZ = 20                # скільки разів на секунду питаємо дрона

# Автозйомка (етап 3)
AUTO_SHOT_AFTER_SEC = 1.0       # "СТАБІЛЬНО" має тривати 1 с
AUTO_SHOT_MIN_INTERVAL = 2.0    # не частіше ніж раз на 2 с

# Фільтр якості кадру (етап 3) — можна змінювати в інтерфейсі
SHARPNESS_MIN_DEFAULT = 100.0   # дисперсія Лапласіана: менше — кадр розмитий
BRIGHTNESS_MIN_DEFAULT = 50.0   # середня яскравість 0..255: менше — темно
BRIGHTNESS_MAX_DEFAULT = 210.0  # більше — пересвічено

# Папка, звідки імпортувати фото з телефона
IMPORT_DIR = DATA_DIR / "import"


def ensure_folders():
    """Створює всі потрібні папки, якщо їх ще немає."""
    for folder in [RAW_DIR, ANNOTATED_DIR, MASKS_DIR, IMPORT_DIR, MODELS_DIR,
                   REPORTS_DIR, LOGS_DIR, STATIC_DIR]:
        folder.mkdir(parents=True, exist_ok=True)
