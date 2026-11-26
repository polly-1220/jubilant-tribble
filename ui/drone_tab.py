"""
Вкладка «Дрон»: підключення, живі кути, графіки, індикатор «СТАБІЛЬНО».
"""
import pandas as pd
import streamlit as st

from core import config
from core.drone_reader import HISTORY_SEC, get_reader
from ui import style


def render():
    reader = get_reader()

    st.subheader("Дрон: нахил і стабільність")
    st.caption("Перед підключенням натисни «Disconnect» у Betaflight Configurator у Chrome "
               "(або закрий його вкладку), інакше порт буде зайнятий.")

    # ---------- Кнопки керування ----------
    col1, col2, _ = st.columns([1, 1, 2], vertical_alignment="center")
    if col1.button("Підключити", icon=":material/link:", type="primary", width="stretch"):
        reader.start()
    if col2.button("Від'єднати", icon=":material/link_off:", width="stretch"):
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
        style.empty(f"<b>Дрон не підключено.</b><br>{style.meme('sleep')}")
        return
    if snap["error"]:
        st.error(snap["error"])
        st.caption("Програма пробує підключитися знову кожні 2 секунди.")
        return
    style.html(style.pill(f"підключено: {snap['port']} · {snap['fc_info']}", "#16B877"))

    data = snap["latest"]
    if data is None:
        st.write("Чекаю перших даних від дрона…")
        return

    # ---------- Великий індикатор ----------
    if data["stable"]:
        bg = "linear-gradient(120deg, #B8FFE4, #2EE6A6)"
        text, sub = f"СТАБІЛЬНО · {data['stable_for']:.1f} с", style.meme("stable")
    else:
        bg = "linear-gradient(120deg, #FFD0DC, #FF7A95)"
        text, sub = "НЕСТАБІЛЬНО", style.meme("unstable")
    style.html(f'<div class="rb-status" style="background:{bg}"><b>{text}</b>'
               f'<small>{sub}</small></div>')
    st.write("")

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
        st.line_chart(angles, x="час, с", y=["крен", "нахил"], height=250,
                      color=["#7C5CFF", "#FF5FA2"])
    with g2:
        st.caption("Гіроскоп, °/с (лінії «поріг +» і «поріг −» — межі стабільності)")
        gyro = df.rename(columns={"gx": "X", "gy": "Y", "gz": "Z"})
        gyro["поріг +"] = threshold
        gyro["поріг −"] = -threshold
        st.line_chart(gyro, x="час, с", y=["X", "Y", "Z", "поріг +", "поріг −"], height=250,
                      color=["#7C5CFF", "#FF5FA2", "#2EC4B6", "#C9C3DA", "#C9C3DA"])
