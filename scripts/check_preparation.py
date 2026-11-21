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
import content_reserve
import preparation
import reliable_delivery
from config import config
from postgres_connection import connect_verified


def main():
    config.validate('database_url')
    schema = 'test_preparation_' + uuid.uuid4().hex
    original = db.connect
    connections = []
    admin = connect_verified(config.database_url)

    def connect():
        conn = connect_verified(config.database_url)
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
        with db.session() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO subscribers(chat_id,level) VALUES(1,'B1')")
            cur.execute("INSERT INTO subscriber_preferences(chat_id,next_due_at,interval_minutes) VALUES(1,now()+interval '25 minutes',30)")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.mp4'
            path.write_bytes(b'previously-verified-media-fixture')
            select = Mock(return_value=(SimpleNamespace(text='Good for you', topic='social'),
                SimpleNamespace(path=path,clip_id='fixture',title='Fixture',url='https://example.com/fixture')))
            explain = Mock(return_value='Fixture explanation')
            assert db.due_subscribers() == []
            assert db.due_subscribers(10) == []
            future = db.due_subscribers(preparation.LOOKAHEAD_MINUTES)
            assert len(future) == 1
            initial = preparation.prepare(future, select, explain)
            print(f'::notice title=Initial preparation::prepared={initial[0]}, failed={initial[1]}', flush=True)
            assert initial == (1,0)
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
            with db.session() as conn, conn.cursor() as cur:
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
            with db.session() as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM delivery_attempts WHERE status='sent'")
                assert cur.fetchone()[0] == 1
            assert db.due_subscribers() == []
            # Freeze the completed fixture away from the next :00/:30 boundary.
            # Otherwise a slow integration run can legitimately make it due again.
            with db.session() as conn, conn.cursor() as cur:
                cur.execute("UPDATE subscriber_preferences SET next_due_at=now()+interval '1 day' WHERE chat_id=1")
            # A daily subscriber later consumes the same persisted lesson.
            with db.session() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO subscribers(chat_id,level) VALUES(2,'B1')")
                cur.execute("INSERT INTO subscriber_preferences(chat_id,next_due_at,interval_minutes) VALUES(2,now()-interval '1 minute',1440)")
            with ExitStack() as media:
                def restore_later(content):
                    return media.enter_context(preparation.restore(content, fallback))
                later = asyncio.run(reliable_delivery.run(db.due_subscribers(), bot, select, explain, restore_later,
                                    prepared_lookup=preparation.ready, shared_queue=True))
            print(f'::notice title=Shared fixture delivery::{later.dict()}', flush=True)
            assert later.sent == 1
            select.assert_called_once()
            explain.assert_called_once()
            assert bot.send_video.call_count == 2
            assert db.due_subscribers() == []
        # Cold-start reserve: build three durable lessons without a Telegram call,
        # then consume them at three independent due slots on fresh runner media.
        with db.session() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO subscribers(chat_id,level) VALUES(3,'C1')")
            cur.execute("INSERT INTO subscriber_preferences(chat_id,next_due_at,interval_minutes) VALUES(3,now()+interval '25 minutes',30)")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'stock.mp4'
            path.write_bytes(b'previously-verified-reserve-fixture')
            counter = []
            def select_stock(level, learning, excluded):
                number = len(counter) + 1
                text = f'Unique reserve expression {number}'
                assert text.casefold() not in excluded
                counter.append(number)
                return (SimpleNamespace(text=text,topic='discussion'),
                    SimpleNamespace(path=path,clip_id=f'stock-{number}',title='Stock fixture',url='https://example.com/stock'))
            upcoming = [s for s in db.due_subscribers(30) if s['chat_id']==3]
            for _ in range(3):
                assert content_reserve.refill(upcoming, select_stock, explain) == (1,0)
            assert content_reserve.stock(upcoming[0]) == 3
            assert content_reserve.refill(upcoming, select_stock, explain) == (0,0)
            assert len(counter) == 3
            path.unlink()
            bot.send_video.reset_mock()
            stats = asyncio.run(reliable_delivery.run(upcoming, bot, fallback, fallback, fallback,
                shared_queue=True))
            assert stats.sent == 0
            bot.send_video.assert_not_called()
            for _ in range(3):
                with db.session() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE subscriber_preferences SET next_due_at=now()-interval '1 minute' WHERE chat_id=3")
                audience = [s for s in db.due_subscribers() if s['chat_id']==3]
                with ExitStack() as media:
                    def restore_stock(content):
                        return media.enter_context(preparation.restore(content, fallback))
                    result = asyncio.run(reliable_delivery.run(audience, bot, fallback, fallback, restore_stock,
                        shared_queue=True))
                    assert result.sent == 1
            assert len(counter) == 3
            assert content_reserve.stock(upcoming[0]) == 0
            assert bot.send_video.call_count == 3
            print('::notice title=Reserve lifecycle::Three complete lessons built without sending; no early send; local files deleted; three due slots consumed from durable stock with NO provider calls; stock and receipts verified in isolated Postgres')
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
    except Exception as error:  # noqa: BLE001 - operator entrypoint reports any integration failure
        import traceback
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print(f'::error title=Preparation integration::{type(error).__name__} at {Path(frame.filename).name}:{frame.lineno}', flush=True)
        sys.exit(1)
