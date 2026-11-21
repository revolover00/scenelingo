"""Bounded bot-local cache of successful movie-audio transcriptions, not verdicts."""
import hashlib
import logging
from contextlib import closing

from config import config
import db

log = logging.getLogger(__name__)
MODEL = 'whisper-large-v3-turbo'


def key(path):
    digest = hashlib.sha256(MODEL.encode())
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def get(audio_hash):
    if not (config.database_url and config.bot_token):
        return None
    try:
        with closing(db.connect()) as conn, conn, conn.cursor() as cur:
            cur.execute('SELECT detected_language,transcript FROM audio_transcripts WHERE audio_hash=%s AND expires_at>now()', (audio_hash,))
            return cur.fetchone()
    except Exception:
        log.warning('Transcript cache lookup unavailable')
        return None


def save(audio_hash, language, transcript):
    if not (config.database_url and config.bot_token) or not transcript.strip() or len(transcript)>12000:
        return
    try:
        with closing(db.connect()) as conn, conn, conn.cursor() as cur:
            cur.execute('DELETE FROM audio_transcripts WHERE expires_at<=now()')
            cur.execute('''INSERT INTO audio_transcripts(audio_hash,detected_language,transcript) VALUES(%s,%s,%s)
                ON CONFLICT(audio_hash) DO UPDATE SET detected_language=EXCLUDED.detected_language,
                transcript=EXCLUDED.transcript,expires_at=now()+interval '7 days' ''', (audio_hash,language,transcript))
            cur.execute('''DELETE FROM audio_transcripts WHERE audio_hash IN
                (SELECT audio_hash FROM audio_transcripts ORDER BY created_at DESC,audio_hash OFFSET 1000)''')
    except Exception:
        log.warning('Transcript cache persistence unavailable')
