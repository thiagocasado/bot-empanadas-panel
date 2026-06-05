CREATE TABLE IF NOT EXISTS conversations (
  id SERIAL PRIMARY KEY,
  phone TEXT NOT NULL,
  profile_name TEXT DEFAULT '',
  user_message TEXT,
  bot_response TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_phone ON conversations (phone);
CREATE INDEX IF NOT EXISTS idx_created_at ON conversations (created_at DESC);
