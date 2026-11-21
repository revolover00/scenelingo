"""Inspect/restore the existing Vercel webhook without exposing credentials."""
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from webhook_auth import webhook_secret

EXPECTED = 'https://scenelingoo.vercel.app/api/telegram'


def main():
    token = os.environ['BOT_TOKEN']
    if token.split(':')[0] != '9051063252':
        raise RuntimeError('Unexpected bot identity')

    def api(method, **payload):
        try:
            r = requests.post(f'https://api.telegram.org/bot{token}/{method}', json=payload, timeout=30)
            data = r.json()
            if not r.ok or not data.get('ok'):
                raise ValueError()
            return data['result']
        except Exception:  # noqa: BLE001 - normalize any failed Telegram API probe
            raise RuntimeError(f'Telegram {method} failed') from None

    info = api('getWebhookInfo')
    matches = info.get('url') == EXPECTED
    print(f'::notice title=Webhook inspection::expected_url={matches}, pending={info.get("pending_update_count", 0)}, recent_error={bool(info.get("last_error_message"))}', flush=True)
    if info.get('last_error_message'):
        message = info['last_error_message']
        # Only emit known diagnostic classifications, never raw remote text.
        classification = next((s for s in ['500', '404', '401', '403', 'timeout', 'SSL'] if s.lower() in message.lower()), 'other')
        print(f'::notice title=Webhook error class::{classification}', flush=True)
    try:
        response = requests.post(EXPECTED, json={}, headers={'X-Telegram-Bot-Api-Secret-Token': webhook_secret(token)}, timeout=45)
        print(f'::notice title=Webhook endpoint::empty_update_http={response.status_code}', flush=True)
        if response.status_code != 200:
            raise ValueError()
    except Exception:  # noqa: BLE001 - fail closed on any probe network or response error
        raise RuntimeError('Production webhook endpoint failed safe empty-update probe') from None
    if os.environ.get('VERIFY_AUTH') == 'true':
        try:
            denied = requests.post(EXPECTED, json={}, timeout=30)
            if denied.status_code != 403:
                raise ValueError()
        except Exception:  # noqa: BLE001 - fail closed if any auth probe or response parsing fails
            raise RuntimeError('Webhook did not reject an unauthenticated update') from None
        print('::notice title=Webhook authentication::Unauthenticated update rejected', flush=True)
    if os.environ.get('REPAIR_WEBHOOK') == 'true':
        api('setWebhook', url=EXPECTED, allowed_updates=['message', 'callback_query'], drop_pending_updates=False, secret_token=webhook_secret(token))
        if api('getWebhookInfo').get('url') != EXPECTED:
            raise RuntimeError('Webhook repair verification failed')
        print('::notice title=Webhook repair::Vercel URL and authentication registered; pending updates preserved', flush=True)
    elif not matches:
        raise RuntimeError('Webhook points away from production Vercel endpoint')
    if (info.get('pending_update_count', 0) > 0
            and info.get('last_error_date', 0) > time.time() - 900):
        raise RuntimeError('Webhook has pending updates and a recent delivery error; inspect Telegram delivery')


if __name__ == '__main__':
    main()
