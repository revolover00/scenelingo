"""Check text generation for each explanation language; no messages sent."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from multilingual import meaning
from preferences import LANGUAGES

results = []
failed = []
for language in LANGUAGES:
    code = language['code']
    try:
        result = meaning('Nice to meet you', 'en', code, 'A2')
        if not result or len(result) > 850:
            raise ValueError('Invalid explanation length')
        results.append(code + ':ok')
    except Exception as exc:  # noqa: BLE001 - live-provider probe records any unavailable language
        failed.append(code)
        results.append(code + ':' + type(exc).__name__)
print('::notice title=Explanation generation::' + '; '.join(results), flush=True)
if failed:
    raise SystemExit(1)
