# Instructivo para armar el Workflow de n8n — Bot de WhatsApp multi-local (Kiosco de Empanadas)

> Documento de especificación para construir/ajustar el workflow en n8n. Incluye contexto, arquitectura, configuración de cada nodo, código de los Code nodes, y los "gotchas" que ya nos hicieron perder tiempo (para no repetirlos).

---

## 1. CONTEXTO DEL PROYECTO

Es un **bot de WhatsApp para tomar pedidos** de un kiosco de empanadas. Funciona así:

- El cliente escribe por WhatsApp → **Meta WhatsApp Cloud API** manda el mensaje a un **webhook de n8n**.
- n8n procesa el mensaje con **IA (Claude, vía un nodo AI Agent)**, que actúa como vendedor (toma pedidos, da precios, horarios, etc.).
- n8n **responde al cliente** por WhatsApp y **guarda todo en PostgreSQL** (conversaciones y pedidos).
- Hay un **panel web (Streamlit, en Railway)** que lee esa base y muestra conversaciones, pedidos, $ facturado, y controles del bot (pausa, horario, stock). **El panel ya está hecho y NO hay que tocarlo.**

### Multi-local
Hay **3 locales** que comparten la **misma base de datos** y el **mismo panel**, pero cada uno tiene su **propio número de WhatsApp**:

| Local | id interno | Dirección | Phone Number ID (Meta) |
|---|---|---|---|
| Kiosco de Empanadas Cabildo | `cabildo` | Cabildo 472 | `1157961537398291` |
| Kiosco de Empanadas Belgrano | `belgrano` | Blanco Encalada 2536 | `1132440169956447` |
| Solo Empanadas Villa Crespo | `villacrespo` | Aguirre 1011 | *(pendiente — irá en otra app de Meta)* |

Los 3 locales tienen **exactamente los mismos** precios, promos, sabores, horarios y costo de envío. **Lo único que cambia es el nombre y la dirección.**

### Estado actual de Meta (IMPORTANTE para la arquitectura)
- **Cabildo y Belgrano están en la MISMA app de Meta.** Meta manda **todos** los mensajes de una app a **un solo webhook**. Por eso, **un solo workflow** atiende a Cabildo y Belgrano, y **detecta de qué número vino el mensaje** (por el `phone_number_id`) para actuar como el local correcto.
- **Villa Crespo irá en otra app de Meta aparte** (otro webhook), así que tendrá su **propio workflow** (una copia de este). No se incluye todavía.

**Objetivo de este instructivo:** dejar UN workflow que atienda Cabildo + Belgrano, ruteando por `phone_number_id`.

---

## 2. BASE DE DATOS (PostgreSQL en Railway)

Ya existe. Tres tablas. **No hay que crearlas**, pero esta es su estructura (para saber qué columnas llenar):

```sql
-- Conversaciones (historial de mensajes)
conversations (
  id SERIAL PK, phone TEXT, profile_name TEXT, user_message TEXT,
  bot_response TEXT, media_b64 TEXT, media_mime TEXT,
  local TEXT DEFAULT 'cabildo', created_at TIMESTAMP DEFAULT NOW()
)

-- Pedidos confirmados
pedidos (
  id SERIAL PK, cliente_phone TEXT, cliente_nombre TEXT, pedido TEXT,
  precio DECIMAL(10,2) DEFAULT 0, local TEXT DEFAULT 'cabildo',
  created_at TIMESTAMP DEFAULT NOW()
)

-- Estado del bot por local (pausa / horario forzado / stock agotado)
bot_state ( key TEXT PK, value JSONB, updated_at TIMESTAMP )
-- key = id del local ('cabildo', 'belgrano', 'villacrespo')
-- value ej: {"paused": false, "horarioForzado": null, "stock": {"JQ": true, "Coca": true}}
```

**Conexión:** se usa una **credencial Postgres nativa de n8n** (host/db/user/pass de Railway). Datos de conexión: usar la URL pública de Railway (host tipo `*.proxy.rlwy.net`, puerto público, db `railway`, user `postgres`). SSL: Disable.

---

## 3. GOTCHAS YA CONOCIDOS (LEER ANTES DE EMPEZAR)

Estos problemas YA nos pasaron. Evitarlos:

1. **El task runner de n8n NO soporta `require('pg')` en Code nodes.** Tira `SyntaxError: Unexpected token '{'`. → **Para leer/escribir en Postgres usar SIEMPRE el nodo Postgres NATIVO**, nunca un Code node con `require('pg')`. Los Code nodes deben ser **JS puro** (sin require).

2. **El body del nodo HTTP "Enviar WhatsApp" NO debe armarse como JSON crudo con la respuesta del bot adentro de comillas.** Si el texto del bot tiene saltos de línea o comillas, rompe el JSON (`The value in the JSON Body field is not valid JSON`). → **Armar el body como un OBJETO con una expresión** (n8n lo serializa bien). Ver sección del nodo Enviar WhatsApp.

3. **Las imágenes en n8n se guardan en disco (binaryDataMode = filesystem).** `items[0].binary.data.data` devuelve `"filesystem-v2"` (una referencia), NO el base64. → Para obtener el base64 real usar `this.helpers.getBinaryDataBuffer(0, 'data')`.

4. **La hora del servidor es UTC.** Para hora de Argentina usar `timeZone: 'America/Argentina/Buenos_Aires'` en las fechas (ya está así en el mensaje al AI Agent).

5. **El `[[PEDIDO]]` que emite el bot NO debe verlo el cliente.** Se borra del texto antes de enviarlo (en el body de Enviar WhatsApp) y antes de guardarlo.

---

## 4. FLUJO DEL WORKFLOW (orden de nodos)

```
Webhook
  → ¿Es verificación? (responde el challenge de Meta / sigue)
  → ¿Tiene mensaje? (filtra pings)
  → Extraer datos (parsea: from, text, profileName, type, phone_number_id)
  → Es multimedia?
       true  → [RAMA IMAGEN] (ver sección 7)
       false → es admin?
                  true  → Responder admin
                  false → Detectar local (NUEVO)
                          → Verificar dirección
                          → Leer estado bot (NUEVO, Postgres)
                          → Armar contexto (NUEVO, Code)
                          → AI Agent (Claude)
                          → Sanitizar output
                          → Enviar WhatsApp (phone_number_id DINÁMICO)
                          → Insert conversación (Postgres, con local)
                          → Detectar pedido (Code)
                          → Guardar pedido (Postgres, con local)
                          → Responder OK
```

Los nodos marcados **(NUEVO)** son los que hay que agregar para el multi-local + stock.

---

## 5. NODOS CLAVE DEL MULTI-LOCAL

### 5.1 Nodo "Extraer datos" — debe extraer el `phone_number_id`
El nodo que parsea el webhook tiene que sacar, además de `from`/`text`/`profileName`/`type`, el **`phone_number_id`** (el número que recibió el mensaje). En el payload de WhatsApp está en:
```
entry[0].changes[0].value.metadata.phone_number_id
```
Dejarlo disponible en el json (ej: `phone_number_id`).

### 5.2 Nodo "Detectar local" (Code, JS puro) — NUEVO
Mapea el `phone_number_id` al local y su dirección.

```javascript
// "Detectar local" — JS puro, sin require
const LOCALES = {
  '1157961537398291': { local: 'cabildo',  nombre: 'Kiosco de Empanadas Cabildo',  direccion: 'Cabildo 472' },
  '1132440169956447': { local: 'belgrano', nombre: 'Kiosco de Empanadas Belgrano', direccion: 'Blanco Encalada 2536' },
  // Villa Crespo se agrega cuando tenga su número:
  // 'XXXXXXXXXX':     { local: 'villacrespo', nombre: 'Solo Empanadas Villa Crespo', direccion: 'Aguirre 1011' },
};

const data = items[0].json;
const pid = String(data.phone_number_id || '');
const cfg = LOCALES[pid] || { local: 'cabildo', nombre: 'Kiosco de Empanadas', direccion: 'Cabildo 472' };

return [{ json: { ...data, phone_id: pid, local: cfg.local, nombre: cfg.nombre, direccion: cfg.direccion } }];
```
*(Si "Extraer datos" no expone `phone_number_id`, leerlo dentro de este nodo desde el nodo Webhook: `$('Webhook').item.json.body.entry[0].changes[0].value.metadata.phone_number_id`.)*

### 5.3 Nodo "Enviar WhatsApp" — phone_number_id DINÁMICO + body como objeto
- **Method:** POST
- **URL:** `https://graph.facebook.com/v21.0/{{ $json.phone_id }}/messages`
  (DINÁMICO: responde desde el mismo número que recibió el mensaje. NO hardcodear el de Cabildo.)
- **Headers:** `Authorization` = `Bearer <WHATSAPP_TOKEN>`
- **Body (modo Expression, como objeto — NO JSON crudo):**
```
{{ ({ messaging_product: "whatsapp", to: $json.from, type: "text", text: { body: ($('Sanitizar output').item.json.output || "").replace(/\[\[PEDIDO\]\][\s\S]*?\[\[\/PEDIDO\]\]/g, "").trim() } }) }}
```
El `.replace(...)` borra la etiqueta `[[PEDIDO]]` para que el cliente no la vea.

### 5.4 Inserts en Postgres — agregar columna `local`
En los 3 nodos Postgres que insertan (conversación, pedido, imagen), mapear la columna **`local`** con el valor `{{ $json.local }}`.

---

## 6. CONVERSACIÓN + PEDIDO (Postgres nativo)

### 6.1 "Insert conversación" (Postgres, operación Insert, tabla `conversations`)
Columnas (borrar id y created_at, los pone la base):
- `phone` → `{{ $('Extraer datos').item.json.from }}`
- `profile_name` → `{{ $('Extraer datos').item.json.profileName }}`
- `user_message` → `{{ $('Extraer datos').item.json.text || $('Extraer datos').item.json.body || '' }}`
- `bot_response` → `{{ ($('Sanitizar output').item.json.output || '').replace(/\[\[PEDIDO\]\][\s\S]*?\[\[\/PEDIDO\]\]/g,'').trim() }}`
- `local` → `{{ $json.local }}`

### 6.2 "Detectar pedido" (Code, JS puro) — parsea la etiqueta del bot
El bot, al cerrar un pedido, emite al final: `[[PEDIDO]] nombre || detalle || total [[/PEDIDO]]`.

```javascript
// "Detectar pedido" — JS puro. Si no hay etiqueta, no devuelve nada (no inserta).
const out = $('Sanitizar output').item.json.output || '';
const m = out.match(/\[\[PEDIDO\]\]([\s\S]*?)\[\[\/PEDIDO\]\]/i);
if (!m) return [];

const parts = m[1].split('||').map(s => s.trim());
const precio = parseInt((parts[2] || '').replace(/[^\d]/g, '') || '0', 10) || 0;

return [{
  json: {
    cliente_phone:  $('Extraer datos').item.json.from || '',
    cliente_nombre: parts[0] || $('Extraer datos').item.json.profileName || '',
    pedido:         parts[1] || '',
    precio:         precio,
    local:          $('Detectar local').item.json.local || 'cabildo'
  }
}];
```

### 6.3 "Guardar pedido" (Postgres, Insert, tabla `pedidos`)
Columnas (borrar id y created_at):
- `cliente_phone` → `{{ $json.cliente_phone }}`
- `cliente_nombre` → `{{ $json.cliente_nombre }}`
- `pedido` → `{{ $json.pedido }}`
- `precio` → `{{ $json.precio }}`
- `local` → `{{ $json.local }}`

---

## 7. RAMA IMAGEN (cliente manda foto, ej. captura de transferencia)
Cuando "Es multimedia?" = true, en esa rama:

1. **"Obtener URL imagen"** (HTTP GET): `https://graph.facebook.com/v21.0/{{ <media_id> }}` con header `Authorization: Bearer <TOKEN>`. El media_id está en `entry[0].changes[0].value.messages[0].image.id`. Devuelve un JSON con `url`.
2. **"Bajar imagen"** (HTTP GET): URL = `{{ $json.url }}`, header `Authorization: Bearer <TOKEN>`, **Response Format: File**. (Si da 401: Authentication = None, y probar desactivar "Follow Redirects".)
3. **"Imagen a base64"** (Code, JS puro):
```javascript
const buffer = await this.helpers.getBinaryDataBuffer(0, 'data');
const mime = items[0].binary.data.mimeType || 'image/jpeg';
return [{ json: { media_b64: buffer.toString('base64'), media_mime: mime } }];
```
4. **"Guardar Imagen"** (Postgres, Insert, tabla `conversations`): columnas `phone`, `profile_name`, `user_message` = `📷 Foto`, `media_b64` = `{{ $json.media_b64 }}`, `media_mime` = `{{ $json.media_mime }}`, `local` = `{{ $('Detectar local').item.json.local }}`.

*(Nota: en la rama imagen también conviene pasar por "Detectar local" para tener el `local`.)*

---

## 8. STOCK / HORARIO / PAUSA (controles del panel → bot)

El panel guarda en `bot_state` (por local) el stock agotado, el horario forzado y la pausa. Para que el bot lo respete, hay que **leer ese estado y metérselo en el mensaje** vía el campo `extraInfo` (que el AI Agent ya incluye en el mensaje del usuario).

### 8.1 "Leer estado bot" (Postgres, Execute Query) — NUEVO
Query: `SELECT value FROM bot_state WHERE key = '{{ $json.local }}'`
(lee el estado del local que corresponde).

### 8.2 "Armar contexto" (Code, JS puro) — NUEVO
Arma `extraInfo` con el nombre/dirección del local + el stock + el horario forzado.

```javascript
// "Armar contexto" — JS puro
const data = $('Detectar local').item.json;   // trae local, nombre, direccion, from, text, etc.

let state = {};
try {
  const v = $('Leer estado bot').item.json.value;
  state = typeof v === 'string' ? JSON.parse(v) : (v || {});
} catch (e) { state = {}; }

const partes = [];
// Local (nombre + dirección) para que el bot use la dirección correcta
partes.push('LOCAL: ' + data.nombre + ' — Dirección para retiros: ' + data.direccion);

// Horario forzado
if (state.horarioForzado === 'cerrado') partes.push('⚠️ HORARIO FORZADO: CERRADO');
else if (state.horarioForzado === 'abierto') partes.push('⚠️ HORARIO FORZADO: ABIERTO');

// Stock agotado
const agotados = state.stock ? Object.keys(state.stock) : [];
if (agotados.length) partes.push('⚠️ PRODUCTOS AGOTADOS: ' + agotados.join(', '));
else partes.push('✅ STOCK: Todos los productos disponibles');

const extraInfo = partes.join('\n');
return [{ json: { ...data, extraInfo } }];
```

### 8.3 El AI Agent ya usa `extraInfo`
El mensaje del usuario que recibe el AI Agent ya lo incluye (esta expresión ya existe en el workflow):
```
{{ '[' + new Date().toLocaleDateString('es-AR', { weekday: 'long', timeZone: 'America/Argentina/Buenos_Aires' }).toUpperCase() + ' ' + new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/Argentina/Buenos_Aires' }) + '] ' + ($json.extraInfo ? $json.extraInfo + '\n\n' : '') + ($json.body || $json.text || 'El cliente envió un ' + $json.type + ' - comprobante') }}
```

### 8.4 Pausa del bot (opcional)
Si `state.paused === true`, lo ideal es **no responder** (cortar el flujo con un IF antes del AI Agent). Si no se implementa, el botón "Pausar" del panel no hace efecto.

---

## 9. EL PROMPT DEL BOT (system message del AI Agent)

Como los 3 locales son iguales salvo nombre/dirección, y la dirección ahora llega por `extraInfo` (línea "LOCAL: ..."), el system prompt debe usar **esa dirección del contexto**, no una fija. Cambios respecto al prompt original:
- Donde dice "retirar en Cabildo 472" → "retirar en la dirección indicada en el contexto del mensaje (línea LOCAL)".
- El nombre/dirección del local salen del `extraInfo`.

El resto del prompt (precios, promos, códigos de empanada, delivery $1.000, formato de la etiqueta `[[PEDIDO]]`, etc.) es **idéntico para los 3**. El prompt completo está en el archivo `prompt-bot.txt` del proyecto.

**Reglas clave del prompt que el bot DEBE cumplir:**
- Al confirmar un pedido, terminar con: `[[PEDIDO]] nombre || detalle || total final $ [[/PEDIDO]]` (en una línea aparte, el cliente no la ve).
- El total es obligatorio y con número. Si es delivery, sumar $1.000 de envío al total.

---

## 10. PENDIENTES / NOTAS
- **Villa Crespo:** va en otra app de Meta (otro webhook) → será una copia de este workflow con su `phone_number_id` y su entrada en el mapa `LOCALES` de "Detectar local". (Requiere verificación de negocio en Meta para sumar el 3er número, que es gratis.)
- **Token de WhatsApp:** el actual es temporal (vence cada 24 hs). Para producción generar un **token permanente** (System User en Meta Business).
- **Aviso de "NUEVO PEDIDO" al dueño:** si se quiere notificar a un número al cerrar un pedido, agregar después de "Guardar pedido" un HTTP Request a WhatsApp con `to` = número del dueño (ojo: WhatsApp solo permite mensaje libre dentro de las 24 hs de la última vez que ese número escribió).
- **Credenciales/secretos** (token de WhatsApp, password de Postgres): NO están en este documento; usar los del entorno.
