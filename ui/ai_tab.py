"""
Вкладка «AI-аналіз»: пошук тріщин і перевірка кожної знахідки людиною.
"""
import streamlit as st

from core import analysis, captures, config, detector
from ui import style

CONF_NOTE = "впевненість моделі, не оцінка небезпеки"


def legend():
    return "".join(style.status_pill(s) for s in
                   (analysis.PENDING, analysis.CONFIRMED, analysis.REJECTED))


def render():
    st.subheader("AI-аналіз і перевірка людиною")

    # ---------- Яка модель працює ----------
    det = detector.get_detector()
    if detector.is_stub():
        style.show_sticker(style.meme("stub"), "#FFC83D", -2)
        st.warning(f"Файл AI-моделі `models/{config.CRACK_MODEL_PATH.name}` не знайдено. "
                   f"Працює **{det.name}**. Числа «впевненості» заглушки умовні.")
    else:
        st.success(f"Модель: {det.name}")

    items = captures.list_captures()
    if not items:
        style.empty("Ще немає знімків. Зроби їх у розділі «Зйомка».<br>"
                    + style.meme("empty_gallery"))
        return

    # ---------- Запуск аналізу ----------
    c1, c2 = st.columns(2)
    conf = c1.slider("Мінімальна впевненість моделі", 0.05, 0.95, 0.25, 0.05, key="conf_thr",
                     help="Знахідки з меншою впевненістю не показуються. " + CONF_NOTE + ".")
    skip_bad = c2.toggle("Пропускати кадри «перезняти»", value=True)

    new = [m for m in items if "analysis" not in m and (m["quality"]["ok"] or not skip_bad)]
    if st.button(f"Аналізувати нові знімки ({len(new)})", icon=":material/auto_awesome:",
                 type="primary", disabled=not new):
        bar = st.progress(0.0, text="AI думає…")
        for i, m in enumerate(new, start=1):
            analysis.analyze(m["id"], conf_thr=conf)
            bar.progress(i / len(new), text=f"Аналіз {i} з {len(new)}")
        st.rerun()

    # ---------- Загальна статистика ----------
    analyzed = [m for m in items if "analysis" in m]
    total = {analysis.PENDING: 0, analysis.CONFIRMED: 0, analysis.REJECTED: 0}
    for m in analyzed:
        for k, v in analysis.counts(m).items():
            total[k] += v
    s = st.columns(4)
    s[0].metric("Проаналізовано", f"{len(analyzed)} / {len(items)}")
    s[1].metric("Чекають перевірки", total[analysis.PENDING])
    s[2].metric("Підтверджено", total[analysis.CONFIRMED])
    s[3].metric("Відхилено", total[analysis.REJECTED])

    if not analyzed:
        return

    # ---------- Вибір знімка для перевірки ----------
    st.divider()

    # Підпис у списку не повинен змінюватися після «Підтвердити»/«Відхилити»,
    # інакше Streamlit вважає список новим і перескакує на перший знімок.
    def label(m):
        sec = m["sector"]["name"] or "сектор ?"
        return f"{m['time'].replace('T', ' ')} · {sec} · знахідок {len(m['analysis']['findings'])}"

    ids = [m["id"] for m in analyzed]
    by_id = {m["id"]: m for m in analyzed}
    cap_id = st.selectbox("Знімок для перевірки", ids, key="review_cap",
                          format_func=lambda i: label(by_id[i]))
    c = analysis.counts(by_id[cap_id])
    style.html("На цьому знімку: " + "".join(style.status_pill(k, v) for k, v in c.items()))
    review_capture(cap_id, conf)


def review_capture(cap_id, conf):
    meta = captures.load(cap_id)
    a = meta["analysis"]
    left, right = st.columns([3, 2])
    with left:
        st.image(str(config.ANNOTATED_DIR / f"{cap_id}.jpg"), width="stretch")
        style.html(legend())
    with right:
        st.write(f"**Сектор:** {meta['sector']['name'] or 'не визначено'}")
        if not meta["quality"]["ok"]:
            st.warning("Кадр позначено «перезняти»: " + ", ".join(meta["quality"]["reasons"]))
        st.write(f"**Модель:** {a['model']}")
        st.write(f"**Час аналізу:** {a['ms']:.0f} мс · поріг впевненості {a['conf_threshold']}")
        if st.button("Проаналізувати знову", icon=":material/refresh:",
                     help="Увага: попередні рішення щодо знахідок цього знімка буде скинуто."):
            analysis.analyze(cap_id, conf_thr=conf)
            st.rerun()

    if not a["findings"]:
        style.empty(f"<b>На цьому знімку тріщин не знайдено.</b><br>{style.meme('no_findings')}")
        return

    st.caption(f"Число біля кожної знахідки — {CONF_NOTE}.")
    for f in a["findings"]:
        finding_card(cap_id, f)


def finding_card(cap_id, f):
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(analysis.crop_finding(cap_id, f), width="stretch")
        with c2:
            style.html(f"<b>Знахідка №{f['n']}</b> &nbsp;" + style.status_pill(f["status"]))
            st.write(f"Впевненість: **{f['confidence']:.2f}**")
            st.caption(CONF_NOTE)
            st.caption(f"Довжина ≈ {f['length_px']:.0f} px · площа маски {f['area_px']} px")

            b1, b2, b3 = st.columns(3)
            if b1.button("Підтвердити", icon=":material/check:", key=f"ok_{cap_id}_{f['n']}",
                         disabled=f["status"] == analysis.CONFIRMED):
                analysis.set_review(cap_id, f["n"], status=analysis.CONFIRMED)
                st.rerun()
            if b2.button("Відхилити", icon=":material/close:", key=f"no_{cap_id}_{f['n']}",
                         disabled=f["status"] == analysis.REJECTED):
                analysis.set_review(cap_id, f["n"], status=analysis.REJECTED)
                st.rerun()
            if b3.button("Скинути", icon=":material/undo:", key=f"reset_{cap_id}_{f['n']}",
                         disabled=f["status"] == analysis.PENDING):
                analysis.set_review(cap_id, f["n"], status=analysis.PENDING)
                st.rerun()

            comment = st.text_input("Коментар", value=f["comment"],
                                    key=f"cm_{cap_id}_{f['n']}",
                                    placeholder="напр.: тріщина в штукатурці біля вікна")
            if comment != f["comment"]:
                analysis.set_review(cap_id, f["n"], comment=comment)
                st.toast("Коментар збережено")
