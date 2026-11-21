import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import multilingual
from lessons import LABELS, caption, compact, parse_lesson, render_lesson, units

DATA = {'meaning': 'مش قادر تكمّل أو تتحمّل أكتر.', 'usage': 'لما تكون مضغوط ومحتاج توضّح إنك وصلت لحدك.',
            'example': "I can’t take it anymore. I need a break.", 'translation': 'مش قادر أتحمّل أكتر. محتاج أرتاح.'}


def test_structured_lesson_is_readable_and_example_is_labeled_new():
    lesson = render_lesson(parse_lesson(json.dumps(DATA)), 'ar')
    result = caption('I can’t take it anymore', lesson, 'B2', 'en', 'ar', 'Example Movie', 'https://example.com/clip')
    for label in ['المعنى', 'تستخدمه إمتى؟', 'مثال جديد', 'ترجمة المثال']:
        assert label in result
    assert result.count('تعبير من مشهد') == 1
    assert DATA['example'] in result
    assert units(result) <= 1024


@pytest.mark.parametrize('raw', ['', 'not json', '{}', '{"meaning":42}', json.dumps({**DATA, 'usage': ''}), json.dumps({**DATA, 'example': 'x' * 2001})])
def test_malformed_lessons_fail_closed(raw):
    with pytest.raises(ValueError):
        parse_lesson(raw)


def test_lesson_payload_must_be_an_object():
    with pytest.raises(TypeError):
        parse_lesson('[]')


@pytest.mark.parametrize('language', list(LABELS))
def test_every_explanation_language_and_emoji_heavy_output_fits(language):
    data = {key: '🙂 ' * 300 for key in DATA}
    lesson = render_lesson(parse_lesson(json.dumps(data)), language)
    expression = 'A real verified expression'
    result = caption(expression, lesson, 'C2', 'en', language, 'Very long movie name ' * 80, 'https://example.com/' + 'x' * 500)
    assert expression in result
    assert units(result) <= 1024
    assert '\ufffd' not in result
    assert 'x' * 500 not in result


def test_plaintext_metadata_cannot_break_caption_or_add_url_lines():
    result = caption('Hello there', render_lesson(DATA, 'en'), 'A2', 'en', 'en', 'Movie\nNew line', 'https://example.com/\nBad')
    assert 'Movie New line' in result
    assert 'https://example.com/' not in result


def test_oversized_verified_expression_is_never_silently_truncated():
    with pytest.raises(ValueError):
        caption('word ' * 1000, render_lesson(DATA, 'en'), 'B1', 'en', 'en', 'Movie')


def test_json_contract_and_no_scene_hallucination_prompt(monkeypatch):
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(DATA)))])
    monkeypatch.setattr(multilingual, 'client', lambda: fake)
    result = multilingual.meaning('I can’t take it anymore', 'en', 'ar', 'B2')
    call = fake.chat.completions.create.call_args.kwargs
    assert call['response_format'] == {'type': 'json_object'}
    prompt = call['messages'][-1]['content']
    assert 'Egyptian Arabic' in prompt and 'have not watched the clip' in prompt
    assert 'المعنى' in result and 'مثال جديد' in result
    fake.chat.completions.create.assert_called_once()


def test_sanitizes_control_characters_and_preserves_natural_script():
    parsed = parse_lesson(json.dumps({**DATA, 'meaning': '\u202eمعنى\n\tواضح'}))
    assert parsed['meaning'] == 'معنى واضح'
    assert units(compact('🙂' * 40, 25)) <= 25
