"""Fail visibly for eligible subscriptions overdue by more than 15 minutes.

Aggregate-only output: no chat IDs, credentials, or learner content. This check
never sends messages, advances schedules, or replays ambiguous deliveries.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db


def check():
    with db.session() as conn, conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM subscribers s
            LEFT JOIN subscriber_preferences p USING(chat_id)
            WHERE s.is_active AND LEFT(COALESCE(p.input_state,''),6)<>'setup_'
            AND COALESCE(p.next_due_at,s.subscribed_at+interval '3 hours')
                < now()-interval '15 minutes'""")
        overdue = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM delivery_attempts
            WHERE status='uncertain' OR (status='sending'
                AND updated_at < now()-interval '15 minutes')""")
        unresolved = cur.fetchone()[0]
    print(f'::notice title=Delivery health::overdue_beyond_15_minutes={overdue}, unresolved_sends={unresolved}', flush=True)
    if overdue or unresolved:
        raise RuntimeError('Subscriptions overdue or sends unresolved; inspect private dashboard')


if __name__ == '__main__':
    check()
