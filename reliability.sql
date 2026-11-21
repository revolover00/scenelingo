-- Bot-local durable delivery state. No tokens or raw exception messages are stored.
CREATE TABLE IF NOT EXISTS lesson_content (
    id BIGSERIAL PRIMARY KEY,
    content_key TEXT NOT NULL UNIQUE,
    phrase TEXT NOT NULL, topic TEXT NOT NULL,
    level TEXT NOT NULL, learning_language TEXT NOT NULL,
    clip_id TEXT NOT NULL, video_title TEXT NOT NULL, source_url TEXT NOT NULL,
    telegram_file_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS lesson_captions (
    content_id BIGINT NOT NULL REFERENCES lesson_content(id) ON DELETE CASCADE,
    explanation_language TEXT NOT NULL, caption TEXT NOT NULL,
    PRIMARY KEY (content_id, explanation_language)
);
CREATE TABLE IF NOT EXISTS delivery_attempts (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL REFERENCES subscribers(chat_id) ON DELETE CASCADE,
    due_at TIMESTAMPTZ NOT NULL,
    explanation_language TEXT NOT NULL DEFAULT 'ar',
    content_id BIGINT REFERENCES lesson_content(id),
    status TEXT NOT NULL CHECK (status IN ('sending','sent','failed','uncertain','blocked','skipped')),
    error_code TEXT, message_id BIGINT,
    attempts INTEGER NOT NULL DEFAULT 1,
    retry_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(chat_id, due_at)
);
CREATE INDEX IF NOT EXISTS delivery_attempts_content_idx ON delivery_attempts(chat_id, content_id);
CREATE TABLE IF NOT EXISTS saved_lessons (
    chat_id BIGINT NOT NULL REFERENCES subscribers(chat_id) ON DELETE CASCADE,
    content_id BIGINT NOT NULL REFERENCES lesson_content(id) ON DELETE CASCADE,
    explanation_language TEXT NOT NULL,
    review_days INTEGER NOT NULL DEFAULT 1 CHECK (review_days BETWEEN 1 AND 30),
    next_review_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(chat_id, content_id)
);
CREATE TABLE IF NOT EXISTS lesson_feedback (
    chat_id BIGINT NOT NULL REFERENCES subscribers(chat_id) ON DELETE CASCADE,
    content_id BIGINT NOT NULL REFERENCES lesson_content(id) ON DELETE CASCADE,
    reason TEXT NOT NULL CHECK (reason IN ('explanation','clip')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(chat_id, content_id, reason)
);
-- Keep backward-compatible coarse run outcomes while adding measurable counters.
ALTER TABLE delivery_runs ADD COLUMN IF NOT EXISTS sent_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE delivery_runs ADD COLUMN IF NOT EXISTS failed_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE delivery_runs ADD COLUMN IF NOT EXISTS skipped_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE delivery_runs ADD COLUMN IF NOT EXISTS uncertain_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE delivery_runs ADD COLUMN IF NOT EXISTS content_requests INTEGER NOT NULL DEFAULT 0;
ALTER TABLE delivery_runs ADD COLUMN IF NOT EXISTS explanation_requests INTEGER NOT NULL DEFAULT 0;
ALTER TABLE delivery_runs ADD COLUMN IF NOT EXISTS cache_hits INTEGER NOT NULL DEFAULT 0;
ALTER TABLE delivery_runs ADD COLUMN IF NOT EXISTS duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS ai_usage (
    id BIGSERIAL PRIMARY KEY,
    operation TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ok','failed')),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    duration_seconds DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Small, short-lived verified media buffer shared by every recipient of a lesson.
-- No binary media is committed to the repository or Actions artifacts.
CREATE TABLE IF NOT EXISTS prepared_media (
    content_id BIGINT PRIMARY KEY REFERENCES lesson_content(id) ON DELETE CASCADE,
    payload BYTEA NOT NULL CHECK (octet_length(payload) <= 20971520),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '24 hours'
);
CREATE TABLE IF NOT EXISTS prepared_slots (
    chat_id BIGINT NOT NULL REFERENCES subscribers(chat_id) ON DELETE CASCADE,
    due_at TIMESTAMPTZ NOT NULL,
    settings_updated_at TIMESTAMPTZ,
    content_id BIGINT NOT NULL REFERENCES lesson_content(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(chat_id,due_at)
);

CREATE TABLE IF NOT EXISTS preparation_runs (
    id BIGSERIAL PRIMARY KEY,
    prepared_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Movie-audio transcripts only; no user messages, bot tokens or AI credentials.
CREATE TABLE IF NOT EXISTS audio_transcripts (
    audio_hash TEXT PRIMARY KEY,
    detected_language TEXT NOT NULL,
    transcript TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '7 days',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
