"""User preference validation."""
from __future__ import annotations
import json
from pathlib import Path
def _load_languages():
    path = Path(__file__).with_name("languages.json")
    return json.loads(path.read_text(encoding="utf-8"))
_LANGUAGES_DATA = _load_languages()
LANGUAGES = _LANGUAGES_DATA
CODES = {item["code"] for item in LANGUAGES}
LANGUAGE_CODES = CODES
LEVELS = ("A2", "B1", "B2", "C1", "C2")
def validate_language(code: str):
    if code not in CODES:
        raise ValueError(f"Unsupported language: {code}")
    return code
def validate_interval(value):
    if isinstance(value, bool):
        raise TypeError('bool not allowed')
    if isinstance(value, float):
        raise TypeError('float not allowed')
    if value is None:
        raise TypeError('None not allowed')
    if isinstance(value, str) and value.strip() == "":
        raise ValueError
    try:
        if isinstance(value, str):
            value = int(value.strip())
        else:
            value = int(value)
    except (ValueError, TypeError):
        raise ValueError
    if not (30 <= value <= 1440):
        raise ValueError
    return value
