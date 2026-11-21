import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import daily_job
import phrases
import pytest


@pytest.fixture(autouse=True)
def no_live_source_requests(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("test source unavailable")
    monkeypatch.setattr(daily_job.source_first, "find_expression_clip", unavailable)


def test_levels_have_multiple_topics_and_full_expressions():
    assert set(phrases.BANK) == set(phrases.LEVELS)
    for entries in phrases.BANK.values():
        assert len(entries) >= 20
        assert len({p.topic for p in entries}) >= 5
        assert all(len(p.text.split()) >= 2 for p in entries)


def test_candidates_exclude_seen_and_prefer_new_topics():
    entries = phrases.BANK['A2']
    seen = {entries[0].text.casefold()}
    result = phrases.candidates('A2', seen, ['greetings'])
    assert all(p.text.casefold() not in seen for p in result)
    assert result[0].topic != 'greetings'


def test_groups_receive_their_own_expression(monkeypatch):
    builds = []
    marked = []
    async def send(bot, chat_ids, path, caption):
        builds.append((chat_ids, caption))
        return len(chat_ids), 0
    monkeypatch.setattr(daily_job, 'Bot', lambda **kwargs: object())
    monkeypatch.setattr(daily_job, 'build_message', lambda level: (
        phrases.BANK[level][0], SimpleNamespace(path='/clip', clip_id=level, title='Movie'), level))
    monkeypatch.setattr(daily_job, 'broadcast', send)
    monkeypatch.setattr(daily_job.db, 'mark_phrase_sent', lambda *args: marked.append(args))
    asyncio.run(daily_job.run_groups({'A2': [1, 2], 'C1': [3]}))
    assert builds == [([1, 2], 'A2'), ([3], 'C1')]
    assert [x[0] for x in marked] == ['A2', 'C1']


def test_failed_delivery_does_not_mark_expression(monkeypatch):
    import pytest
    marked = []
    monkeypatch.setattr(daily_job, 'Bot', lambda **kwargs: object())
    monkeypatch.setattr(daily_job, 'build_message', lambda level: (
        phrases.BANK[level][0], SimpleNamespace(path='/clip', clip_id=level, title='Movie'), 'caption'))
    monkeypatch.setattr(daily_job, 'broadcast', AsyncMock(return_value=(0, 1)))
    monkeypatch.setattr(daily_job.db, 'mark_phrase_sent', lambda *args: marked.append(args))
    with pytest.raises(RuntimeError, match='A2'):
        asyncio.run(daily_job.run_groups({'A2': [1]}))
    assert not marked


def test_only_due_users_are_sent_and_advanced(monkeypatch):
    sent, advanced, marked = [], [], []
    users = [{'chat_id': 12, 'level': 'A2', 'learning_language': 'en', 'explanation_language': 'ar', 'settings_updated_at': 'v1'},
             {'chat_id': 13, 'level': 'A2', 'learning_language': 'en', 'explanation_language': 'ar', 'settings_updated_at': None}]
    monkeypatch.setattr(daily_job, 'Bot', lambda **kwargs: object())
    monkeypatch.setattr(daily_job, 'select_localized_clip', lambda level, learning: (
        phrases.BANK[level][0], SimpleNamespace(path='/clip', clip_id='id', title='Movie')))
    monkeypatch.setattr(daily_job, 'localized_caption', lambda *args: 'caption')
    async def send(bot, ids, path, caption):
        sent.extend(ids)
        return (1, 0) if ids == [12] else (0, 1)
    monkeypatch.setattr(daily_job, 'broadcast', send)
    monkeypatch.setattr(daily_job.db, 'still_due_with_settings', lambda sub: True)
    monkeypatch.setattr(daily_job.db, 'advance_due_after_delivery', lambda *args: advanced.append(args) or True)
    monkeypatch.setattr(daily_job.db, 'mark_phrase_sent', lambda *args: marked.append(args))
    import pytest
    with pytest.raises(RuntimeError):
        asyncio.run(daily_job.run_due_subscribers(users))
    assert sent == [12, 13]
    assert advanced == [(12, 'v1')]
    assert len(marked) == 1


def test_unverified_clip_fails_without_sending(monkeypatch):
    import pytest
    monkeypatch.setattr(daily_job, 'Bot', lambda **kwargs: object())
    send = AsyncMock()
    monkeypatch.setattr(daily_job, 'select_localized_clip', lambda *args: (_ for _ in ()).throw(RuntimeError('No verified clip')))
    monkeypatch.setattr(daily_job, 'broadcast', send)
    with pytest.raises(RuntimeError):
        asyncio.run(daily_job.run_due_subscribers([{'chat_id': 1, 'level': 'A2', 'learning_language': 'ja', 'explanation_language': 'ar', 'settings_updated_at': None}]))
    send.assert_not_called()


def test_changed_settings_or_unsubscribe_prevents_delivery(monkeypatch):
    monkeypatch.setattr(daily_job, 'Bot', lambda **kwargs: object())
    monkeypatch.setattr(daily_job, 'select_localized_clip', lambda *args: (
        phrases.BANK['A2'][0], SimpleNamespace(path='/clip', clip_id='id', title='Movie')))
    monkeypatch.setattr(daily_job, 'localized_caption', lambda *args: 'caption')
    monkeypatch.setattr(daily_job.db, 'still_due_with_settings', lambda sub: False)
    send = AsyncMock()
    monkeypatch.setattr(daily_job, 'broadcast', send)
    asyncio.run(daily_job.run_due_subscribers([{'chat_id': 1, 'level': 'A2', 'learning_language': 'en', 'explanation_language': 'ar', 'settings_updated_at': None}]))
    send.assert_not_called()


def test_localized_build_passes_correct_verifier_and_language(monkeypatch, tmp_path):
    import clip_cafe
    import multilingual
    from preferences import LANGUAGES
    path = tmp_path / 'sample.mp4'
    path.write_bytes(b'fake')
    checked = []
    monkeypatch.setattr(daily_job.db, 'phrase_history', lambda *args: (set(), []))
    monkeypatch.setattr(daily_job.source_first, 'find_expression_clip', lambda *args: (_ for _ in ()).throw(RuntimeError('none')))
    monkeypatch.setattr(multilingual, 'expressions', lambda *args: [('example phrase', 'greeting')])
    monkeypatch.setattr(multilingual, 'meaning', lambda text, learning, explanation, level: f'{learning}/{explanation}/{level}')
    monkeypatch.setattr(multilingual, 'verify_audio', lambda p, phrase, lang: checked.append((p, phrase, lang)) or True)
    def find(text, *, verify, audio_language):
        assert verify(path, text)
        assert checked[-1][2] == audio_language
        return SimpleNamespace(path=path, clip_id='id', title='Movie', url='https://clip.cafe/movie/')
    monkeypatch.setattr(clip_cafe, 'find_clip', find)
    for entry in LANGUAGES:
        lang = entry['code']
        phrase, _clip, caption = daily_job.build_localized_message('A2', lang, 'ar')
        assert phrase.text in caption
        assert f'{lang}/ar/A2' in caption
        assert checked[-1][2] == lang


def test_exhausted_english_bank_tries_new_generated_expressions(monkeypatch, tmp_path):
    import clip_cafe
    import multilingual
    seen = {p.text.casefold() for p in phrases.BANK['A2']}
    monkeypatch.setattr(daily_job.db, 'phrase_history', lambda *args: (seen, []))
    monkeypatch.setattr(multilingual, 'expressions', lambda *args: [('A fresh sentence', 'new topic')])
    monkeypatch.setattr(multilingual, 'meaning', lambda *args: 'meaning')
    seen_queries = []
    def find(text, **kwargs):
        seen_queries.append(text)
        return SimpleNamespace(path=tmp_path / 'clip', clip_id='id', title='Movie', url='https://clip.cafe/movie/')
    monkeypatch.setattr(clip_cafe, 'find_clip', find)
    result, _, _ = daily_job.build_localized_message('A2', 'en', 'ar')
    assert result.text == 'A fresh sentence'
    assert seen_queries == ['A fresh sentence']


def test_source_first_build_uses_verified_selected_expression(monkeypatch):
    monkeypatch.setattr(daily_job.db, 'phrase_history', lambda *args: (set(), []))
    clip = SimpleNamespace(path='/clip', clip_id='id', title='Movie', url='https://clip.cafe/movie/')
    monkeypatch.setattr(daily_job.source_first, 'find_expression_clip', lambda *args: (('これは何ですか', 'questions'), clip))
    monkeypatch.setattr(daily_job.multilingual, 'meaning', lambda *args: 'meaning')
    expression, found, caption = daily_job.build_localized_message('A2', 'ja', 'ar')
    assert expression.text == 'これは何ですか' and found is clip
    assert expression.text in caption and 'meaning' in caption


def test_same_learning_group_reuses_clip_across_explanation_languages(monkeypatch):
    users = [{'chat_id': i, 'level': 'A2', 'learning_language': 'ja', 'explanation_language': exp, 'settings_updated_at': None}
             for i, exp in [(1, 'ar'), (2, 'en')]]
    clip = SimpleNamespace(path='/clip', clip_id='id', title='Movie')
    selected, captions, marked = [], [], []
    monkeypatch.setattr(daily_job, 'Bot', lambda **kwargs: object())
    monkeypatch.setattr(daily_job, 'select_localized_clip', lambda *args: (selected.append(args) or (phrases.BANK['A2'][0], clip)))
    monkeypatch.setattr(daily_job, 'localized_caption', lambda text, clip, level, learning, explanation: captions.append(explanation) or explanation)
    monkeypatch.setattr(daily_job.db, 'still_due_with_settings', lambda sub: True)
    monkeypatch.setattr(daily_job.db, 'advance_due_after_delivery', lambda *args: True)
    monkeypatch.setattr(daily_job.db, 'mark_phrase_sent', lambda *args: marked.append(args))
    monkeypatch.setattr(daily_job, 'broadcast', AsyncMock(return_value=(1, 0)))
    asyncio.run(daily_job.run_due_subscribers(users))
    assert selected == [('A2', 'ja')]
    assert captions == ['ar', 'en'] and len(marked) == 1


def test_failed_explanation_does_not_block_other_languages(monkeypatch):
    import pytest
    users = [{'chat_id': i, 'level': 'A2', 'learning_language': 'ja', 'explanation_language': exp, 'settings_updated_at': None}
             for i, exp in [(1, 'ar'), (2, 'en')]]
    clip = SimpleNamespace(path='/clip', clip_id='id', title='Movie')
    sent, marked = [], []
    monkeypatch.setattr(daily_job, 'Bot', lambda **kwargs: object())
    monkeypatch.setattr(daily_job, 'select_localized_clip', lambda *args: (phrases.BANK['A2'][0], clip))
    def caption(text, clip, level, learning, explanation):
        if explanation == 'ar':
            raise RuntimeError('temporary error')
        return 'caption'
    monkeypatch.setattr(daily_job, 'localized_caption', caption)
    monkeypatch.setattr(daily_job.db, 'still_due_with_settings', lambda sub: True)
    monkeypatch.setattr(daily_job.db, 'advance_due_after_delivery', lambda *args: True)
    monkeypatch.setattr(daily_job.db, 'mark_phrase_sent', lambda *args: marked.append(args))
    async def send(bot, ids, path, caption):
        sent.extend(ids)
        return 1, 0
    monkeypatch.setattr(daily_job, 'broadcast', send)
    with pytest.raises(RuntimeError):
        asyncio.run(daily_job.run_due_subscribers(users))
    assert sent == [2] and len(marked) == 1


def test_reloading_saved_lesson_cannot_substitute_another_movie(monkeypatch):
    import pytest
    lesson={'phrase':'Good for you','learning_language':'en','clip_id':'original','source_url':'https://clip.cafe/original/'}
    monkeypatch.setattr(daily_job.clip_cafe,'load_clip',lambda *args,**kwargs:SimpleNamespace(clip_id='different'))
    with pytest.raises(RuntimeError,match='source substitution'):
        daily_job.reload_verified_clip(lesson)
    original=SimpleNamespace(clip_id='original')
    monkeypatch.setattr(daily_job.clip_cafe,'load_clip',lambda *args,**kwargs:original)
    assert daily_job.reload_verified_clip(lesson) is original


def test_unavailable_unseen_english_bank_refreshes_without_recycling(monkeypatch):
    monkeypatch.setattr(daily_job.db, 'phrase_history', lambda *args: (set(), []))
    monkeypatch.setattr(phrases, 'candidates', lambda *args: [phrases.Phrase('Unavailable phrase', 'work')])
    generated = []
    def refresh(language, level, excluded, topics):
        generated.append((language, level, excluded))
        return [('Unavailable phrase', 'work'), ('A fresh expression', 'discussion')]
    monkeypatch.setattr(daily_job.multilingual, 'expressions', refresh)
    queries = []
    clip = SimpleNamespace(clip_id='verified')
    def find(text, **kwargs):
        queries.append(text)
        assert kwargs['audio_language'] == 'en' and callable(kwargs['verify'])
        if text == 'Unavailable phrase':
            raise RuntimeError('no matching audio')
        return clip
    monkeypatch.setattr(daily_job.clip_cafe, 'find_clip', find)
    expression, found = daily_job.select_localized_clip('C1', 'en')
    assert expression.text == 'A fresh expression' and found is clip
    assert queries == ['Unavailable phrase', 'A fresh expression']
    assert generated == [('en', 'C1', {'unavailable phrase'})]


def test_fresh_search_failure_never_accepts_unverified_audio(monkeypatch):
    import pytest
    monkeypatch.setattr(daily_job.db, 'phrase_history', lambda *args: (set(), []))
    monkeypatch.setattr(phrases, 'candidates', lambda *args: [])
    monkeypatch.setattr(daily_job.multilingual, 'expressions', lambda *args: [('Fresh but wrong audio', 'work')])
    def reject(*args, **kwargs):
        raise RuntimeError('audio mismatch')
    monkeypatch.setattr(daily_job.clip_cafe, 'find_clip', reject)
    with pytest.raises(RuntimeError, match='No verified clip'):
        daily_job.select_localized_clip('C1', 'en')
