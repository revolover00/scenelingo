"""Report aggregate subscription counts and optionally make eligible users due now.

The manual override never reactivates stopped subscriptions or bypasses setup.
Delivery still uses the normal verification, preflight and scheduling pipeline.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db


def prepare(force: bool = False) -> dict:
    db.init_db()
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT count(*), count(*) FILTER (WHERE s.is_active),
                count(*) FILTER (WHERE s.is_active AND LEFT(COALESCE(p.input_state, ''), 6) <> 'setup_'),
                count(*) FILTER (WHERE NOT s.is_active)
            FROM subscribers s LEFT JOIN subscriber_preferences p USING (chat_id)
        """)
        total, active, eligible, stopped = cur.fetchone()
        queued = 0
        if force:
            cur.execute("""
                INSERT INTO subscriber_preferences (chat_id, next_due_at)
                SELECT s.chat_id, now() FROM subscribers s
                LEFT JOIN subscriber_preferences p USING (chat_id)
                WHERE s.is_active AND LEFT(COALESCE(p.input_state, ''), 6) <> 'setup_'
                ON CONFLICT (chat_id) DO UPDATE SET next_due_at = now(), updated_at = now()
                WHERE LEFT(COALESCE(subscriber_preferences.input_state, ''), 6) <> 'setup_'
                RETURNING chat_id
            """)
            queued = cur.rowcount
    return dict(total=total, active=active, eligible=eligible, stopped=stopped, queued=queued)


def main() -> None:
    counts = prepare(os.getenv('SEND_NOW', '').lower() == 'true')
    summary = ', '.join(f'{key}={value}' for key, value in counts.items())
    print(f'::notice title=Subscriber counts::{summary}', flush=True)
    if path := os.getenv('GITHUB_STEP_SUMMARY'):
        with open(path, 'a', encoding='utf-8') as file:
            file.write(f'## Subscriber counts\n\n{summary}\n\nQueued does not mean delivered; see delivery results.\n')


if __name__ == '__main__':
    main()
