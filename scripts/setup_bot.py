"""Initialize the current bot's isolated database and register its webhook."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import db
from config import config
from bot_identity import database_schema
from scripts.bot_profile import configure_profile
from webhook_auth import webhook_secret


def main():
    config.validate('bot_token')
    if os.environ.get('PROFILE_ONLY', '').lower() != 'true':
        config.validate('database_url')
    base = f'https://api.telegram.org/bot{config.bot_token}'
    # Never log request URLs: Telegram embeds the credential in the path.
    def api(method, **payload):
        try:
            response = requests.post(f'{base}/{method}', json=payload, timeout=30)
            body = response.json()
        except Exception:
            raise RuntimeError(f'Telegram {method} request failed') from None
        if not response.ok or not body.get('ok'):
            raise RuntimeError(f'Telegram {method} failed (HTTP {response.status_code})')
        return body['result']

    identity = api('getMe')
    if database_schema(config.bot_token) != f"bot_{identity['id']}":
        raise RuntimeError('Bot identity mismatch')
    expected = os.environ.get('EXPECTED_BOT_ID', '')
    if not expected or str(identity['id']) != expected:
        raise RuntimeError('GitHub BOT_TOKEN does not match the requested new bot; update the secret first')
    configure_profile(api)
    if os.environ.get('PROFILE_ONLY', '').lower() == 'true':
        print('::notice title=Bot profile::Name, descriptions, commands and menu applied and verified; webhook unchanged', flush=True)
        return
    db.init_db()
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT count(*), count(*) FILTER (WHERE is_active) FROM subscribers')
        total, active = cur.fetchone()
    url = os.environ.get('WEBHOOK_URL', 'https://scenelingoo.vercel.app/api/telegram')
    api('setWebhook', url=url, allowed_updates=['message', 'callback_query'],
        secret_token=webhook_secret(config.bot_token), drop_pending_updates=False)
    info = api('getWebhookInfo')
    if info.get('url') != url:
        raise RuntimeError('Webhook URL verification failed')
    print(f"::notice title=Bot setup::bot_id={identity['id']}, username={identity.get('username', '')}, total={total}, active={active}, webhook=registered", flush=True)


if __name__ == '__main__':
    main()
