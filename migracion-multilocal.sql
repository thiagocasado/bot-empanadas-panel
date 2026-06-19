-- ============================================================
-- Migración multi-local — correr UNA vez en Railway → Postgres → Query
-- Asigna todos los datos actuales al local 'cabildo' y crea los otros 2.
-- ============================================================

-- 1) Columna 'local' en las tablas (los datos actuales quedan como 'cabildo')
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS local TEXT DEFAULT 'cabildo';
ALTER TABLE pedidos       ADD COLUMN IF NOT EXISTS local TEXT DEFAULT 'cabildo';

UPDATE conversations SET local = 'cabildo' WHERE local IS NULL;
UPDATE pedidos       SET local = 'cabildo' WHERE local IS NULL;

-- 2) Estado del bot por local (sin SELECT, porque el editor de Railway
--    le agrega un LIMIT automático si detecta un SELECT)
INSERT INTO bot_state (key, value) VALUES
  ('cabildo',     '{"paused": false, "horarioForzado": null, "stock": {}}'),
  ('belgrano',    '{"paused": false, "horarioForzado": null, "stock": {}}'),
  ('villacrespo', '{"paused": false, "horarioForzado": null, "stock": {}}')
ON CONFLICT (key) DO NOTHING;

-- 4) Índices para que filtrar por local sea rápido
CREATE INDEX IF NOT EXISTS idx_conv_local ON conversations (local);
CREATE INDEX IF NOT EXISTS idx_ped_local  ON pedidos (local);
