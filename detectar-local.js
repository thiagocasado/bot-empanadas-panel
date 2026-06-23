// "Detectar local" — JS puro, sin require.
// Mapea el phone_number_id (número que recibió el mensaje) al local, su
// dirección y su alias de transferencia.

const LOCALES = {
  '1157961537398291': { local: 'cabildo',  nombre: 'Kiosco de Empanadas Cabildo',  direccion: 'Cabildo 472',           alias: 'cabildo472',  titular: 'Thiago Agustin Salinas Casado Cerrudo', numeroLocal: '5491124955042' },
  '1132440169956447': { local: 'belgrano', nombre: 'Kiosco de Empanadas Belgrano', direccion: 'Blanco Encalada 2536', alias: 'adrisosa.mp', titular: 'Adriana Beatriz Sosa',                  numeroLocal: '5491130051626' },
  // Villa Crespo (cuando tenga número):
  // 'XXXXXXXXXX':     { local: 'villacrespo', nombre: 'Solo Empanadas Villa Crespo', direccion: 'Aguirre 1011', alias: 'XXXX', titular: 'XXXX', numeroLocal: '549XXXX' },
};

const data = items[0].json;
const pid = String(data.phone_number_id || '');
const cfg = LOCALES[pid] || { local: 'cabildo', nombre: 'Kiosco de Empanadas Cabildo', direccion: 'Cabildo 472', alias: 'cabildo472', titular: 'Thiago Agustin Salinas Casado Cerrudo', numeroLocal: '5491124955042' };

return [{
  json: {
    ...data,
    phone_id:    pid,
    local:       cfg.local,
    nombreLocal: cfg.nombre,
    direccion:   cfg.direccion,
    alias:       cfg.alias,
    titular:     cfg.titular,
    numeroLocal: cfg.numeroLocal
  }
}];
