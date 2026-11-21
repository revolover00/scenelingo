"""Shared verified PostgreSQL transport for Python production and integration."""
import certifi
import psycopg2
from psycopg2.extensions import parse_dsn


def connect_verified(dsn):
    # Keyword settings override weaker URL options. Never downgrade on failure.
    host = parse_dsn(dsn).get('host', '')
    overrides = {}
    # SET search_path and session advisory locks require a session connection.
    # Neon transaction pooling can move subsequent transactions to another server.
    if host.endswith('.neon.tech') and host.split('.')[0].endswith('-pooler'):
        overrides['host'] = host.replace('-pooler.', '.', 1)
    conn = psycopg2.connect(dsn, **overrides, sslmode='verify-full', sslrootcert=certifi.where(),
                            connect_timeout=10)
    try:
        # Transaction poolers reject statement_timeout in startup options.
        with conn.cursor() as cur:
            cur.execute('SET statement_timeout = 15000')
        conn.commit()
        return conn
    except Exception:
        conn.close()
        raise
