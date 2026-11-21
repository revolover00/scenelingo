"""Live read-only sample clip/audio probe; never sends bot messages."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clip_cafe import find_clip
from multilingual import verify_audio

examples = {
    'en': 'Nice to meet you', 'es': 'muchas gracias', 'fr': 'je suis désolé',
    'ar': 'مرحبا', 'pt': 'muito obrigado', 'de': 'vielen dank',
    'ru': 'спасибо', 'hi': 'नमस्ते', 'ja': 'こんにちは', 'zh': '谢谢',
}
lang = sys.argv[1]
phrase = examples[lang]
with TemporaryDirectory() as out:
    try:
        clip = find_clip(phrase, Path(out), verify=lambda path, text: verify_audio(path, text, lang), audio_language=lang)
        result = f'verified {clip.clip_id}'
    except Exception as exc:  # noqa: BLE001 - live-provider probe reports any unavailable sample
        result = f'unavailable: {type(exc).__name__}'
    print(f'::notice title=Audio sample {lang}::{result}', flush=True)
    if result.startswith('unavailable:'):
        raise SystemExit(1)
