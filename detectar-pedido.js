// Code node "Detectar pedido" — SIN require, no rompe el task runner.
// Lee la salida del bot; si trae la etiqueta [[PEDIDO]]...[[/PEDIDO]],
// devuelve los datos del pedido. Si no, no devuelve nada (no inserta).

const out = $('Sanitizar output').item.json.output || '';

const m = out.match(/\[\[PEDIDO\]\]([\s\S]*?)\[\[\/PEDIDO\]\]/i);
if (!m) {
  return [];           // no hay pedido -> el nodo siguiente no se ejecuta
}

const parts = m[1].split('||').map(s => s.trim());
const precio = parseInt((parts[2] || '').replace(/[^\d]/g, '') || '0', 10) || 0;

return [{
  json: {
    cliente_phone:  $('Extraer datos').item.json.from || '',
    cliente_nombre: parts[0] || $('Extraer datos').item.json.profileName || '',
    pedido:         parts[1] || '',
    precio:         precio
  }
}];
