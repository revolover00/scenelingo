"""Verify session settings and lock release on two real direct connections.

No subscriber tables or production worker lock keys are touched. Test locks use
an unpredictable namespace; closing the connections removes them.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import config
from postgres_connection import connect_verified


def main():
    config.validate('database_url')
    first = second = None
    key = uuid.uuid4().hex
    try:
        first = connect_verified(config.database_url)
        second = connect_verified(config.database_url)
        with first.cursor() as cur:
            cur.execute('SET search_path TO pg_catalog')
        first.commit()
        with second.cursor() as cur:
            cur.execute('SET search_path TO pg_catalog, public')
        second.commit()
        for conn, expected in ((first, 'pg_catalog'), (second, 'pg_catalog, public')):
            with conn.cursor() as cur:
                cur.execute('SHOW search_path')
                assert cur.fetchone()[0] == expected
            conn.commit()
        with first.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(hashtext(%s),7195)', (key,))
            assert cur.fetchone()[0]
        first.commit()
        with second.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(hashtext(%s),7195)', (key,))
            assert not cur.fetchone()[0]
        second.commit()
        first.close(); first = None
        with second.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(hashtext(%s),7195)', (key,))
            assert cur.fetchone()[0]
        second.commit()
        print('::notice title=Database sessions::Independent settings survived commits; concurrent lock refused; lock released when owner disconnected. No subscriber data modified.', flush=True)
    finally:
        for conn in (first, second):
            if conn is not None:
                conn.close()


if __name__ == '__main__':
    main()
