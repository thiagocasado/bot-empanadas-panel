// Code node "Imagen a base64"
// Lee el binario REAL (funciona aunque n8n guarde en disco, modo filesystem)
// y lo convierte a base64 para guardarlo en la base.

const buffer = await this.helpers.getBinaryDataBuffer(0, 'data');
const mime = items[0].binary.data.mimeType || 'image/jpeg';

return [{
  json: {
    media_b64: buffer.toString('base64'),
    media_mime: mime
  }
}];
