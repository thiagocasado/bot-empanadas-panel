const { Client } = require('pg');

const data = items[0].json;
const userData = $('Extraer datos').item.json;
const botData = $('Sanitizar output').item.json;

const PG_PASSWORD = (typeof $vars !== 'undefined' && $vars.PG_PASSWORD) || '';
const PG_HOST = 'postgres.railway.internal';

const client = new Client({
  host: PG_HOST,
  port: 5432,
  database: 'railway',
  user: 'postgres',
  password: PG_PASSWORD
});

try {
  await client.connect();
  await client.query(
    `INSERT INTO conversations (phone, profile_name, user_message, bot_response)
     VALUES ($1, $2, $3, $4)`,
    [
      userData.from || '',
      userData.profileName || '',
      userData.text || userData.body || '',
      botData.output || ''
    ]
  );
} catch(e) {
  // Si falla el guardado, no interrumpe el flujo
} finally {
  await client.end().catch(() => {});
}

return [{ json: data }];
