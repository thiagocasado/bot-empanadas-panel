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

CREATE INDEX IF NOT EXISTS idx_conv_phone      ON conversations (phone);
CREATE INDEX IF NOT EXISTS idx_conv_created_at ON conversations (created_at DESC);

-- Pedidos confirmados (insertados por el bot al cerrar un pedido)
CREATE TABLE IF NOT EXISTS pedidos (
  id              SERIAL PRIMARY KEY,
  cliente_phone   TEXT NOT NULL,
  cliente_nombre  TEXT DEFAULT '',
  pedido          TEXT,
  created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ped_phone      ON pedidos (cliente_phone);
CREATE INDEX IF NOT EXISTS idx_ped_created_at ON pedidos (created_at DESC);

-- Estado global del bot (pausa, stock agotado, horario forzado)
CREATE TABLE IF NOT EXISTS bot_state (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Fila inicial (si no existe)
INSERT INTO bot_state (key, value)
VALUES ('global', '{"paused": false, "horarioForzado": null, "stock": {}}')
ON CONFLICT (key) DO NOTHING;
