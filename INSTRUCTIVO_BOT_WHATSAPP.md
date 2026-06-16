# 🫓 Instructivo: Bot de WhatsApp + Panel Streamlit

## Resumen del Proyecto

Bot de WhatsApp automatizado que:
- Recibe mensajes por WhatsApp Business API
- Procesa con Claude IA (Haiku o modelo mejor)
- Guarda conversaciones en PostgreSQL
- Panel web Streamlit para:
  - Ver conversaciones en tiempo real
  - Registrar pedidos
  - Controlar estado del bot (pausa, horarios, stock)

---

## 1. ARQUITECTURA

```
WhatsApp → n8n workflow → Claude IA → PostgreSQL
                                    ↓
                            Streamlit Panel (Railway)
```

### Flujo de datos:
1. **WhatsApp → n8n**: webhook recibe mensaje
2. **n8n → Claude**: envía a IA para procesar
3. **Claude → n8n**: retorna respuesta
4. **n8n → PostgreSQL**: guarda conversación
5. **n8n → WhatsApp**: envía respuesta al usuario
6. **Streamlit lee DB**: muestra conversaciones en tiempo real

---

## 2. SETUP INICIAL

### 2.1 WhatsApp Business Account
- Crear app en Meta Developers: https://developers.facebook.com
- Obtener:
  - **WHATSAPP_TOKEN**: Token de acceso
  - **WHATSAPP_PHONE_ID**: ID del número de teléfono
  - **Webhook URL**: Será la URL de n8n (ej: https://n8n.railway.app/webhook/whatsapp)

### 2.2 Railway Setup
- Crear proyecto en https://railway.app
- Crear servicio PostgreSQL
- Crear servicio n8n
- Crear servicio Streamlit
- Obtener variables de entorno:
  - `DATABASE_URL`: PostgreSQL connection string
  - `WHATSAPP_TOKEN`: Desde Meta
  - `WHATSAPP_PHONE_ID`: Desde Meta

### 2.3 Anthropic API
- Obtener API key en https://console.anthropic.com
- Modelo recomendado: `claude-opus-4-6` o `claude-sonnet-4-6` (mejor que Haiku para IA conversacional)

---

## 3. ESTRUCTURA DE BASE DE DATOS

### Crear el schema.sql:

```sql
-- Conversaciones (historial completo)
CREATE TABLE IF NOT EXISTS conversations (
  id           SERIAL PRIMARY KEY,
  phone        TEXT NOT NULL,
  profile_name TEXT DEFAULT '',
  user_message TEXT,
  bot_response TEXT,
  precio       DECIMAL(10,2),
  created_at   TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_phone ON conversations (phone);
CREATE INDEX IF NOT EXISTS idx_conv_created_at ON conversations (created_at DESC);

-- Pedidos confirmados
CREATE TABLE IF NOT EXISTS pedidos (
  id              SERIAL PRIMARY KEY,
  cliente_phone   TEXT NOT NULL,
  cliente_nombre  TEXT DEFAULT '',
  pedido          TEXT,
  precio          DECIMAL(10,2) DEFAULT 0,
  created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ped_phone ON pedidos (cliente_phone);
CREATE INDEX IF NOT EXISTS idx_ped_created_at ON pedidos (created_at DESC);

-- Estado global del bot
CREATE TABLE IF NOT EXISTS bot_state (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO bot_state (key, value)
VALUES ('global', '{"paused": false, "horarioForzado": null, "stock": {}}')
ON CONFLICT (key) DO NOTHING;
```

Ejecutar en Railway → PostgreSQL → Query editor.

---

## 4. N8N WORKFLOW

### Estructura del workflow (20+ nodes):

1. **Webhook**: Recibe mensajes de WhatsApp
2. **Extraer datos**: Parse del JSON de WhatsApp
3. **AI Agent (Claude)**: Procesa mensaje con IA
   - Prompt: Roleplaying como vendedor de empanadas
   - Toma pedidos, da info de horarios, stock
4. **Guardar conversación**: INSERT en tabla conversations
5. **Verificar si es pedido**: Regex/lógica para detectar confirmación
6. **Guardar pedido**: INSERT en tabla pedidos (si aplica)
7. **Respond to Webhook**: Envía respuesta a WhatsApp

### Nodos críticos:

**AI Agent (Claude)**:
```
Url: https://api.anthropic.com/v1/messages
Headers: Authorization: Bearer {{env.ANTHROPIC_API_KEY}}
Body (JSON):
{
  "model": "claude-opus-4-6",
  "max_tokens": 500,
  "messages": [
    {
      "role": "user",
      "content": "{{$node['Extraer datos'].json.text}}"
    }
  ]
}
```

**Guardar conversación**:
```javascript
const payload = {
  host: 'postgres.railway.internal',
  user: 'postgres',
  password: '{{env.PG_PASSWORD}}',
  database: 'railway',
  ssl: false,
  query: `
    INSERT INTO conversations (phone, profile_name, user_message, bot_response, created_at)
    VALUES ('{{$node['Extraer datos'].json.phone}}', '{{$node['Extraer datos'].json.name}}', 
            '{{$node['Extraer datos'].json.text}}', '{{$node['Claude'].json.content[0].text}}', NOW())
  `
};
```

---

## 5. PANEL STREAMLIT

### Estructura app.py:

#### 5.1 Configuración inicial
```python
import streamlit as st
import psycopg2
import psycopg2.extras
from datetime import datetime, time as dt_time
import time

st.set_page_config(page_title="Bot Empanadas", layout="wide", page_icon="🫓")

DB_URL = os.environ.get("DATABASE_URL")
```

#### 5.2 Auto-refresh cada 60 segundos (11-23:30)
```python
now = datetime.now()
hour = now.hour
minute = now.minute
in_schedule = (11 <= hour <= 23 and not (hour == 23 and minute > 30))

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if in_schedule:
    elapsed = time.time() - st.session_state.last_refresh
    if elapsed > 60:
        st.session_state.last_refresh = time.time()
        st.rerun()
    
    remaining = int(60 - elapsed)
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"🔄 Auto-refresh activo")
    with col2:
        st.metric("Próximo", f"{remaining}s", label_visibility="collapsed")
```

#### 5.3 Estilos CSS
```python
st.markdown("""
<style>
  .bubble-user  { background:#dcf8c6; color:#1a1a1a; border-radius:16px 16px 16px 4px; font-weight:500; }
  .bubble-bot   { background:#2d2d2d; color:#ffffff; border-radius:16px 16px 4px 16px; float:right; }
  .row-user     { text-align:left;  overflow:hidden; margin:5px 0; }
  .row-bot      { text-align:right; overflow:hidden; margin:5px 0; }
</style>

<script>
  // Sonido cuando llega mensaje nuevo
  let prevBubbleCount = document.querySelectorAll('.bubble').length;
  setInterval(() => {
    const currentBubbleCount = document.querySelectorAll('.bubble').length;
    if (currentBubbleCount > prevBubbleCount) {
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
      prevBubbleCount = currentBubbleCount;
    }
  }, 500);
</script>
""", unsafe_allow_html=True)
```

#### 5.4 Tab 1: Conversaciones
```python
tab_conv, tab_ped, tab_ctrl = st.tabs(["💬 Conversaciones", "📦 Pedidos", "⚙️ Control"])

with tab_conv:
    # Query con contador de no leídos
    contacts = fetch(conn, """
        SELECT
            phone, profile_name, MAX(created_at) AS last_msg,
            (SELECT user_message FROM conversations c2 WHERE c2.phone = c.phone ORDER BY created_at DESC LIMIT 1) AS preview,
            (SELECT COUNT(*) FROM conversations c3 WHERE c3.phone = c.phone AND c3.bot_response IS NOT NULL AND c3.created_at > NOW() - INTERVAL '24 hours') AS unread_count
        FROM conversations c
        GROUP BY phone, profile_name
        ORDER BY last_msg DESC
        LIMIT 60
    """)
    
    col_list, col_chat = st.columns([1, 2.8], gap="medium")
    
    with col_list:
        for row in contacts:
            unread = row["unread_count"] or 0
            unread_badge = f" 🔴 {unread}" if unread > 0 else ""
            label = f"👤 {row['profile_name']}{unread_badge}\n{row['phone']}"
            if st.button(label, key=f"c_{row['phone']}", use_container_width=True):
                st.session_state["sel_phone"] = row['phone']
                st.rerun()
    
    with col_chat:
        # Mostrar conversación seleccionada
        # Renderizar bubbles con HTML
```

#### 5.5 Tab 2: Pedidos
```python
with tab_ped:
    # Métricas
    stats = fetch(conn, """
        SELECT
            COUNT(*) AS total,
            SUM(precio) AS total_vendido,
            COUNT(CASE WHEN created_at > NOW() - INTERVAL '24 hours' THEN 1 END) AS hoy
        FROM pedidos
    """)
    
    if stats and stats[0]['total_vendido']:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total pedidos", stats[0]['total'])
        m2.metric("Total vendido", f"${stats[0]['total_vendido']:.2f}")
        m3.metric("Hoy", stats[0]['hoy'])
    
    # Tabla de pedidos
    pedidos = fetch(conn, """
        SELECT id, cliente_nombre, cliente_phone, pedido, precio, created_at
        FROM pedidos
        ORDER BY created_at DESC
        LIMIT 100
    """)
```

#### 5.6 Tab 3: Control del Bot
```python
with tab_ctrl:
    # Botones para pausar/activar bot
    # Botones para forzar horarios
    # Checkboxes para stock agotado
    
    state = get_bot_state(conn)  # Lee de bot_state table
    
    paused = state.get("paused", False)
    if st.button("✅ Activar bot", disabled=not paused):
        state["paused"] = False
        save_bot_state(conn, state)
        st.rerun()
    
    if st.button("⏸️ Pausar bot", disabled=paused):
        state["paused"] = True
        save_bot_state(conn, state)
        st.rerun()
```

---

## 6. DEPLOYMENT EN RAILWAY

### 6.1 GitHub Repository
```bash
cd C:\tu-proyecto
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/tu-usuario/tu-repo.git
git push -u origin main
```

### 6.2 Railway Configuration
1. Conectar repo GitHub a Railway
2. Crear servicio: **Streamlit**
   - Comando: `streamlit run app.py`
   - Puerto: 8501
   - Agregar variables de entorno:
     - `DATABASE_URL`: PostgreSQL URL
     - `WHATSAPP_TOKEN`: Token de WhatsApp
     - `WHATSAPP_PHONE_ID`: ID del teléfono
     - `ANTHROPIC_API_KEY`: API key de Claude

3. Deploy automático al hacer push a main

### 6.3 requirements.txt
```
streamlit==1.28.0
psycopg2-binary==2.9.9
requests==2.31.0
```

---

## 7. FLUJO COMPLETO

### Paso a paso:
1. **Usuario manda mensaje** por WhatsApp
2. **Meta webhook** envía a n8n
3. **n8n recibe**, extrae phone, nombre, texto
4. **n8n llamaClause IA** con el mensaje
5. **Claude responde** (vende, cierra pedido, etc)
6. **n8n guarda** en DB conversación
7. **n8n verifica** si es pedido (regex)
8. **Si es pedido**: inserta en tabla pedidos
9. **n8n responde** a WhatsApp
10. **Streamlit recibe** via session_state/rerun cada 60 seg
11. **Panel muestra** conversación, pedidos, total vendido

---

## 8. MEJORAS FUTURAS

1. **Usar modelo mejor**: Cambiar `claude-haiku-4-5-20251001` por `claude-opus-4-6`
   - Mejor comprensión de contexto
   - Mejor procesamiento de números (precios)
   - Mejor respuestas conversacionales

2. **Persistencia de sesión**: Guardar conversación completa en session_state para contexto

3. **Análisis de pedidos**:
   - Detectar ítems (qué empanadas) y cantidad automáticamente
   - Calcular precio total automáticamente
   - Enviar invoice a cliente

4. **Notificaciones**:
   - Email al admin cuando hay pedido nuevo
   - SMS de confirmación

5. **Analytics**:
   - Gráficos de ventas por hora/día
   - Productos más vendidos
   - Clientes frecuentes

6. **Multi-idioma**: Agregar soporte para español/inglés

---

## 9. TROUBLESHOOTING

### "Auto-refresh no funciona"
- Usar `st.rerun()` de Python, no JavaScript
- Guardar timestamp en `st.session_state`
- Validar que session_state persiste entre reruns

### "No se escucha sonido"
- JavaScript Web Audio API es nativo, no requiere librería
- Detectar cambios en `.bubble` elements
- Triggear sonido cada 500ms

### "Pedidos no se guardan"
- Verificar que n8n inserta correctamente en tabla
- Usar `ON CONFLICT DO NOTHING` en schema para evitar duplicados
- Agregar `precio` a INSERT statement

### "Hora de servidor diferente"
- PostgreSQL usa `NOW()` del servidor (UTC probablemente)
- Ajustar en queries con `AT TIME ZONE 'America/Argentina/Buenos_Aires'`

---

## 10. VARIABLES DE ENTORNO

Guardar en Railway como "variables":

```
DATABASE_URL=postgresql://user:pass@host:port/dbname
WHATSAPP_TOKEN=EAAbCDEFG...
WHATSAPP_PHONE_ID=1234567890123456
ANTHROPIC_API_KEY=sk-ant-...
PG_PASSWORD=tu_password_segura
```

---

## 11. COMANDOS RÁPIDOS

```bash
# Clonar repo
git clone https://github.com/tu-usuario/tu-repo.git
cd tu-repo

# Crear venv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Correr Streamlit localmente
export DATABASE_URL="postgresql://..."
streamlit run app.py

# Hacer cambios y push
git add .
git commit -m "mensaje"
git push origin main

# Railway redeploy (automático) o manual desde https://railway.app
```

---

**Última actualización**: Junio 2026
**Próxima iteración**: Cambiar a Claude Opus para mejor IA, agregar análisis de pedidos automático.
