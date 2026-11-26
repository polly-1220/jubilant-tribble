"""
ReBuildDrone — головний файл застосунку.
Запуск:  streamlit run app.py
"""
import streamlit as st

from core import config, db
from ui import ai_tab, camera_tab, drone_tab, report_tab, style, twin_tab

# Налаштування сторінки (має бути першою командою Streamlit)
st.set_page_config(page_title="ReBuildDrone", page_icon=str(config.STATIC_DIR / "icon.png"),
                   layout="wide")

# Створюємо папки для даних і базу даних, якщо їх ще немає
config.ensure_folders()
db.init()

# Наші стилі: кольори, картки, стікери
style.inject()

# ---------- Бічна панель: обстеження і стан системи ----------
with st.sidebar:
    st.header("Обстеження")
    surveys = db.list_surveys()
    by_id = {s["id"]: s for s in surveys}
    active = db.get_active_survey_id()
    chosen = st.selectbox(
        "Нові знімки зберігаються в:", list(by_id), index=list(by_id).index(active),
        format_func=lambda i: f"{by_id[i]['name']} ({by_id[i]['created_at'][:10]})",
    )
    if chosen != active:
        db.set_active_survey_id(chosen)
        st.rerun()
    st.caption(f"Знімків у цьому обстеженні: {by_id[chosen]['images']}")
    with st.expander("Нове обстеження", icon=":material/add:"):
        new_name = st.text_input("Назва", placeholder="напр.: Макет школи, сторона А")
        new_notes = st.text_area("Примітки (необов'язково)", height=70)
        if st.button("Створити", disabled=not new_name.strip()):
            db.set_active_survey_id(db.create_survey(new_name, new_notes))
            st.rerun()

    st.divider()
    st.subheader("Стан системи")

    # Перевіряємо, чи встановлені потрібні бібліотеки
    def lib_ok(name):
        try:
            __import__(name)
            return True
        except ImportError:
            return False

    checks = {
        "Streamlit": lib_ok("streamlit"),
        "pyserial · дрон": lib_ok("serial"),
        "OpenCV · камера": lib_ok("cv2"),
        "ONNX Runtime · AI": lib_ok("onnxruntime"),
        "ReportLab · PDF": lib_ok("reportlab"),
    }
    rows = [style.pill(name, "#16B877" if ok else "#FF4D6D") for name, ok in checks.items()]
    rows.append(style.pill("AI-модель: є" if config.CRACK_MODEL_PATH.exists()
                           else "AI-модель: заглушка",
                           "#16B877" if config.CRACK_MODEL_PATH.exists() else "#FFC83D"))
    rows.append(style.pill("3D-модель: є" if config.MAKET_MODEL_PATH.exists()
                           else "3D: тестова будівля",
                           "#16B877" if config.MAKET_MODEL_PATH.exists() else "#FFC83D"))
    style.html("<div>" + "".join(rows) + "</div>")
    style.html('<div class="rb-footer">зроблено з кавою, паяльником і дедлайнами</div>')

# ---------- Банер ----------
style.hero("ReBuild", "Drone",
           "Шукаємо тріщини на макеті будівлі: дрон, камера, AI і людина, яка все перевіряє. "
           "Працює офлайн.",
           "beta, але вже вміє")

# ---------- Розділи: показуємо лише вибраний ----------
# (Звичайні st.tabs малюють усі вкладки одразу, і живі панелі дрона й камери
#  оновлювалися б навіть тоді, коли ти перевіряєш знахідки, — через це губилися б кліки.)
SECTIONS = {
    "drone": ("Дрон", ":material/flight:"),
    "camera": ("Зйомка", ":material/photo_camera:"),
    "ai": ("AI-аналіз", ":material/auto_awesome:"),
    "report": ("Звіт", ":material/description:"),
    "twin": ("3D-двійник", ":material/view_in_ar:"),
}
section = st.segmented_control(
    "Розділ", list(SECTIONS), key="section", default="drone", required=True,
    format_func=lambda k: f"{SECTIONS[k][1]} {SECTIONS[k][0]}",
    label_visibility="collapsed", width="stretch",
)

if section == "drone":
    drone_tab.render()
elif section == "camera":
    camera_tab.render()
elif section == "ai":
    ai_tab.render()
elif section == "report":
    report_tab.render()
else:
    twin_tab.render()
