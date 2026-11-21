from unittest.mock import Mock

import content_reserve as reserve
from test_reliable_delivery import subscriber, content


def setup(monkeypatch, count=0):
    monkeypatch.setattr(reserve.db, 'still_due_with_settings', Mock(return_value=True))
    monkeypatch.setattr(reserve, 'stock', Mock(return_value=count))
    monkeypatch.setattr(reserve, 'library_phrases', Mock(return_value={'reserved phrase'}))
    monkeypatch.setattr(reserve, 'incomplete', Mock(return_value=None))
    monkeypatch.setattr(reserve.store, 'content', Mock(return_value=content()))
    monkeypatch.setattr(reserve.store, 'seen_by', Mock(return_value=False))
    monkeypatch.setattr(reserve.store, 'get_caption', Mock(return_value=None))
    monkeypatch.setattr(reserve.store, 'save_caption', Mock())
    monkeypatch.setattr(reserve.preparation, 'save_media', Mock())


def test_no_demand_or_full_stock_never_calls_providers(monkeypatch):
    setup(monkeypatch, reserve.TARGET)
    select, explain = Mock(), Mock()
    assert reserve.refill([], select, explain) == (0, 0)
    assert reserve.refill([subscriber()], select, explain) == (0, 0)
    select.assert_not_called(); explain.assert_not_called()


def test_refill_is_bounded_shared_and_never_claims_or_sends(monkeypatch):
    from types import SimpleNamespace
    setup(monkeypatch)
    select = Mock(return_value=(object(), SimpleNamespace(path='clip')))
    explain = Mock(return_value='caption')
    assert reserve.refill([subscriber(1), subscriber(2)], select, explain) == (1, 0)
    select.assert_called_once_with('B1', 'en', excluded={'reserved phrase'})
    explain.assert_called_once()
    reserve.store.save_caption.assert_called_once()


def test_partial_caption_retries_same_media_without_new_search(monkeypatch):
    setup(monkeypatch)
    reserve.incomplete.return_value = content()
    select = Mock()
    explain = Mock(side_effect=RuntimeError('quota'))
    assert reserve.refill([subscriber()], select, explain) == (0, 1)
    select.assert_not_called()
    reserve.preparation.save_media.assert_not_called()
    explain.side_effect = None; explain.return_value = 'caption'
    assert reserve.refill([subscriber()], select, explain) == (1, 0)
    select.assert_not_called()


def test_changed_settings_do_not_trigger_reserve_generation(monkeypatch):
    setup(monkeypatch)
    reserve.db.still_due_with_settings.return_value = False
    select = Mock()
    assert reserve.refill([subscriber()], select, Mock()) == (0, 0)
    select.assert_not_called()
