import pytest

from bot_identity import database_schema


def test_schema_stable_across_token_rotation():
    assert database_schema('123:old') == database_schema('123:new') == 'bot_123'
    assert database_schema('456:other') != database_schema('123:old')


@pytest.mark.parametrize('token', ['', 'abc:def', '123', '123;DROP:bad', '-1:bad'])
def test_invalid_bot_identity_rejected(token):
    with pytest.raises(ValueError):
        database_schema(token)
