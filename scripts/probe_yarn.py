"""Check multilingual movie clip matching, without sending bot messages."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clip_cafe import find_clip, matches

EXAMPLES = {
    'en': 'Nice to meet you', 'es': 'muchas gracias', 'fr': 'je suis désolé',
    'ar': 'مرحبا', 'pt': 'muito obrigado', 'de': 'vielen dank',
    'ru': 'спасибо', 'hi': 'नमस्ते', 'ja': 'こんにちは', 'zh': '谢谢',
}
with TemporaryDirectory() as directory:
    for lang, expression in EXAMPLES.items():
        try:
            clip = find_clip(expression, Path(directory))
            assert matches(expression, clip.quote)
            print(f'::notice title=Clip {lang}::{clip.title}; {clip.path.stat().st_size} bytes')
        except Exception as exc:  # noqa: BLE001 - probe keeps testing other languages after any provider failure
            print(f'::warning title=Clip {lang} unavailable::{type(exc).__name__}: {exc}')
