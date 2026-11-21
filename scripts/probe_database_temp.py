"""Exercise scheduling against isolated temporary Postgres tables; never send."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db

conn = db.connect()
try:
    # Temporary tables live only in this connection and shadow production tables.
    schema = Path('schema.sql').read_text().replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE IF NOT EXISTS')
    with conn.cursor() as cur:
        cur.execute(schema)
        cur.execute("INSERT INTO subscribers (chat_id, level, subscribed_at) VALUES (111, 'A2', now() - interval '1 day'), (222, 'B1', now() - interval '1 day')")
        cur.execute("INSERT INTO subscriber_preferences (chat_id, learning_language, explanation_language, interval_minutes, next_due_at) VALUES (222, 'ja', 'en', 5, now() - interval '1 minute')")
    conn.commit()
    original = db.connect
    db.connect = lambda: conn
    try:
        users = {u['chat_id']: u for u in db.due_subscribers()}
        assert set(users) == {111, 222}
        assert users[111]['learning_language'] == 'en' and users[111]['explanation_language'] == 'ar'
        assert db.still_due_with_settings(users[222])
        with conn.cursor() as cur:
            cur.execute("UPDATE subscriber_preferences SET updated_at = updated_at + interval '1 second', next_due_at = now() + interval '7 minutes' WHERE chat_id = 222")
        conn.commit()
        assert not db.still_due_with_settings(users[222])
        assert not db.advance_due_after_delivery(222, users[222]['settings_updated_at'])
        with conn.cursor() as cur:
            cur.execute("UPDATE subscriber_preferences SET next_due_at = now() - interval '1 minute' WHERE chat_id = 222")
        conn.commit()
        assert db.advance_due_after_delivery(222, users[222]['settings_updated_at'])
        with conn.cursor() as cur:
            cur.execute("UPDATE subscriber_preferences SET next_due_at = now() - interval '1 minute' WHERE chat_id = 222")
        conn.commit()
        users = {u['chat_id']: u for u in db.due_subscribers()}
        with conn.cursor() as cur:
            cur.execute("UPDATE subscribers SET level = 'C1' WHERE chat_id = 222")
        conn.commit()
        assert not db.still_due_with_settings(users[222])
        with conn.cursor() as cur:
            cur.execute("UPDATE subscribers SET level = 'B1' WHERE chat_id = 222")
        conn.commit()
        assert db.advance_due_after_delivery(222, users[222]['settings_updated_at'])
        assert not db.still_due_with_settings(users[222])
        assert db.advance_due_after_delivery(111, None)
        assert db.due_subscribers() == []
        db.mark_phrase_sent('B1', 'こんにちは', 'greeting', 'sample', 'Sample', 'ja')
        assert 'こんにちは' in db.phrase_history('B1', 'ja')[0]
        assert not db.phrase_history('B1', 'en')[0]
    finally:
        db.connect = original
    print('::notice title=Database integration::Temporary tables validated scheduling and language history; no messages sent', flush=True)
finally:
    conn.close()
