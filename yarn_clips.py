"""Find a movie quote containing a word and download its short Yarn clip."""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

log = logging.getLogger(__name__)
BASE = 'https://yarn.co'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; MovieWordBot/1.0)'}
CLIP_ID = re.compile(r'/yarn-clip/([0-9a-f-]{36})(?:["\'/#?]|$)', re.IGNORECASE)
MP4_URL = re.compile(r'https://[^\s"\'<>\\]+\.mp4(?:\?[^\s"\'<>\\]*)?', re.IGNORECASE)
TITLE = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
MAX_BYTES = 20 * 1024 * 1024

@dataclass(frozen=True)
class YarnClip:
    clip_id: str
    title: str
    quote: str
    url: str
    path: Path


def _validate_yarn_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ''
    try:
        port = parsed.port
    except ValueError:
        port = -1

    if (
        parsed.scheme != 'https'
        or not (host == 'yarn.co' or host.endswith('.yarn.co'))
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f'Refusing to fetch unexpected URL: {url!r}')
    return url


class _YarnRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = _validate_yarn_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, target)


_YARN_OPENER = build_opener(_YarnRedirectHandler)


def _get(url: str):
    # The URL and every HTTP redirect stay on Yarn's HTTPS origin/subdomains.
    # This also allows its media CDN hosts, which the caller validates too.
    return _YARN_OPENER.open(Request(_validate_yarn_url(url), headers=HEADERS), timeout=30)


def _get_text(url: str) -> str:
    with _get(url) as response:
        return response.read().decode("utf-8", "replace")


def _parse_title(page: str, word: str) -> tuple[str, str] | None:
    match = TITLE.search(page)
    if not match:
        return None
    parts = [html.unescape(p).strip() for p in match.group(1).split('|')]
    if len(parts) < 4 or parts[0].upper() != 'YARN':
        return None
    quote, title = parts[1:3]
    if not re.search(rf'(?<!\w){re.escape(word)}(?!\w)', quote, re.IGNORECASE):
        return None
    return quote, title


def find_clip(word: str, out_dir: Path = Path('clips')) -> YarnClip:
    """Find a quote matching the whole word; never use an unrelated fallback."""
    search_url = f"{BASE}/yarn-find?{urlencode({'text': word, 'type': 'movies'})}"
    ids = list(dict.fromkeys(CLIP_ID.findall(_get_text(search_url))))[:20]
    for clip_id in ids:
        url = f'{BASE}/yarn-clip/{clip_id}'
        try:
            page = _get_text(url)
            parsed = _parse_title(page, word)
            if not parsed:
                continue
            match = MP4_URL.search(html.unescape(page))
            if not match:
                continue
            video_url = match.group(0)
            host = urlparse(video_url).hostname or ''
            if host != 'yarn.co' and not host.endswith('.yarn.co'):
                continue
            with _get(video_url) as video:
                final = urlparse(video.url)
                if final.scheme != 'https' or not (final.hostname == 'yarn.co' or (final.hostname or '').endswith('.yarn.co')):
                    raise ValueError('unexpected video host')
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f'yarn-{clip_id}.mp4'
                size = 0
                try:
                    with path.open('wb') as f:
                        for chunk in iter(lambda: video.read(65536), b''):
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise ValueError('Yarn video exceeds size limit')
                            f.write(chunk)
                    with path.open('rb') as f:
                        header = f.read(64)
                    if size < 1024 or b'ftyp' not in header:
                        raise ValueError('Yarn returned invalid MP4 data')
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
            quote, title = parsed
            log.info('Selected Yarn clip %s: %s', clip_id, title)
            return YarnClip(clip_id, title, quote, url, path)
        except (URLError, ValueError, OSError) as exc:
            log.warning('Could not use Yarn clip %s: %s', clip_id, exc)
    raise RuntimeError(f'No downloadable movie clip with the word {word!r} found on Yarn')
