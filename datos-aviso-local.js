// "Datos aviso local" — JS puro. Va en la rama del comprobante (foto).
// Según el número del bot que recibió, define a qué número del local avisar.

const LOCALES = {
  '1157961537398291': { numeroLocal: '5491124955042', local: 'cabildo' },   // Cabildo
  '1132440169956447': { numeroLocal: '5491130051626', local: 'belgrano' },  // Belgrano
  // Villa Crespo: 'XXXX': { numeroLocal: '549XXXX', local: 'villacrespo' },
};

const d = $('Extraer datos').item.json;
const pid = String(d.phone_number_id || '');
const cfg = LOCALES[pid] || { numeroLocal: '5491124955042', local: 'cabildo' };

return [{
  json: {
    from:        d.from || '',
    profileName: d.profileName || '',
    numeroLocal: cfg.numeroLocal,
    local_id:    cfg.local
  }
}];
