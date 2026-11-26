"""
ReBuildDrone — головний файл застосунку.
Запуск:  streamlit run app.py
"""
import streamlit as st

from core import config, db
from ui import ai_tab, camera_tab, drone_tab, report_tab

# Налаштування сторінки (має бути першою командою Streamlit)
st.set_page_config(page_title="ReBuildDrone", page_icon="🛸", layout="wide")

# Створюємо папки для даних і базу даних, якщо їх ще немає
config.ensure_folders()
db.init()

st.title("🛸 ReBuildDrone")
st.caption("Пошук тріщин на макеті будівлі за допомогою дрона та AI. Працює офлайн.")

# ---------- Бічна панель: обстеження і стан системи ----------
with st.sidebar:
    st.header("📋 Обстеження")
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
    with st.expander("➕ Нове обстеження"):
        new_name = st.text_input("Назва", placeholder="напр.: Макет школи, сторона А")
        new_notes = st.text_area("Примітки (необов'язково)", height=70)
        if st.button("Створити", disabled=not new_name.strip()):
            db.set_active_survey_id(db.create_survey(new_name, new_notes))
            st.rerun()

    st.divider()
    st.header("Стан системи")

    # Перевіряємо, чи встановлені потрібні бібліотеки
    def lib_ok(name):
        try:
            __import__(name)
            return True
        except ImportError:
            return False

    checks = {
        "Streamlit": lib_ok("streamlit"),
        "pyserial (дрон)": lib_ok("serial"),
        "OpenCV (камера)": lib_ok("cv2"),
        "ONNX Runtime (AI)": lib_ok("onnxruntime"),
        "ReportLab (PDF)": lib_ok("reportlab"),
    }
    for name, ok in checks.items():
        st.write(("✅ " if ok else "❌ ") + name)

    st.divider()
    st.write("AI-модель:", "✅ знайдено" if config.CRACK_MODEL_PATH.exists()
             else "⚠️ немає (буде заглушка)")
    st.write("3D-модель:", "✅ знайдено" if config.MAKET_MODEL_PATH.exists()
             else "⚠️ немає (буде тестовий куб)")

# ---------- Розділи: показуємо лише вибраний ----------
# (Звичайні st.tabs малюють усі вкладки одразу, і живі панелі дрона й камери
#  оновлювалися б навіть тоді, коли ти перевіряєш знахідки, — через це губилися б кліки.)
SECTIONS = ["🛸 Дрон", "📷 Зйомка", "🤖 AI-аналіз", "📄 Звіт", "🧊 3D-двійник"]
section = st.radio("Розділ", SECTIONS, horizontal=True, key="section",
                   label_visibility="collapsed")
st.divider()

if section == "🛸 Дрон":
    drone_tab.render()
elif section == "📷 Зйомка":
    camera_tab.render()
elif section == "🤖 AI-аналіз":
    ai_tab.render()
elif section == "📄 Звіт":
    report_tab.render()
else:
    st.subheader("3D-двійник макета")
    st.info("Етап 6: 3D-модель із кольоровими секторами.")
