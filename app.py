import streamlit as st
import psycopg2
import os
from datetime import datetime

DB_URL = os.environ.get("DATABASE_URL", "")

def get_conn():
    if not DB_URL:
        st.error("DATABASE_URL no configurada")
        return None
    return psycopg2.connect(DB_URL)

def get_contacts(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT phone, profile_name, MAX(created_at) as last_msg,
               (SELECT bot_response FROM conversations c2
                WHERE c2.phone = c.phone ORDER BY created_at DESC LIMIT 1) as last_response
        FROM conversations c
        GROUP BY phone, profile_name
        ORDER BY last_msg DESC
    """)
    return cur.fetchall()

def get_messages(conn, phone):
    cur = conn.cursor()
    cur.execute("""
        SELECT user_message, bot_response, created_at
        FROM conversations
        WHERE phone = %s
        ORDER BY created_at ASC
    """, (phone,))
    return cur.fetchall()

st.set_page_config(page_title="Bot Empanadas - Panel", layout="wide")

st.markdown("""
<style>
    .chat-container { max-width: 700px; margin: 0 auto; }
    .msg-user { background: #e3f2fd; padding: 10px 15px; border-radius: 15px 15px 15px 3px;
                margin: 8px 0; max-width: 80%; }
    .msg-bot { background: #f0f0f0; padding: 10px 15px; border-radius: 15px 15px 3px 15px;
               margin: 8px 0; max-width: 80%; margin-left: auto; }
    .msg-time { font-size: 0.7em; color: #999; margin-top: 4px; }
    .contact-card { padding: 8px 12px; border-radius: 8px; margin: 2px 0; cursor: pointer; }
    .contact-card:hover { background: #e8e8e8; }
    .contact-active { background: #d0d0d0; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

conn = get_conn()
if conn is None:
    st.stop()

contacts = get_contacts(conn)

st.title("Bot Empanadas")

col1, col2 = st.columns([1, 2.5])

with col1:
    st.markdown("### Contactos")
    st.markdown("---")
    phone_map = {}
    for phone, name, last_msg, last_resp in contacts:
        label = f"{name or phone[:8]}..."
        if st.button(label, key=phone, use_container_width=True):
            st.session_state["selected"] = phone
        phone_map[phone] = (name, last_msg)

selected = st.session_state.get("selected", contacts[0][0] if contacts else None)

with col2:
    if not selected:
        st.info("Seleccioná un contacto")
        st.stop()

    name, _ = phone_map.get(selected, (selected, None))
    st.markdown(f"### {name or selected}")

    messages = get_messages(conn, selected)

    with st.container():
        for user_msg, bot_resp, ts in messages:
            t = ts.strftime("%d/%m %H:%M") if isinstance(ts, datetime) else str(ts)[:16]
            if user_msg:
                st.markdown(f'<div class="chat-container"><div class="msg-user">'
                           f'{user_msg}<div class="msg-time">{t}</div></div></div>',
                           unsafe_allow_html=True)
            if bot_resp:
                st.markdown(f'<div class="chat-container"><div class="msg-bot">'
                           f'{bot_resp}<div class="msg-time">{t}</div></div></div>',
                           unsafe_allow_html=True)

    if st.button("🗑️ Eliminar conversación"):
        cur = conn.cursor()
        cur.execute("DELETE FROM conversations WHERE phone = %s", (selected,))
        conn.commit()
        st.rerun()

conn.close()
