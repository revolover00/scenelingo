from unittest.mock import MagicMock

import db


def mock_db(monkeypatch, *, rows=None, row=None):
    conn = MagicMock()
    cur = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = row
    monkeypatch.setattr(db, 'connect', lambda: conn)
    return cur


def test_due_query_excludes_inactive_and_uses_database_time(monkeypatch):
    cur = mock_db(monkeypatch, rows=[{'chat_id': 1, 'level': 'A2'}])
    assert db.due_subscribers() == [{'chat_id': 1, 'level': 'A2'}]
    sql = cur.execute.call_args.args[0]
    assert 's.is_active = TRUE' in sql
    assert "LEFT(COALESCE(p.input_state, ''), 6) <> 'setup_'" in sql
    assert '<= now()' in sql


def test_advance_new_subscriber_does_not_overwrite_concurrent_settings(monkeypatch):
    cur = mock_db(monkeypatch, row=None)
    assert not db.advance_due_after_delivery(42, None)
    sql, params = cur.execute.call_args_list[0].args
    assert 'ON CONFLICT (chat_id) DO NOTHING' in sql
    assert params == (42,)
    fallback, params = cur.execute.call_args_list[1].args
    assert '<= now()' in fallback and params == (42,)


def test_advance_existing_subscriber_checks_version(monkeypatch):
    cur = mock_db(monkeypatch, row=(42,))
    assert db.advance_due_after_delivery(42, 'version')
    sql, params = cur.execute.call_args.args
    assert 'p.updated_at = %s' in sql
    assert params == (42, 'version')


def test_preflight_checks_current_level_preferences_and_due_time(monkeypatch):
    cur = mock_db(monkeypatch, row=(1,))
    user = {'chat_id': 1, 'level': 'B1', 'learning_language': 'ja', 'explanation_language': 'ar', 'settings_updated_at': 'v'}
    assert db.still_due_with_settings(user)
    sql, params = cur.execute.call_args.args
    assert 's.is_active = TRUE' in sql and 's.level = %s' in sql
    assert "LEFT(COALESCE(p.input_state, ''), 6) <> 'setup_'" in sql
    assert 'IS NOT DISTINCT FROM' in sql and '<= now()' in sql
    assert params == (1, 'B1', 'ja', 'ar', 'v', None, None, 0)


def test_advance_changed_settings_only_when_current_schedule_is_overdue(monkeypatch):
    cur = mock_db(monkeypatch)
    cur.fetchone.side_effect = [None, (42,)]
    assert db.advance_due_after_delivery(42, 'old-version')
    first, fallback = [call.args[0] for call in cur.execute.call_args_list]
    assert 'p.updated_at = %s' in first
    assert "next_delivery_at(p.interval_minutes)" in fallback
    assert "<= now()" in fallback


def test_lookahead_is_parameterized_and_preflight_uses_same_horizon(monkeypatch):
    cur = mock_db(monkeypatch, row=(1,))
    db.due_subscribers(10)
    assert cur.execute.call_args.args[1] == (10,)
    user = {'chat_id': 1, 'level': 'B1', 'learning_language': 'ja', 'explanation_language': 'ar', 'settings_updated_at': 'v'}
    assert db.still_due_with_settings(user, 10)
    assert cur.execute.call_args.args[1][-1] == 10


def test_due_query_has_only_bound_percent_placeholders(monkeypatch):
    # psycopg2 interprets literal '%' when parameters are supplied, unlike mocks.
    cur = mock_db(monkeypatch)
    for horizon in (0, 10):
        db.due_subscribers(horizon)
        sql, params = cur.execute.call_args.args
        assert sql.count('%s') == len(params)
        assert '%' not in sql.replace('%s', '').replace('%%', '')


def test_preflight_pins_exact_slot_even_with_unchanged_settings(monkeypatch):
    cur=mock_db(monkeypatch,row=(1,))
    sub=dict(chat_id=1,level='C1',learning_language='en',explanation_language='ar',settings_updated_at='v',due_at='2026-11-20T10:00:00Z')
    assert db.still_due_with_settings(sub)
    query,params=cur.execute.call_args.args
    assert '%s::timestamptz' in query
    assert params[-3:-1]==(sub['due_at'],sub['due_at'])


def test_session_always_closes_connection_after_success_and_failure(monkeypatch):
    from unittest.mock import MagicMock
    import pytest
    conn=MagicMock();monkeypatch.setattr(db,'connect',lambda:conn)
    with db.session() as actual:
        assert actual is conn
    conn.close.assert_called_once()
    conn.reset_mock()
    with pytest.raises(RuntimeError), db.session():
        raise RuntimeError('transaction failed')
    conn.close.assert_called_once()
    assert conn.__exit__.call_args.args[0] is RuntimeError


def test_schema_migrations_lock_before_ddl(monkeypatch):
    cur = mock_db(monkeypatch)
    db.init_db()
    statements = [call.args[0] for call in cur.execute.call_args_list]
    assert 'pg_advisory_xact_lock' in statements[0]
    assert 'current_schema()' in statements[0]
    assert 'CREATE TABLE' in statements[1]


def test_worker_lock_uses_new_session_namespace_and_always_closes(monkeypatch):
    import delivery_store
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
    monkeypatch.setattr(delivery_store.db, 'connect', lambda: conn)
    with delivery_store.worker_lock() as acquired:
        assert acquired
    sql = conn.cursor.return_value.__enter__.return_value.execute.call_args_list[0].args[0]
    assert 'pg_try_advisory_lock' in sql and '7195' in sql and '7194' not in sql
    conn.close.assert_called_once()
