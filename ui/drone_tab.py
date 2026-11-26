"""
Вкладка «Дрон»: підключення, живі кути, графіки, індикатор «СТАБІЛЬНО».
"""
import pandas as pd
import streamlit as st

from core import config
from core.drone_reader import HISTORY_SEC, get_reader


def render():
    reader = get_reader()

    st.subheader("Дрон: нахил і стабільність")
    st.caption("⚠️ Перед підключенням натисни «Disconnect» у Betaflight Configurator у Chrome "
               "(або закрий його вкладку), інакше порт буде зайнятий.")

    # ---------- Кнопки керування ----------
    col1, col2, col3 = st.columns([1, 1, 2])
    demo = col3.toggle("Демо-режим (без дрона)", value=False,
                       help="Несправжні дані, щоб перевірити інтерфейс без дрона.")
    if col1.button("🔌 Підключити", width="stretch"):
        reader.start(demo=demo)
    if col2.button("⏹ Від'єднати", width="stretch"):
        reader.stop()

    # ---------- Поріг стабільності ----------
    threshold = st.slider(
        "Поріг стабільності, °/с (менше — суворіше)",
        min_value=1.0, max_value=60.0, value=float(reader.detector.threshold), step=1.0,
        help=f"«СТАБІЛЬНО» — коли гіроскоп по всіх осях нижче порогу "
             f"протягом {int(config.STABLE_HOLD_SEC * 1000)} мс.",
    )
    reader.set_threshold(threshold)

    # Жива панель оновлюється сама 4 рази на секунду (лише коли дрон увімкнений),
    # не перезапускаючи всю сторінку
    st.fragment(live_panel, run_every=0.25 if reader.running else None)(threshold)


def live_panel(threshold):
    snap = get_reader().snapshot()

    # ---------- Стан зв'язку ----------
    if not snap["running"]:
        st.info("Дрон не підключено. Натисни «🔌 Підключити».")
        return
    if snap["error"]:
        st.error(snap["error"])
        st.caption("Програма пробує підключитися знову кожні 2 секунди.")
        return
    if snap["demo"]:
        st.warning("Демо-режим: дані несправжні.")
    else:
        st.success(f"Підключено: {snap['port']} · прошивка {snap['fc_info']}")

    data = snap["latest"]
    if data is None:
        st.write("Чекаю перших даних від дрона…")
        return

    # ---------- Великий індикатор ----------
    if data["stable"]:
        color, text = "#1e9e4a", f"СТАБІЛЬНО · {data['stable_for']:.1f} с"
    else:
        color, text = "#c0392b", "НЕСТАБІЛЬНО"
    st.markdown(
        f"<div style='background:{color};color:white;font-size:2.2rem;font-weight:700;"
        f"text-align:center;padding:14px;border-radius:12px'>{text}</div>",
        unsafe_allow_html=True,
    )

    # ---------- Числа ----------
    c = st.columns(3)   # перший рядок: кути
    c[0].metric("Крен (roll)", f"{data['roll']:+.1f}°")
    c[1].metric("Нахил (pitch)", f"{data['pitch']:+.1f}°")
    c[2].metric("Рискання (yaw)", f"{data['yaw']:.0f}°")
    c = st.columns(3)   # другий рядок: гіроскоп
    c[0].metric("Гіро X", f"{data['gx']:+.1f} °/с")
    c[1].metric("Гіро Y", f"{data['gy']:+.1f} °/с")
    c[2].metric("Гіро Z", f"{data['gz']:+.1f} °/с")

    # ---------- Графіки за останні 10 секунд ----------
    hist = snap["history"]
    if len(hist) < 2:
        return
    df = pd.DataFrame(hist)
    df["час, с"] = df["t"] - df["t"].iloc[-1]   # 0 = зараз, -10 = 10 с тому
    df = df[df["час, с"] >= -HISTORY_SEC]         # лише останні 10 секунд

    g1, g2 = st.columns(2)
    with g1:
        st.caption("Кути, °")
        angles = df.rename(columns={"roll": "крен", "pitch": "нахил"})
        st.line_chart(angles, x="час, с", y=["крен", "нахил"], height=250)
    with g2:
        st.caption("Гіроскоп, °/с (лінії «поріг +» і «поріг −» — межі стабільності)")
        gyro = df.rename(columns={"gx": "X", "gy": "Y", "gz": "Z"})
        gyro["поріг +"] = threshold
        gyro["поріг −"] = -threshold
        st.line_chart(gyro, x="час, с", y=["X", "Y", "Z", "поріг +", "поріг −"], height=250)
