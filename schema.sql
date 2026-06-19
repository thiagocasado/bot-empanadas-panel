-- ============================================================
-- Bot Empanadas — Schema completo
-- Correr este archivo una vez en la DB de Railway
-- ============================================================

-- Conversaciones (historial completo)
CREATE TABLE IF NOT EXISTS conversations (
  id           SERIAL PRIMARY KEY,
  phone        TEXT NOT NULL,
  profile_name TEXT DEFAULT '',
  user_message TEXT,
  bot_response TEXT,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- Para guardar fotos que mandan los clientes (capturas de transferencia)
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS media_b64  TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS media_mime TEXT;

-- Multi-local: cada conversación pertenece a un local
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS local TEXT DEFAULT 'cabildo';

CREATE INDEX IF NOT EXISTS idx_conv_phone      ON conversations (phone);
CREATE INDEX IF NOT EXISTS idx_conv_created_at ON conversations (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_local      ON conversations (local);

-- Pedidos confirmados (insertados por el bot al cerrar un pedido)
CREATE TABLE IF NOT EXISTS pedidos (
  id              SERIAL PRIMARY KEY,
  cliente_phone   TEXT NOT NULL,
  cliente_nombre  TEXT DEFAULT '',
  pedido          TEXT,
  precio          DECIMAL(10,2) DEFAULT 0,
  created_at      TIMESTAMP DEFAULT NOW()
);

-- Si la tabla ya existía sin la columna precio, la agrega
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS precio DECIMAL(10,2) DEFAULT 0;
-- Multi-local
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS local TEXT DEFAULT 'cabildo';

CREATE INDEX IF NOT EXISTS idx_ped_phone      ON pedidos (cliente_phone);
CREATE INDEX IF NOT EXISTS idx_ped_created_at ON pedidos (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ped_local      ON pedidos (local);

-- Estado global del bot (pausa, stock agotado, horario forzado)
CREATE TABLE IF NOT EXISTS bot_state (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Estado del bot por local (una fila por cada uno)
INSERT INTO bot_state (key, value) VALUES
  ('cabildo',     '{"paused": false, "horarioForzado": null, "stock": {}}'),
  ('belgrano',    '{"paused": false, "horarioForzado": null, "stock": {}}'),
  ('villacrespo', '{"paused": false, "horarioForzado": null, "stock": {}}')
ON CONFLICT (key) DO NOTHING;
