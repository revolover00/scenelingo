"""Experimental source-first clip selection; no clip is accepted without audio checks."""
from __future__ import annotations

import json
import random

import clip_cafe
import multilingual
from ai_observability import tracked
from preferences import validate_language

# Seeds are search hints, not the expression sent to the learner. The actual
# expression is extracted and checked against the detected audio transcript.
SEEDS = {
    'en': ('consequences', 'underestimate', 'perspective', 'circumstances',
           'assumptions', 'compromise', 'inevitable', 'responsibility'),
    'es': ('gracias', 'hola', 'no lo sé', 'qué pasó'),
    'fr': ('merci', 'bonjour', 'je ne sais pas', 'ça va'),
    'pt': ('obrigado', 'olá', 'não sei', 'tudo bem'),
    'de': ('danke', 'hallo', 'ich weiß nicht', 'was ist los'),
    'ja': ('こんにちは', 'ありがとう', '大丈夫', 'わかりました'),
    'zh': ('谢谢', '你好', '没关系', '对不起'),
    'ar': ('مرحبا', 'شكرا', 'كيف حالك', 'لا أعرف'),
    'hi': ('नमस्ते', 'धन्यवाद', 'कैसे हो', 'मुझे पता'),
    'ru': ('спасибо', 'привет', 'извини', 'я не знаю'),
}


def extract_expression(transcript: str, language: str, level: str, seen: set[str], topics: list[str]):
    """Pick an exact transcript span at the requested level, or return None."""
    validate_language(language)
    prompt = (
        f'Choose one complete useful {multilingual.NAMES[language]} sentence or multi-word expression '
        f'suitable for CEFR {level} learners from this speech transcript. '
        'Copy it exactly, as a contiguous span. Do not invent, translate, paraphrase, or use a single word. '
        'Do not use a name, profanity or unrelated sound. If no suitable expression exists return null. '
        f'Prefer topics other than {", ".join(topics[:3])}. '
        f'Do not select these previously used or reserved expressions: {sorted(seen)[-100:]!r}. '
        f'Transcript: {transcript[:3000]!r}\n'
        'Return JSON only: {"text": "...", "topic": "..."}, or {"text": null}.')
    response = tracked('source_expression', multilingual.client().chat.completions.create,
        model=multilingual.config.groq_model, messages=[{'role': 'user', 'content': prompt}],
        temperature=0.1, max_tokens=250, response_format={'type': 'json_object'},
    )
    try:
        raw = json.loads(response.choices[0].message.content or '{}')
        text, topic = raw.get('text'), raw.get('topic')
    except (ValueError, AttributeError, TypeError):
        return None
    if not isinstance(text, str) or not isinstance(topic, str):
        return None
    text, topic = text.strip(), topic.strip()
    if not (2 <= len(text) <= 100 and 1 <= len(topic) <= 50 and '\n' not in text):
        return None
    if language not in {'zh', 'ja'} and len(text.split()) < 2:
        return None
    if text.casefold() in seen or not clip_cafe.matches(text, transcript):
        return None
    return text, topic


def find_expression_clip(language: str, level: str, seen: set[str], topics: list[str]):
    """Find a real clip first, then select a transcript-verified expression."""
    validate_language(language)
    seeds = [(seed, language) for seed in SEEDS.get(language, ())] if language != 'hi' else []
    # English subtitles can locate a scene even where the site's target-language
    # subtitle index is sparse (notably Hindi); audio is independently checked.
    seeds += [(seed, 'en') for seed in ('thank you', 'what happened', 'i dont know', 'lets go')]
    if language == 'en':
        seeds = [(seed, language) for seed in SEEDS['en']]
    random.shuffle(seeds)
    # Bound the search per run so one difficult language cannot stall all users.
    for seed, search_language in seeds[:2]:
        chosen = None
        def verify(path, search, current_search_language=search_language):
            nonlocal chosen
            transcript = multilingual.transcript_for_language(path, language)
            if transcript is None or (language != 'en' and current_search_language == language and not clip_cafe.matches(search, transcript)):
                return False
            chosen = extract_expression(transcript, language, level, seen, topics)
            return chosen is not None
        try:
            clip = clip_cafe.find_clip(seed, verify=verify, audio_language=language, search_language=search_language, max_results=8, max_seconds=30)
        except RuntimeError:
            continue
        if chosen is not None:
            return chosen, clip
    raise RuntimeError(f'No transcript-verified expression found for {level}/{language}')
