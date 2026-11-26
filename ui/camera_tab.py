"""
Вкладка «Зйомка»: вебкамера, автозйомка, кнопка знімка, імпорт фото, галерея знімків.
"""
import cv2
import streamlit as st

from core import captures, config, quality, sector
from core.camera import get_camera
from core.drone_reader import get_reader
from ui import style

NO_SECTOR = "— не визначено —"
GOOD, BAD = "#16B877", "#FF4D6D"


def render():
    cam = get_camera()
    st.subheader("Зйомка макета")

    # ---------- Камера ----------
    c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    index = c1.selectbox("Камера", [0, 1, 2, 3], index=cam.index,
                         help="0 — зазвичай вбудована камера Mac. "
                              "Телефон (Continuity Camera) часто має номер 1.")
    if c2.button("Увімкнути камеру", icon=":material/videocam:", type="primary",
                 width="stretch"):
        cam.start(index)
    if c3.button("Вимкнути камеру", icon=":material/videocam_off:", width="stretch"):
        cam.stop()

    cam.auto_enabled = st.toggle(
        "Автозйомка: знімок, коли дрон «СТАБІЛЬНО» вже 1 с",
        value=cam.auto_enabled,
        help="Не частіше ніж раз на 2 с. Наступний автознімок — після того, "
             "як дрон знову похитнеться і стане рівно.",
    )

    # ---------- Пороги якості ----------
    with st.expander("Пороги якості кадру", icon=":material/tune:"):
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

    # Живий перегляд оновлюється 4 рази на секунду — лише коли камера увімкнена
    st.session_state.setdefault("seen_shots", cam.shots_count)
    st.fragment(live_camera, run_every=0.25 if cam.running else None)()

    # ---------- Імпорт фото ----------
    with st.expander("Імпорт фото з телефона", icon=":material/upload:"):
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
        if st.button("Імпортувати з папки", icon=":material/folder_open:"):
            count, errors = captures.import_folder(folder)
            for e in errors:
                st.error(e)
            st.success(f"Імпортовано: {count}. Оброблені фото перенесено в підпапку «імпортовано».")

    gallery()


def live_camera():
    cam = get_camera()
    # З'явився новий знімок (наприклад, автозйомка) — оновлюємо всю сторінку, щоб він
    # потрапив у галерею. Те саме, якщо камера раптом вимкнулась (помилка).
    if cam.shots_count != st.session_state["seen_shots"]:
        st.session_state["seen_shots"] = cam.shots_count
        st.rerun(scope="app")
    if cam.error:
        st.error(cam.error)
        if st.session_state.get("cam_was_running"):
            st.session_state["cam_was_running"] = False
            st.rerun(scope="app")
    st.session_state["cam_was_running"] = cam.running
    frame = cam.get_frame()
    if frame is None:
        if cam.running:
            st.info("Камера вмикається… (якщо macOS питає дозвіл на камеру — дозволь)")
        else:
            style.empty(f"<b>{style.meme('camera_off')}.</b><br>Натисни «Увімкнути камеру» "
                        "або імпортуй фото нижче.")
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
            style.html(style.pill("дрон не підключений — автозйомка чекає", "#FFC83D"))
        elif sample["stable"]:
            style.html(style.pill(f"дрон: СТАБІЛЬНО · {sample['stable_for']:.1f} с", GOOD))
        else:
            style.html(style.pill("дрон: НЕСТАБІЛЬНО", BAD))

        # Якість і сектор поточного кадру
        q = quality.check(frame)
        st.write(f"Різкість: **{q['sharpness']:.0f}** · Яскравість: **{q['brightness']:.0f}**")
        style.html(style.pill("кадр добрий", GOOD) if q["ok"]
                   else style.pill("перезняти: " + ", ".join(q["reasons"]), BAD))
        sec = sector.find_sector(small)
        style.html(style.pill(f"сектор {sec['name']} · ArUco", "#7C5CFF") if sec["name"]
                   else style.pill("мітку не видно", "#C9C3DA"))
        st.write("")
        if st.button("Зробити знімок", icon=":material/photo_camera:", type="primary",
                     width="stretch"):
            cam.take_shot("кнопка")
        if cam.last_message:
            st.caption("Останній знімок: " + cam.last_message)


# Галерея знімків (нові знімки з'являються, коли живий перегляд оновлює сторінку)
@st.fragment
def gallery():
    items = captures.list_captures()
    st.subheader(f"Знімки · {len(items)}")
    if not items:
        style.empty(style.meme("empty_gallery"))
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
        pills = [style.pill(f"якість добра · {q['sharpness']:.0f}", GOOD) if q["ok"]
                 else style.pill("перезняти: " + ", ".join(q["reasons"]), BAD)]
        d = meta["drone"]
        if d:
            pills.append(style.pill(f"крен {d['roll']:+.1f}° · нахил {d['pitch']:+.1f}° · "
                                    f"рискання {d['yaw']:.0f}°", "#7CD3FF"))
        else:
            pills.append(style.pill("кути дрона: немає", "#C9C3DA"))
        style.html("".join(pills))

        # Сектор: автоматично з ArUco або вибір вручну
        s = meta["sector"]
        options = [NO_SECTOR] + config.SECTOR_NAMES
        current = s["name"] if s["name"] in config.SECTOR_NAMES else NO_SECTOR
        label = "Сектор" + (f" ({s['method']})" if s["method"] else "")
        choice = st.selectbox(label, options, index=options.index(current), key=f"sec_{cap_id}")
        if choice != current:
            captures.set_sector_manual(cap_id, None if choice == NO_SECTOR else choice)
            st.rerun(scope="fragment")

        if st.button("Видалити", icon=":material/delete:", key=f"del_{cap_id}"):
            captures.delete_capture(cap_id)
            st.rerun(scope="fragment")
