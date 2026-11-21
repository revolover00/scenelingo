from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import multilingual


def test_generated_expressions_are_checked(monkeypatch):
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"expressions":[{"text":"Hola amigo", "topic":"greetings"},{"text":"seen", "topic":"work"}]}'))])
    monkeypatch.setattr(multilingual, 'client', lambda: fake)
    assert multilingual.expressions('es', 'A2', {'seen'}, []) == [('Hola amigo', 'greetings')]
    with pytest.raises(ValueError):
        multilingual.expressions('xx', 'A2', set(), [])


def test_audio_verification_rejects_wrong_language_or_phrase(monkeypatch, tmp_path):
    clip = tmp_path / 'sample.mp4'
    clip.write_bytes(b'fake video')
    fake = MagicMock()
    monkeypatch.setattr(multilingual, 'client', lambda: fake)
    fake.audio.transcriptions.create.return_value = SimpleNamespace(language='english', text='Nice to meet you.')
    assert multilingual.verify_audio(clip, 'Nice to meet you', 'en')
    assert not multilingual.verify_audio(clip, 'Nice to meet you', 'es')
    assert not multilingual.verify_audio(clip, 'Good morning', 'en')


def test_stream_hint_avoids_transcribing_wrong_language(monkeypatch, tmp_path):
    clip = tmp_path / 'sample.mp4'
    clip.write_bytes(b'fake')
    fake = MagicMock()
    monkeypatch.setattr(multilingual, 'client', lambda: fake)
    monkeypatch.setattr(multilingual.shutil, 'which', lambda name: '/usr/bin/ffprobe')
    monkeypatch.setattr(multilingual.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='{"streams":[{"tags":{"language":"eng"}}]}'))
    assert not multilingual.verify_audio(clip, 'こんにちは', 'ja')
    fake.audio.transcriptions.create.assert_not_called()
    assert multilingual.likely_audio_language(clip, 'en')


def test_unknown_stream_language_falls_back_to_transcription(monkeypatch, tmp_path):
    monkeypatch.setattr(multilingual.shutil, 'which', lambda name: '/usr/bin/ffprobe')
    monkeypatch.setattr(multilingual.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='{"streams":[{"tags":{"language":"und"}}]}'))
    assert multilingual.likely_audio_language(tmp_path / 'clip.mp4', 'ja')


def test_single_word_expression_is_rejected_for_space_delimited_language(monkeypatch):
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"expressions":[{"text":"Hola", "topic":"greeting"},{"text":"Muchas gracias", "topic":"thanks"}]}'))])
    monkeypatch.setattr(multilingual, 'client', lambda: fake)
    assert multilingual.expressions('es', 'A2', set(), []) == [('Muchas gracias', 'thanks')]


def test_bundled_ffmpeg_can_identify_wrong_audio_without_ffprobe(monkeypatch, tmp_path):
    monkeypatch.setattr(multilingual.shutil, 'which', lambda name: None)
    monkeypatch.setattr(multilingual, 'ffmpeg_executable', lambda: '/bundled/ffmpeg')
    monkeypatch.setattr(multilingual.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(
        stderr='  Stream #0:1(eng): Audio: aac, 48000 Hz', stdout=''))
    assert not multilingual.likely_audio_language(tmp_path / 'clip.mp4', 'ja')
    assert multilingual.likely_audio_language(tmp_path / 'clip.mp4', 'en')


def test_cached_transcript_skips_provider_and_still_checks_language(monkeypatch, tmp_path):
    path = tmp_path / 'clip.mp4'; path.write_bytes(b'movie')
    monkeypatch.setattr(multilingual, 'likely_audio_language', lambda *args: True)
    monkeypatch.setattr(multilingual.audio_cache, 'get', lambda _: ('english', "Let's cut to the chase"))
    fake = MagicMock()
    monkeypatch.setattr(multilingual, 'client', lambda: fake)
    assert multilingual.verify_audio(path, 'Let us cut to the chase', 'en')
    assert not multilingual.verify_audio(path, 'Let us cut to the chase', 'fr')
    assert not multilingual.verify_audio(path, 'Something entirely different', 'en')
    fake.audio.transcriptions.create.assert_not_called()


def test_successful_transcript_is_cached_but_provider_failure_is_not(monkeypatch, tmp_path):
    path = tmp_path / 'clip.mp4'; path.write_bytes(b'movie')
    monkeypatch.setattr(multilingual, 'likely_audio_language', lambda *args: True)
    monkeypatch.setattr(multilingual.audio_cache, 'get', lambda _: None)
    fake = MagicMock()
    fake.audio.transcriptions.create.return_value = SimpleNamespace(language='english', text='Hello there')
    monkeypatch.setattr(multilingual, 'client', lambda: fake)
    save = MagicMock(); monkeypatch.setattr(multilingual.audio_cache, 'save', save)
    assert multilingual.transcript_for_language(path, 'en') == 'Hello there'
    save.assert_called_once()
    save.reset_mock(); fake.audio.transcriptions.create.side_effect = RuntimeError('provider limit')
    with pytest.raises(RuntimeError):
        multilingual.transcript_for_language(path, 'en')
    save.assert_not_called()
