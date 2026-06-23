// "Detectar local" — workflow de VILLA CRESPO (app y webhook aparte).
// Este workflow atiende SOLO Villa Crespo, así que siempre devuelve sus datos.

const VC = {
  local:       'villacrespo',
  nombre:      'Solo Empanadas Villa Crespo',
  direccion:   'Aguirre 1011',
  alias:       'andrescasado.mp',
  titular:     'Andres Alejandro Salinas Casado',
  numeroLocal: '5491130661318'
};

const data = items[0].json;
const pid = String(data.phone_number_id || '');

return [{
  json: {
    ...data,
    phone_id:    pid,
    local:       VC.local,
    nombreLocal: VC.nombre,
    direccion:   VC.direccion,
    alias:       VC.alias,
    titular:     VC.titular,
    numeroLocal: VC.numeroLocal
  }
}];
