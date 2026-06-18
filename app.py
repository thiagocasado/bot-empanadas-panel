import streamlit as st
import streamlit.components.v1 as components
import psycopg2
import psycopg2.extras
import os
import io
import json
import math
import wave
import struct
import requests
import time
from collections import defaultdict
from datetime import datetime, time as dt_time, timedelta, timezone

# streamlit-autorefresh es opcional: si no está, usamos un fallback JS
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except Exception:
    HAS_AUTOREFRESH = False

DB_URL      = os.environ.get("DATABASE_URL", "")
WA_TOKEN    = os.environ.get("WHATSAPP_TOKEN", "")
WA_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")

REFRESH_SECONDS = 15  # cada cuánto refresca para detectar mensajes nuevos

TZ_AR  = timezone(timedelta(hours=-3))  # Argentina (UTC-3, sin horario de verano)
TZ_UTC = timezone.utc

# set_page_config DEBE ser el primer comando de Streamlit del script
st.set_page_config(
    page_title="Bot Empanadas",
    layout="wide",
    page_icon="🫓",
    initial_sidebar_state="collapsed",
)


# ─────────────────────────── SONIDO ───────────────────────────

@st.cache_data
def make_beep():
    """Genera un beep corto (WAV en memoria) para la notificación."""
    sr, dur, amp = 22050, 0.22, 0.4
    n = int(sr * dur)
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    frames = bytearray()
    for i in range(n):
        # dos tonos: ding-dong (880 → 1175 Hz)
        freq = 880 if i < n / 2 else 1175
        env = min(1.0, i / (sr * 0.01)) * max(0.0, 1 - i / n)
        s = int(amp * env * 32767 * math.sin(2 * math.pi * freq * i / sr))
        frames += struct.pack("<h", s)
    w.writeframes(bytes(frames))
    w.close()
    return buf.getvalue()


BEEP_WAV = make_beep()


def send_whatsapp(to_phone, text):
    """Manda un mensaje de texto por la API de WhatsApp Cloud (Meta)."""
    if not WA_TOKEN or not WA_PHONE_ID:
        return False, "Faltan WHATSAPP_TOKEN / WHATSAPP_PHONE_ID en las variables de entorno."
    url = f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {WA_TOKEN}"},
            json=payload,
            timeout=15,
        )
        if r.status_code == 200:
            return True, ""
        err = r.json().get("error", {}).get("message", r.text)
        return False, err
    except Exception as e:
        return False, str(e)


st.markdown("""
<style>
  /* ---- Ocultar chrome de Streamlit ---- */
  #MainMenu {visibility:hidden;}
  header[data-testid="stHeader"] {display:none;}
  footer {visibility:hidden;}
  .block-container {padding-top:1rem; padding-bottom:2rem; max-width:1300px;}

  /* ---- Reproductor de audio oculto (suena igual) ---- */
  [data-testid="stAudio"] {display:none !important;}
  audio {display:none !important;}

  /* ---- Topbar ---- */
  .topbar {
    display:flex; align-items:center; justify-content:space-between;
    flex-wrap:wrap; gap:10px;
    background:#111b21; border:1px solid #222e35; border-radius:14px;
    padding:12px 18px; margin-bottom:14px;
  }
  .brand { font-size:1.35em; font-weight:800; color:#fff; letter-spacing:.2px; }
  .brand small { display:block; font-size:.5em; font-weight:500; color:#8696a0; letter-spacing:.5px; }
  .pills { display:flex; gap:8px; flex-wrap:wrap; }
  .pill {
    font-size:.82em; font-weight:600; padding:5px 12px; border-radius:999px;
    border:1px solid transparent; white-space:nowrap;
  }
  .pill.on      { background:#0b3d2e; color:#25d366; border-color:#1f6b50; }
  .pill.off     { background:#3d1417; color:#f87171; border-color:#7f1d1d; }
  .pill.neutral { background:#202c33; color:#cbd5e1; border-color:#2a3942; }
  .pill.alert   { background:#3a2c0a; color:#fbbf24; border-color:#854d0e; }

  /* ---- Lista de chats ---- */
  .chats-title { font-weight:700; color:#e9edef; margin:2px 0 8px; font-size:1.05em; }
  .wa-av {
    width:40px; height:40px; border-radius:50%; background:#2a3942; color:#00a884;
    display:flex; align-items:center; justify-content:center; font-weight:700; font-size:.95em;
  }
  .wa-name { font-weight:600; color:#e9edef; line-height:1.15; }
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius:12px; }
  div[data-testid="stVerticalBlock"] button { text-align:left !important; }

  /* ---- Chat estilo WhatsApp ---- */
  .wa-chat-bg { background:#0b141a; border-radius:10px; max-height:60vh; overflow-y:auto; padding:12px 14px; }
  .chat-wrap { padding:3px 0; overflow:hidden; }
  .bubble {
    display:inline-block; padding:7px 11px 5px; border-radius:10px;
    max-width:75%; word-wrap:break-word; font-size:0.9em; line-height:1.4;
    box-shadow:0 1px 1px rgba(0,0,0,.3);
  }
  .bubble-in  { background:#202c33; color:#e9edef; border-top-left-radius:3px; }
  .bubble-out { background:#005c4b; color:#e9edef; border-top-right-radius:3px; float:right; }
  .row-in     { text-align:left;  overflow:hidden; margin:4px 0; }
  .row-out    { text-align:right; overflow:hidden; margin:4px 0; }
  .msg-time   { font-size:0.64em; color:#8696a0; margin-top:2px; text-align:right; }

  .stTabs [data-baseweb="tab"] { font-size:1em; padding:8px 18px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────── DB ───────────────────────────

def get_conn():
    if not DB_URL:
        st.error(
            "⚠️ **DATABASE_URL** no configurada.  \n"
            "Localmente: `export DATABASE_URL=postgresql://...`  \n"
            "En Railway: agregala como variable de entorno del servicio."
        )
        st.stop()
    try:
        return psycopg2.connect(DB_URL)
    except Exception as e:
        st.error(f"❌ No se puede conectar a la DB: {e}")
        st.stop()


def fetch(conn, sql, params=()):
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception as e:
        conn.rollback()
        st.error(f"Error DB: {e}")
        return []


def execute(conn, sql, params=()):
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error DB: {e}")
        return False


def get_bot_state(conn):
    rows = fetch(conn, "SELECT value FROM bot_state WHERE key = 'global'")
    if not rows:
        return {"paused": False, "horarioForzado": None, "stock": {}}
    v = rows[0]["value"]
    return v if isinstance(v, dict) else json.loads(v)


def save_bot_state(conn, state):
    execute(conn, """
        INSERT INTO bot_state (key, value, updated_at)
        VALUES ('global', %s::jsonb, NOW())
        ON CONFLICT (key) DO UPDATE
          SET value = EXCLUDED.value, updated_at = NOW()
    """, (json.dumps(state),))


def _naive(dt):
    """Quita la zona horaria para poder comparar timestamps sin líos."""
    if dt is not None and getattr(dt, "tzinfo", None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def to_ar(dt):
    """Convierte un timestamp de la DB (UTC) a hora de Argentina para mostrar."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=TZ_UTC)
    return dt.astimezone(TZ_AR)


def iniciales(nombre):
    """Iniciales para el avatar (1-2 letras)."""
    parts = [p for p in str(nombre).split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def fmt_money(x):
    """Formatea un número como pesos: 12600 -> $12.600"""
    try:
        return "$" + f"{float(x or 0):,.0f}".replace(",", ".")
    except Exception:
        return "$0"


# ─────────────────────────── APP ───────────────────────────

conn = get_conn()

now = datetime.now(TZ_AR)
hour, minute = now.hour, now.minute
in_schedule = (11 <= hour <= 23 and not (hour == 23 and minute > 30))

# Estado del bot (para el topbar y el tab de control)
try:
    state = get_bot_state(conn)
except Exception:
    state = {"paused": False, "horarioForzado": None, "stock": {}}
paused = state.get("paused", False)
hf = state.get("horarioForzado")

# ── AUTO-REFRESH (detecta mensajes nuevos solo) ──
if HAS_AUTOREFRESH:
    st_autorefresh(interval=REFRESH_SECONDS * 1000, key="auto_refresh")
else:
    components.html(
        f"<script>setTimeout(function(){{window.parent.location.reload();}}, {REFRESH_SECONDS*1000});</script>",
        height=0,
    )

# ── Baseline para no-leídos (timestamps de la DB, evita líos de zona horaria) ──
if "read_baseline" not in st.session_state:
    row = fetch(conn, "SELECT COALESCE(MAX(created_at), NOW()) AS m FROM conversations WHERE user_message <> ''")
    st.session_state.read_baseline = _naive(row[0]["m"]) if row else None
st.session_state.setdefault("read_at", {})       # phone -> timestamp visto
st.session_state.setdefault("sound_on", True)
st.session_state.setdefault("play_now", False)

# ── Detección de mensaje nuevo (para el sonido) ──
mid = fetch(conn, "SELECT COALESCE(MAX(id), 0) AS m FROM conversations WHERE user_message <> ''")
cur_max_id = mid[0]["m"] if mid else 0
if "seen_max_id" not in st.session_state:
    st.session_state.seen_max_id = cur_max_id
elif cur_max_id > st.session_state.seen_max_id:
    st.session_state.seen_max_id = cur_max_id
    if st.session_state.sound_on:
        st.session_state.play_now = True

# Reproducir el beep si corresponde (el reproductor está oculto por CSS)
if st.session_state.play_now:
    st.audio(BEEP_WAV, format="audio/wav", autoplay=True)
    st.session_state.play_now = False

# ── Mensajes de clientes de los últimos 7 días → para contar no-leídos ──
client_rows = fetch(conn, """
    SELECT phone, created_at FROM conversations
    WHERE user_message IS NOT NULL AND user_message <> ''
      AND created_at > NOW() - INTERVAL '7 days'
""")
client_ts = defaultdict(list)
for r in client_rows:
    if r["created_at"]:
        client_ts[r["phone"]].append(_naive(r["created_at"]))


def unread_for(phone):
    thr = st.session_state.read_at.get(phone, st.session_state.read_baseline)
    if thr is None:
        return 0
    return sum(1 for t in client_ts.get(phone, []) if t > thr)


# ── TOPBAR ──
if hf == "cerrado":
    sched_label = "🔴 Forzado CERRADO"
elif hf == "abierto":
    sched_label = "🟢 Forzado ABIERTO"
elif in_schedule:
    sched_label = "🕐 Abierto (11–23:30)"
else:
    sched_label = f"🌙 Fuera de horario ({hour:02d}:{minute:02d})"

total_unread = sum(unread_for(p) for p in client_ts.keys())
unread_pill = (
    f'<span class="pill alert">🔔 {total_unread} sin leer</span>'
    if total_unread > 0 else
    '<span class="pill neutral">🔕 todo leído</span>'
)
bot_pill = ('<span class="pill on">🟢 Bot activo</span>' if not paused
            else '<span class="pill off">🔴 Bot pausado</span>')

st.markdown(f"""
<div class="topbar">
  <div class="brand">🫓 Bot Empanadas<small>PANEL DE PEDIDOS</small></div>
  <div class="pills">
    {bot_pill}
    <span class="pill neutral">{sched_label}</span>
    {unread_pill}
    <span class="pill neutral">🔄 cada {REFRESH_SECONDS}s</span>
  </div>
</div>
""", unsafe_allow_html=True)

tab_conv, tab_ped, tab_ctrl = st.tabs(
    ["💬  Conversaciones", "📦  Pedidos", "⚙️  Control del Bot"]
)


# ══════════════════ TAB 1 — CONVERSACIONES ══════════════════
with tab_conv:

    contacts = fetch(conn, """
        SELECT
            phone,
            MAX(profile_name) AS profile_name,
            MAX(created_at)   AS last_msg,
            (SELECT user_message FROM conversations c2
             WHERE c2.phone = c.phone ORDER BY created_at DESC LIMIT 1) AS preview
        FROM conversations c
        GROUP BY phone
        ORDER BY last_msg DESC
        LIMIT 60
    """)

    col_list, col_chat = st.columns([1, 2.6], gap="medium")

    with col_list:
        st.markdown('<div class="chats-title">💬 Chats</div>', unsafe_allow_html=True)
        buscar = st.text_input(
            "Buscar", key="buscar_chat",
            placeholder="🔍 Buscar por nombre o teléfono…",
            label_visibility="collapsed",
        )
        if buscar:
            q = buscar.lower()
            contacts = [
                c for c in contacts
                if q in (c["profile_name"] or "").lower() or q in (c["phone"] or "")
            ]

        if not contacts:
            st.info("Sin chats.")

        for row in contacts:
            phone    = row["phone"]
            name     = row["profile_name"] or phone
            ts       = to_ar(row["last_msg"])
            time_str = ts.strftime("%d/%m %H:%M") if ts else ""
            preview  = (row["preview"] or "").replace("\n", " ")[:34]
            unread   = unread_for(phone)
            sel_now  = st.session_state.get("sel_phone") == phone

            with st.container(border=True):
                ac, nc = st.columns([1, 4], gap="small", vertical_alignment="center")
                with ac:
                    st.markdown(f'<div class="wa-av">{iniciales(name)}</div>', unsafe_allow_html=True)
                with nc:
                    badge = f"   🟢 {unread}" if unread > 0 else ""
                    if st.button(f"{name}{badge}", key=f"c_{phone}",
                                 use_container_width=True,
                                 type="primary" if sel_now else "secondary"):
                        st.session_state["sel_phone"] = phone
                        st.rerun()
                st.caption(f"{time_str}  ·  {preview}…")

    with col_chat:
        sel = st.session_state.get("sel_phone")

        if not sel:
            st.markdown("### 👈 Seleccioná un chat")
            st.caption("Elegí un contacto de la izquierda para ver la conversación.")
        else:
            info = next((r for r in contacts if r["phone"] == sel), None)
            name = (info["profile_name"] or sel) if info else sel

            hc1, hc2, hc3 = st.columns([1, 6, 2], gap="small", vertical_alignment="center")
            with hc1:
                st.markdown(f'<div class="wa-av">{iniciales(name)}</div>', unsafe_allow_html=True)
            with hc2:
                st.markdown(f'<div class="wa-name" style="font-size:1.15em">{name}</div>', unsafe_allow_html=True)
                st.caption(sel)
            with hc3:
                if st.button("🗑️ Borrar", key="del_chat", use_container_width=True):
                    execute(conn, "DELETE FROM conversations WHERE phone = %s", (sel,))
                    st.session_state.pop("sel_phone", None)
                    st.rerun()

            st.divider()

            msgs = fetch(conn, """
                SELECT user_message, bot_response, media_b64, media_mime, created_at
                FROM conversations
                WHERE phone = %s
                ORDER BY created_at ASC
            """, (sel,))

            # Abrir el chat = marcarlo como leído (hasta el último mensaje visto)
            if msgs:
                last_ts = max((m["created_at"] for m in msgs if m["created_at"]), default=None)
                if last_ts:
                    st.session_state.read_at[sel] = _naive(last_ts)

            html = '<div class="wa-chat-bg">'
            for m in msgs:
                u   = (m["user_message"] or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                b   = (m["bot_response"]  or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                img = m.get("media_b64")
                ts  = to_ar(m["created_at"])
                t   = ts.strftime("%d/%m %H:%M") if ts else ""
                if u:
                    html += f'<div class="chat-wrap row-in"><div class="bubble bubble-in">{u}<div class="msg-time">{t}</div></div></div>'
                if img:
                    mime = m.get("media_mime") or "image/jpeg"
                    html += (f'<div class="chat-wrap row-in"><div class="bubble bubble-in" style="padding:4px">'
                             f'<img src="data:{mime};base64,{img}" style="max-width:230px;border-radius:8px;display:block">'
                             f'<div class="msg-time">{t}</div></div></div>')
                if b:
                    html += f'<div class="chat-wrap row-out"><div class="bubble bubble-out">{b}<div class="msg-time">{t}</div></div></div>'
            html += "</div>"
            st.markdown(html, unsafe_allow_html=True)

            with st.form(key=f"send_{sel}", clear_on_submit=True):
                fc1, fc2 = st.columns([5, 1])
                with fc1:
                    txt = st.text_input(
                        "Mensaje", key=f"msg_{sel}",
                        placeholder="Escribí una respuesta…",
                        label_visibility="collapsed",
                    )
                with fc2:
                    enviar = st.form_submit_button("📤 Enviar", use_container_width=True, type="primary")

            if enviar and txt.strip():
                ok, err = send_whatsapp(sel, txt.strip())
                if ok:
                    execute(conn, """
                        INSERT INTO conversations (phone, profile_name, user_message, bot_response)
                        VALUES (%s, %s, '', %s)
                    """, (sel, name if name != sel else "", f"👤 {txt.strip()}"))
                    st.rerun()
                else:
                    st.error(f"No se pudo enviar: {err}")
            st.caption("⚠️ WhatsApp solo permite responder hasta 24 hs después del último mensaje del cliente.")


# ══════════════════ TAB 2 — PEDIDOS ══════════════════
with tab_ped:

    try:
        stats = fetch(conn, """
            SELECT
                COUNT(*)                                                                 AS total_n,
                COUNT(CASE WHEN created_at > NOW() - INTERVAL '24 hours' THEN 1 END)      AS hoy_n,
                COUNT(CASE WHEN created_at > NOW() - INTERVAL '7 days'   THEN 1 END)      AS sem_n,
                COALESCE(SUM(precio), 0)                                                  AS total_m,
                COALESCE(SUM(CASE WHEN created_at > NOW() - INTERVAL '24 hours' THEN precio END), 0) AS hoy_m,
                COALESCE(SUM(CASE WHEN created_at > NOW() - INTERVAL '7 days'   THEN precio END), 0) AS sem_m
            FROM pedidos
        """)
    except Exception:
        stats = []

    if stats:
        s = stats[0]
        m1, m2, m3 = st.columns(3)
        m1.metric("💵 Total facturado", fmt_money(s["total_m"]), f"{s['total_n']} pedidos", delta_color="off")
        m2.metric("💵 Hoy", fmt_money(s["hoy_m"]), f"{s['hoy_n']} pedidos", delta_color="off")
        m3.metric("💵 Últimos 7 días", fmt_money(s["sem_m"]), f"{s['sem_n']} pedidos", delta_color="off")
        st.divider()

    try:
        pedidos = fetch(conn, """
            SELECT id, cliente_nombre, cliente_phone, pedido, precio, created_at
            FROM pedidos
            ORDER BY created_at DESC
            LIMIT 100
        """)
    except Exception:
        st.warning("La tabla `pedidos` no existe todavía. Ejecutá `schema.sql` en tu DB de Railway.")
        pedidos = []

    if not pedidos:
        st.info("Sin pedidos confirmados aún. Aparecen acá cuando el bot cierra un pedido.")
    else:
        for p in pedidos:
            ts    = to_ar(p["created_at"])
            t     = ts.strftime("%d/%m/%Y %H:%M") if ts else "—"
            name  = p["cliente_nombre"] or p["cliente_phone"]
            money = fmt_money(p["precio"])
            with st.expander(f"🛒  {name}  —  {money}  —  {t}"):
                st.markdown(f"**Teléfono:** `{p['cliente_phone']}`")
                st.markdown(f"**Precio:** {money}")
                st.markdown("**Detalle del pedido:**")
                st.text(p["pedido"] or "—")


# ══════════════════ TAB 3 — CONTROL DEL BOT ══════════════════
with tab_ctrl:

    try:
        state = get_bot_state(conn)
    except Exception:
        st.warning("La tabla `bot_state` no existe todavía. Ejecutá `schema.sql` en tu DB de Railway.")
        st.stop()

    paused = state.get("paused", False)
    hf     = state.get("horarioForzado")
    if not isinstance(state.get("stock"), dict):
        state["stock"] = {}
    stock  = state["stock"]

    # ── Notificaciones ──
    st.markdown("#### 🔔 Notificaciones")
    n1, n2 = st.columns([2, 1])
    with n1:
        st.session_state.sound_on = st.toggle(
            "Sonido al llegar un mensaje nuevo", value=st.session_state.sound_on
        )
    with n2:
        if st.button("▶️ Probar sonido", use_container_width=True):
            st.audio(BEEP_WAV, format="audio/wav", autoplay=True)
    st.caption("Si no se escucha, hacé clic una vez en la página (el navegador bloquea el audio hasta la primera interacción).")

    st.divider()

    # ── Estado actual ──
    st.markdown("#### Estado actual")
    i1, i2, i3 = st.columns(3)
    with i1:
        st.markdown(f"**Bot:** {'🔴 PAUSADO' if paused else '🟢 ACTIVO'}")
    with i2:
        if hf == "cerrado":
            lbl = "🔴 Forzado CERRADO"
        elif hf == "abierto":
            lbl = "🟢 Forzado ABIERTO"
        else:
            lbl = "🕐 Automático (11–23:30)"
        st.markdown(f"**Horario:** {lbl}")
    with i3:
        agotados = list(stock.keys())
        st.markdown(f"**Agotados:** {', '.join(agotados) if agotados else 'Ninguno'}")

    st.divider()

    # ── Bot on/off ──
    st.markdown("#### 🤖 Bot")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("✅ Activar bot", disabled=not paused, use_container_width=True, type="primary"):
            state["paused"] = False
            save_bot_state(conn, state)
            st.success("Bot activado ✅")
            st.rerun()
    with b2:
        if st.button("⏸️ Pausar bot", disabled=paused, use_container_width=True):
            state["paused"] = True
            save_bot_state(conn, state)
            st.warning("Bot pausado ⏸️")
            st.rerun()

    st.divider()

    # ── Horario ──
    st.markdown("#### 🕐 Horario")
    h1, h2, h3 = st.columns(3)
    with h1:
        if st.button("🟢 Forzar ABIERTO", use_container_width=True):
            state["horarioForzado"] = "abierto"
            save_bot_state(conn, state)
            st.rerun()
    with h2:
        if st.button("🔴 Forzar CERRADO", use_container_width=True):
            state["horarioForzado"] = "cerrado"
            save_bot_state(conn, state)
            st.rerun()
    with h3:
        if st.button("🕐 Volver a automático", use_container_width=True,
                     type="primary" if hf else "secondary"):
            state["horarioForzado"] = None
            save_bot_state(conn, state)
            st.rerun()

    st.divider()

    # ── Stock ──
    st.markdown("#### 📦 Stock de empanadas")
    st.caption("Tildá lo que está agotado — el bot deja de ofrecerlo automáticamente.")

    PRODUCTOS = {
        "CS": "Carne suave",       "CP": "Carne picante",
        "BQ": "Cerdo BBQ",         "JQ": "Jamón y queso",
        "HU": "Humita",            "VE": "Verdura",
        "PO": "Pollo",             "PB": "Pollo s. blanca",
        "PH": "Pollo cheddar",     "RJ": "Roquefort jamón",
        "CQ": "Cebolla queso",     "HC": "Calabaza choclo",
        "SC": "Salchicha cheddar", "PC": "Panceta queso",
        "BC": "Brócoli champignon","OS": "Osobuco",
    }

    changed = False
    cols = st.columns(4)
    for i, (code, pname) in enumerate(PRODUCTOS.items()):
        with cols[i % 4]:
            prev = code in stock
            val  = st.checkbox(f"**{code}** {pname}", value=prev, key=f"sk_{code}")
            if val and not prev:
                state["stock"][code] = True
                changed = True
            elif not val and prev:
                state["stock"].pop(code, None)
                changed = True

    if changed:
        save_bot_state(conn, state)
        st.rerun()

    st.divider()
    if st.button("🧹 Limpiar todos los agotados"):
        state["stock"] = {}
        save_bot_state(conn, state)
        st.rerun()


conn.close()
