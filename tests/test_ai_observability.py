from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ai_observability as usage
import db


def setup(monkeypatch):
    monkeypatch.setattr(usage,'config',SimpleNamespace(database_url='configured',bot_token='configured'))
    conn=MagicMock()
    conn.__enter__.return_value=conn
    cur=conn.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(db,'connect',lambda:conn)
    return cur


def test_record_reported_counts_without_prompt_or_response_content(monkeypatch):
    cur=setup(monkeypatch)
    response=SimpleNamespace(usage=SimpleNamespace(prompt_tokens=12,completion_tokens=34),secret='never store')
    assert usage.tracked('explanation',lambda **_:response,model='test') is response
    params=cur.execute.call_args.args[1]
    assert params[:5]==('explanation','test','ok',12,34)
    assert 'never store' not in str(cur.execute.call_args)


def test_audio_unknown_token_usage_is_null_not_fabricated(monkeypatch):
    cur=setup(monkeypatch)
    usage.tracked('transcription',lambda **_:SimpleNamespace(),model='audio')
    assert cur.execute.call_args.args[1][3:5]==(None,None)


def test_metrics_failure_never_masks_original_error(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(db,'connect',lambda:(_ for _ in ()).throw(RuntimeError('db unavailable')))
    with pytest.raises(ValueError,match='original'):
        usage.tracked('explanation',lambda **_:(_ for _ in ()).throw(ValueError('original')),model='test')
