import re
from pathlib import Path

from scripts.bot_profile import COMMANDS, PROFILES, configure_profile


def test_profile_limits_and_commands_match_implemented_handlers():
    handler = Path('api/telegram.js').read_text()
    assert len({cmd for cmd, _, _ in COMMANDS}) == len(COMMANDS)
    for cmd, en, ar in COMMANDS:
        assert re.fullmatch('[a-z_]{1,32}', cmd)
        assert f"'/{cmd}'" in handler
        assert 1 <= len(en) <= 256 and 1 <= len(ar) <= 256
    for description, short in PROFILES.values():
        assert 0 < len(description) <= 512
        assert 0 < len(short) <= 120


def test_configuration_reads_back_values_and_never_changes_webhook():
    state = {}
    calls = []
    def api(method, **payload):
        calls.append(method)
        key = (payload.get('language_code'), str(payload.get('scope')))
        if method.startswith('set'):
            state[(method, key)] = payload
            return True
        written = state[(method.replace('get', 'set', 1), key)]
        if method == 'getMyCommands':
            return written['commands']
        if method == 'getChatMenuButton':
            return written['menu_button']
        return {k: v for k, v in written.items() if k != 'language_code'}
    configure_profile(api)
    assert calls.count('setMyCommands') == 6
    assert not any('Webhook' in method or method.startswith('send') for method in calls)


def test_profile_readback_failure_is_not_silenced():
    import pytest
    with pytest.raises(RuntimeError, match='verification'):
        configure_profile(lambda *args, **kwargs: [])
