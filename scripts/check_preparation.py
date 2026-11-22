"""Real Postgres two-phase integration in a disposable schema; NO Telegram calls.

Fixture bytes stand in for a previously verified clip. This tests durable storage,
slot mapping and delivery decisions, not audio quality or actual Telegram transport.
"""
import asyncio
import sys
import tempfile
import uuid
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from psycopg2 import sql
import db
import preparation
import reliable_delivery
from config import config


def main():
    config.validate('database_url')
    schema = 'test_preparation_' + uuid.uuid4().hex
    original = db.connect
    connections = []
    admin = psycopg2.connect(config.database_url)

    def connect():
        conn = psycopg2.connect(config.database_url)
        connections.append(conn)
        with conn.cursor() as cur:
            cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        conn.commit()
        return conn

    try:
        with admin, admin.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        db.connect = connect
        db.init_db()
        with connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO subscribers(chat_id,level) VALUES(1,'B1')")
            cur.execute("INSERT INTO subscriber_preferences(chat_id,next_due_at,interval_minutes) VALUES(1,now()+interval '5 minutes',30)")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.mp4'
            path.write_bytes(b'previously-verified-media-fixture')
            select = Mock(return_value=(SimpleNamespace(text='Good for you', topic='social'),
                SimpleNamespace(path=path,clip_id='fixture',title='Fixture',url='https://example.com/fixture')))
            explain = Mock(return_value='Fixture explanation')
            assert db.due_subscribers() == []
            future = db.due_subscribers(10)
            assert len(future) == 1
            assert preparation.prepare(future, select, explain) == (1,0)
            assert preparation.ready(future[0])
            # Simulate a different Actions runner: original local media disappears.
            path.unlink()
            assert preparation.prepare(future, select, explain) == (0,0)
            select.assert_called_once()
            bot = SimpleNamespace(send_video=AsyncMock(return_value=SimpleNamespace(message_id=1,video=None)))
            fallback = Mock(side_effect=AssertionError('Should not download prepared media'))
            stats = asyncio.run(reliable_delivery.run(future, bot, select, explain, fallback,
                                prepared_lookup=preparation.ready, shared_queue=True))
            assert stats.sent == 0
            bot.send_video.assert_not_called()
            # Advance only the fixture clock by shifting both sides of its slot key.
            with connect() as conn, conn.cursor() as cur:
                cur.execute("UPDATE subscriber_preferences SET next_due_at=now()-interval '1 minute' RETURNING next_due_at")
                due = cur.fetchone()[0]
                cur.execute('UPDATE prepared_slots SET due_at=%s', (due,))
            with ExitStack() as media:
                def restore(content):
                    return media.enter_context(preparation.restore(content, fallback))
                stats = asyncio.run(reliable_delivery.run(db.due_subscribers(), bot, select, explain, restore,
                                    prepared_lookup=preparation.ready, shared_queue=True))
            assert stats.sent == 1
            select.assert_called_once()
            explain.assert_called_once()
            fallback.assert_not_called()
            with connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM delivery_attempts WHERE status='sent'")
                assert cur.fetchone()[0] == 1
            assert db.due_subscribers() == []
            # A daily subscriber later consumes the same persisted lesson.
            with connect() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO subscribers(chat_id,level) VALUES(2,'B1')")
                cur.execute("INSERT INTO subscriber_preferences(chat_id,next_due_at,interval_minutes) VALUES(2,now()-interval '1 minute',1440)")
            with ExitStack() as media:
                def restore_later(content):
                    return media.enter_context(preparation.restore(content, fallback))
                later = asyncio.run(reliable_delivery.run(db.due_subscribers(), bot, select, explain, restore_later,
                                    prepared_lookup=preparation.ready, shared_queue=True))
            assert later.sent == 1
            select.assert_called_once()
            explain.assert_called_once()
            assert bot.send_video.call_count == 2
            assert db.due_subscribers() == []
        print('::notice title=Preparation integration::Real isolated Postgres: persisted media restored after local deletion, no early send, two simulated deliveries across 30-minute/daily intervals, no repeated generation; no real Telegram calls')
    finally:
        db.connect = original
        for conn in connections:
            conn.close()
        with admin, admin.cursor() as cur:
            cur.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
        admin.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import traceback
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print(f'::error title=Preparation integration::{type(error).__name__} at {Path(frame.filename).name}:{frame.lineno}', flush=True)
        sys.exit(1)
