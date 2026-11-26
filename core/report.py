"""
PDF-звіт українською (бібліотека ReportLab, шрифт DejaVuSans).

Що є у звіті:
  1. Назва обстеження, дата, примітки
  2. ЗАСТЕРЕЖЕННЯ: звіт не є висновком про технічний стан будівлі
  3. Підсумок (скільки знімків, знахідок, рішень людини)
  4. Знімок 3D-моделі (або схема секторів, якщо 3D-знімка ще немає)
  5. Таблиця за секторами A1–C3
  6. Картки ПІДТВЕРДЖЕНИХ знахідок
  7. Знахідки, які ще не перевірені
  8. ВІДХИЛЕНІ знахідки — окремо
  9. Список знімків
"""
import io
import time
from datetime import datetime
from xml.sax.saxutils import escape

import cv2
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from core import analysis, captures, config, db, stats, timing_log
from core.fonts import register_reportlab_fonts

CONF_NOTE = "впевненість моделі, не оцінка небезпеки"
DISCLAIMER = (
    "<b>Важливо.</b> Цей звіт створено навчальною програмою ReBuildDrone під час обстеження "
    "<b>макета</b>. Він <b>не є висновком про технічний стан будівлі</b> і не замінює "
    "обстеження кваліфікованим фахівцем. Знахідки — це місця, які AI-модель (або програмна "
    "заглушка) вважає схожими на тріщини; число «впевненість» — це " + CONF_NOTE + ". "
    "Кожну знахідку переглянула або має переглянути людина."
)


# ---------- Стилі тексту ----------
def _styles():
    register_reportlab_fonts()
    base = dict(fontName="DejaVu", fontSize=10, leading=13)
    return {
        "title": ParagraphStyle("title", fontName="DejaVu-Bold", fontSize=20, leading=24,
                                spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=14, leading=18,
                             spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("body", **base),
        "small": ParagraphStyle("small", fontName="DejaVu", fontSize=8, leading=10,
                                textColor=colors.HexColor("#555555")),
        "cell": ParagraphStyle("cell", fontName="DejaVu", fontSize=8.5, leading=11),
        "cellc": ParagraphStyle("cellc", fontName="DejaVu", fontSize=8.5, leading=11,
                                alignment=TA_CENTER),
        "warn": ParagraphStyle("warn", fontName="DejaVu", fontSize=9.5, leading=13,
                               textColor=colors.HexColor("#7a1f1f")),
    }


def _table_style(header=True):
    cmds = [
        ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        cmds += [("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
                 ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5"))]
    return TableStyle(cmds)


def _img_flowable(rgb, max_w, max_h):
    """Картинка (numpy RGB) -> об'єкт для PDF, вписаний у max_w × max_h."""
    # JPEG — щоб PDF був невеликим
    ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                           [cv2.IMWRITE_JPEG_QUALITY, 85])
    h, w = rgb.shape[:2]
    scale = min(max_w / w, max_h / h)
    return Image(io.BytesIO(jpg.tobytes()), width=w * scale, height=h * scale)


def _fmt_time(iso):
    return iso.replace("T", " ") if iso else "—"


def _drone_text(meta):
    d = meta["drone"]
    if not d:
        return "кути дрона: немає"
    return f"крен {d['roll']:+.1f}°, нахил {d['pitch']:+.1f}°, рискання {d['yaw']:.0f}°"


# ---------- Головна функція ----------
def build_report(survey_id=None):
    """Створює PDF. Повертає шлях до файлу."""
    t0 = time.perf_counter()
    if survey_id is None:
        survey_id = db.get_active_survey_id()
    survey = db.get_survey(survey_id)
    items = captures.list_captures(survey_id)
    by_id = {m["id"]: m for m in items}
    sectors = stats.by_sector(survey_id)
    st = _styles()

    config.REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.REPORTS_DIR / f"ReBuildDrone_zvit_{survey_id}_{stamp}.pdf"

    story = []
    # 1. Заголовок
    story.append(Paragraph("Звіт обстеження макета", st["title"]))
    story.append(Paragraph(f"<b>Обстеження:</b> {escape(survey['name'])}", st["body"]))
    story.append(Paragraph(f"<b>Створено:</b> {_fmt_time(survey['created_at'])} · "
                           f"<b>Звіт сформовано:</b> {datetime.now():%Y-%m-%d %H:%M}", st["body"]))
    if survey.get("notes"):
        story.append(Paragraph(f"<b>Примітки:</b> {escape(survey['notes'])}", st["body"]))
    story.append(Spacer(1, 8))

    # 2. Застереження (у рамці)
    box = Table([[Paragraph(DISCLAIMER, st["warn"])]], colWidths=[17 * cm])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#c0392b")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdf0ef")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(box)

    # 3. Підсумок
    # Знімки впорядковуємо за сектором (A1…C3, без сектора — в кінці), потім за часом
    analyzed = sorted([m for m in items if "analysis" in m],
                      key=lambda m: (m["sector"]["name"] or "Я", m["time"]))
    all_f = [f for m in analyzed for f in m["analysis"]["findings"]]
    cnt = {s: sum(1 for f in all_f if f["status"] == s)
           for s in (stats.CONFIRMED, stats.REJECTED, stats.PENDING)}
    models = sorted({m["analysis"]["model"] for m in analyzed})
    any_stub = any(m["analysis"]["is_stub"] for m in analyzed)
    story.append(Paragraph("Підсумок", st["h2"]))
    summary = [
        ["Знімків у обстеженні", str(len(items))],
        ["з них позначено «перезняти» (погана якість)",
         str(sum(1 for m in items if not m["quality"]["ok"]))],
        ["Проаналізовано знімків", str(len(analyzed))],
        ["Усього знахідок", str(len(all_f))],
        ["Підтверджено людиною", str(cnt[stats.CONFIRMED])],
        ["Відхилено людиною (хибні спрацювання)", str(cnt[stats.REJECTED])],
        ["Ще не перевірено", str(cnt[stats.PENDING])],
        ["Модель", Paragraph(escape("; ".join(models)) or "—", st["cell"])],
    ]
    t = Table(summary, colWidths=[9 * cm, 8 * cm])
    t.setStyle(_table_style(header=False))
    story.append(t)
    if any_stub:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "⚠ Частину або всі знімки проаналізовано <b>заглушкою</b> (простий алгоритм пошуку "
            "темних ліній, не штучний інтелект). Її «впевненість» умовна.", st["warn"]))

    # 4. Знімок 3D-моделі або схема секторів
    story.append(Paragraph("Модель макета", st["h2"]))
    if config.SNAPSHOT_3D.exists():
        img = cv2.cvtColor(cv2.imread(str(config.SNAPSHOT_3D)), cv2.COLOR_BGR2RGB)
        story.append(_img_flowable(_crop_to_content(img), 15 * cm, 10 * cm))
        story.append(Paragraph("Знімок 3D-двійника макета. Колір сектора — за кількістю "
                               "підтверджених тріщин.", st["small"]))
    else:
        story.append(_sector_scheme(sectors, st))
        story.append(Paragraph("Схема секторів (знімка 3D-моделі ще немає).", st["small"]))
    story.append(Paragraph("Колір: зелений — 0 підтверджених тріщин, жовтий — 1–2, "
                           "червоний — 3 і більше.", st["small"]))

    # 5. Таблиця за секторами (заголовок і таблиця — разом, без розриву)
    rows = [["Сектор", "Знімків", "Підтверджено", "Відхилено", "Не перевірено", "Рівень"]]
    styles_extra = []
    keys = config.SECTOR_NAMES + ([None] if sectors[None]["images"] else [])
    for i, name in enumerate(keys, start=1):
        s = sectors[name]
        rows.append([name or "без сектора", s["images"], s["confirmed"], s["rejected"],
                     s["pending"], stats.sector_level(s["confirmed"]) if name else "—"])
        if name:
            styles_extra.append(("BACKGROUND", (5, i), (5, i), colors.HexColor(s["color"])))
    t = Table(rows, colWidths=[2.3 * cm, 2 * cm, 2.8 * cm, 2.4 * cm, 3 * cm, 4.5 * cm])
    ts = _table_style()
    for cmd in styles_extra:
        ts.add(*cmd)
    ts.add("ALIGN", (1, 1), (4, -1), "CENTER")
    t.setStyle(ts)
    story.append(KeepTogether([Paragraph("Результати за секторами", st["h2"]), t]))

    # 6. Підтверджені знахідки — картки
    story.append(Paragraph("Підтверджені знахідки", st["h2"]))
    confirmed = [(m, f) for m in analyzed for f in m["analysis"]["findings"]
                 if f["status"] == stats.CONFIRMED]
    if not confirmed:
        story.append(Paragraph("Підтверджених знахідок немає.", st["body"]))
    for m, f in confirmed:
        story.append(_finding_card(m, f, st))
        story.append(Spacer(1, 6))

    # 7. Не перевірені
    pending = [(m, f) for m in analyzed for f in m["analysis"]["findings"]
               if f["status"] == stats.PENDING]
    if pending:
        story.append(Paragraph("Знахідки, які ще не перевірені людиною", st["h2"]))
        story.append(Paragraph("Ці місця ще треба переглянути: їх не враховано в кольорах "
                               "секторів.", st["small"]))
        story.append(_findings_table(pending, st))

    # 8. Відхилені — окремо
    story.append(Paragraph("Відхилені знахідки (хибні спрацювання)", st["h2"]))
    rejected = [(m, f) for m in analyzed for f in m["analysis"]["findings"]
                if f["status"] == stats.REJECTED]
    if rejected:
        story.append(Paragraph("Людина вирішила, що це не тріщини. Їх не враховано в "
                               "кольорах секторів.", st["small"]))
        story.append(_findings_table(rejected, st))
    else:
        story.append(Paragraph("Відхилених знахідок немає.", st["body"]))

    # 9. Список знімків
    story.append(PageBreak())
    story.append(Paragraph("Список знімків", st["h2"]))
    rows = [["Час", "Джерело", "Сектор", "Якість", "Кути дрона", "Знахідок"]]
    for m in items:
        q = "добра" if m["quality"]["ok"] else "перезняти: " + ", ".join(m["quality"]["reasons"])
        n = len(m["analysis"]["findings"]) if "analysis" in m else "не аналізовано"
        sec = (m["sector"]["name"] or "—") + (f" ({m['sector']['method']})"
                                               if m["sector"]["method"] else "")
        rows.append([_fmt_time(m["time"]), m["source"], sec, Paragraph(q, st["cell"]),
                     Paragraph(_drone_text(m), st["cell"]), n])
    t = Table(rows, colWidths=[3.2 * cm, 2.1 * cm, 2.3 * cm, 3 * cm, 4.6 * cm, 1.8 * cm],
              repeatRows=1)
    t.setStyle(_table_style())
    story.append(t)

    # Нижній колонтитул на кожній сторінці
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVu", 7.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(1.8 * cm, 1.1 * cm,
                          f"ReBuildDrone · {survey['name'][:60]} · "
                          "не є висновком про технічний стан будівлі")
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.1 * cm, f"сторінка {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.8 * cm,
                            title=f"Звіт ReBuildDrone — {survey['name']}", author="ReBuildDrone")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)

    ms = (time.perf_counter() - t0) * 1000
    timing_log.log("PDF-звіт", ms, path.name,
                   f"знімків: {len(items)}; знахідок: {len(all_f)}")
    return path, ms


def _crop_to_content(rgb, pad=30):
    """Обрізає однотонне тло навколо моделі на 3D-знімку."""
    bg = rgb[0, 0].astype(int)
    diff = np.abs(rgb.astype(int) - bg).sum(axis=2) > 30
    ys, xs = np.nonzero(diff)
    if len(xs) == 0:
        return rgb
    h, w = rgb.shape[:2]
    return rgb[max(ys.min() - pad, 0):min(ys.max() + pad, h),
               max(xs.min() - pad, 0):min(xs.max() + pad, w)]


def _sector_scheme(sectors, st):
    """Схема 3×3: A — верхній ряд, C — нижній. Колір — за підтвердженими тріщинами."""
    cells, cmds = [], []
    for r, row_letter in enumerate("ABC"):
        row = []
        for c in range(3):
            name = f"{row_letter}{c + 1}"
            s = sectors[name]
            row.append(Paragraph(f"<b>{name}</b><br/>підтв.: {s['confirmed']}<br/>"
                                 f"знімків: {s['images']}", st["cellc"]))
            cmds.append(("BACKGROUND", (c, r), (c, r), colors.HexColor(s["color"])))
        cells.append(row)
    t = Table(cells, colWidths=[3.2 * cm] * 3, rowHeights=[2 * cm] * 3)
    ts = TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.white),
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE")] + cmds)
    t.setStyle(ts)
    return t


def _finding_card(m, f, st):
    crop = analysis.crop_finding(m["id"], f)
    img = _img_flowable(crop, 5.5 * cm, 6 * cm)
    comment = escape(f["comment"]) if f["comment"] else "—"
    text = (
        f"<b>Сектор {m['sector']['name'] or '—'} · знахідка №{f['n']}</b><br/>"
        f"Знімок: {_fmt_time(m['time'])} ({m['source']})<br/>"
        f"Впевненість: <b>{f['confidence']:.2f}</b> — {CONF_NOTE}<br/>"
        f"Довжина ≈ {f['length_px']:.0f} px · площа маски {f['area_px']} px<br/>"
        f"Кути дрона: {_drone_text(m).replace('кути дрона: ', '')}<br/>"
        f"Перевірено: {_fmt_time(f.get('reviewed_at'))}<br/>"
        f"<b>Коментар:</b> {comment}"
    )
    t = Table([[img, Paragraph(text, st["cell"])]], colWidths=[6 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d63b3b")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    return KeepTogether(t)


def _findings_table(pairs, st):
    rows = [["Фрагмент", "Сектор", "Знімок", "№", "Впевненість*", "Коментар"]]
    for m, f in pairs:
        crop = analysis.crop_finding(m["id"], f, pad=20)
        rows.append([_img_flowable(crop, 2.2 * cm, 2.2 * cm), m["sector"]["name"] or "—",
                     _fmt_time(m["time"]), f["n"], f"{f['confidence']:.2f}",
                     Paragraph(escape(f["comment"]) or "—", st["cell"])])
    t = Table(rows, colWidths=[2.6 * cm, 1.8 * cm, 3.4 * cm, 1 * cm, 2.4 * cm, 5.8 * cm],
              repeatRows=1)
    t.setStyle(_table_style())
    return KeepTogether([t, Paragraph("* " + CONF_NOTE, st["small"])])
