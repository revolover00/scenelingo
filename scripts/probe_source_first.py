"""Probe the transcript-first prototype without touching users or sending."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import clip_cafe
import multilingual
import source_first

language = sys.argv[1]
seed = source_first.SEEDS[language][0]
original = clip_cafe.find_clip
with TemporaryDirectory() as tmp, \
     patch.dict(source_first.SEEDS, {language: (() if language == 'hi' else (seed,))}), \
     patch.object(source_first.random, 'shuffle', lambda seeds: None), \
     patch.object(clip_cafe, 'find_clip', side_effect=lambda text, **kw: original(text, Path(tmp), **kw)):
    try:
        (text, topic), clip = source_first.find_expression_clip(language, 'A2', set(), [])
        meaning = multilingual.meaning(text, language, 'ar', 'A2')
        assert clip.path.is_file() and meaning
        print(f'::notice title=Source-first {language}::Verified A2 expression and explanation from {clip.clip_id}', flush=True)
    except Exception as exc:  # noqa: BLE001 - operator probe reports any source or provider failure
        print(f'::error title=Source-first {language} unavailable::{type(exc).__name__}', flush=True)
        raise SystemExit(1)
