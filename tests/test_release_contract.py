from pathlib import Path

import pytest
import release_contract as contract


def test_current_release_contains_required_production_capabilities():
    assert len(contract.verify()) == 16


def test_partial_rollback_is_rejected_before_delivery(tmp_path):
    for name in contract.REQUIRED:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((contract.ROOT / name).read_text())
    (tmp_path / 'content_reserve.py').unlink()
    with pytest.raises(RuntimeError, match='component missing'):
        contract.verify(tmp_path)
