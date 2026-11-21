import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import check_webhook


class WebhookRecoveryTests(unittest.TestCase):
    def run_check(self, info, endpoint_status=200, repair=True):
        self.calls = []

        def post(url, **kwargs):
            payload = kwargs.get('json', {})
            self.calls.append((url, payload))
            if url == check_webhook.EXPECTED:
                return SimpleNamespace(status_code=endpoint_status)
            method = url.rsplit('/', 1)[-1]
            result = info.pop(0) if method == 'getWebhookInfo' else True
            return SimpleNamespace(ok=True, json=lambda: {'ok': True, 'result': result})

        with patch.dict(os.environ, {'BOT_TOKEN': '9051063252:test', 'REPAIR_WEBHOOK': 'true' if repair else 'false'}), patch.object(check_webhook.requests, 'post', post):
            check_webhook.main()

    def test_repair_preserves_pending_and_only_sets_webhook(self):
        self.run_check([{'url': 'https://example.com/other', 'pending_update_count': 4}, {'url': check_webhook.EXPECTED}])
        writes = [p for url, p in self.calls if url.endswith('/setWebhook')]
        self.assertEqual(writes, [{'url': check_webhook.EXPECTED, 'allowed_updates': ['message', 'callback_query'], 'drop_pending_updates': False, 'secret_token': check_webhook.webhook_secret('9051063252:test')}])
        self.assertFalse(any('/send' in url for url, _ in self.calls))

    def test_correct_webhook_is_not_rewritten(self):
        self.run_check([{'url': check_webhook.EXPECTED}], repair=False)
        self.assertFalse(any(url.endswith('/setWebhook') for url, _ in self.calls))

    def test_unhealthy_endpoint_cannot_replace_webhook(self):
        with self.assertRaisesRegex(RuntimeError, 'endpoint failed'):
            self.run_check([{'url': 'https://example.com'}], 500)
        self.assertFalse(any(url.endswith('/setWebhook') for url, _ in self.calls))

    def test_shared_secret_matches_javascript_vector(self):
        self.assertEqual(check_webhook.webhook_secret('123456:test-token'),
                         '955961b5fd65a32feff2104749ff616a5af4d27aa07adbe4836505c583beaa39')

    def test_recent_errors_with_pending_updates_are_reported(self):
        import time
        with self.assertRaisesRegex(RuntimeError, 'pending updates'):
            self.run_check([{'url': check_webhook.EXPECTED, 'pending_update_count': 2,
                             'last_error_date': int(time.time())}], repair=False)
