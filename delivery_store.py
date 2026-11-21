"""Durable bot-local delivery ledger and reusable verified Telegram video cache."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager

import psycopg2.extras

import db


@contextmanager
def worker_lock():
    """Session advisory lock also serializes workers outside the Actions queue."""
    # New lock namespace: the old transaction-pooled endpoint could strand
    # session locks on pooled backends after the worker exited. Direct session
    # connections now guarantee close() releases this lock.
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext(current_schema()), 7195)")
            locked = cur.fetchone()[0]
        if locked:
            # A terminated worker may have sent before dying. Never auto-replay it.
            with conn, conn.cursor() as cur:
                cur.execute("UPDATE delivery_attempts SET status='uncertain', error_code='worker_interrupted', updated_at=now() WHERE status='sending'")
        yield locked
    finally:
        conn.close()  # session advisory lock is released even after exceptions


def state(sub):
    with db.session() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute('SELECT * FROM delivery_attempts WHERE chat_id=%s AND due_at=%s', (sub['chat_id'], sub['due_at']))
        row = cur.fetchone()
        return dict(row) if row else None


def claim(sub, content_id):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO delivery_attempts(chat_id,due_at,content_id,status,explanation_language)
            VALUES (%s,%s,%s,'sending',%s) ON CONFLICT(chat_id,due_at) DO UPDATE
            SET status='sending', attempts=delivery_attempts.attempts+1, updated_at=now()
            WHERE delivery_attempts.status='failed' AND delivery_attempts.retry_at <= now()
              AND delivery_attempts.attempts < 3
              AND delivery_attempts.content_id = EXCLUDED.content_id
            RETURNING id""", (sub['chat_id'], sub['due_at'], content_id, sub['explanation_language']))
        row = cur.fetchone()
        return row[0] if row else None


def finish(attempt_id, status, code=None, message_id=None):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE delivery_attempts SET status=%s,error_code=%s,message_id=%s,
            retry_at=CASE WHEN %s='failed' THEN now()+interval '15 minutes' END,updated_at=now()
            WHERE id=%s""", (status, code, message_id, status, attempt_id))


def content(expression, clip, level, learning):
    key = hashlib.sha256(f'{level}\0{learning}\0{expression.text}\0{clip.clip_id}'.encode()).hexdigest()
    with db.session() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""INSERT INTO lesson_content(content_key,phrase,topic,level,learning_language,clip_id,video_title,source_url)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(content_key) DO UPDATE SET content_key=EXCLUDED.content_key
            RETURNING *""", (key, expression.text, expression.topic, level, learning, clip.clip_id, clip.title, clip.url))
        return dict(cur.fetchone())


def cached(level, learning, chat_ids):
    """Only use verified, reusable uploads unseen by EVERY intended recipient."""
    with db.session() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT c.* FROM lesson_content c WHERE c.level=%s AND c.learning_language=%s
            AND c.telegram_file_id IS NOT NULL
            AND NOT EXISTS(SELECT 1 FROM delivery_attempts a WHERE a.content_id=c.id
                AND a.chat_id=ANY(%s) AND a.status IN ('sent','uncertain','sending'))
            ORDER BY c.created_at DESC LIMIT 1""", (level, learning, chat_ids))
        row = cur.fetchone()
        return dict(row) if row else None


def get_content(content_id):
    with db.session() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute('SELECT * FROM lesson_content WHERE id=%s', (content_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def file_id(content_id, value):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute('UPDATE lesson_content SET telegram_file_id=%s WHERE id=%s', (value, content_id))


def get_caption(content_id, language):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute('SELECT caption FROM lesson_captions WHERE content_id=%s AND explanation_language=%s', (content_id, language))
        row = cur.fetchone()
        return row[0] if row else None


def save_caption(content_id, language, caption):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute('INSERT INTO lesson_captions(content_id,explanation_language,caption) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (content_id, language, caption))


def record_run(status, due_count, stats, duration):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO delivery_runs(status,due_count,sent_count,failed_count,skipped_count,uncertain_count,
            content_requests,explanation_requests,cache_hits,duration_seconds) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (status, due_count, stats['sent'], stats['failed'], stats['skipped'], stats['uncertain'],
             stats['content_requests'], stats['explanation_requests'], stats['cache_hits'], duration))


def seen_by(content_id, chat_ids):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM delivery_attempts WHERE content_id=%s AND chat_id=ANY(%s) AND status IN ('sent','uncertain','sending') LIMIT 1", (content_id,chat_ids))
        return cur.fetchone() is not None


def assign_cached(subscribers):
    """Oldest unseen reusable lesson per person, independent of delivery interval.

    One query per language/level, not one query per subscriber. Receipts, not a
    group-wide history, decide whether each person has already received a lesson.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for sub in subscribers:
        groups[(sub['level'], sub['learning_language'])].append(sub)
    assigned = {}
    for (level, learning), audience in groups.items():
        with db.session() as conn, conn.cursor() as cur:
            cur.execute("""SELECT recipient.chat_id, chosen.id
                FROM unnest(%s::bigint[]) AS recipient(chat_id)
                LEFT JOIN LATERAL (
                    SELECT c.id FROM lesson_content c
                    WHERE c.level=%s AND c.learning_language=%s
                      AND (c.telegram_file_id IS NOT NULL OR EXISTS (
                        SELECT 1 FROM prepared_media m WHERE m.content_id=c.id AND m.expires_at>now()))
                      AND NOT EXISTS (SELECT 1 FROM delivery_attempts a
                        WHERE a.chat_id=recipient.chat_id AND a.content_id=c.id
                          AND a.status IN ('sent','uncertain','sending'))
                    ORDER BY c.created_at,c.id LIMIT 1
                ) chosen ON TRUE""", ([s['chat_id'] for s in audience], level, learning))
            assigned.update(cur.fetchall())
    return [dict(sub, queue_content_id=assigned.get(sub['chat_id'])) for sub in subscribers]
