from types import SimpleNamespace
from unittest.mock import MagicMock

import source_first


def response(text):
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    return client


def test_extraction_requires_actual_unseen_multiword_transcript(monkeypatch):
    monkeypatch.setattr(source_first.multilingual, 'client', lambda: response('{"text":"كيف حالك", "topic":"greeting"}'))
    assert source_first.extract_expression('مرحبا كيف حالك اليوم', 'ar', 'A2', set(), []) == ('كيف حالك', 'greeting')
    assert source_first.extract_expression('مرحبا صديقي', 'ar', 'A2', set(), []) is None
    assert source_first.extract_expression('مرحبا كيف حالك اليوم', 'ar', 'A2', {'كيف حالك'}, []) is None
    monkeypatch.setattr(source_first.multilingual, 'client', lambda: response('{"text":"مرحبا", "topic":"greeting"}'))
    assert source_first.extract_expression('مرحبا صديقي', 'ar', 'A2', set(), []) is None


def test_source_first_never_accepts_wrong_language_or_phrase(monkeypatch, tmp_path):
    import pytest
    monkeypatch.setattr(source_first, 'SEEDS', {'ja': ('こんにちは',)})
    monkeypatch.setattr(source_first.multilingual, 'transcript_for_language', lambda *args: 'さようなら')
    monkeypatch.setattr(source_first.random, 'shuffle', lambda x: None)
    monkeypatch.setattr(source_first, 'extract_expression', lambda *args: None)
    def search(seed, verify, audio_language, search_language, max_results, max_seconds):
        assert audio_language == 'ja'
        assert not verify(tmp_path / 'test.mp4', seed)
        raise RuntimeError('none')
    monkeypatch.setattr(source_first.clip_cafe, 'find_clip', search)
    with pytest.raises(RuntimeError):
        source_first.find_expression_clip('ja', 'A2', set(), [])


def test_english_search_can_select_verified_target_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(source_first, 'SEEDS', {'hi': ()})
    monkeypatch.setattr(source_first.random, 'shuffle', lambda x: None)
    monkeypatch.setattr(source_first.multilingual, 'transcript_for_language', lambda *args: 'बहुत बहुत धन्यवाद')
    monkeypatch.setattr(source_first, 'extract_expression', lambda *args: ('बहुत बहुत धन्यवाद', 'gratitude'))
    clip = object()
    def search(seed, verify, audio_language, search_language, max_results, max_seconds):
        assert audio_language == 'hi' and search_language == 'en'
        assert verify(tmp_path / 'test.mp4', seed)
        return clip
    monkeypatch.setattr(source_first.clip_cafe, 'find_clip', search)
    expression, found = source_first.find_expression_clip('hi', 'A2', set(), [])
    assert expression[0] == 'बहुत बहुत धन्यवाद' and found is clip


def test_english_search_hint_need_not_be_spoken_but_expression_must_be(monkeypatch, tmp_path):
    monkeypatch.setattr(source_first.random, 'shuffle', lambda x: None)
    monkeypatch.setattr(source_first.multilingual, 'transcript_for_language', lambda *args: 'We must consider all the implications before we proceed.')
    monkeypatch.setattr(source_first.multilingual, 'client', lambda: response('{"text":"consider all the implications", "topic":"judgment"}'))
    clip = object()
    def search(seed, verify, **kwargs):
        assert seed == 'consequences'
        assert verify(tmp_path / 'clip.mp4', seed)
        return clip
    monkeypatch.setattr(source_first.clip_cafe, 'find_clip', search)
    expression, found = source_first.find_expression_clip('en', 'C1', set(), [])
    assert expression[0] == 'consider all the implications' and found is clip
