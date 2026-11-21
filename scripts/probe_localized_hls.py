"""Validate public alternate audio tracks with Whisper; never sends messages."""
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hls_clips
import multilingual

samples = {'ar': ('thanks-s750', 'شكرا'), 'hi': ('thanks-s750', ''),
           'ru': ('gomabseubnida-gomabseubnida-gomabseubnida', 'спасибо'),
           'zh': ('na-mei-guan-xi-xie-xie-chui-pao-pao-bu-cuo-a-mei-guan-xi-xie-xie', '谢谢')}
lang = sys.argv[1]
slug, phrase = samples[lang]
with TemporaryDirectory() as out:
    path = Path(out) / 'sample.mp4'
    try:
        if not hls_clips.download_localized(slug, lang, path):
            raise RuntimeError('HLS download failed')
        stream = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                                 'stream_tags=language', '-of', 'json', str(path)], check=False, capture_output=True, text=True, timeout=15)
        with path.open('rb') as f:
            transcript = multilingual.client().audio.transcriptions.create(model='whisper-large-v3-turbo', file=f, response_format='verbose_json', temperature=0)
        detected = getattr(transcript, 'language', '')
        text = getattr(transcript, 'text', '')
        print(f'::notice title=Localized audio {lang}::Detected={detected}; ffprobe={stream.stdout.strip()}; seed match={not phrase or multilingual.matches(phrase, text)}; transcript length={len(text)}', flush=True)
    except Exception as exc:  # noqa: BLE001 - live-provider probe reports any integration failure
        print(f'::error title=Localized audio {lang} unavailable::{type(exc).__name__}: {str(exc)[:200]}', flush=True)
        raise SystemExit(1)
