"""
Пошук тріщин на знімку.

Два режими:
1) Справжня AI-модель — файл models/crack_seg.onnx (YOLO-seg, навчена в Ultralytics
   і експортована командою:  yolo export model=best.pt format=onnx).
   Запускаємо її через onnxruntime — це швидко і працює офлайн, без PyTorch.
2) ЗАГЛУШКА — якщо моделі ще немає. Це НЕ штучний інтелект, а простий алгоритм:
   шукає на фото тонкі темні видовжені лінії. Потрібна лише для того,
   щоб уся інша частина програми (перевірка людиною, звіт, 3D) вже працювала.

Обидва режими повертають однаковий результат — список знахідок:
    {"bbox": [x, y, w, h], "confidence": 0..1, "mask": масив 0/1 розміром з фото}
"""
import math

import cv2
import numpy as np

from core import config, sector


# =====================================================================
#                         1) СПРАВЖНЯ МОДЕЛЬ (ONNX)
# =====================================================================
def _letterbox(img, size):
    """Зменшує фото до size×size, зберігаючи пропорції; порожнє місце — сірим."""
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    pad_w, pad_h = (size - nw) / 2, (size - nh) / 2
    top, bottom = int(round(pad_h - 0.1)), int(round(pad_h + 0.1))
    left, right = int(round(pad_w - 0.1)), int(round(pad_w + 0.1))
    out = cv2.copyMakeBorder(resized, top, bottom, left, right,
                             cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return out, r, left, top


def _nms(boxes_xyxy, scores, iou_thr=0.45):
    """Прибирає дублікати: з рамок, що сильно перекриваються, лишає найвпевненішу."""
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(boxes_xyxy[i, 0], boxes_xyxy[order[1:], 0])
        yy1 = np.maximum(boxes_xyxy[i, 1], boxes_xyxy[order[1:], 1])
        xx2 = np.minimum(boxes_xyxy[i, 2], boxes_xyxy[order[1:], 2])
        yy2 = np.minimum(boxes_xyxy[i, 3], boxes_xyxy[order[1:], 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area = lambda b: (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])  # noqa: E731
        iou = inter / (area(boxes_xyxy[i]) + area(boxes_xyxy[order[1:]]) - inter + 1e-9)
        order = order[1:][iou < iou_thr]
    return keep


class OnnxCrackModel:
    """YOLO-seg модель у форматі ONNX (Ultralytics YOLOv8 / YOLO11 / YOLO26)."""

    def __init__(self, path):
        import onnxruntime as ort
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.size = inp.shape[2] if isinstance(inp.shape[2], int) else 640
        meta = self.session.get_modelmeta().custom_metadata_map or {}
        # Ultralytics записує в модель, чи вона «end2end» (YOLO26: без окремого NMS)
        self.end2end = str(meta.get("end2end", "")).lower() == "true"
        self.names = meta.get("names", "")
        self.name = f"{config.CRACK_MODEL_PATH.name} (YOLO-seg, ONNX)"

    def predict(self, img_bgr, conf_thr=0.25):
        h0, w0 = img_bgr.shape[:2]
        img, r, pad_x, pad_y = _letterbox(img_bgr, self.size)
        blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        outputs = self.session.run(None, {self.input_name: blob})
        pred, protos = outputs[0][0], outputs[1][0]   # protos: (nm, mh, mw)
        nm, mh, mw = protos.shape

        # --- розбираємо рамки ---
        if pred.shape[0] < pred.shape[1] and not self.end2end:
            pred = pred.T   # формат YOLOv8/11: (4+класи+nm, N) -> (N, 4+класи+nm)
        if self.end2end or pred.shape[1] == 6 + nm and pred.shape[0] <= 300:
            # формат YOLO26 / end2end: x1, y1, x2, y2, впевненість, клас, коефіцієнти маски
            boxes = pred[:, 0:4]
            scores = pred[:, 4]
            coeffs = pred[:, 6:6 + nm]
            ok = scores >= conf_thr
            boxes, scores, coeffs = boxes[ok], scores[ok], coeffs[ok]
        else:
            # формат YOLOv8/11: cx, cy, w, h, впевненості класів..., коефіцієнти маски
            n_cls = pred.shape[1] - 4 - nm
            cls_scores = pred[:, 4:4 + n_cls]
            scores = cls_scores.max(axis=1)
            ok = scores >= conf_thr
            p, scores = pred[ok], scores[ok]
            cx, cy, bw, bh = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
            boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
            coeffs = p[:, 4 + n_cls:]
            if len(scores):
                keep = _nms(boxes, scores)
                boxes, scores, coeffs = boxes[keep], scores[keep], coeffs[keep]

        findings = []
        for box, score, coef in zip(boxes, scores, coeffs):
            # --- маска: коефіцієнти × «прототипи» моделі ---
            m = 1 / (1 + np.exp(-(coef @ protos.reshape(nm, -1)))).reshape(mh, mw)
            m = cv2.resize(m, (self.size, self.size), interpolation=cv2.INTER_LINEAR)
            x1, y1, x2, y2 = box
            crop = np.zeros_like(m)
            xi1, yi1 = max(int(x1), 0), max(int(y1), 0)
            xi2, yi2 = min(int(math.ceil(x2)), self.size), min(int(math.ceil(y2)), self.size)
            crop[yi1:yi2, xi1:xi2] = m[yi1:yi2, xi1:xi2]
            # прибираємо сірі поля і повертаємо до розміру оригінального фото
            crop = crop[pad_y:self.size - pad_y, pad_x:self.size - pad_x]
            mask = (cv2.resize(crop, (w0, h0)) > 0.5).astype(np.uint8)
            if mask.sum() == 0:
                continue
            # рамка в координатах оригінального фото
            bx1 = (x1 - pad_x) / r
            by1 = (y1 - pad_y) / r
            bx2 = (x2 - pad_x) / r
            by2 = (y2 - pad_y) / r
            findings.append({
                "bbox": [int(max(bx1, 0)), int(max(by1, 0)),
                         int(min(bx2, w0) - max(bx1, 0)), int(min(by2, h0) - max(by1, 0))],
                "confidence": float(score),
                "mask": mask,
            })
        return findings


# =====================================================================
#                         2) ЗАГЛУШКА (не AI)
# =====================================================================
class StubCrackDetector:
    """Шукає тонкі темні видовжені лінії. НЕ є штучним інтелектом."""

    name = "ЗАГЛУШКА (простий алгоритм пошуку темних ліній, не AI)"

    def predict(self, img_bgr, conf_thr=0.25):
        h0, w0 = img_bgr.shape[:2]
        scale = 1024 / w0
        img = cv2.resize(img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        # «Чорний капелюх» підсвічує тонкі темні деталі на світлішому фоні
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
        blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
        thr = max(30.0, float(blackhat.mean() + 4 * blackhat.std()))
        bw = (blackhat > thr).astype(np.uint8)

        # ArUco-мітки теж чорні — прибираємо їх разом з білою рамкою і краєм паперу
        # (зона у 1.8 раза більша за саму мітку), щоб не плутати з тріщинами
        corners, _ids = sector.detect(img)
        for c in corners:
            pts = c.reshape(4, 2)
            center = pts.mean(axis=0)
            poly = (center + (pts - center) * 1.8).astype(np.int32)
            cv2.fillPoly(bw, [poly], 0)

        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)

        findings = []
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 40:
                continue
            ys, xs = np.where(labels == i)
            (_, _), (rw, rh), _ = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
            length, width = max(rw, rh), max(min(rw, rh), 1.0)
            fill = area / max(rw * rh, 1.0)
            # тріщина — довга і тонка (або звивиста, тоді заповнення рамки мале)
            if length < 40 or (length / width < 4 and fill > 0.35):
                continue
            # «умовна впевненість» заглушки — що довша лінія, то більше
            score = float(np.clip(0.3 + 0.12 * math.log(length / 40 + 1), 0.3, 0.75))
            if score < conf_thr:
                continue
            small = (labels == i).astype(np.uint8)
            small = cv2.dilate(small, np.ones((3, 3), np.uint8))
            mask = (cv2.resize(small, (w0, h0), interpolation=cv2.INTER_NEAREST) > 0).astype(np.uint8)
            x, y, w, h = cv2.boundingRect(mask)
            findings.append({"bbox": [x, y, w, h], "confidence": score, "mask": mask})

        findings.sort(key=lambda f: -f["confidence"])
        return findings[:20]


# =====================================================================
_detector = None
_detector_mtime = None


def get_detector():
    """Повертає справжню модель, якщо є файл models/crack_seg.onnx, інакше заглушку."""
    global _detector, _detector_mtime
    path = config.CRACK_MODEL_PATH
    mtime = path.stat().st_mtime if path.exists() else None
    if _detector is None or mtime != _detector_mtime:
        if mtime is not None:
            try:
                _detector = OnnxCrackModel(path)
            except Exception as e:   # пошкоджений файл моделі
                print("Не вдалося завантажити модель:", e)
                _detector = StubCrackDetector()
                _detector.name += f" — модель не відкрилась: {e}"
        else:
            _detector = StubCrackDetector()
        _detector_mtime = mtime
    return _detector


def is_stub():
    return isinstance(get_detector(), StubCrackDetector)
