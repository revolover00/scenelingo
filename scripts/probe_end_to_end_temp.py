"""Run delivery against temp DB tables and a fake Telegram client; no messages sent."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import daily_job
import db


class FakeBot:
    def __init__(self, **kwargs):
        self.sent = []
    async def send_video(self, chat_id, video, caption):
        assert video.read(16) and caption
        self.sent.append(chat_id)

conn = db.connect()
try:
    schema = Path('schema.sql').read_text().replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE IF NOT EXISTS')
    with conn.cursor() as cur:
        cur.execute(schema)
        cur.execute("INSERT INTO subscribers (chat_id, level, subscribed_at) VALUES (1001, 'A2', now() - interval '1 day'), (1002, 'A2', now() - interval '1 day')")
        cur.execute("INSERT INTO subscriber_preferences (chat_id, learning_language, explanation_language, interval_minutes, next_due_at) VALUES (1001, 'en', 'ar', 5, now() - interval '1 minute'), (1002, 'en', 'en', 10, now() - interval '1 minute')")
    conn.commit()
    bot = FakeBot()
    with patch.object(db, 'connect', lambda: conn), patch.object(daily_job, 'Bot', lambda **kwargs: bot):
        users = db.due_subscribers()
        assert len(users) == 2
        asyncio.run(daily_job.run_due_subscribers(users))
        assert set(bot.sent) == {1001, 1002}
        assert db.due_subscribers() == []
        assert db.phrase_history('A2', 'en')[0]
    print('::notice title=End-to-end temporary test::Real content and DB scheduling passed with fake Telegram; no messages sent', flush=True)
finally:
    conn.close()
