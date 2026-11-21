"""Search public Clip.Cafe movie dialogue and download a matching clip."""
from __future__ import annotations

import logging
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = 'https://clip.cafe/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'}
MAX_BYTES = 20 * 1024 * 1024
log = logging.getLogger(__name__)

@dataclass(frozen=True)
class Clip:
    clip_id: str
    title: str
    quote: str
    url: str
    path: Path

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.meta = {}
        self.audio_languages = {}
        self.current_link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'picture' and attrs.get('data-link'):
            self.current_link = attrs['data-link']
            self.links.append(self.current_link)
        audio = attrs.get('aria-label', '')
        if self.current_link and audio.startswith('Audio: '):
            self.audio_languages[self.current_link] = {x.strip().casefold() for x in audio[7:].split(',')}
        if tag == 'meta' and attrs.get('property') and attrs.get('content'):
            self.meta[attrs['property']] = attrs['content']


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise ValueError('Unexpected source redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = build_opener(SafeRedirect())


def get(url):
    if not allowed(url):
        raise ValueError('Unexpected source URL')
    return _opener.open(Request(url, headers=HEADERS), timeout=30)


def page(url):
    with get(url) as response:
        data = response.read(2_000_000).decode('utf-8', 'replace')
    parser = PageParser()
    parser.feed(data)
    return parser


def normalize_contractions(text: str) -> str:
    """Expand unambiguous English contractions; retain strict word order/negation.

    Ambiguous 's / 'd forms are intentionally left alone except a small set of
    unmistakable predicate contexts. This is not fuzzy or semantic matching.
    """
    text = text.casefold().replace('’', "'").replace('‘', "'")
    forms = {
        "let's": 'let us', "i'm": 'i am', "you're": 'you are', "we're": 'we are',
        "they're": 'they are', "don't": 'do not', "doesn't": 'does not',
        "didn't": 'did not', "can't": 'can not', 'cannot': 'can not',
        "won't": 'will not', "isn't": 'is not', "aren't": 'are not',
        "wasn't": 'was not', "weren't": 'were not', "haven't": 'have not',
        "hasn't": 'has not', "hadn't": 'had not', "wouldn't": 'would not',
        "shouldn't": 'should not', "couldn't": 'could not',
        "i'll": 'i will', "you'll": 'you will', "we'll": 'we will',
        "they'll": 'they will', "he'll": 'he will', "she'll": 'she will',
        "i've": 'i have', "you've": 'you have', "we've": 'we have', "they've": 'they have',
    }
    for contraction, expanded in forms.items():
        text = re.sub(r"(?<![\w'])" + re.escape(contraction) + r"(?![\w'])", expanded, text)
    text = re.sub(r"\b(it|that|there|what|here)'s(?=\s+(?:a|an|the|no|not|beside)\b)", r'\1 is', text)
    return text


def matches(phrase: str, quote: str) -> bool:
    """Require all expression words in order, ignoring punctuation and case."""
    def tokenize(text: str) -> list[str]:
        # Fold Latin accents but preserve combining marks in scripts where
        # they are essential to meaning (e.g. Hindi vowel signs).
        result, current = [], []
        latin = False
        for char in unicodedata.normalize('NFKD', text.casefold()):
            if unicodedata.category(char).startswith('M'):
                if current and not latin:
                    current.append(char)
            elif char.isalnum():
                current.append(char)
                latin = 'LATIN' in unicodedata.name(char, '')
            elif current:
                result.append(''.join(current))
                current = []
                latin = False
        if current:
            result.append(''.join(current))
        return result

    tokens = tokenize(normalize_contractions(phrase))
    words = tokenize(normalize_contractions(quote))
    if not tokens:
        return False
    # CJK scripts commonly omit spaces between words; match the continuous
    # sequence, but retain whole-word boundaries for other writing systems.
    cjk = lambda word: any('\u3040' <= c <= '\u30ff' or '\u3400' <= c <= '\u9fff' for c in word)
    if any(cjk(token) for token in tokens):
        return ''.join(tokens) in ''.join(words)
    return any(words[i:i + len(tokens)] == tokens for i in range(len(words)))


def allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (parsed.scheme == 'https' and parsed.hostname == 'clip.cafe'
                and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except ValueError:
        return False


def search_links(phrase: str, audio_language: str | None, search_language: str | None = None, limit: int = 15):
    """Prefer source language filters, then try unrestricted results.

    Source metadata is not proof of the MP4's spoken language; callers must
    verify audio before accepting multilingual clips.
    """
    base = {'s': f'"{phrase}"', 'usersearch': '1', 'ss': 's'}
    queries = ([dict(base, audio=audio_language, sl=search_language or audio_language), base]
               if audio_language else [base])
    seen = set()
    for query in queries:
        result = page(BASE + '?' + urlencode(query))
        links = list(dict.fromkeys(result.links[:30]))
        if len(links) > limit and limit < 15:
            # Keep some top-ranked clips and sample beyond them so repeated
            # bounded retries can discover other actual audio tracks.
            first = (limit + 1) // 2
            links = links[:first] + random.sample(links[first:], limit - first)
        else:
            links = links[:limit]
        for link in links:
            if link not in seen:
                seen.add(link)
                yield link


def load_clip(url: str, phrase: str, out_dir: Path = Path('clips'), *, verify=None,
              audio_language=None, expected_id=None) -> Clip:
    """Restore a specific source page without searching or substituting scenes."""
    if not allowed(url):
        raise ValueError('Unexpected clip source')
    details = page(url)
    quote = details.meta.get('og:description', '')
    title = details.meta.get('og:title', '')
    video_url = details.meta.get('og:video:secure_url') or details.meta.get('og:video', '')
    if (verify is None and not matches(phrase, quote)) or not allowed(video_url):
        raise ValueError("Clip metadata or audio verification rejected")
    # Movie title appears after the separator in the page title.
    movie = title.rsplit('|', 1)[-1].strip().removesuffix(' scene').strip() or 'Film'
    slug = urlparse(video_url).path.rsplit('/', 1)[-1].removesuffix('.mp4')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', slug) or (expected_id is not None and slug != expected_id):
        raise ValueError("Clip metadata or audio verification rejected")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'clipcafe-{slug}.mp4'
    localized = False
    if audio_language and verify is not None:
        from hls_clips import download_localized
        localized = download_localized(slug, audio_language, path)
    if not localized:
        with get(video_url) as video:
            if not allowed(video.url):
                raise ValueError('Unexpected video redirect')
            size = 0
            try:
                with path.open('wb') as output:
                    for chunk in iter(lambda: video.read(65536), b''):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError('Clip exceeds size limit')
                        output.write(chunk)
                with path.open('rb') as f:
                    if size < 1024 or b'ftyp' not in f.read(64):
                        raise ValueError('Invalid MP4')
            except Exception:
                path.unlink(missing_ok=True)
                raise
    if verify is not None:
        try:
            verified = verify(path, phrase)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        if not verified:
            path.unlink(missing_ok=True)
            log.info('Audio did not match the requested expression in clip %s', slug)
            raise ValueError("Clip metadata or audio verification rejected")
    log.info('Selected Clip.Cafe clip %s: %s', slug, movie)
    return Clip(slug, movie, quote, url, path)


def find_clip(phrase: str, out_dir: Path = Path('clips'), *, verify=None, audio_language: str | None = None, search_language: str | None = None, max_results: int = 15, max_seconds: int = 45) -> Clip:
    deadline = time.monotonic() + max_seconds
    for link in search_links(phrase, audio_language, search_language, max_results):
        if time.monotonic() >= deadline:
            break
        url = urljoin(BASE, link)
        if not allowed(url):
            continue
        try:
            return load_clip(url, phrase, out_dir, verify=verify, audio_language=audio_language)
        except (URLError, ValueError, OSError) as exc:
            log.warning('Could not use clip %s: %s', url, exc)
    raise RuntimeError(f'No downloadable clip matching {phrase!r} found on Clip.Cafe')
