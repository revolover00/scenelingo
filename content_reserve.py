"""Bounded, demand-only stock of verified media and complete lesson captions.

No Telegram calls, slot reservations, claims or schedule changes. The existing
shared queue consumes this stock oldest-unseen-first at the normal due time.
"""
from collections import defaultdict
from types import SimpleNamespace

import db
import delivery_store as store
import preparation

TARGET = 3
MAX_NEW_PER_RUN = 1


def stock(sub):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute('''SELECT count(*) FROM lesson_content c
            WHERE c.level=%s AND c.learning_language=%s
              AND (c.telegram_file_id IS NOT NULL OR EXISTS (
                SELECT 1 FROM prepared_media m WHERE m.content_id=c.id AND m.expires_at>now()))
              AND EXISTS (SELECT 1 FROM lesson_captions cap WHERE cap.content_id=c.id
                AND cap.explanation_language=%s)
              AND NOT EXISTS (SELECT 1 FROM delivery_attempts a WHERE a.content_id=c.id
                AND a.chat_id=%s AND a.status IN ('sent','uncertain','sending'))''',
            (sub['level'], sub['learning_language'], sub['explanation_language'], sub['chat_id']))
        return cur.fetchone()[0]


def library_phrases(level, learning):
    with db.session() as conn, conn.cursor() as cur:
        cur.execute('''SELECT phrase FROM lesson_content c WHERE level=%s AND learning_language=%s
            AND (telegram_file_id IS NOT NULL OR EXISTS(SELECT 1 FROM prepared_media m WHERE m.content_id=c.id AND m.expires_at>now())
              OR EXISTS(SELECT 1 FROM delivery_attempts a WHERE a.content_id=c.id AND a.status IN ('sent','uncertain','sending')))''', (level, learning))
        return {row[0].casefold() for row in cur.fetchall()}



def incomplete(level, learning, audience):
    import psycopg2.extras
    with db.session() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute('''SELECT c.* FROM lesson_content c WHERE c.level=%s AND c.learning_language=%s
            AND (c.telegram_file_id IS NOT NULL OR EXISTS(SELECT 1 FROM prepared_media m
                WHERE m.content_id=c.id AND m.expires_at>now()))
            AND NOT EXISTS(SELECT 1 FROM delivery_attempts a WHERE a.content_id=c.id AND a.chat_id=ANY(%s)
                AND a.status IN ('sent','uncertain','sending'))
            AND EXISTS(SELECT 1 FROM unnest(%s::text[]) lang WHERE NOT EXISTS(
                SELECT 1 FROM lesson_captions cap WHERE cap.content_id=c.id AND cap.explanation_language=lang))
            ORDER BY c.created_at,c.id LIMIT 1''', (level, learning,
                [s['chat_id'] for s in audience], list({s['explanation_language'] for s in audience})))
        row = cur.fetchone()
        return dict(row) if row else None


def refill(subscribers, select, explain):
    groups = defaultdict(list)
    for sub in subscribers:
        if db.still_due_with_settings(sub, 1440):
            groups[(sub['level'], sub['learning_language'])].append(sub)
    # Refill the most depleted audience first, not whichever level sorts first.
    ranked = sorted((min(stock(s) for s in audience), key, audience)
                    for key, audience in groups.items())
    built = failed = 0
    for available, (level, learning), audience in ranked:
        if available >= TARGET or built + failed >= MAX_NEW_PER_RUN:
            continue
        try:
            audience = [s for s in audience if db.still_due_with_settings(s, 1440)]
            if not audience:
                continue
            content = incomplete(level, learning, audience)
            if not content:
                expression, clip = select(level, learning, excluded=library_phrases(level, learning))
                content = store.content(expression, clip, level, learning)
                if store.seen_by(content['id'], [s['chat_id'] for s in audience]):
                    raise RuntimeError('Reserve selection is already consumed')
                if not content['telegram_file_id']:
                    preparation.save_media(content['id'], clip.path)
            # Persist media first. Partial captions are retried without replacing
            # the source or falsely declaring this lesson ready for that language.
            for language in {s['explanation_language'] for s in audience}:
                if not store.get_caption(content['id'], language):
                    caption = explain(content['phrase'], SimpleNamespace(title=content['video_title'],
                        url=content['source_url']), level, learning, language)
                    store.save_caption(content['id'], language, caption)
            built += 1
        except Exception as error:
            print(f'::warning title=Reserve refill::{level}/{learning}: {type(error).__name__}', flush=True)
            failed += 1
    for (level, learning), audience in groups.items():
        print(f'::notice title=Reserve stock::{level}/{learning}: minimum_ready={min(stock(s) for s in audience)}, target={TARGET}', flush=True)
    print(f'::notice title=Verified lesson reserve::built={built}, failed={failed}, target_per_person={TARGET}', flush=True)
    return built, failed
