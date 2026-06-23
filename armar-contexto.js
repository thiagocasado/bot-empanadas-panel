// "Armar contexto" — JS puro, sin require.
// Toma el local detectado + el estado del bot (stock/horario del local)
// y arma extraInfo, que el AI Agent ya incluye en el mensaje del usuario.

const data = $('Detectar local').item.json;   // local, nombreLocal, direccion, alias, etc.

let state = {};
try {
  const v = $('Leer estado bot').item.json.value;   // del nodo Postgres
  state = typeof v === 'string' ? JSON.parse(v) : (v || {});
} catch (e) { state = {}; }

const paused = state.paused === true;   // bandera para desviar si está pausado

const partes = [];

// Local: dirección y alias correctos según el número
partes.push('LOCAL: ' + data.nombreLocal + ' — Dirección para retiros: ' + data.direccion);
partes.push('ALIAS para transferencias: ' + data.alias + ' (a nombre de ' + data.titular + ')');

// Horario forzado
if (state.horarioForzado === 'cerrado') partes.push('⚠️ HORARIO FORZADO: CERRADO');
else if (state.horarioForzado === 'abierto') partes.push('⚠️ HORARIO FORZADO: ABIERTO');

// Stock agotado
const agotados = state.stock ? Object.keys(state.stock) : [];
if (agotados.length) partes.push('⚠️ PRODUCTOS AGOTADOS: ' + agotados.join(', '));
else partes.push('✅ STOCK: Todos los productos disponibles');

const extraInfo = partes.join('\n');
return [{ json: { ...data, extraInfo, paused } }];
