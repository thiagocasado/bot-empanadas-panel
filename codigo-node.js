const { Client } = require('pg');

const data = items[0].json;
const userData = $('Extraer datos').item.json;
const botData = $('Sanitizar output').item.json;

const PG_PASSWORD = (typeof $vars !== 'undefined' && $vars.PG_PASSWORD) || '';
const PG_HOST = 'postgres.railway.internal';

// ── Texto crudo del bot (puede traer la etiqueta oculta de pedido) ──
const rawOutput = botData.output || '';

// Detectar etiqueta: [[PEDIDO]] nombre || detalle || total [[/PEDIDO]]
const pedidoMatch = rawOutput.match(/\[\[PEDIDO\]\]([\s\S]*?)\[\[\/PEDIDO\]\]/i);
let pedido = null;
if (pedidoMatch) {
  const parts = pedidoMatch[1].split('||').map(s => s.trim());
  // El total "$12.600" -> 12600 (saca todo lo que no sea dígito)
  const precioNum = parseInt((parts[2] || '').replace(/[^\d]/g, '') || '0', 10) || 0;
  pedido = {
    nombre:  parts[0] || userData.profileName || '',
    detalle: parts[1] || '',
    total:   parts[2] || '',
    precio:  precioNum
  };
}

// Texto limpio (sin la etiqueta) para guardar en el chat y para enviar a WhatsApp
const cleanOutput = rawOutput
  .replace(/\[\[PEDIDO\]\][\s\S]*?\[\[\/PEDIDO\]\]/gi, '')
  .trim();

const client = new Client({
  host: PG_HOST,
  port: 5432,
  database: 'railway',
  user: 'postgres',
  password: PG_PASSWORD
});

try {
  await client.connect();

  // Guardar la conversación (con el texto YA limpio, sin la etiqueta)
  await client.query(
    `INSERT INTO conversations (phone, profile_name, user_message, bot_response)
     VALUES ($1, $2, $3, $4)`,
    [
      userData.from || '',
      userData.profileName || '',
      userData.text || userData.body || '',
      cleanOutput
    ]
  );

  // Si el bot cerró un pedido, guardarlo en la tabla pedidos
  if (pedido) {
    await client.query(
      `INSERT INTO pedidos (cliente_phone, cliente_nombre, pedido, precio)
       VALUES ($1, $2, $3, $4)`,
      [
        userData.from || '',
        pedido.nombre,
        pedido.detalle,
        pedido.precio
      ]
    );
  }
} catch (e) {
  // Si falla el guardado, no interrumpe el flujo
} finally {
  await client.end().catch(() => {});
}

// Devolvemos el texto LIMPIO en "output" para que el nodo de envío a
// WhatsApp use este nodo y el cliente nunca vea la etiqueta.
return [{ json: { ...data, output: cleanOutput } }];
