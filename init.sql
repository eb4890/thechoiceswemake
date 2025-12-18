-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Settings table
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Categories
CREATE TABLE IF NOT EXISTS categories (
  name TEXT PRIMARY KEY,
  description TEXT
);

INSERT INTO categories (name, description) VALUES
('Choices', 'Direct moral dilemmas requiring decisive action'),
('Explorations', 'Open-ended speculative futures and thought experiments'),
ON CONFLICT (name) DO NOTHING;

-- Scenarios (live)
CREATE TABLE IF NOT EXISTS scenarios (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  prompt TEXT NOT NULL,
  author TEXT,
  category TEXT DEFAULT 'Uncategorized',
  submitted_at TIMESTAMP DEFAULT NOW(),
  plays INTEGER DEFAULT 0,
  release_date TIMESTAMP  -- NULL = immediate
);

-- Pending submissions
CREATE TABLE IF NOT EXISTS pending_scenarios (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  prompt TEXT NOT NULL,
  author TEXT,
  category TEXT DEFAULT 'Uncategorized',
  submitted_at TIMESTAMP DEFAULT NOW(),
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  release_date TIMESTAMP
);

-- Initial settings
INSERT INTO settings (key, value) VALUES
('daily_limit', '150'),
('current_date', CURRENT_DATE::TEXT),
('current_count', '0')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
