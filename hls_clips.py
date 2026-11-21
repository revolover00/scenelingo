"""Download a public Clip.Cafe HLS rendition with the requested audio track."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.error import URLError

from media_tools import ffmpeg_executable
from preferences import validate_language

MAX_FILES = 30
MAX_PLAYLIST = 100_000


def _read(url: str, limit: int) -> bytes:
    # Import lazily to avoid a module cycle; enforce the existing source policy.
    from clip_cafe import allowed, get
    if not allowed(url):
        raise ValueError('Untrusted HLS URL')
    with get(url) as response:
        if not allowed(response.url):
            raise ValueError('Unexpected HLS redirect')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('HLS asset exceeds size limit')
    return data


def playlist_files(content: str) -> set[str]:
    """Allow only same-directory media filenames and unencrypted VOD streams."""
    if not content.startswith('#EXTM3U') or '#EXT-X-ENDLIST' not in content:
        raise ValueError('Invalid or non-VOD playlist')
    if '#EXT-X-KEY' in content or '#EXT-X-SESSION-KEY' in content:
        raise ValueError('Encrypted stream is not supported')
    names = []
    allowed_tags = {
        '#EXTM3U', '#EXT-X-VERSION', '#EXT-X-TARGETDURATION',
        '#EXT-X-MEDIA-SEQUENCE', '#EXT-X-PLAYLIST-TYPE',
        '#EXT-X-INDEPENDENT-SEGMENTS', '#EXTINF', '#EXT-X-BYTERANGE',
        '#EXT-X-ENDLIST', '#EXT-X-DISCONTINUITY',
        '#EXT-X-DISCONTINUITY-SEQUENCE', '#EXT-X-PROGRAM-DATE-TIME',
    }
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#EXT-X-MAP:'):
            match = re.fullmatch(r'#EXT-X-MAP:URI="([^"]+)"(?:,BYTERANGE="[0-9]+(?:@[0-9]+)?")?', line)
            if not match:
                raise ValueError('Invalid HLS initialization asset')
            names.append(match.group(1))
        elif line.startswith('#'):
            if line.split(':', 1)[0] not in allowed_tags or 'URI=' in line.upper():
                raise ValueError('Unsupported HLS playlist directive')
        else:
            names.append(line)
    if not names or len(set(names)) > MAX_FILES:
        raise ValueError('Invalid HLS asset count')
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name) or '..' in name for name in names):
        raise ValueError('Invalid HLS asset name')
    return set(names)


def download_localized(slug: str, language: str, path: Path) -> bool:
    """Create an MP4 with a requested public audio track, or return False.

    All manifests and referenced media are fetched with explicit size and host
    limits. FFmpeg receives local files only and cannot access the network.
    """
    from clip_cafe import BASE, MAX_BYTES
    validate_language(language)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', slug):
        raise ValueError('Invalid clip slug')
    try:
        info = json.loads(_read(f'{BASE}hls/{slug}/info.json', MAX_PLAYLIST))
        imdb = info.get('imdb')
        if (not info.get('hls_exists') or language not in info.get('audio_languages', [])
                or not isinstance(imdb, str) or not re.fullmatch(r'tt[0-9]+', imdb)):
            return False
        base = f'{BASE}hls/{imdb}/{slug}/'
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            files = set()
            for name in ('video-lq.m3u8', f'audio-{language}.m3u8'):
                data = _read(base + name, MAX_PLAYLIST)
                content = data.decode('utf-8')
                files.update(playlist_files(content))
                (tmp / name).write_bytes(data)
            if len(files) > MAX_FILES:
                raise ValueError('Too many HLS assets')
            remaining = MAX_BYTES
            for name in files:
                data = _read(base + name, remaining)
                remaining -= len(data)
                (tmp / name).write_bytes(data)
            path.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run([
                ffmpeg_executable(), '-nostdin', '-v', 'error', '-y',
                '-protocol_whitelist', 'file', '-i', str(tmp / 'video-lq.m3u8'),
                '-protocol_whitelist', 'file', '-i', str(tmp / f'audio-{language}.m3u8'),
                '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', '-movflags', '+faststart', str(path),
            ], check=False, capture_output=True, timeout=60)
            if result.returncode or not path.is_file() or not 1024 <= path.stat().st_size <= MAX_BYTES:
                path.unlink(missing_ok=True)
                return False
            with path.open('rb') as video:
                if b'ftyp' not in video.read(64):
                    path.unlink(missing_ok=True)
                    return False
            return True
    except (ValueError, TypeError, AttributeError, UnicodeError, URLError, OSError, subprocess.SubprocessError):
        path.unlink(missing_ok=True)
        return False
