"""
Аналіз знімка і перевірка людиною.

analyze(cap_id):
  1) запускає детектор (AI-модель або заглушку);
  2) зберігає маску кожної знахідки в data/masks/<знімок>_<номер>.png;
  3) малює розмічену копію в data/annotated/<знімок>.jpg;
  4) записує знахідки в опис знімка і час аналізу в logs/timing.csv.

Кожна знахідка має статус: «очікує» → «підтверджено» або «відхилено» (вирішує людина).
"""
import time
from datetime import datetime

import cv2
import numpy as np

from core import captures, config, detector, timing_log

PENDING, CONFIRMED, REJECTED = "очікує", "підтверджено", "відхилено"

# Кольори для розмітки (BGR): чекає перевірки — жовтий, підтверджено — червоний, відхилено — сірий
STATUS_COLORS = {PENDING: (0, 200, 255), CONFIRMED: (40, 40, 230), REJECTED: (150, 150, 150)}


def analyze(cap_id, conf_thr=0.25):
    meta = captures.load(cap_id)
    img = cv2.imread(str(config.RAW_DIR / meta["file"]))
    if img is None:
        raise FileNotFoundError(f"Не знайдено файл знімка {meta['file']}")

    det = detector.get_detector()
    t0 = time.perf_counter()
    found = det.predict(img, conf_thr=conf_thr)
    ms = (time.perf_counter() - t0) * 1000

    # Старі маски цього знімка видаляємо (якщо аналізуємо повторно)
    for p in config.MASKS_DIR.glob(f"{cap_id}_*.png"):
        p.unlink()

    findings = []
    for n, f in enumerate(found, start=1):
        mask_name = f"{cap_id}_{n}.png"
        cv2.imwrite(str(config.MASKS_DIR / mask_name), f["mask"] * 255)
        ys, xs = np.nonzero(f["mask"])
        length = 0.0
        if len(xs) >= 5:
            (_, _), (rw, rh), _ = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
            length = float(max(rw, rh))
        findings.append({
            "n": n,
            "bbox": [int(v) for v in f["bbox"]],
            "confidence": round(float(f["confidence"]), 3),
            "area_px": int(f["mask"].sum()),
            "length_px": round(length, 1),
            "mask": mask_name,
            "status": PENDING,
            "comment": "",
        })

    def change(m):
        m["analysis"] = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "model": det.name,
            "is_stub": detector.is_stub(),
            "conf_threshold": conf_thr,
            "ms": round(ms, 1),
            "findings": findings,
        }
    meta = captures.update(cap_id, change)
    render_annotated(cap_id)
    timing_log.log("аналіз кадру", ms, cap_id,
                   f"{'заглушка' if detector.is_stub() else 'модель'}; знахідок: {len(findings)}")
    return meta


def render_annotated(cap_id):
    """Малює маски, рамки і номери знахідок. Колір залежить від статусу."""
    meta = captures.load(cap_id)
    img = cv2.imread(str(config.RAW_DIR / meta["file"]))
    findings = (meta.get("analysis") or {}).get("findings", [])
    overlay = img.copy()
    thick = max(2, img.shape[1] // 500)
    for f in findings:
        color = STATUS_COLORS[f["status"]]
        mask = cv2.imread(str(config.MASKS_DIR / f["mask"]), cv2.IMREAD_GRAYSCALE)
        if mask is not None:
            overlay[mask > 0] = color
    out = cv2.addWeighted(overlay, 0.55, img, 0.45, 0)
    for f in findings:
        color = STATUS_COLORS[f["status"]]
        x, y, w, h = f["bbox"]
        cv2.rectangle(out, (x, y), (x + w, y + h), color, thick)
        label = f"#{f['n']} {f['confidence']:.2f}"
        scale = max(0.6, img.shape[1] / 1600)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        ty = max(y - 6, th + 6)
        cv2.rectangle(out, (x, ty - th - 6), (x + tw + 6, ty + 4), color, -1)
        cv2.putText(out, label, (x + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick)
    path = config.ANNOTATED_DIR / f"{cap_id}.jpg"
    cv2.imwrite(str(path), out, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path


def crop_finding(cap_id, finding, pad=40):
    """Вирізає фрагмент знімка навколо знахідки (для картки перевірки). Повертає RGB."""
    meta = captures.load(cap_id)
    img = cv2.imread(str(config.ANNOTATED_DIR / f"{cap_id}.jpg"))
    if img is None:
        img = cv2.imread(str(config.RAW_DIR / meta["file"]))
    x, y, w, h = finding["bbox"]
    H, W = img.shape[:2]
    x1, y1 = max(x - pad, 0), max(y - pad, 0)
    x2, y2 = min(x + w + pad, W), min(y + h + pad, H)
    return cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)


# ---------- Перевірка людиною ----------
def set_review(cap_id, n, status=None, comment=None):
    """Змінює статус і/або коментар знахідки номер n."""
    def change(meta):
        for f in meta["analysis"]["findings"]:
            if f["n"] == n:
                if status is not None:
                    f["status"] = status
                    f["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
                if comment is not None:
                    f["comment"] = comment
    captures.update(cap_id, change)
    if status is not None:
        render_annotated(cap_id)   # перемальовуємо кольори


def counts(meta):
    """Скільки знахідок у кожному статусі."""
    res = {PENDING: 0, CONFIRMED: 0, REJECTED: 0}
    for f in (meta.get("analysis") or {}).get("findings", []):
        res[f["status"]] += 1
    return res
