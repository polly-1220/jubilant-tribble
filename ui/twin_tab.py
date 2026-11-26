"""
Розділ «3D-двійник»: модель макета з кольоровими секторами.

- Якщо є models/maket.glb — показуємо її. Сектори треба один раз розмітити кліком
  (режим «Розмітка»), розмітка зберігається в sectors.json.
- Якщо моделі немає — тестова триповерхова будівля, де сектори A1–C3 вже є на фасаді.
- Колір сектора — за кількістю ПІДТВЕРДЖЕНИХ тріщин: зелений 0, жовтий 1–2, червоний 3+.
- Клік по сектору — список знахідок цього сектора.
- «Знімок для звіту» — картинка 3D-моделі потрапляє в PDF.
"""
import base64
import json
import shutil
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from core import analysis, captures, config, db, stats
from ui import style

# Наш власний компонент: HTML + three.js з папки ui/twin_component (без інтернету)
_twin = components.declare_component(
    "rebuild_twin", path=str(Path(__file__).parent / "twin_component"))



# ---------- sectors.json ----------
def load_sectors(model_name):
    """Розмітка секторів для цієї моделі (словник сектор -> {point, normal, radius})."""
    if not config.SECTORS_JSON.exists():
        return {}
    try:
        data = json.loads(config.SECTORS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if data.get("model") != model_name:
        return {}   # розмітка зроблена для іншої моделі
    return data.get("sectors", {})


def save_sectors(model_name, sectors):
    data = {"model": model_name, "sectors": sectors}
    config.SECTORS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def model_url():
    """
    Копіюємо models/maket.glb у static/, звідки Streamlit віддає файли браузеру
    (адреса /app/static/maket.glb). Повертаємо адресу або None, якщо моделі немає.
    """
    src = config.MAKET_MODEL_PATH
    if not src.exists():
        return None
    dst = config.STATIC_DIR / "maket.glb"
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        shutil.copy2(src, dst)
    return f"/app/static/maket.glb?v={int(src.stat().st_mtime)}"


# ---------- Розділ ----------
def render():
    st.subheader("3D-двійник макета")
    style.meme_line("twin")
    survey_id = db.get_active_survey_id()
    url = model_url()
    is_test = url is None
    model_name = "test_house" if is_test else "maket.glb"
    sectors = load_sectors(model_name)

    if is_test:
        st.info("Файлу `models/maket.glb` немає — показано **тестову будівлю** (3 поверхи): "
                "сектори A1–C3 розташовані на фасаді (A — верхній ряд).")

    # ---------- Режим ----------
    mode = "view"
    mark_sector = None
    if not is_test:
        missing = [s for s in config.SECTOR_NAMES if s not in sectors]
        if missing:
            st.warning(f"Не розмічено сектори: {', '.join(missing)}. "
                       "Увімкни «Розмітка секторів» і клікни на моделі.")
        mode_label = st.segmented_control(
            "Режим", ["Перегляд", "Розмітка секторів"], key="twin_mode", default="Перегляд",
            required=True)
        if mode_label == "Розмітка секторів":
            mode = "mark"
            c1, c2, c3 = st.columns([1, 2, 1])
            default = missing[0] if missing else config.SECTOR_NAMES[0]
            if "twin_mark_sector" not in st.session_state:
                st.session_state["twin_mark_sector"] = default
            # Наступний сектор після кліку задаємо ДО того, як намалюємо список
            # (Streamlit не дозволяє змінювати значення вже намальованого списку)
            if "twin_next_sector" in st.session_state:
                st.session_state["twin_mark_sector"] = st.session_state.pop("twin_next_sector")
            mark_sector = c1.selectbox("Сектор", config.SECTOR_NAMES, key="twin_mark_sector")
            radius = c2.slider("Розмір позначки", 0.03, 0.25,
                               float(sectors.get(mark_sector, {}).get("radius", 0.08)), 0.01,
                               help="Частка від розміру моделі")
            if mark_sector in sectors and radius != sectors[mark_sector].get("radius"):
                sectors[mark_sector]["radius"] = radius
                save_sectors(model_name, sectors)
            st.session_state["twin_radius"] = radius
            if c3.button("Прибрати", icon=":material/delete:", disabled=mark_sector not in sectors):
                sectors.pop(mark_sector, None)
                save_sectors(model_name, sectors)
                st.rerun()

    # ---------- Дані для 3D ----------
    by_sector = stats.by_sector(survey_id)
    stats_js = {name: {k: by_sector[name][k] for k in
                       ("images", "confirmed", "rejected", "pending", "color")}
                for name in config.SECTOR_NAMES}

    event = _twin(
        mode=mode, mark_sector=mark_sector, is_test_model=is_test, model_url=url,
        sectors=sectors, stats=stats_js, selected=st.session_state.get("twin_selected"),
        key="twin", default=None,
    )

    # ---------- Подія з 3D (клік або знімок) ----------
    if event and event.get("id") != st.session_state.get("twin_last_event"):
        st.session_state["twin_last_event"] = event.get("id")
        if event["type"] == "select":
            st.session_state["twin_selected"] = event["sector"]
            st.rerun()
        elif event["type"] == "mark" and mark_sector:
            sectors[event["sector"]] = {
                "point": event["point"], "normal": event["normal"],
                "mesh": event.get("mesh"),
                "radius": st.session_state.get("twin_radius", 0.08),
            }
            save_sectors(model_name, sectors)
            # одразу пропонуємо наступний нерозмічений сектор
            left = [s for s in config.SECTOR_NAMES if s not in sectors]
            if left:
                st.session_state["twin_next_sector"] = left[0]
            st.rerun()
        elif event["type"] == "snapshot":
            png = base64.b64decode(event["png"].split(",", 1)[1])
            config.SNAPSHOT_3D.write_bytes(png)
            st.success("Знімок 3D-моделі збережено — він буде у PDF-звіті.")

    if config.SNAPSHOT_3D.exists():
        st.caption("У звіті буде останній збережений знімок 3D-моделі "
                   "(зроби новий, якщо змінилися кольори).")

    # ---------- Знахідки вибраного сектора ----------
    sel = st.session_state.get("twin_selected")
    if sel:
        sector_findings(sel, by_sector[sel])
    else:
        st.caption("Клікни на сектор у 3D, щоб побачити його знахідки.")


def sector_findings(name, s):
    st.markdown(f"### Сектор {name}")
    style.html(style.pill(f"знімків: {s['images']}", "#7CD3FF")
               + style.status_pill(stats.CONFIRMED, s["confirmed"])
               + style.status_pill(stats.PENDING, s["pending"])
               + style.status_pill(stats.REJECTED, s["rejected"])
               + style.pill(f"рівень: {stats.sector_level(s['confirmed'])}", s["color"]))
    if not s["findings"]:
        st.caption("Знахідок у цьому секторі немає.")
        return
    order = {stats.CONFIRMED: 0, stats.PENDING: 1, stats.REJECTED: 2}
    items = sorted(s["findings"], key=lambda f: (order[f["status"]], f["image_time"], f["n"]))
    cols = st.columns(3)
    for i, f in enumerate(items):
        with cols[i % 3], st.container(border=True):
            st.image(analysis.crop_finding(f["image_id"], f), width="stretch")
            style.html(f"<b>№{f['n']}</b> &nbsp;" + style.status_pill(f["status"]))
            st.caption(f"Знімок {f['image_time'].replace('T', ' ')} · впевненість "
                       f"{f['confidence']:.2f} (впевненість моделі, не оцінка небезпеки)")
            if f["comment"]:
                st.caption(f"Коментар: {f['comment']}")
    st.caption("Змінити рішення можна в розділі «AI-аналіз».")
