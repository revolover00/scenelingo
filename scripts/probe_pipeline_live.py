"""Exercise one complete content pipeline without touching subscribers or sending."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import clip_cafe
import daily_job

lang = sys.argv[1]
level = sys.argv[2] if len(sys.argv) > 2 else 'A2'
original = clip_cafe.find_clip
with TemporaryDirectory() as tmp, patch.object(daily_job.db, 'phrase_history', return_value=(set(), [])), \
     patch.object(clip_cafe, 'find_clip', side_effect=lambda text, **kw: original(text, Path(tmp), **kw)):
    try:
        phrase, clip, caption = daily_job.build_localized_message(level, lang, 'ar')
        assert phrase.text and clip.path.is_file() and len(caption) <= 1024
        print(f'::notice title=Pipeline {lang}::{level} verified audio and explanation generated, no delivery', flush=True)
    except Exception as exc:  # noqa: BLE001 - operator probe reports any pipeline failure
        print(f'::error title=Pipeline {lang} unavailable::{type(exc).__name__}', flush=True)
        raise SystemExit(1)
