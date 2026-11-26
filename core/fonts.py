"""
Шрифт DejaVuSans з українськими літерами.
Він уже є всередині бібліотеки matplotlib, тому нічого не треба завантажувати з інтернету.
"""
from pathlib import Path

import matplotlib


def dejavu_path(bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name


def register_reportlab_fonts():
    """Реєструє шрифт у ReportLab під назвами 'DejaVu' і 'DejaVu-Bold'."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(dejavu_path())))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(dejavu_path(bold=True))))
        # «Сімейство»: щоб <b>текст</b> у звіті ставав жирним
        pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                                      italic="DejaVu", boldItalic="DejaVu-Bold")
