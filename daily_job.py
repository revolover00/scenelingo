"""Send one matching movie expression to each subscribed CEFR-level group."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from telegram import Bot

import clip_cafe
import db
import multilingual
import phrases
import source_first
from async_file import open_binary_async
from config import config
from lessons import caption as render_caption

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


def build_message(level: str):
    """Select an unseen expression with a real matching movie clip."""
    seen, recent_topics = db.phrase_history(level)
    for expression in phrases.candidates(level, seen, recent_topics):
        try:
            clip = clip_cafe.find_clip(expression.text)
        except RuntimeError as exc:
            log.info('No matching clip for %r: %s', expression.text, exc)
            continue
        caption = localized_caption(expression.text, clip, level, 'en', 'ar')
        return expression, clip, caption
    raise RuntimeError(f'No matching movie clip for level {level}')


def localized_caption(text: str, clip, level: str, learning: str, explanation: str) -> str:
    meaning = multilingual.meaning(text, learning, explanation, level)
    return render_caption(text, meaning, level, learning, explanation, clip.title, clip.url)



def select_localized_clip(level: str, learning: str, excluded=None):
    """Find an expression and verify its audio before returning its clip."""
    seen, topics = db.phrase_history(level, learning)
    seen = seen | {text.casefold() for text in (excluded or ())}
    if learning in source_first.SEEDS:
        try:
            (text, topic), clip = source_first.find_expression_clip(learning, level, seen, topics)
        except RuntimeError:
            log.info('No suitable expression found in sampled %s audio', learning)
        else:
            return phrases.Phrase(text, topic), clip
    deadline = time.monotonic() + 120
    refresh_after_search = False
    if learning == 'en':
        candidates = [(p.text, p.topic) for p in phrases.candidates(level, seen, topics)]
        # Once the finite curated bank is exhausted, try new generated
        # expressions before recycling the bank. Clip audio is still verified.
        refresh_after_search = not all(p.text.casefold() in seen for p in phrases.BANK[level])
        if not refresh_after_search:
            try:
                candidates = multilingual.expressions(learning, level, seen, topics) + candidates
            except Exception:  # noqa: BLE001 - a failed AI refresh falls back to the curated bank
                log.warning('Could not generate fresh English expressions; using curated bank')
    else:
        candidates = multilingual.expressions(learning, level, seen, topics)
    attempted = set()
    # Reserve time for fresh expressions when the remaining curated phrases
    # have no available verified audio. Unsent does not mean searchable.
    curated_deadline = deadline - 60 if refresh_after_search else deadline
    for text, topic in candidates:
        if time.monotonic() >= curated_deadline:
            log.warning('Content search budget exhausted for %s/%s', level, learning)
            break
        attempted.add(text.casefold())
        try:
            clip = clip_cafe.find_clip(
                text, verify=lambda path, phrase: multilingual.verify_audio(path, phrase, learning),
                audio_language=learning)
        except RuntimeError:
            log.info('No verified audio found for expression %r', text)
            continue
        return phrases.Phrase(text, topic), clip
    if refresh_after_search and time.monotonic() < deadline:
        try:
            fresh = multilingual.expressions(learning, level, seen | attempted, topics)
        except Exception:  # noqa: BLE001 - fail closed if the provider is unavailable
            log.warning('Fresh English content unavailable after curated search')
            fresh = []
        for text, topic in fresh:
            if time.monotonic() >= deadline:
                break
            if text.casefold() in seen | attempted:
                continue
            attempted.add(text.casefold())
            try:
                clip = clip_cafe.find_clip(
                    text, verify=lambda path, phrase: multilingual.verify_audio(path, phrase, learning),
                    audio_language=learning)
            except RuntimeError:
                continue
            return phrases.Phrase(text, topic), clip
    raise RuntimeError(f'No verified clip for {level}/{learning}')


def reload_verified_clip(content):
    """Never attach a saved lesson's caption/source to a different movie clip."""
    clip = clip_cafe.load_clip(content['source_url'], content['phrase'], expected_id=content['clip_id'], audio_language=content['learning_language'],
        verify=lambda path, phrase: multilingual.verify_audio(path, phrase, content['learning_language']))
    if clip.clip_id != content['clip_id']:
        raise RuntimeError('Original lesson clip is unavailable; refusing source substitution')
    return clip


def build_localized_message(level: str, learning: str, explanation: str):
    expression, clip = select_localized_clip(level, learning)
    return expression, clip, localized_caption(expression.text, clip, level, learning, explanation)


async def broadcast(bot: Bot, chat_ids: list[int], clip_path: str, caption: str) -> tuple[int, int]:
    sent = failed = 0
    for chat_id in chat_ids:
        try:
            async with open_binary_async(clip_path) as video:
                await bot.send_video(chat_id=chat_id, video=video, caption=caption)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - one recipient's transport failure must not stop the group
            log.warning('Send to %s failed: %s', chat_id, exc)
            failed += 1
        await asyncio.sleep(config.send_delay)
    return sent, failed


async def run_groups(groups: dict[str, list[int]]) -> None:
    bot = Bot(token=config.bot_token)
    failures = []
    for level in phrases.LEVELS:
        chat_ids = groups.get(level, [])
        if not chat_ids:
            continue
        try:
            expression, clip, caption = build_message(level)
            sent, failed = await broadcast(bot, chat_ids, str(clip.path), caption)
            log.info('Level %s: %d sent, %d failed', level, sent, failed)
            print(f'::notice title=Level {level} delivery::{sent} sent, {failed} failed', flush=True)
            if sent:
                db.mark_phrase_sent(level, expression.text, expression.topic, clip.clip_id, clip.title)
            else:
                raise RuntimeError('Failed to send to any subscriber')
        except Exception:
            log.exception('Failed to process level %s', level)
            failures.append(level)
    if failures:
        raise RuntimeError('Failed levels: ' + ', '.join(failures))



async def run_due_subscribers(subscribers: list[dict]) -> None:
    """Deliver only to due subscribers; advance each schedule after successful sends.

    Clips must pass audio verification before delivery.
    """
    # Recheck before content search, not just before sending.
    subscribers = [sub for sub in subscribers if db.still_due_with_settings(sub)]
    if not subscribers:
        return
    bot = Bot(token=config.bot_token)
    groups: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for sub in subscribers:
        key = (sub['level'], sub['learning_language'])
        groups.setdefault(key, {}).setdefault(sub['explanation_language'], []).append(sub)
    failures = []
    for (level, learning), explanations in groups.items():
        explanations = {language: [sub for sub in group if db.still_due_with_settings(sub)]
                        for language, group in explanations.items()}
        explanations = {language: group for language, group in explanations.items() if group}
        if not explanations:
            continue
        try:
            expression, clip = select_localized_clip(level, learning)
        except Exception:
            log.exception('Failed to find content for %s/%s', level, learning)
            failures.append(f'{level}/{learning}')
            continue
        sent_count = 0
        for explanation, group in explanations.items():
            group = [sub for sub in group if db.still_due_with_settings(sub)]
            if not group:
                continue
            try:
                caption = localized_caption(expression.text, clip, level, learning, explanation)
            except Exception:
                log.exception('Failed to create explanation for %s/%s/%s', level, learning, explanation)
                failures.append(f'{level}/{learning}/{explanation}')
                continue
            for sub in group:
                try:
                    if not db.still_due_with_settings(sub):
                        log.info('Subscriber %s is no longer due with these settings', sub['chat_id'])
                        continue
                    sent, failed = await broadcast(bot, [sub['chat_id']], str(clip.path), caption)
                    if sent:
                        sent_count += 1
                        if not db.advance_due_after_delivery(sub['chat_id'], sub['settings_updated_at']):
                            log.info('New subscriber schedule was left unchanged')
                    elif failed:
                        failures.append(f"chat {sub['chat_id']}")
                except Exception:
                    log.exception('Failed delivery bookkeeping for chat %s', sub['chat_id'])
                    failures.append(f"chat {sub['chat_id']}")
        if sent_count:
            try:
                db.mark_phrase_sent(level, expression.text, expression.topic, clip.clip_id, clip.title, learning)
            except Exception:
                log.exception('Failed to record phrase for %s/%s', level, learning)
                failures.append(f'{level}/{learning} history')
        print(f'::notice title=Level {level} delivery::{sent_count} sent', flush=True)
    if failures:
        raise RuntimeError(f'Failed to deliver {len(failures)} group(s) or subscriber(s)')

def main() -> None:
    from contextlib import ExitStack

    import delivery_store
    import preparation
    from reliable_delivery import Stats, run

    config.validate('database_url', 'bot_token')
    db.init_db()
    with delivery_store.worker_lock() as acquired:
        if not acquired:
            raise RuntimeError('Delivery worker lock unavailable; retry rather than reporting an idle success')
        preparation.cleanup()
        subscribers = db.due_subscribers()
        if not subscribers:
            prepared, failed = preparation.prepare([sub for sub in db.due_subscribers(preparation.LOOKAHEAD_MINUTES) if sub['due_at'] > datetime.now(timezone.utc)], select_localized_clip, localized_caption)
            db.record_delivery_run('failed' if failed else ('completed' if prepared else 'idle'), 0)
            log.info('Lookahead: %s slots prepared, %s failed', prepared, failed)
            if failed:
                raise RuntimeError('Lookahead preparation failed; will retry next tick')
            return
        stats = Stats()
        started = time.monotonic()
        status = 'failed'


        try:
            # Send due lessons first, so future preparation cannot delay them.
            with ExitStack() as media:
                def restore_clip(content):
                    return media.enter_context(preparation.restore(content, reload_verified_clip))
                asyncio.run(run(subscribers, Bot(token=config.bot_token), select_localized_clip,
                                localized_caption, restore_clip, stats, prepared_lookup=preparation.ready, shared_queue=True))
            prepared, failed = preparation.prepare([sub for sub in db.due_subscribers(preparation.LOOKAHEAD_MINUTES) if sub['due_at'] > datetime.now(timezone.utc)], select_localized_clip, localized_caption)
            log.info('Lookahead: %s slots prepared, %s failed', prepared, failed)
            status = 'failed' if stats.failed or stats.uncertain or failed else 'completed'
        finally:
            try:
                delivery_store.record_run(status, len(subscribers), stats.dict(), time.monotonic() - started)
            except Exception:  # noqa: BLE001 - telemetry must not undo or mask delivery outcomes
                log.warning('Run summary persistence unavailable; consult slot ledger')
                status = 'failed'
            print(f'::notice title=SceneLingo delivery::{stats.dict()}', flush=True)
        if status == 'failed':
            raise RuntimeError('Delivery had failed or uncertain outcomes; inspect the private dashboard')


if __name__ == '__main__':
    main()
