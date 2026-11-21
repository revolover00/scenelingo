-- SceneLingo schema (Neon Postgres)
-- Run once in the Neon SQL editor or via: python -m db init

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS sent_words (
    word TEXT PRIMARY KEY,
    video_id TEXT,
    video_title TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Keep existing subscribers and give them a sensible default level.
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS level TEXT NOT NULL DEFAULT 'A2';

CREATE TABLE IF NOT EXISTS sent_phrases (
    id BIGSERIAL PRIMARY KEY,
    level TEXT NOT NULL,
    phrase TEXT NOT NULL,
    topic TEXT NOT NULL,
    clip_id TEXT,
    video_title TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sent_phrases_level_sent_at_idx ON sent_phrases (level, sent_at DESC);

-- Additive preferences for the upcoming multilingual scheduler. Existing
-- subscribers remain untouched; settings are created only on first use.
CREATE TABLE IF NOT EXISTS subscriber_preferences (
    chat_id BIGINT PRIMARY KEY REFERENCES subscribers(chat_id) ON DELETE CASCADE,
    learning_language TEXT NOT NULL DEFAULT 'en'
      CHECK (learning_language IN ('en', 'zh', 'hi', 'es', 'fr', 'ar', 'pt', 'ru', 'de', 'ja')),
    explanation_language TEXT NOT NULL DEFAULT 'ar'
      CHECK (explanation_language IN ('en', 'zh', 'hi', 'es', 'fr', 'ar', 'pt', 'ru', 'de', 'ja')),
    interval_minutes INTEGER NOT NULL DEFAULT 180 CHECK (interval_minutes BETWEEN 30 AND 1440),
    next_due_at TIMESTAMPTZ,
    input_state TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE subscriber_preferences ADD COLUMN IF NOT EXISTS input_state TEXT;

ALTER TABLE sent_phrases ADD COLUMN IF NOT EXISTS learning_language TEXT NOT NULL DEFAULT 'en';

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'subscriber_preferences'::regclass
    AND conname = 'subscriber_preferences_interval_minutes_check'
    AND pg_get_constraintdef(oid) NOT LIKE '%30%') THEN
-- Raise old short intervals while preserving the remaining preferences.
ALTER TABLE subscriber_preferences DROP CONSTRAINT IF EXISTS subscriber_preferences_interval_minutes_check;
UPDATE subscriber_preferences SET interval_minutes = 30,
    next_due_at = GREATEST(next_due_at, now() + interval '30 minutes'), updated_at = now()
    WHERE interval_minutes < 30;
ALTER TABLE subscriber_preferences ADD CONSTRAINT subscriber_preferences_interval_minutes_check
    CHECK (interval_minutes BETWEEN 30 AND 1440);
  END IF;
END $$;

-- Bot menus are independent of the learning and explanation languages.
ALTER TABLE subscriber_preferences ADD COLUMN IF NOT EXISTS ui_language TEXT NOT NULL DEFAULT 'ar'
    CHECK (ui_language IN ('ar', 'en'));

-- Operational outcomes only; never store API secrets or raw exception text.
CREATE TABLE IF NOT EXISTS delivery_runs (
    id BIGSERIAL PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('idle', 'completed', 'failed')),
    due_count INTEGER NOT NULL CHECK (due_count >= 0),
    finished_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Distributed admin login throttling; only salted IP hashes, never credentials.
CREATE TABLE IF NOT EXISTS admin_login_limits (
    key_hash TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
