"""Neon Postgres data layer.

Tables:
    subscribers(chat_id, username, first_name, subscribed_at, is_active)
    sent_words(word, video_id, video_title, sent_at)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import psycopg2.extras
from psycopg2 import sql

from bot_identity import database_schema
from config import config
from postgres_connection import connect_verified

log = logging.getLogger(__name__)


def connect():
    """Open a Neon Postgres connection."""
    config.validate("database_url", "bot_token")
    schema = database_schema(config.bot_token)
    conn = connect_verified(config.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema)))
            cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        conn.commit()
        return conn
    except Exception:
        conn.close()
        raise


@contextmanager
def session():
    """Commit/rollback a short-lived transaction and always close its connection.

    Raw connect() remains available for the session-level delivery advisory lock.
    psycopg2's connection context manager alone does not close a connection.
    """
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they do not exist."""
    with open("schema.sql", encoding="utf-8") as f:
        ddl = f.read()
    with session() as conn:
        with conn.cursor() as cur:
            # Serialize migrations per bot even when delivery initializes in
            # parallel. Keep the migration workflow out of the delivery queue:
            # GitHub concurrency retains only one pending run per group.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema()), hashtext('schema-migration'))")
            cur.execute(ddl)
            cur.execute(Path(__file__).with_name('scheduling.sql').read_text(encoding='utf-8'))
            cur.execute(Path(__file__).with_name('reliability.sql').read_text(encoding='utf-8'))
        conn.commit()
    log.info("Database initialized")


def add_subscriber(chat_id: int, username: str | None, first_name: str | None) -> None:
    """Subscribe (or reactivate) a user."""
    with session() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscribers (chat_id, username, first_name, is_active)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (chat_id) DO UPDATE
                SET username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    is_active = TRUE
                """,
                (chat_id, username, first_name),
            )
        conn.commit()


def remove_subscriber(chat_id: int) -> None:
    """Unsubscribe a user (soft delete)."""
    with session() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscribers SET is_active = FALSE WHERE chat_id = %s",
                (chat_id,),
            )
        conn.commit()


def list_subscribers() -> list[dict]:
    """Return all active subscribers."""
    with session() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT chat_id FROM subscribers WHERE is_active = TRUE ORDER BY chat_id"
        )
        return [dict(row) for row in cur.fetchall()]


def was_sent(word: str) -> bool:
    """Check whether a word was already sent."""
    with session() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM sent_words WHERE word = %s", (word,))
        return cur.fetchone() is not None


def mark_sent(word: str, video_id: str | None, video_title: str | None) -> None:
    """Record a word as sent."""
    with session() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sent_words (word, video_id, video_title)
                VALUES (%s, %s, %s)
                ON CONFLICT (word) DO NOTHING
                """,
                (word, video_id, video_title),
            )
        conn.commit()


def last_sent_word() -> str | None:
    """Return the most recently sent word, if any."""
    with session() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT word FROM sent_words ORDER BY sent_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        return row[0] if row else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()


def active_subscribers_by_level() -> dict[str, list[int]]:
    """Return active subscriber chat IDs grouped by their selected CEFR level."""
    with session() as conn, conn.cursor() as cur:
        cur.execute("SELECT level, chat_id FROM subscribers WHERE is_active = TRUE ORDER BY chat_id")
        groups: dict[str, list[int]] = {}
        for level, chat_id in cur.fetchall():
            groups.setdefault(level, []).append(chat_id)
        return groups


def phrase_history(level: str, language: str = 'en') -> tuple[set[str], list[str]]:
    with session() as conn, conn.cursor() as cur:
        cur.execute("""SELECT phrase,topic FROM (
            SELECT phrase,topic,sent_at FROM sent_phrases WHERE level=%s AND learning_language=%s
            UNION ALL
            SELECT c.phrase,c.topic,a.updated_at AS sent_at FROM lesson_content c
            JOIN delivery_attempts a ON a.content_id=c.id
            WHERE c.level=%s AND c.learning_language=%s AND a.status IN ('sent','uncertain')
        ) history ORDER BY sent_at DESC""", (level, language, level, language))
        rows = cur.fetchall()
        return {row[0].casefold() for row in rows}, [row[1] for row in rows[:3]]


def mark_phrase_sent(level: str, phrase: str, topic: str, clip_id: str, title: str, language: str = 'en') -> None:
    with session() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sent_phrases (level, phrase, topic, clip_id, video_title, learning_language) VALUES (%s, %s, %s, %s, %s, %s)",
            (level, phrase, topic, clip_id, title, language),
        )


def due_subscribers(lookahead_minutes: int = 0) -> list[dict]:
    """List active users due now or within the optional lookahead window.

    This is a scheduling building block, not a delivery claim. The caller must
    serialize scheduling runs and advance a user's due time only after delivery.
    """
    with session() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT s.chat_id, s.level,
                   COALESCE(p.learning_language, 'en') AS learning_language,
                   COALESCE(p.explanation_language, 'ar') AS explanation_language,
                   COALESCE(p.interval_minutes, 180) AS interval_minutes,
                   p.updated_at AS settings_updated_at,
                   COALESCE(p.next_due_at, s.subscribed_at + interval '3 hours') AS due_at,
                   COALESCE(p.ui_language, 'ar') AS ui_language
            FROM subscribers s
            LEFT JOIN subscriber_preferences p ON p.chat_id = s.chat_id
            WHERE s.is_active = TRUE
              AND LEFT(COALESCE(p.input_state, ''), 6) <> 'setup_'
              AND COALESCE(p.next_due_at, s.subscribed_at + interval '3 hours') <= now() + %s * interval '1 minute'
            ORDER BY COALESCE(p.next_due_at, s.subscribed_at + interval '3 hours'), s.chat_id
        """, (lookahead_minutes,))
        return [dict(row) for row in cur.fetchall()]


def advance_due_after_delivery(chat_id: int, settings_updated_at) -> bool:
    """Advance after a successful send without clobbering a newer schedule.

    If settings changed during delivery, preserve a future due time set by the
    user. If the new schedule is still overdue, advance using its current
    interval to avoid an immediate duplicate on the next scheduler tick.
    """
    with session() as conn, conn.cursor() as cur:
        if settings_updated_at is None:
            cur.execute("""
                INSERT INTO subscriber_preferences (chat_id, next_due_at)
                SELECT chat_id, now() + interval '3 hours' FROM subscribers
                WHERE chat_id = %s AND is_active = TRUE
                ON CONFLICT (chat_id) DO NOTHING
                RETURNING chat_id
            """, (chat_id,))
        else:
            cur.execute("""
                UPDATE subscriber_preferences p
                SET next_due_at = next_delivery_at(p.interval_minutes)
                FROM subscribers s
                WHERE p.chat_id = %s AND s.chat_id = p.chat_id AND s.is_active = TRUE
                  AND p.updated_at = %s
                RETURNING p.chat_id
            """, (chat_id, settings_updated_at))
        if cur.fetchone() is not None:
            return True
        cur.execute("""
            UPDATE subscriber_preferences p
            SET next_due_at = next_delivery_at(p.interval_minutes)
            FROM subscribers s
            WHERE p.chat_id = %s AND s.chat_id = p.chat_id AND s.is_active = TRUE
              AND COALESCE(p.next_due_at, s.subscribed_at + interval '3 hours') <= now()
            RETURNING p.chat_id
        """, (chat_id,))
        return cur.fetchone() is not None


def still_due_with_settings(subscriber: dict, lookahead_minutes: int = 0) -> bool:
    """Recheck activity, level, preferences and due time just before sending.

    This narrows races with /stop and settings changes. Telegram and Postgres
    cannot share a transaction, so it cannot eliminate all delivery races.
    """
    with session() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM subscribers s
            LEFT JOIN subscriber_preferences p ON p.chat_id = s.chat_id
            WHERE s.chat_id = %s AND s.is_active = TRUE AND s.level = %s
              AND COALESCE(p.learning_language, 'en') = %s
              AND COALESCE(p.explanation_language, 'ar') = %s
              AND LEFT(COALESCE(p.input_state, ''), 6) <> 'setup_'
              AND p.updated_at IS NOT DISTINCT FROM %s
              AND (%s::timestamptz IS NULL OR COALESCE(p.next_due_at, s.subscribed_at + interval '3 hours') = %s::timestamptz)
              AND COALESCE(p.next_due_at, s.subscribed_at + interval '3 hours') <= now() + %s * interval '1 minute'
        """, (subscriber['chat_id'], subscriber['level'], subscriber['learning_language'],
              subscriber['explanation_language'], subscriber['settings_updated_at'], subscriber.get('due_at'), subscriber.get('due_at'), lookahead_minutes))
        return cur.fetchone() is not None


def record_delivery_run(status: str, due_count: int) -> None:
    """Record coarse run outcomes, not a claim of per-user delivery or AI usage."""
    with session() as conn, conn.cursor() as cur:
        cur.execute('INSERT INTO delivery_runs (status, due_count) VALUES (%s, %s)', (status, due_count))
