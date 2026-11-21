import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut

import reliable_delivery as worker


def subscriber(chat=1):
    return {'chat_id': chat, 'due_at': datetime(2026,1,1,tzinfo=UTC),
                'level': 'B1','learning_language': 'en','explanation_language': 'ar',
                'ui_language': 'ar','settings_updated_at': None}


def content():
    return {'id': 1,'telegram_file_id': 'reusable-file','phrase': 'Good for you','topic': 'social',
                'level': 'B1','learning_language': 'en','video_title': 'Movie','source_url': 'https://example.com','clip_id': '1'}


def fixture(monkeypatch):
    monkeypatch.setattr(worker.store,'assign_cached',lambda subs:subs)
    monkeypatch.setattr(worker.db,'still_due_with_settings',lambda _:True)
    monkeypatch.setattr(worker.db,'advance_due_after_delivery',Mock(return_value=True))
    monkeypatch.setattr(worker.db,'remove_subscriber',Mock())
    monkeypatch.setattr(worker.db,'mark_phrase_sent',Mock())
    monkeypatch.setattr(worker.store,'state',lambda _:None)
    monkeypatch.setattr(worker.store,'claim',Mock(return_value=42))
    monkeypatch.setattr(worker.store,'finish',Mock())
    monkeypatch.setattr(worker.store,'cached',Mock(return_value=content()))
    monkeypatch.setattr(worker.store,'get_caption',Mock(return_value='Cached lesson'))
    monkeypatch.setattr(worker.store,'save_caption',Mock())
    monkeypatch.setattr(worker.store,'file_id',Mock())
    monkeypatch.setattr(worker.store,'seen_by',Mock(return_value=False))
    monkeypatch.setattr(worker,'config',SimpleNamespace(send_delay=0))
    bot=SimpleNamespace(send_video=AsyncMock(return_value=SimpleNamespace(message_id=90,video=SimpleNamespace(file_id='uploaded'))))
    return bot


def run(bot, audience=None, select=None, explain=None):
    return asyncio.run(worker.run([subscriber()] if audience is None else audience,bot,
        select or Mock(side_effect=AssertionError('No source generation expected')),
        explain or Mock(side_effect=AssertionError('No AI explanation expected')),
        Mock(side_effect=AssertionError('No reload expected'))))


def test_cached_delivery_reuses_video_and_caption_without_ai(monkeypatch):
    bot=fixture(monkeypatch)
    stats=run(bot)
    assert stats.sent==1 and stats.content_requests==0 and stats.explanation_requests==0
    assert stats.cache_hits==2
    assert bot.send_video.call_args.kwargs['video']=='reusable-file'
    worker.store.finish.assert_called_once_with(42,'sent',None,90)


@pytest.mark.parametrize('state', ['sent','uncertain','sending','blocked'])
def test_existing_slot_never_resends_or_generates(monkeypatch,state):
    bot=fixture(monkeypatch)
    monkeypatch.setattr(worker.store,'state',lambda _:{'status':state})
    assert run(bot).skipped==1
    bot.send_video.assert_not_called()
    worker.store.cached.assert_not_called()


def test_blocked_chat_is_deactivated(monkeypatch):
    bot=fixture(monkeypatch)
    bot.send_video.side_effect=Forbidden('blocked')
    stats=run(bot)
    assert stats.failed==1
    worker.db.remove_subscriber.assert_called_once_with(1)
    worker.store.finish.assert_called_once_with(42,'blocked','bot_blocked',None)


def test_timeout_is_uncertain_and_never_blindly_retried(monkeypatch):
    bot=fixture(monkeypatch)
    bot.send_video.side_effect=TimedOut()
    stats=run(bot)
    assert stats.uncertain==1
    assert bot.send_video.call_count==1
    worker.store.finish.assert_called_once_with(42,'uncertain','network_timeout',None)


def test_rate_limit_retries_only_explicit_refusals(monkeypatch):
    fixture(monkeypatch)
    bot=SimpleNamespace(send_video=AsyncMock(side_effect=[RetryAfter(1),SimpleNamespace(message_id=1)]))
    sleep=AsyncMock()
    outcome,_,_=asyncio.run(worker.send_video(bot,1,'file','caption',None,sleep=sleep))
    assert outcome=='sent' and bot.send_video.call_count==2
    sleep.assert_awaited_once_with(2)


def test_rate_limit_long_wait_is_deferred_without_sleeping(monkeypatch):
    fixture(monkeypatch)
    bot=SimpleNamespace(send_video=AsyncMock(side_effect=RetryAfter(120)))
    sleep=AsyncMock()
    assert asyncio.run(worker.send_video(bot,1,'file','caption',None,sleep=sleep))[:2]==('failed','rate_limited')
    sleep.assert_not_called()


def test_bad_request_is_definite_rejection_not_ambiguous_timeout(monkeypatch):
    bot=fixture(monkeypatch)
    bot.send_video.side_effect=BadRequest('rejected')
    assert run(bot).failed==1
    worker.store.finish.assert_called_once_with(42,'failed','telegram_rejected',None)


def test_duplicate_claim_loses_without_sending(monkeypatch):
    bot=fixture(monkeypatch)
    monkeypatch.setattr(worker.store,'claim',lambda *_:None)
    assert run(bot).skipped==1
    bot.send_video.assert_not_called()


def test_ledger_write_failure_does_not_retry_telegram(monkeypatch):
    bot=fixture(monkeypatch)
    monkeypatch.setattr(worker.store,'finish',Mock(side_effect=RuntimeError('db unavailable')))
    with pytest.raises(RuntimeError):run(bot)
    assert bot.send_video.call_count==1
    worker.db.advance_due_after_delivery.assert_not_called()


def test_failed_send_waits_until_retry_time(monkeypatch):
    bot=fixture(monkeypatch)
    monkeypatch.setattr(worker.store,'state',lambda _:{'status':'failed','attempts':1,'retry_at':datetime.now(UTC)+timedelta(hours=1),'content_id':1})
    assert run(bot).skipped==1
    bot.send_video.assert_not_called()


def test_empty_or_stopped_audience_does_no_work(monkeypatch):
    bot=fixture(monkeypatch)
    assert run(bot,[]).sent==0
    monkeypatch.setattr(worker.db,'still_due_with_settings',lambda _:False)
    assert run(bot).skipped==1
    worker.store.cached.assert_not_called()


def test_matching_recipients_share_cached_lesson(monkeypatch):
    bot=fixture(monkeypatch)
    assert run(bot,[subscriber(1),subscriber(2)]).sent==2
    worker.store.cached.assert_called_once()
    worker.store.get_caption.assert_called_once()


def test_content_failure_does_not_send_wrong_level_or_fake_clip(monkeypatch):
    bot=fixture(monkeypatch)
    monkeypatch.setattr(worker.store,'cached',lambda *_:None)
    stats=run(bot,select=Mock(side_effect=RuntimeError('no verified clip')))
    assert stats.failed==1 and stats.content_requests==1
    bot.send_video.assert_not_called()


def test_expired_cached_file_is_invalidated_without_ambiguous_retries(monkeypatch):
    bot=fixture(monkeypatch)
    bot.send_video.side_effect=BadRequest('Wrong file identifier')
    assert run(bot).failed==1
    assert bot.send_video.call_count==1
    worker.store.file_id.assert_called_once_with(1,None)


def test_demand_disappears_before_explanation_skips_ai(monkeypatch):
    bot=fixture(monkeypatch)
    checks=iter([True,True,False])
    monkeypatch.setattr(worker.db,'still_due_with_settings',lambda _:next(checks))
    assert run(bot).skipped==1
    worker.store.get_caption.assert_not_called()
    bot.send_video.assert_not_called()


def test_one_blocked_recipient_does_not_prevent_next_delivery(monkeypatch):
    bot=fixture(monkeypatch)
    bot.send_video.side_effect=[Forbidden('blocked'),SimpleNamespace(message_id=90,video=None)]
    stats=run(bot,[subscriber(1),subscriber(2)])
    assert stats.sent==1 and stats.failed==1
    worker.db.remove_subscriber.assert_called_once_with(1)


def test_retry_exhaustion_skips_slot_without_generation(monkeypatch):
    bot=fixture(monkeypatch)
    monkeypatch.setattr(worker.store,'state',lambda _:{'status':'failed','attempts':3,'content_id':1})
    assert run(bot).skipped==1
    worker.db.advance_due_after_delivery.assert_called_once()
    worker.store.cached.assert_not_called()


def test_shared_queue_splits_mixed_audience_without_new_generation(monkeypatch):
    bot = fixture(monkeypatch)
    monkeypatch.setattr(worker.store, 'assign_cached', lambda subs: [dict(s, queue_content_id=s['chat_id']) for s in subs])
    monkeypatch.setattr(worker.store, 'get_content', lambda lesson: dict(content(), id=lesson))
    select, explain = Mock(), Mock()
    stats = asyncio.run(worker.run([subscriber(1),subscriber(2)], bot, select, explain, Mock(), shared_queue=True))
    assert stats.sent == 2
    select.assert_not_called()
    explain.assert_not_called()
    assert [c.args[1] for c in worker.store.claim.call_args_list] == [1,2]


def test_invalid_file_stops_cohort_and_preserves_schedule_for_safe_retry(monkeypatch):
    bot=fixture(monkeypatch)
    bot.send_video.side_effect=BadRequest('Wrong file identifier')
    stats=run(bot,[subscriber(1),subscriber(2)])
    assert stats.failed==1 and stats.skipped==1
    assert bot.send_video.call_count==1
    worker.db.advance_due_after_delivery.assert_not_called()


def test_legacy_summary_failure_does_not_abort_next_group(monkeypatch):
    bot=fixture(monkeypatch)
    worker.db.mark_phrase_sent.side_effect=RuntimeError('summary unavailable')
    users=[subscriber(1),dict(subscriber(2),level='B2')]
    assert run(bot,users).sent==2
    assert bot.send_video.call_count==2
