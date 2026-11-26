"""
Підсумки за секторами: скільки знімків і знахідок у кожному секторі A1–C3.
Використовується у PDF-звіті і в 3D-двійнику.

Колір сектора — за кількістю ПІДТВЕРДЖЕНИХ людиною тріщин:
    0     — зелений
    1–2   — жовтий
    3 і більше — червоний
"""
from core import captures, config

PENDING, CONFIRMED, REJECTED = "очікує", "підтверджено", "відхилено"

# Кольори у форматі #RRGGBB (для PDF і 3D)
GREEN, YELLOW, RED, GREY = "#2e9e4f", "#f2c12e", "#d63b3b", "#9aa0a6"


def sector_color(confirmed):
    if confirmed >= 3:
        return RED
    if confirmed >= 1:
        return YELLOW
    return GREEN


def sector_level(confirmed):
    """Словами — для таблиці у звіті."""
    if confirmed >= 3:
        return "червоний (3+)"
    if confirmed >= 1:
        return "жовтий (1–2)"
    return "зелений (0)"


def by_sector(survey_id=None):
    """
    Повертає словник: назва сектора -> {images, confirmed, rejected, pending, color, findings}
    Плюс ключ None для знімків без сектора.
    """
    items = captures.list_captures(survey_id)
    result = {name: {"images": 0, "confirmed": 0, "rejected": 0, "pending": 0, "findings": []}
              for name in config.SECTOR_NAMES}
    result[None] = {"images": 0, "confirmed": 0, "rejected": 0, "pending": 0, "findings": []}
    for meta in items:
        s = result[meta["sector"]["name"] if meta["sector"]["name"] in result else None]
        s["images"] += 1
        for f in (meta.get("analysis") or {}).get("findings", []):
            key = {CONFIRMED: "confirmed", REJECTED: "rejected", PENDING: "pending"}[f["status"]]
            s[key] += 1
            s["findings"].append({**f, "image_id": meta["id"], "image_time": meta["time"]})
    for s in result.values():
        s["color"] = sector_color(s["confirmed"])
    return result
