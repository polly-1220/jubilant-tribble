"""
Дизайн застосунку: яскраві пастельні кольори, «стікери», картки з тінню,
кольорові позначки статусів і трохи жартівливих підписів.

Кольори і шрифти — у .streamlit/config.toml, а тут — додаткові стилі (CSS)
і маленькі функції, які повертають шматочки HTML.
Серйозні речі (застереження, PDF-звіт) — без жартів.
"""
import random

import streamlit as st

INK = "#2A2342"      # колір обводки і тіней
VIOLET = "#7C5CFF"
PINK = "#FF5FA2"
MINT = "#2EE6A6"
SUN = "#FFD447"
SKY = "#7CD3FF"

# Кольори статусів (однакові по всьому застосунку)
STATUS_COLORS = {"очікує": "#FFC83D", "підтверджено": "#FF4D6D", "відхилено": "#B9B4C7"}

CSS = f"""
<style>
/* ---------- Фон: м'які кольорові плями ---------- */
.stApp {{
  background:
    radial-gradient(circle at 8% 0%, #FFE1F0 0, transparent 32%),
    radial-gradient(circle at 98% 6%, #D9F4FF 0, transparent 30%),
    radial-gradient(circle at 85% 95%, #EAE2FF 0, transparent 35%),
    radial-gradient(circle at 0% 90%, #FFF3C9 0, transparent 30%),
    #FFFBF4;
}}
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #F1EAFF 0%, #FFEFF7 100%);
  border-right: 2px solid {INK};
}}
[data-testid="stHeader"] {{ background: transparent; }}

/* ---------- Кнопки: обводка + «тінь-наклейка» ---------- */
.stButton > button, .stDownloadButton > button {{
  border: 2px solid {INK} !important;
  box-shadow: 3px 3px 0 {INK};
  font-weight: 700;
  transition: transform .08s ease, box-shadow .08s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  transform: translate(-1px, -1px);
  box-shadow: 4px 4px 0 {INK};
}}
.stButton > button:active, .stDownloadButton > button:active {{
  transform: translate(2px, 2px);
  box-shadow: 1px 1px 0 {INK};
}}
.stButton > button:disabled {{ box-shadow: none; opacity: .45; }}

/* ---------- Картки, метрики, розгортки ---------- */
[data-testid="stMetric"] {{
  background: #FFFFFF;
  border: 2px solid {INK};
  border-radius: 18px;
  padding: 10px 16px;
  box-shadow: 4px 4px 0 {INK};
}}
[data-testid="stMetricValue"] {{ font-family: Unbounded, sans-serif; }}
[data-testid="stExpander"] details {{
  background: #FFFFFF;
  border: 2px solid {INK};
  border-radius: 16px;
}}
[data-testid="stAlert"] {{ border-radius: 16px; }}
[data-testid="stImage"] img {{ border-radius: 14px; }}

/* ---------- Заголовок-банер ---------- */
.rb-hero {{
  position: relative;
  padding: 26px 28px 22px;
  margin: 4px 0 14px;
  border: 2px solid {INK};
  border-radius: 26px;
  box-shadow: 6px 6px 0 {INK};
  background: linear-gradient(120deg, #E9E1FF 0%, #FFE3F1 48%, #FFF1C7 100%);
  overflow: hidden;
}}
.rb-hero h1 {{
  font-family: Unbounded, sans-serif;
  font-weight: 800;
  font-size: clamp(2rem, 5vw, 3.3rem);
  line-height: 1.05;
  margin: 0;
  padding: 0;
  letter-spacing: -0.03em;
  color: {INK};
}}
.rb-hero h1 span {{
  background: linear-gradient(90deg, {VIOLET}, {PINK} 60%, #FF9F43);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}}
.rb-hero p {{ margin: 8px 0 0; font-size: 1.02rem; color: #4A4266; }}
.rb-hero .rb-sticker {{ position: absolute; top: 18px; right: 22px; }}
@media (max-width: 1000px) {{
  .rb-hero .rb-sticker {{ position: static; margin-bottom: 10px; }}
}}
.rb-blob {{
  position: absolute; border-radius: 50%; border: 2px solid {INK}; opacity: .9;
}}

/* ---------- Стікер ---------- */
.rb-sticker {{
  display: inline-block;
  font-family: Unbounded, sans-serif; font-weight: 700; font-size: .78rem;
  padding: 5px 12px;
  border: 2px solid {INK};
  border-radius: 999px;
  box-shadow: 2px 2px 0 {INK};
  transform: rotate(-3deg);
  color: {INK};
  white-space: nowrap;
}}

/* ---------- Позначки статусів ---------- */
.rb-pill {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 10px; margin: 2px 4px 2px 0;
  border: 1.5px solid {INK}; border-radius: 999px;
  background: #FFFFFF; font-size: .85rem; font-weight: 600; color: {INK};
}}
.rb-dot {{
  display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  border: 1.5px solid {INK}; flex: none;
}}

/* ---------- Великий індикатор стабільності ---------- */
.rb-status {{
  border: 2px solid {INK};
  border-radius: 24px;
  box-shadow: 5px 5px 0 {INK};
  padding: 18px 20px 14px;
  text-align: center;
  color: {INK};
}}
.rb-status b {{
  display: block;
  font-family: Unbounded, sans-serif; font-weight: 800;
  font-size: clamp(1.6rem, 4vw, 2.6rem); letter-spacing: -0.02em;
}}
.rb-status small {{ font-size: .95rem; opacity: .85; }}

/* ---------- Порожній стан ---------- */
.rb-empty {{
  border: 2px dashed {INK}; border-radius: 20px; padding: 18px;
  text-align: center; color: #4A4266; background: rgba(255,255,255,.6);
}}

/* ---------- Підпис-жарт ---------- */
.rb-meme {{ font-size: .88rem; color: #6A6286; font-style: italic; margin: -4px 0 10px; }}

.rb-footer {{ font-size: .8rem; color: #6A6286; margin-top: 8px; }}
</style>
"""


def inject():
    """Підключає стилі на сторінку (викликати один раз на початку app.py)."""
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title_plain, title_color, subtitle, sticker_text):
    """Великий банер угорі сторінки."""
    st.markdown(
        f"""<div class="rb-hero">
        <div class="rb-blob" style="width:90px;height:90px;right:-24px;bottom:-30px;background:{MINT}"></div>
        <div class="rb-blob" style="width:46px;height:46px;right:80px;bottom:-14px;background:{SKY}"></div>
        <span class="rb-sticker" style="background:{SUN}">{sticker_text}</span>
        <h1>{title_plain}<span>{title_color}</span></h1>
        <p>{subtitle}</p></div>""",
        unsafe_allow_html=True,
    )


def sticker(text, color=SUN, rotate=-3):
    return (f'<span class="rb-sticker" style="background:{color};'
            f'transform:rotate({rotate}deg)">{text}</span>')


def show_sticker(text, color=SUN, rotate=-3):
    st.markdown(sticker(text, color, rotate), unsafe_allow_html=True)


def dot(color):
    return f'<span class="rb-dot" style="background:{color}"></span>'


def pill(text, color):
    """Позначка: кольорова крапка + текст."""
    return f'<span class="rb-pill">{dot(color)}{text}</span>'


def status_pill(status, count=None):
    label = status if count is None else f"{status}: {count}"
    return pill(label, STATUS_COLORS[status])


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def empty(text):
    html(f'<div class="rb-empty">{text}</div>')


# ---------- Жартівливі підписи (обираються один раз на сесію) ----------
MEMES = {
    "stable": ["дрон на чілі — можна знімати", "рівно, як лінійка на контрольній",
               "стабільніше, ніж мій сон перед іспитом"],
    "unstable": ["тримай рівніше, бро", "дрон трясеться, як я перед захистом проєкту",
                 "вдих — видих — і рівненько"],
    "sleep": ["дрон ще спить. розбуди його кнопкою «Підключити»",
              "дрон у режимі «ще 5 хвилин»"],
    "empty_gallery": ["тут поки пусто, як у холодильнику о 2 ночі",
                      "знімків нуль. час створити контент"],
    "no_findings": ["тріщин нема. макет живе своє найкраще життя",
                    "чисто. навіть підозріло чисто"],
    "stub": ["AI поки на заміні — грає заглушка", "заглушка старається, як може"],
    "twin": ["крути модельку — це законно", "3D, бо 2D — це вже минуле століття"],
    "camera_off": ["камера відпочиває", "об'єктив на перерві"],
}


def meme(kind):
    """Один жартівливий підпис для цього місця (не міняється при кожному кліку)."""
    key = f"meme_{kind}"
    if key not in st.session_state:
        st.session_state[key] = random.choice(MEMES[kind])
    return st.session_state[key]


def meme_line(kind):
    html(f'<div class="rb-meme">{meme(kind)}</div>')
