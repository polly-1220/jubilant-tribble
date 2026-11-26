"""
Генерує ArUco-мітки для друку: словник DICT_4X4_50, ID 0–8 = сектори A1–C3.

Запуск (з головної папки проєкту, з увімкненим .venv):
    python tools/make_aruco_markers.py              # мітки по 5 см
    python tools/make_aruco_markers.py --size-cm 3  # менші мітки

Результат у папці markers/:
    aruco_sheet_A4.pdf   — аркуш A4 з усіма 9 мітками (ДРУКУВАТИ В МАСШТАБІ 100%)
    aruco_<ID>_<сектор>.png — кожна мітка окремо
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from core import config  # noqa: E402
from core.fonts import register_reportlab_fonts  # noqa: E402

OUT_DIR = config.ROOT / "markers"


def make_marker_png(marker_id, side_px=600):
    """Створює картинку мітки з білою рамкою (рамка потрібна, щоб камера знайшла мітку)."""
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    img = cv2.aruco.generateImageMarker(dictionary, marker_id, side_px)
    margin = side_px // 6
    img = cv2.copyMakeBorder(img, margin, margin, margin, margin,
                             cv2.BORDER_CONSTANT, value=255)
    path = OUT_DIR / f"aruco_{marker_id}_{config.SECTOR_NAMES[marker_id]}.png"
    cv2.imwrite(str(path), img)
    return path, side_px, margin


def main():
    parser = argparse.ArgumentParser(description="Генерація ArUco-міток для макета")
    parser.add_argument("--size-cm", type=float, default=5.0,
                        help="розмір чорного квадрата мітки в сантиметрах (за замовч. 5)")
    args = parser.parse_args()
    OUT_DIR.mkdir(exist_ok=True)
    register_reportlab_fonts()

    pdf_path = OUT_DIR / "aruco_sheet_A4.pdf"
    page_w, page_h = A4
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setFont("DejaVu-Bold", 14)
    c.drawString(1.5 * cm, page_h - 1.5 * cm, "ReBuildDrone — ArUco-мітки секторів (DICT_4X4_50)")
    c.setFont("DejaVu", 9)
    c.drawString(1.5 * cm, page_h - 2.1 * cm,
                 f"Друкувати в масштабі 100%. Розмір мітки: {args.size_cm:g} см. "
                 "Не обрізати білу рамку навколо мітки.")

    size = args.size_cm * cm
    cell_w = (page_w - 3 * cm) / 3
    cell_h = (page_h - 4 * cm) / 3
    if size > min(cell_w, cell_h) - 1 * cm:
        print("❌ Мітки такого розміру не вміщаються по 9 на аркуш A4. Спробуй --size-cm 5")
        return

    for marker_id in range(9):
        path, side_px, margin = make_marker_png(marker_id)
        row, col = divmod(marker_id, 3)   # A — верхній рядок, C — нижній
        cx = 1.5 * cm + cell_w * (col + 0.5)
        cy = page_h - 2.5 * cm - cell_h * (row + 0.5)
        # Картинка має білу рамку — масштабуємо так, щоб саме чорний квадрат був size
        full = size * (side_px + 2 * margin) / side_px
        c.drawImage(ImageReader(str(path)), cx - full / 2, cy - full / 2 + 0.3 * cm,
                    width=full, height=full)
        c.setFont("DejaVu-Bold", 12)
        label = f"Сектор {config.SECTOR_NAMES[marker_id]}  ·  ID {marker_id}"
        c.drawCentredString(cx, cy - full / 2 - 0.1 * cm, label)
        print(f"✅ {path.name}")

    c.showPage()
    c.save()
    print(f"\n✅ Аркуш для друку: {pdf_path}")
    print("   Друкуй у масштабі 100% (не «підігнати під сторінку»).")


if __name__ == "__main__":
    main()
