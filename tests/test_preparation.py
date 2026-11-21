from types import SimpleNamespace
from unittest.mock import Mock

from test_reliable_delivery import content, fixture, subscriber

import preparation as prep
import reliable_delivery as worker


def setup(monkeypatch):
    bot = fixture(monkeypatch)
    monkeypatch.setattr(prep.db, 'still_due_with_settings', Mock(return_value=True))
    monkeypatch.setattr(prep, 'ready', Mock(return_value=None))
    monkeypatch.setattr(prep, 'reserve', Mock())
    monkeypatch.setattr(prep, 'save_media', Mock())
    return bot


def test_future_preparation_never_sends_or_claims(monkeypatch):
    bot = setup(monkeypatch)
    select, explain = Mock(), Mock()
    assert prep.prepare([subscriber()], select, explain) == (1, 0)
    bot.send_video.assert_not_called()
    worker.store.claim.assert_not_called()
    worker.db.advance_due_after_delivery.assert_not_called()
    select.assert_not_called()
    explain.assert_not_called()


def test_stopped_or_changed_settings_do_not_generate(monkeypatch):
    setup(monkeypatch)
    prep.db.still_due_with_settings.return_value = False
    select, explain = Mock(), Mock()
    assert prep.prepare([subscriber()], select, explain) == (0, 0)
    worker.store.cached.assert_not_called()
    select.assert_not_called()


def test_ready_slot_does_not_repeat_work(monkeypatch):
    setup(monkeypatch)
    prep.ready.return_value = 1
    assert prep.prepare([subscriber()], Mock(), Mock()) == (0, 0)
    worker.store.cached.assert_not_called()


def test_generation_shared_and_media_saved_once(monkeypatch):
    setup(monkeypatch)
    worker.store.cached.return_value = None
    c = content(); c['telegram_file_id'] = None
    monkeypatch.setattr(worker.store, 'content', Mock(return_value=c))
    worker.store.get_caption.return_value = None
    clip = SimpleNamespace(path='verified.mp4')
    select, explain = Mock(return_value=(object(), clip)), Mock(return_value='caption')
    assert prep.prepare([subscriber(1), subscriber(2)], select, explain) == (2, 0)
    select.assert_called_once_with('B1', 'en')
    explain.assert_called_once()
    prep.save_media.assert_called_once_with(1, 'verified.mp4')
    assert prep.reserve.call_count == 4  # partial assignment + completed assignment


def test_explanation_failure_keeps_partial_assignment(monkeypatch):
    setup(monkeypatch)
    worker.store.get_caption.return_value = None
    assert prep.prepare([subscriber()], Mock(), Mock(side_effect=RuntimeError())) == (0, 1)
    prep.reserve.assert_called_once()


def test_partial_preparation_resumes_without_select(monkeypatch):
    setup(monkeypatch)
    prep.ready.side_effect = [None, 1]
    monkeypatch.setattr(worker.store, 'get_content', Mock(return_value=content()))
    select = Mock()
    assert prep.prepare([subscriber()], select, Mock()) == (1, 0)
    select.assert_not_called()
    worker.store.cached.assert_not_called()


def test_existing_delivery_attempt_not_prepared_again(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(worker.store, 'state', lambda sub: {'status':'uncertain'})
    assert prep.prepare([subscriber()], Mock(), Mock()) == (0, 0)
    worker.store.cached.assert_not_called()


def test_media_too_large_is_not_read_or_stored(monkeypatch):
    path = Mock()
    path.stat.return_value.st_size = prep.MAX_ITEM + 1
    monkeypatch.setattr(prep, 'Path', lambda _: path)
    import pytest
    with pytest.raises(ValueError, match='20 MiB'):
        prep.save_media(1, 'big.mp4')
    path.read_bytes.assert_not_called()


def test_delivery_uses_prepared_assignment(monkeypatch):
    import asyncio
    bot = fixture(monkeypatch)
    monkeypatch.setattr(worker.store, 'get_content', Mock(return_value=content()))
    select, explain, reload = Mock(), Mock(), Mock()
    stats = asyncio.run(worker.run([subscriber()], bot, select, explain, reload,
                                  prepared_lookup=lambda sub: 1))
    assert stats.sent == 1
    select.assert_not_called()
    explain.assert_not_called()
    worker.store.cached.assert_not_called()


def test_future_recipient_is_not_sent_even_when_ready(monkeypatch):
    import asyncio
    bot = fixture(monkeypatch)
    monkeypatch.setattr(worker.db, 'still_due_with_settings', lambda _: False)
    lookup = Mock(return_value=1)
    stats = asyncio.run(worker.run([subscriber()], bot, Mock(), Mock(), Mock(), prepared_lookup=lookup))
    assert stats.skipped == 1
    lookup.assert_not_called()
    bot.send_video.assert_not_called()


def test_restore_cleans_temporary_file_and_avoids_download(monkeypatch):
    from pathlib import Path
    from unittest.mock import MagicMock
    conn, cur = MagicMock(), MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = (memoryview(b'verified-video'),)
    monkeypatch.setattr(prep.db, 'connect', lambda: conn)
    fallback = Mock()
    with prep.restore({'id':1}, fallback) as clip:
        path = Path(clip.path)
        assert path.read_bytes() == b'verified-video'
    assert not path.exists()
    fallback.assert_not_called()


def test_restore_missing_media_uses_verified_fallback(monkeypatch):
    from unittest.mock import MagicMock
    conn, cur = MagicMock(), MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = None
    monkeypatch.setattr(prep.db, 'connect', lambda: conn)
    fallback = Mock(return_value='verified')
    with prep.restore({'id':1}, fallback) as clip:
        assert clip == 'verified'
    fallback.assert_called_once_with({'id':1})


def test_buffer_budget_blocks_write(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    import pytest
    path = tmp_path/'clip.mp4'; path.write_bytes(b'abc')
    conn, cur = MagicMock(), MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = (prep.MAX_TOTAL,)
    monkeypatch.setattr(prep.db, 'connect', lambda: conn)
    with pytest.raises(ValueError, match='full'):
        prep.save_media(1, path)
    assert cur.execute.call_count == 1


def test_settings_change_during_preparation_prevents_reservation(monkeypatch):
    setup(monkeypatch)
    prep.db.still_due_with_settings.side_effect = [True, True, False]
    select, explain = Mock(), Mock()
    assert prep.prepare([subscriber()], select, explain) == (0, 0)
    prep.reserve.assert_not_called()
    explain.assert_not_called()


def test_media_read_is_bounded_even_if_file_grows_after_stat(monkeypatch):
    import pytest
    from unittest.mock import MagicMock
    path=MagicMock()
    path.stat.return_value.st_size=1
    stream=path.open.return_value.__enter__.return_value
    stream.read.return_value=b'x'*(prep.MAX_ITEM+1)
    monkeypatch.setattr(prep,'Path',lambda _:path)
    with pytest.raises(ValueError,match='grew'):
        prep.save_media(1,'growing.mp4')
    stream.read.assert_called_once_with(prep.MAX_ITEM+1)


def test_preparation_consistently_uses_thirty_minute_horizon(monkeypatch):
    setup(monkeypatch)
    assert prep.LOOKAHEAD_MINUTES == 30
    prep.prepare([subscriber()], Mock(), Mock())
    assert prep.db.still_due_with_settings.call_count > 0
    assert all(call.args[1] == 30 for call in prep.db.still_due_with_settings.call_args_list)
