import streamlit as st
import psycopg2
import psycopg2.extras
import os
import json
import requests
import time
from datetime import datetime, time as dt_time

DB_URL = os.environ.get("DATABASE_URL", "")
WA_TOKEN    = os.environ.get("WHATSAPP_TOKEN", "")
WA_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")


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

st.set_page_config(
    page_title="Bot Empanadas",
    layout="wide",
    page_icon="🫓",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<div id="refresh-timer" style="position:fixed;top:10px;right:10px;background:#2d2d2d;color:#fff;padding:10px 15px;border-radius:8px;font-size:14px;z-index:9999;font-weight:bold;">🔄 Cargando...</div>

<style>
  /* ---- Sonido ---- */
  .sound-player { display: none; }

  /* ---- Chat bubbles ---- */
  .chat-wrap { padding: 4px 0; overflow: hidden; }
  .bubble {
    display: inline-block;
    padding: 9px 13px;
    border-radius: 16px;
    max-width: 72%;
    word-wrap: break-word;
    font-size: 0.9em;
    line-height: 1.45;
  }
  .bubble-user  { background:#dcf8c6; color:#1a1a1a; border-radius:16px 16px 16px 4px; font-weight:500; }
  .bubble-bot   { background:#2d2d2d; color:#ffffff; border-radius:16px 16px 4px 16px; float:right; }
  .row-user     { text-align:left;  overflow:hidden; margin:5px 0; }
  .row-bot      { text-align:right; overflow:hidden; margin:5px 0; }
  .msg-time     { font-size:0.68em; color:#aaa; margin-top:3px; }

  /* ---- Contact list ---- */
  div[data-testid="stVerticalBlock"] button { text-align:left !important; }

  /* ---- General ---- */
  .stTabs [data-baseweb="tab"] { font-size:1em; padding:8px 18px; }
</style>

<script>
  // Auto-refresh cada 60 segundos (solo 11-23:30)
  const timerElement = document.getElementById('refresh-timer');
  const checkTimeAndRefresh = () => {
    const now = new Date();
    const hour = now.getHours();
    const min = now.getMinutes();
    const timeInMin = hour * 60 + min;
    const startMin = 11 * 60; // 11:00
    const endMin = 23 * 60 + 30; // 23:30

    const inSchedule = timeInMin >= startMin && timeInMin <= endMin;
    if (inSchedule) {
      let timeLeft = 60;
      if (timerElement) timerElement.textContent = '🔄 60s';
      const counter = setInterval(() => {
        if (timerElement) timerElement.textContent = '🔄 ' + timeLeft + 's';
        if (timeLeft <= 0) {
          clearInterval(counter);
          if (timerElement) timerElement.textContent = '⏳ Refrescando...';
          setTimeout(() => { location.reload(); }, 500);
        }
        timeLeft--;
      }, 1000);
    } else {
      if (timerElement) timerElement.textContent = '⏰ Fuera de horario (11-23:30)';
    }
  };
  setTimeout(checkTimeAndRefresh, 100);

  // Sonido cuando llega un mensaje nuevo
  const playNotificationSound = () => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 800;
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.4);
    } catch (e) {}
  };

  // Detectar nuevos mensajes
  let lastBubbleCount = 0;
  const checkNewMessages = setInterval(() => {
    const bubbleCount = document.querySelectorAll('.bubble').length;
    if (bubbleCount > lastBubbleCount && lastBubbleCount > 0) {
      playNotificationSound();
    }
    lastBubbleCount = bubbleCount;
  }, 1000);
</script>
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
          SET value = EXCLUDED.value,
              updated_at = NOW()
    """, (json.dumps(state),))


# ─────────────────────────── APP ───────────────────────────

conn = get_conn()

st.markdown("## 🫓 Bot Empanadas — Panel")

tab_conv, tab_ped, tab_ctrl = st.tabs(
    ["💬  Conversaciones", "📦  Pedidos", "⚙️  Control del Bot"]
)


# ══════════════════ TAB 1 — CONVERSACIONES ══════════════════
with tab_conv:

    contacts = fetch(conn, """
        SELECT
            phone,
            profile_name,
            MAX(created_at) AS last_msg,
            (SELECT user_message
             FROM conversations c2
             WHERE c2.phone = c.phone
             ORDER BY created_at DESC LIMIT 1) AS preview
        FROM conversations c
        GROUP BY phone, profile_name
        ORDER BY last_msg DESC
        LIMIT 60
    """)

    col_list, col_chat = st.columns([1, 2.8], gap="medium")

    with col_list:
        st.markdown("#### Chats")
        if not contacts:
            st.info("Sin mensajes todavía.")

        for row in contacts:
            phone    = row["phone"]
            name     = row["profile_name"] or phone
            ts       = row["last_msg"]
            time_str = ts.strftime("%d/%m %H:%M") if ts else ""
            preview  = (row["preview"] or "")[:35]

            label = f"👤 {name}\n{phone}\n{time_str}  ·  {preview}…"
            btn_type = "primary" if st.session_state.get("sel_phone") == phone else "secondary"
            if st.button(label, key=f"c_{phone}", use_container_width=True, type=btn_type):
                st.session_state["sel_phone"] = phone
                st.rerun()

    with col_chat:
        sel = st.session_state.get("sel_phone")

        if not sel:
            st.markdown("### 👈 Seleccioná un chat")
        else:
            info = next((r for r in contacts if r["phone"] == sel), None)
            name = (info["profile_name"] or sel) if info else sel

            hdr1, hdr2 = st.columns([4, 1])
            with hdr1:
                st.markdown(f"### {name}")
                st.caption(sel)
            with hdr2:
                if st.button("🗑️ Borrar", key="del_chat"):
                    execute(conn, "DELETE FROM conversations WHERE phone = %s", (sel,))
                    del st.session_state["sel_phone"]
                    st.rerun()

            st.divider()

            msgs = fetch(conn, """
                SELECT user_message, bot_response, created_at
                FROM conversations
                WHERE phone = %s
                ORDER BY created_at ASC
            """, (sel,))

            html = '<div style="max-height:62vh;overflow-y:auto;padding:6px 2px;">'
            for m in msgs:
                u   = (m["user_message"] or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                b   = (m["bot_response"]  or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                ts  = m["created_at"]
                t   = ts.strftime("%d/%m %H:%M") if isinstance(ts, datetime) else str(ts)[:16]

                if u:
                    html += f'<div class="chat-wrap row-user"><div class="bubble bubble-user">{u}<div class="msg-time">{t}</div></div></div>'
                if b:
                    html += f'<div class="chat-wrap row-bot"><div class="bubble bubble-bot">{b}<div class="msg-time">{t}</div></div></div>'
            html += "</div>"

            st.markdown(html, unsafe_allow_html=True)

            # ── Enviar mensaje ──
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

    st.divider()
    if st.button("🔄 Actualizar conversaciones"):
        st.rerun()


# ══════════════════ TAB 2 — PEDIDOS ══════════════════
with tab_ped:

    try:
        stats = fetch(conn, """
            SELECT
                COUNT(*)                                                              AS total,
                COUNT(CASE WHEN created_at > NOW() - INTERVAL '24 hours' THEN 1 END) AS hoy,
                COUNT(CASE WHEN created_at > NOW() - INTERVAL '7 days'   THEN 1 END) AS semana
            FROM pedidos
        """)
    except Exception:
        stats = []

    if stats:
        s = stats[0]
        m1, m2, m3 = st.columns(3)
        m1.metric("Total pedidos", s["total"])
        m2.metric("Últimas 24 hs", s["hoy"])
        m3.metric("Últimos 7 días", s["semana"])
        st.divider()

    try:
        pedidos = fetch(conn, """
            SELECT id, cliente_nombre, cliente_phone, pedido, created_at
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
            ts   = p["created_at"]
            t    = ts.strftime("%d/%m/%Y %H:%M") if isinstance(ts, datetime) else str(ts)[:16]
            name = p["cliente_nombre"] or p["cliente_phone"]
            with st.expander(f"🛒  {name}  —  {t}"):
                st.markdown(f"**Teléfono:** `{p['cliente_phone']}`")
                st.markdown("**Detalle del pedido:**")
                st.text(p["pedido"] or "—")

    if st.button("🔄 Actualizar pedidos"):
        st.rerun()


# ══════════════════ TAB 3 — CONTROL DEL BOT ══════════════════
with tab_ctrl:

    try:
        state = get_bot_state(conn)
    except Exception:
        st.warning("La tabla `bot_state` no existe todavía. Ejecutá `schema.sql` en tu DB de Railway.")
        st.stop()

    paused = state.get("paused", False)
    hf     = state.get("horarioForzado")
    stock  = state.get("stock", {}) or {}

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
    for i, (code, name) in enumerate(PRODUCTOS.items()):
        with cols[i % 4]:
            prev = code in stock
            val  = st.checkbox(f"**{code}** {name}", value=prev, key=f"sk_{code}")
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
