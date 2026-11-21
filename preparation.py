"""Durable thirty-minute lookahead. Preparation never calls Telegram or claims delivery.

Media is bounded to 20 MiB/item and 80 MiB total, expires after 24h, and is
shared by content ID. This small MVP buffer uses the existing Postgres database.
"""
import logging
import time
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import db
import delivery_store as store

log = logging.getLogger(__name__)
LOOKAHEAD_MINUTES = 30
MAX_ITEM = 20 * 1024 * 1024
MAX_TOTAL = 80 * 1024 * 1024


def cleanup():
    with db.session() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM prepared_slots WHERE due_at < now()-interval '24 hours'")
        cur.execute('''DELETE FROM prepared_media m WHERE expires_at <= now()
            OR EXISTS (SELECT 1 FROM lesson_content c WHERE c.id=m.content_id AND c.telegram_file_id IS NOT NULL)''')


def ready(sub, require_caption=True):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute('''SELECT p.content_id FROM prepared_slots p
            JOIN lesson_content c ON c.id=p.content_id
            WHERE p.chat_id=%s AND p.due_at=%s
              AND p.settings_updated_at IS NOT DISTINCT FROM %s
              AND (c.telegram_file_id IS NOT NULL OR EXISTS (
                SELECT 1 FROM prepared_media m WHERE m.content_id=c.id AND m.expires_at>now()))
              AND (NOT %s OR EXISTS (SELECT 1 FROM lesson_captions cap WHERE cap.content_id=c.id
                AND cap.explanation_language=%s))''',
            (sub['chat_id'], sub['due_at'], sub['settings_updated_at'], require_caption, sub['explanation_language']))
        row = cur.fetchone()
        return row[0] if row else None


def save_media(content_id, path):
    path = Path(path)
    if path.stat().st_size > MAX_ITEM:
        raise ValueError('Prepared clip exceeds 20 MiB buffer limit')
    with path.open('rb') as media:
        payload = media.read(MAX_ITEM + 1)
    if len(payload) > MAX_ITEM:
        raise ValueError('Prepared clip grew beyond buffer limit')
    with db.session() as conn, conn.cursor() as cur:
        # Same worker lock as delivery serializes budget accounting.
        cur.execute('SELECT COALESCE(sum(octet_length(payload)),0) FROM prepared_media WHERE content_id<>%s', (content_id,))
        if cur.fetchone()[0] + len(payload) > MAX_TOTAL:
            raise ValueError('Prepared media buffer full')
        cur.execute('''INSERT INTO prepared_media(content_id,payload) VALUES(%s,%s)
            ON CONFLICT(content_id) DO UPDATE SET payload=EXCLUDED.payload,
            expires_at=now()+interval '24 hours' ''', (content_id, payload))


def reserve(sub, content_id):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute('''INSERT INTO prepared_slots(chat_id,due_at,settings_updated_at,content_id)
            VALUES(%s,%s,%s,%s) ON CONFLICT(chat_id,due_at) DO UPDATE SET
            settings_updated_at=EXCLUDED.settings_updated_at,content_id=EXCLUDED.content_id,created_at=now()''',
            (sub['chat_id'],sub['due_at'],sub['settings_updated_at'],content_id))


def _prepare(subscribers, select, explain):
    """Retry missing preparation next tick; never mark a partial lesson ready."""
    groups = defaultdict(list)
    for sub in store.assign_cached(subscribers):
        if db.still_due_with_settings(sub, LOOKAHEAD_MINUTES) and not ready(sub) and not store.state(sub):
            groups[(sub['level'],sub['learning_language'],ready(sub, require_caption=False) or sub.get('queue_content_id'))].append(sub)
    prepared = failed = 0
    for (level, learning, pinned), audience in groups.items():
        try:
            audience = [s for s in audience if db.still_due_with_settings(s, LOOKAHEAD_MINUTES)]
            if not audience:
                continue
            content = store.get_content(pinned) if pinned else store.cached(level, learning, [s['chat_id'] for s in audience])
            if not content:
                expression, clip = select(level, learning)
                content = store.content(expression, clip, level, learning)
                if store.seen_by(content['id'], [s['chat_id'] for s in audience]):
                    raise ValueError('No unseen verified content')
                if not content['telegram_file_id']:
                    save_media(content['id'], clip.path)
        except Exception as error:  # noqa: BLE001 - isolate provider, media, and database failures per audience
            log.warning('Preparation content failed (%s)', type(error).__name__)
            failed += len(audience)
            continue
        for language in {s['explanation_language'] for s in audience}:
            recipients = [s for s in audience if s['explanation_language']==language
                          and db.still_due_with_settings(s, LOOKAHEAD_MINUTES)]
            if not recipients:
                continue
            try:
                # Persist the media assignment even if explanation generation fails.
                for sub in recipients:
                    reserve(sub, content['id'])
                if not store.get_caption(content['id'], language):
                    caption = explain(content['phrase'], SimpleNamespace(title=content['video_title'],
                        url=content['source_url']), level, learning, language)
                    store.save_caption(content['id'], language, caption)
                for sub in recipients:
                    if db.still_due_with_settings(sub, LOOKAHEAD_MINUTES):
                        reserve(sub, content['id'])
                        prepared += 1
            except Exception as error:  # noqa: BLE001 - isolate model and database failures per recipient group
                log.warning('Preparation explanation failed (%s)', type(error).__name__)
                failed += len(recipients)
    return prepared, failed


def restore(content, fallback):
    """Materialize only for this invocation; deletion is guaranteed by context exit."""
    from contextlib import contextmanager

    @contextmanager
    def materialize():
        with db.session() as conn, conn.cursor() as cur:
            cur.execute('SELECT payload FROM prepared_media WHERE content_id=%s AND expires_at>now()', (content['id'],))
            row = cur.fetchone()
        if row:
            with TemporaryDirectory(prefix='scenelingo-') as directory:
                path = Path(directory)/'clip.mp4'
                path.write_bytes(bytes(row[0]))
                yield SimpleNamespace(path=path)
        else:
            yield fallback(content)
    return materialize()


def prepare(subscribers, select, explain):
    """Record preparation separately from delivery; telemetry never masks results."""
    started = time.monotonic()
    prepared, failed = 0, 0
    try:
        prepared, failed = _prepare(subscribers, select, explain)
        return prepared, failed
    except Exception:
        failed = max(1, len(subscribers))
        raise
    finally:
        try:
            with db.session() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO preparation_runs(prepared_count,failed_count,duration_seconds)
                    VALUES(%s,%s,%s)""", (prepared, failed, time.monotonic()-started))
                cur.execute("DELETE FROM preparation_runs WHERE finished_at<now()-interval '30 days'")
        except Exception:  # noqa: BLE001 - failure in best-effort telemetry must not mask preparation
            log.warning('Preparation telemetry unavailable')
