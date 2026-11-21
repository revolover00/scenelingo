import json
from unittest.mock import MagicMock

import pytest
from scripts import check_delivery_health as health
from scripts import delivery_alert as alert


def test_overdue_monitor_is_aggregate_read_only_and_fails_closed(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(health.db, 'session', lambda: conn)
    cur = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (0,)
    health.check()
    sql = cur.execute.call_args_list[0].args[0]
    assert 'SELECT count(*)' in sql and "interval '15 minutes'" in sql
    assert 's.is_active' in sql and 'setup_' in sql
    cur.fetchone.return_value = (1,)
    with pytest.raises(RuntimeError, match='overdue'):
        health.check()


def incident(number=42):
    return dict(number=number, title=alert.TITLE, body=alert.MARKER,
                author={'login': 'github-actions[bot]'})


def test_failure_alert_deduplicates_and_never_includes_logs(monkeypatch):
    calls = []
    def gh(*args):
        calls.append(args)
        return '[]' if args[1] == 'list' else ''
    monkeypatch.setattr(alert, 'gh', gh)
    alert.reconcile(True, 'https://github.com/owner/repo/actions/runs/123')
    assert calls[-1][:2] == ('issue', 'create')
    monkeypatch.setattr(alert, 'gh', lambda *args: json.dumps([incident()]) if args[1] == 'list' else pytest.fail('duplicate alert'))
    alert.reconcile(True, 'run')


def test_recovery_closes_only_marked_bot_incidents(monkeypatch):
    calls = []
    human = incident(99); human['author'] = {'login': 'owner'}
    unrelated = incident(100); unrelated['body'] = ''
    def gh(*args):
        calls.append(args)
        return json.dumps([incident(), human, unrelated]) if args[1] == 'list' else ''
    monkeypatch.setattr(alert, 'gh', gh)
    alert.reconcile(False, 'run')
    assert len(calls) == 2 and calls[-1][:3] == ('issue', 'close', '42')


def test_unresolved_send_keeps_incident_open_without_replay(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(health.db, 'session', lambda: conn)
    cur = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [(0,), (1,)]
    with pytest.raises(RuntimeError, match='unresolved'):
        health.check()
    assert all(call.args[0].lstrip().startswith('SELECT') for call in cur.execute.call_args_list)


def test_github_app_author_format_is_deduplicated(monkeypatch):
    app_issue = incident(); app_issue['author'] = {'login': 'app/github-actions'}
    monkeypatch.setattr(alert, 'gh', lambda *args: json.dumps([app_issue]) if args[1] == 'list' else pytest.fail('duplicate alert'))
    alert.reconcile(True, 'run')
