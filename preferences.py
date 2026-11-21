"""Validation shared by the subscriber settings and scheduling pipeline."""
from __future__ import annotations

import json
from pathlib import Path

LANGUAGES = json.loads((Path(__file__).parent / 'languages.json').read_text(encoding='utf-8'))
LANGUAGE_CODES = frozenset(language['code'] for language in LANGUAGES)
MIN_INTERVAL_MINUTES = 30
MAX_INTERVAL_MINUTES = 24 * 60


def validate_language(code: str) -> str:
    if code not in LANGUAGE_CODES:
        raise ValueError('Unsupported language')
    return code


def validate_interval(value: str | int) -> int:
    """Accept whole minutes only; never round fractional values silently."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError('Interval must be a whole number of minutes')
    text = str(value).strip()
    if not text.isascii() or not text.isdecimal():
        raise ValueError('Interval must be a whole number of minutes')
    minutes = int(text)
    if not MIN_INTERVAL_MINUTES <= minutes <= MAX_INTERVAL_MINUTES:
        raise ValueError('Interval must be between 30 and 1440 minutes')
    return minutes
