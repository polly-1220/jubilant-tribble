"""
ReBuildDrone — головний файл застосунку.
Запуск:  streamlit run app.py
"""
import streamlit as st

from core import config
from ui import ai_tab, camera_tab, drone_tab

# Налаштування сторінки (має бути першою командою Streamlit)
st.set_page_config(page_title="ReBuildDrone", page_icon="🛸", layout="wide")

# Створюємо папки для даних, якщо їх ще немає
config.ensure_folders()

st.title("🛸 ReBuildDrone")
st.caption("Пошук тріщин на макеті будівлі за допомогою дрона та AI. Працює офлайн.")

# ---------- Бічна панель: стан системи ----------
with st.sidebar:
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
    st.subheader("PDF-звіт")
    st.info("Етап 5: збереження в базу і формування звіту.")
else:
    st.subheader("3D-двійник макета")
    st.info("Етап 6: 3D-модель із кольоровими секторами.")
