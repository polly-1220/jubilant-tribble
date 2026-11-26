"""
Вкладка «Зйомка»: вебкамера, автозйомка, кнопка знімка, імпорт фото, галерея знімків.
"""
import cv2
import streamlit as st

from core import captures, config, quality, sector
from core.camera import get_camera
from core.drone_reader import get_reader

NO_SECTOR = "— не визначено —"


def render():
    cam = get_camera()
    st.subheader("Зйомка макета")

    # ---------- Камера ----------
    c1, c2, c3 = st.columns([1, 1, 1])
    index = c1.selectbox("Камера", [0, 1, 2, 3], index=cam.index,
                         help="0 — зазвичай вбудована камера Mac. "
                              "Телефон (Continuity Camera) часто має номер 1.")
    if c2.button("📷 Увімкнути камеру", width="stretch"):
        cam.start(index)
    if c3.button("⏹ Вимкнути камеру", width="stretch"):
        cam.stop()

    cam.auto_enabled = st.toggle(
        "🤖 Автозйомка: знімок, коли дрон «СТАБІЛЬНО» вже 1 с",
        value=cam.auto_enabled,
        help="Не частіше ніж раз на 2 с. Наступний автознімок — після того, "
             "як дрон знову похитнеться і стане рівно.",
    )

    # ---------- Пороги якості ----------
    with st.expander("⚙️ Пороги якості кадру"):
        q1, q2 = st.columns(2)
        quality.QualitySettings.sharpness_min = q1.slider(
            "Мінімальна різкість", 10.0, 500.0, float(quality.QualitySettings.sharpness_min), 10.0,
            help="Дисперсія Лапласіана. Менше цього числа — кадр «розмитий».")
        bmin, bmax = q2.slider(
            "Допустима яскравість (0–255)", 0.0, 255.0,
            (float(quality.QualitySettings.brightness_min),
             float(quality.QualitySettings.brightness_max)), 5.0)
        quality.QualitySettings.brightness_min = bmin
        quality.QualitySettings.brightness_max = bmax

    live_camera()

    # ---------- Імпорт фото ----------
    with st.expander("📂 Імпорт фото (з телефона)"):
        st.caption("Підходять JPG і PNG. Фото iPhone у форматі HEIC треба спершу зберегти як JPEG "
                   "(Налаштування → Камера → Формати → «Найсумісніший»).")
        files = st.file_uploader("Вибери фото", type=["jpg", "jpeg", "png"],
                                 accept_multiple_files=True)
        if files and st.button("Імпортувати вибрані фото"):
            for f in files:
                res = captures.import_bytes(f.getvalue(), f.name)
                if isinstance(res, str):
                    st.error(res)
            st.success(f"Імпортовано: {len(files)}")
        st.divider()
        folder = st.text_input("…або всі фото з папки", value=str(config.IMPORT_DIR))
        if st.button("Імпортувати з папки"):
            count, errors = captures.import_folder(folder)
            for e in errors:
                st.error(e)
            st.success(f"Імпортовано: {count}. Оброблені фото перенесено в підпапку «імпортовано».")

    gallery()


# Живий перегляд камери (оновлюється 4 рази на секунду)
@st.fragment(run_every=0.25)
def live_camera():
    cam = get_camera()
    if cam.error:
        st.error(cam.error)
    frame = cam.get_frame()
    if frame is None:
        if cam.running:
            st.info("Камера вмикається… (якщо macOS питає дозвіл на камеру — дозволь)")
        else:
            st.info("Камеру вимкнено. Натисни «📷 Увімкнути камеру». "
                    "Без камери можна імпортувати фото нижче.")
        return

    left, right = st.columns([3, 2])
    with left:
        small = cv2.resize(frame, (640, int(640 * frame.shape[0] / frame.shape[1])))
        preview = sector.draw(small)
        st.image(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB), width="stretch")
    with right:
        # Стан дрона
        sample = get_reader().latest_sample()
        if sample is None:
            st.warning("Дрон не підключений — автозйомка не спрацює (вкладка «🛸 Дрон»).")
        elif sample["stable"]:
            st.success(f"Дрон: СТАБІЛЬНО · {sample['stable_for']:.1f} с")
        else:
            st.error("Дрон: НЕСТАБІЛЬНО")

        # Якість і сектор поточного кадру
        q = quality.check(frame)
        st.write(f"Різкість: **{q['sharpness']:.0f}** · Яскравість: **{q['brightness']:.0f}**")
        st.write("✅ Кадр добрий" if q["ok"] else "⚠️ Перезняти: " + ", ".join(q["reasons"]))
        sec = sector.find_sector(small)
        st.write(f"Сектор: **{sec['name']}** (ArUco)" if sec["name"]
                 else "Сектор: мітку не видно")

        if st.button("📸 Зробити знімок", type="primary", width="stretch"):
            cam.take_shot("кнопка")
        if cam.last_message:
            st.caption("Останній знімок: " + cam.last_message)


# Галерея знімків (оновлюється кожні 3 секунди, щоб з'являлися автознімки)
@st.fragment(run_every=3)
def gallery():
    items = captures.list_captures()
    st.subheader(f"Знімки ({len(items)})")
    if not items:
        st.caption("Ще немає знімків.")
        return
    show = st.slider("Скільки показувати", 3, max(3, min(60, len(items))),
                     min(9, max(3, len(items))), 3) if len(items) > 3 else len(items)
    cols = st.columns(3)
    for n, meta in enumerate(items[:show]):
        with cols[n % 3]:
            capture_card(meta)


def capture_card(meta):
    cap_id = meta["id"]
    with st.container(border=True):
        st.image(str(config.RAW_DIR / meta["file"]), width="stretch")
        st.caption(f"{meta['time'].replace('T', ' ')} · {meta['source']}")

        q = meta["quality"]
        if q["ok"]:
            st.write(f"✅ Якість добра (різкість {q['sharpness']:.0f})")
        else:
            st.write(f"⚠️ **Перезняти**: {', '.join(q['reasons'])} "
                     f"(різкість {q['sharpness']:.0f}, яскравість {q['brightness']:.0f})")

        d = meta["drone"]
        if d:
            demo = " (демо)" if d.get("demo") else ""
            st.write(f"🛸 крен {d['roll']:+.1f}°, нахил {d['pitch']:+.1f}°, "
                     f"рискання {d['yaw']:.0f}°{demo}")
        else:
            st.write("🛸 кути дрона: немає")

        # Сектор: автоматично з ArUco або вибір вручну
        s = meta["sector"]
        options = [NO_SECTOR] + config.SECTOR_NAMES
        current = s["name"] if s["name"] in config.SECTOR_NAMES else NO_SECTOR
        label = "Сектор" + (f" ({s['method']})" if s["method"] else "")
        choice = st.selectbox(label, options, index=options.index(current), key=f"sec_{cap_id}")
        if choice != current:
            captures.set_sector_manual(cap_id, None if choice == NO_SECTOR else choice)
            st.rerun(scope="fragment")

        if st.button("🗑 Видалити", key=f"del_{cap_id}"):
            captures.delete_capture(cap_id)
            st.rerun(scope="fragment")
