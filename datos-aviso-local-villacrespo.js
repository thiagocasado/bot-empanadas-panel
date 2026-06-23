// "Datos aviso local" — workflow de VILLA CRESPO (rama de la foto/comprobante).
// Atiende solo Villa Crespo, así que el número del local es fijo.

const d = $('Extraer datos').item.json;

return [{
  json: {
    from:        d.from || '',
    profileName: d.profileName || '',
    numeroLocal: '5491130661318',
    local_id:    'villacrespo'
  }
}];
