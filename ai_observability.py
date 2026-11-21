"""Record reported API usage only, never prompts, transcripts, keys or prices."""
import logging
import time

from config import config

log = logging.getLogger(__name__)


def tracked(operation, request, **kwargs):
    started = time.monotonic()
    response = None
    status = 'failed'
    try:
        response = request(**kwargs)
        status = 'ok'
        return response
    finally:
        if config.database_url and config.bot_token:
            try:
                import db
                usage = getattr(response, 'usage', None)
                def count(name):
                    value = getattr(usage, name, None)
                    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
                with db.session() as conn, conn.cursor() as cur:
                    cur.execute('''INSERT INTO ai_usage(operation,model,status,prompt_tokens,completion_tokens,duration_seconds)
                        VALUES(%s,%s,%s,%s,%s,%s)''', (operation,kwargs.get('model','unknown'),status,
                        count('prompt_tokens'),count('completion_tokens'),time.monotonic()-started))
            except Exception:  # noqa: BLE001 - telemetry must never mask the primary API result
                # Observability failure must never mask an API response or its original error.
                log.warning('AI usage recording unavailable')
