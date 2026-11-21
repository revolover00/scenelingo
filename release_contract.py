"""Executable regression guard for the delivery capabilities required in production.

This detects accidental partial rollbacks in normal CI. It cannot stop a history
rewrite that removes this guard too; protected main history is still required.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED = {
    '.github/workflows/daily.yml': ('scripts/refill_reserve.py', 'scripts/check_delivery_health.py'),
    'daily_job.py': ('reload_verified_clip', 'preparation.LOOKAHEAD_MINUTES'),
    'delivery_store.py': ('7195', 'pg_try_advisory_lock'),
    'content_reserve.py': ('def refill(', 'def incomplete('),
    'postgres_connection.py': ("sslmode='verify-full'", "overrides['host']"),
    'lib/postgres-config.js': ('rejectUnauthorized:true', "replace('-pooler.'"),
    'source_first.py': ("'en':", "tracked('source_expression'"),
    'audio_cache.py': ('def get(', 'def save('),
    'scripts/delivery_alert.py': ('app/github-actions',),
}


def verify(root=ROOT):
    digest = hashlib.sha256()
    for name, markers in REQUIRED.items():
        path = root / name
        if not path.is_file():
            raise RuntimeError(f'Required reliability component missing: {name}')
        content = path.read_text(encoding='utf-8')
        if not all(marker in content for marker in markers):
            raise RuntimeError(f'Required reliability capability missing: {name}')
        digest.update(name.encode()); digest.update(content.encode())
    return digest.hexdigest()[:16]


if __name__ == '__main__':
    print(f'::notice title=Delivery release contract::capabilities=verified fingerprint={verify()}', flush=True)
