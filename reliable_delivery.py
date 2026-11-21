"""Demand-driven delivery with durable slot claims and explicit uncertain outcomes.

Telegram has no sendVideo idempotency key: a timeout is ambiguous, not retryable.
This favors avoiding duplicate replays over silently claiming exactly-once delivery.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    RetryAfter,
    TelegramError,
)

import db
import delivery_store as store
from async_file import open_binary_async
from config import config

log = logging.getLogger(__name__)


@dataclass
class Stats:
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    uncertain: int = 0
    content_requests: int = 0
    explanation_requests: int = 0
    cache_hits: int = 0

    def dict(self):
        return asdict(self)


def keyboard(content_id, language):
    ar = language == 'ar'
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('احفظ التعبير ⭐' if ar else 'Save expression ⭐', callback_data=f'lesson_save:{content_id}')],
        [InlineKeyboardButton('الشرح مش واضح' if ar else 'Unclear explanation', callback_data=f'lesson_explanation:{content_id}'),
         InlineKeyboardButton('مشكلة في المقطع' if ar else 'Clip issue', callback_data=f'lesson_clip:{content_id}')],
    ])


async def send_video(bot, chat_id, video, caption, markup, sleep=asyncio.sleep):
    """Retry ONLY explicit rate-limit refusals; never blindly retry timeouts."""
    for attempt in range(3):
        try:
            result = await bot.send_video(chat_id=chat_id, video=video, caption=caption, reply_markup=markup)
            return 'sent', None, result
        except RetryAfter as error:
            seconds = error.retry_after.total_seconds() if hasattr(error.retry_after, 'total_seconds') else float(error.retry_after)
            if attempt == 2 or seconds > 60:
                return 'failed', 'rate_limited', None
            if hasattr(video, 'seek'):
                video.seek(0)
            await sleep(max(0, seconds) + 1)
        except Forbidden:
            return 'blocked', 'bot_blocked', None
        except BadRequest as error:
            message = str(error).lower()
            invalid_file = any(term in message for term in ('file identifier', 'file_id', 'file reference'))
            return 'failed', 'cached_media_invalid' if invalid_file else 'telegram_rejected', None
        except NetworkError:
            return 'uncertain', 'network_timeout', None
        except TelegramError:
            return 'uncertain', 'telegram_unknown', None
    raise AssertionError('Unreachable')


async def run(subscribers, bot, select, explain, reload_clip, stats=None, prepared_lookup=None, shared_queue=False):
    stats = stats or Stats()
    groups = defaultdict(list)
    if shared_queue:
        subscribers = store.assign_cached(subscribers)
    for sub in subscribers:
        if not db.still_due_with_settings(sub):
            stats.skipped += 1
            continue
        previous = store.state(sub)
        if previous and previous['status'] in ('sent', 'uncertain', 'blocked', 'skipped'):
            if previous['status'] == 'blocked':
                db.remove_subscriber(sub['chat_id'])
            else:
                db.advance_due_after_delivery(sub['chat_id'], sub['settings_updated_at'])
            stats.skipped += 1
            continue
        if previous and previous['status'] == 'sending':
            stats.skipped += 1
            continue
        if previous and previous['status'] == 'failed':
            if previous['attempts'] >= 3:
                db.advance_due_after_delivery(sub['chat_id'], sub['settings_updated_at'])
                stats.skipped += 1
                continue
            if previous['retry_at'] and previous['retry_at'] > datetime.now(UTC):
                stats.skipped += 1
                continue
        # Retrying an explicitly refused send must use its original lesson.
        pinned = previous['content_id'] if previous else ((prepared_lookup(sub) if prepared_lookup else None) or sub.get('queue_content_id'))
        key = (sub['level'], sub['learning_language'], pinned)
        groups[key].append(sub)
    for (level, learning, pinned), audience in groups.items():
        eligible = [sub for sub in audience if db.still_due_with_settings(sub)]
        stats.skipped += len(audience) - len(eligible)
        audience = eligible
        if not audience:
            continue
        sent_before = stats.sent
        local_clip = None
        stage = 'lookup'
        try:
            content = store.get_content(pinned) if pinned else store.cached(level, learning, [s['chat_id'] for s in audience])
            if content:
                if content['telegram_file_id']:
                    stats.cache_hits += 1
                else:
                    stats.content_requests += 1
                    stage = 'restore_saved_media'
                    local_clip = reload_clip(content)
            else:
                stats.content_requests += 1
                stage = 'select_new_clip'
                expression, local_clip = select(level, learning)
                content = store.content(expression, local_clip, level, learning)
                stage = 'check_unseen'
                if store.seen_by(content['id'], [s['chat_id'] for s in audience]):
                    raise RuntimeError('No unseen verified content for this audience')
        except Exception as error:  # noqa: BLE001 - isolate external content-provider failures per group
            # Store only a classified outcome; never leak source URLs or secrets.
            log.warning('Content unavailable for %s/%s at %s (%s)', level, learning, stage, type(error).__name__)
            stats.failed += len(audience)
            continue
        invalid_cached = False
        explanations = defaultdict(list)
        for sub in audience:
            explanations[sub['explanation_language']].append(sub)
        for language, recipients in explanations.items():
            if invalid_cached:
                stats.skipped += len(recipients)
                continue
            eligible = [s for s in recipients if db.still_due_with_settings(s)]
            stats.skipped += len(recipients) - len(eligible)
            recipients = eligible
            if not recipients:
                continue
            try:
                caption = store.get_caption(content['id'], language)
                if caption:
                    stats.cache_hits += 1
                else:
                    stats.explanation_requests += 1
                    caption = explain(content['phrase'], SimpleNamespace(title=content['video_title'], url=content['source_url']), level, learning, language)
                    store.save_caption(content['id'], language, caption)
            except Exception as error:  # noqa: BLE001 - mark provider failures for this explanation group
                log.warning('Explanation unavailable (%s)', type(error).__name__)
                stats.failed += len(recipients)
                continue
            for recipient_index, sub in enumerate(recipients):
                if not db.still_due_with_settings(sub):
                    stats.skipped += 1
                    continue
                attempt_id = store.claim(sub, content['id'])
                if not attempt_id:
                    stats.skipped += 1
                    continue
                try:
                    if content['telegram_file_id']:
                        outcome, code, message = await send_video(bot, sub['chat_id'], content['telegram_file_id'], caption, keyboard(content['id'], sub.get('ui_language', 'ar')))
                    else:
                        async with open_binary_async(local_clip.path) as video:
                            outcome, code, message = await send_video(bot, sub['chat_id'], video, caption, keyboard(content['id'], sub.get('ui_language', 'ar')))
                except OSError:
                    outcome, code, message = 'failed', 'local_media_unavailable', None
                except Exception:  # noqa: BLE001 - preserve the durable uncertain-send state for any failure
                    # An unclassified error after starting an upload is ambiguous.
                    store.finish(attempt_id, 'uncertain', 'unclassified_send_error')
                    stats.uncertain += 1
                    continue
                # Persist the receipt BEFORE advancing the due time. If this write
                # fails the durable 'sending' claim prevents a blind resend.
                store.finish(attempt_id, outcome, code, getattr(message, 'message_id', None))
                if outcome == 'sent':
                    stats.sent += 1
                    db.advance_due_after_delivery(sub['chat_id'], sub['settings_updated_at'])
                    uploaded = getattr(getattr(message, 'video', None), 'file_id', None)
                    if uploaded:
                        content['telegram_file_id'] = uploaded
                        store.file_id(content['id'], uploaded)
                elif outcome == 'blocked':
                    stats.failed += 1
                    db.remove_subscriber(sub['chat_id'])
                elif outcome == 'uncertain':
                    stats.uncertain += 1
                    db.advance_due_after_delivery(sub['chat_id'], sub['settings_updated_at'])
                else:
                    stats.failed += 1
                    if code == 'cached_media_invalid':
                        store.file_id(content['id'], None)
                        invalid_cached = True
                        # Explicit rejection is safe to retry after reloading the
                        # original verified lesson. Never send a known-invalid ID
                        # to the remaining recipients in this cohort.
                        stats.skipped += len(recipients) - recipient_index - 1
                        break
                    if code not in ('rate_limited', 'cached_media_invalid'):
                        db.advance_due_after_delivery(sub['chat_id'], sub['settings_updated_at'])
                await asyncio.sleep(config.send_delay)
        # History is best effort, and never controls slot deduplication.
        if stats.sent > sent_before:
            try:
                db.mark_phrase_sent(level, content['phrase'], content['topic'], content['clip_id'], content['video_title'], learning)
            except Exception:
                # The durable receipt already controls replay prevention/history.
                log.warning('Legacy phrase summary unavailable; delivery receipt retained')
    return stats
