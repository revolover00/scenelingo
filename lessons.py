"""Validate and present compact lessons independently of the language model."""
from __future__ import annotations

import json
import re

# Telegram animated emojis (bot can use these with Premium - fallback to static)
ANIMATED = {
    'ar': ('🎬', '📖', '💬', '✍️', '↳', '🎞️'),
    'en': ('🎬', '📖', '💬', '✍️', '↳', '🎞️'),
}
LABELS = {
    'ar': ('المعنى', 'تستخدمه إمتى؟', 'مثال جديد', 'ترجمة المثال', 'من', 'تعبير من مشهد'),
    'en': ('Meaning', 'When to use it', 'New example', 'Example translation', 'From', 'An expression from a scene'),
    'es': ('Significado', 'Cuándo usarlo', 'Ejemplo nuevo', 'Traducción', 'De', 'Una expresión de una escena'),
    'fr': ('Sens', 'Quand l’utiliser', 'Nouvel exemple', 'Traduction', 'Source', 'Une expression en scène'),
    'de': ('Bedeutung', 'Verwendung', 'Neues Beispiel', 'Übersetzung', 'Quelle', 'Ein Ausdruck aus einer Szene'),
    'pt': ('Significado', 'Quando usar', 'Novo exemplo', 'Tradução', 'Fonte', 'Uma expressão em cena'),
    'ru': ('Значение', 'Когда использовать', 'Новый пример', 'Перевод', 'Источник', 'Выражение из сцены'),
    'zh': ('含义', '使用场景', '新例句', '例句翻译', '来源', '片段中的表达'),
    'ja': ('意味', '使う場面', '新しい例文', '例文の訳', '出典', 'シーンに出てくる表現'),
    'ko': ('의미', '사용법', '새 예문', '번역', '출처', '장면 속 표현'),
}
FIELDS = ('meaning', 'usage', 'example', 'translation')


def units(value: str) -> int:
    return len(value.encode('utf-16-le')) // 2


def compact(value: str, limit: int) -> str:
    """Shorten presentation only, at a word boundary where practical."""
    if units(value) <= limit:
        return value
    short = ''
    for char in value:
        if units(short + char) > limit - 1:
            break
        short += char
    if ' ' in short and len(short.rsplit(' ', 1)[0]) > len(short) * .65:
        short = short.rsplit(' ', 1)[0]
    return short.rstrip(' ,،;؛:') + '…'


def parse_lesson(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError('Model returned invalid lesson JSON') from None
    if not isinstance(data, dict):
        raise TypeError('Lesson must be an object')
    result = {}
    for key in FIELDS:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError(f'Invalid lesson field: {key}')
        # Collapse model-generated layout; the renderer owns headings and spacing.
        value = re.sub(r'[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]', ' ', value)
        result[key] = ' '.join(value.split())
        if not result[key]:
            raise ValueError(f'Empty lesson field: {key}')
    return result


def render_lesson(data: dict[str, str], explanation: str) -> str:
    # Animated emoji support - uses standard emoji with Telegram animation effect via entities if available
    # Fallback: static emoji above - Telegram will auto-animate some (🎬, 💬) for Premium users
    labels = LABELS[explanation]
    budgets = (140, 120, 150, 140)
    icons = ('📖', '💬', '✍️', '↳')
    return '\n\n'.join(f'{icon} {label}\n{compact(data[key], budget)}'
                        for key, label, budget, icon in zip(FIELDS, labels, budgets, icons))


def caption(phrase: str, body: str, level: str, learning: str,
            explanation: str, title: str, url: str = '') -> str:
    """Preserve the exact verified expression and keep a full lesson under Telegram's limit."""
    labels = LABELS[explanation]
    header = f'🎬 {labels[5]} · {level} · {learning.upper()}\n\n{phrase}'
    source = f'🎞 {labels[4]}: {compact(" ".join((title or "—").split()), 80)}'
    result = f'{header}\n\n{body}\n\n{source}'
    if url.startswith('https://') and not any(char.isspace() for char in url) and units(url) <= 200:
        linked = f'{result}\n{url}'
        if units(linked) <= 1024:
            result = linked
    if units(result) > 1024:
        # Never silently cut the expression, example, translation or source in half.
        raise ValueError('Lesson exceeds Telegram caption budget')
    return result
