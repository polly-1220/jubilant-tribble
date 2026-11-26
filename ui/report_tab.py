"""
Розділ «Звіт»: підсумок за секторами, створення PDF, попередні звіти, лог тестування.
"""
import pandas as pd
import streamlit as st

from core import config, db, report, stats, timing_log
from ui import style


def sector_grid(sectors):
    """Схема 3×3 кольоровими плитками (A — верхній ряд)."""
    tiles = []
    for name in config.SECTOR_NAMES:
        s = sectors[name]
        tiles.append(
            f'<div style="background:{s["color"]};border:2px solid {style.INK};'
            f'border-radius:16px;box-shadow:3px 3px 0 {style.INK};padding:10px 12px;'
            f'color:{style.INK}"><div style="font-family:Unbounded,sans-serif;font-weight:800;'
            f'font-size:1.3rem">{name}</div><div style="font-size:.85rem">'
            f'підтв. {s["confirmed"]} · знімків {s["images"]}</div></div>')
    style.html('<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;'
               'max-width:520px;margin:6px 0 14px">' + "".join(tiles) + "</div>")


def render():
    st.subheader("PDF-звіт")
    style.show_sticker("тут без мемів: звіт серйозний", "#7CD3FF", 2)
    survey_id = db.get_active_survey_id()
    survey = db.get_survey(survey_id)
    st.write(f"Обстеження: **{survey['name']}** (змінити — у бічній панелі ліворуч)")

    # ---------- Короткий підсумок за секторами ----------
    sectors = stats.by_sector(survey_id)
    sector_grid(sectors)
    style.html(style.pill("0 підтверджених", stats.GREEN) + style.pill("1–2", stats.YELLOW)
               + style.pill("3 і більше", stats.RED))
    rows = []
    for name in config.SECTOR_NAMES + [None]:
        s = sectors[name]
        if name is None and not s["images"]:
            continue
        rows.append({"Сектор": name or "без сектора", "Знімків": s["images"],
                     "Підтверджено": s["confirmed"], "Відхилено": s["rejected"],
                     "Не перевірено": s["pending"],
                     "Рівень": stats.sector_level(s["confirmed"]) if name else "—"})
    with st.expander("Таблиця за секторами", icon=":material/table:"):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    pending = sum(s["pending"] for s in sectors.values())
    if pending:
        st.warning(f"Ще не перевірено знахідок: {pending}. Їх можна перевірити в розділі "
                   "«AI-аналіз» — у звіті вони будуть в окремому списку.")
    if not config.SNAPSHOT_3D.exists():
        st.caption("Знімка 3D-моделі ще немає — у звіті буде схема секторів 3×3 "
                   "(знімок можна зробити в розділі «3D-двійник»).")

    # ---------- Створення PDF ----------
    if st.button("Сформувати PDF-звіт", icon=":material/picture_as_pdf:", type="primary"):
        with st.spinner("Формую звіт…"):
            path, ms = report.build_report(survey_id)
        st.session_state["last_report"] = str(path)
        st.success(f"Готово за {ms:.0f} мс: {path.name}")

    last = st.session_state.get("last_report")
    if last:
        with open(last, "rb") as f:
            st.download_button("Завантажити останній звіт", f.read(), icon=":material/download:",
                               file_name=last.split("/")[-1], mime="application/pdf")

    # ---------- Попередні звіти ----------
    old = sorted(config.REPORTS_DIR.glob("*.pdf"), reverse=True)
    if old:
        with st.expander(f"Усі звіти ({len(old)}) — папка reports/", icon=":material/folder:"):
            for p in old[:20]:
                c1, c2 = st.columns([3, 1])
                c1.write(p.name)
                with open(p, "rb") as f:
                    c2.download_button("PDF", f.read(), icon=":material/download:", file_name=p.name,
                                       mime="application/pdf", key=f"dl_{p.name}")

    # ---------- Лог для тестування ----------
    with st.expander("Лог тестування (час аналізу кадру і формування звіту)", icon=":material/timer:"):
        log = timing_log.read_rows()
        if not log:
            st.caption("Лог порожній.")
        else:
            df = pd.DataFrame(log)
            df["мс"] = pd.to_numeric(df["мс"])
            summary = df.groupby("подія")["мс"].agg(["count", "mean", "min", "max"]).round(1)
            summary.columns = ["разів", "середнє, мс", "мін, мс", "макс, мс"]
            st.dataframe(summary, width="stretch")
            st.dataframe(df.iloc[::-1], hide_index=True, width="stretch")
            st.caption(f"Файл: {timing_log.LOG_PATH.relative_to(config.ROOT)}")
