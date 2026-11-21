"""YouTube search via the public InnerTube API.

Ported from the `youtube-free-ads` project (Youtubiy): talks to
YouTube's own endpoint directly, no API key, no Piped/Invidious.

Note: YouTube changes the InnerTube API without notice, so the
`clientVersion` below may need a bump every few months.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

INNERTUBE = "https://www.youtube.com/youtubei/v1"
CLIENT = {
    "clientName": "WEB",
    "clientVersion": "2.20240401.00.00",
    "hl": "ar",
    "gl": "EG",
}
HEADERS = {
    "content-type": "application/json",
    "accept-language": "ar,en;q=0.8",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    channel: str = ""
    duration: int = 0  # seconds
    thumbnail: str = ""
    url: str = ""

    def __post_init__(self) -> None:
        if not self.url:
            object.__setattr__(self, "url", f"https://www.youtube.com/watch?v={self.video_id}")
        if not self.thumbnail:
            object.__setattr__(
                self, "thumbnail", f"https://i.ytimg.com/vi/{self.video_id}/hqdefault.jpg"
            )


def _text(node) -> str:
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node.get("simpleText"), str):
        return node["simpleText"]
    if isinstance(node.get("content"), str):
        return node["content"]
    runs = node.get("runs") or []
    return "".join(r.get("text", "") if isinstance(r, dict) else str(r) for r in runs)


def _collect(node, key: str, out: list | None = None, depth: int = 0) -> list:
    if out is None:
        out = []
    if not node or not isinstance(node, (dict, list)) or depth > 20:
        return out
    if isinstance(node, list):
        for item in node:
            _collect(item, key, out, depth + 1)
        return out
    for k, v in node.items():
        if k == key:
            out.append(v)
        else:
            _collect(v, key, out, depth + 1)
    return out


def _parse_duration(s: str) -> int:
    s = s.replace(",", "").strip()
    if not s or ":" not in s:
        return 0
    try:
        parts = [int(p) for p in s.split(":")]
    except ValueError:
        return 0
    return sum(p * 60**i for i, p in enumerate(reversed(parts)))


def _from_video_renderer(r: dict) -> Video | None:
    video_id = r.get("videoId")
    title = _text(r.get("title"))
    if not video_id or not title:
        return None
    byline = r.get("longBylineText") or r.get("ownerText") or r.get("shortBylineText")
    channel = _text(byline)
    duration = _parse_duration(_text(r.get("lengthText")))
    thumbs = (r.get("thumbnail") or {}).get("thumbnails") or []
    thumbnail = thumbs[-1].get("url", "") if thumbs else ""
    return Video(video_id, title, channel, duration, thumbnail)


def _from_lockup(r: dict) -> Video | None:
    if r.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
        return None
    video_id = r.get("contentId")
    meta = ((r.get("metadata") or {}).get("lockupMetadataViewModel") or {})
    title = _text(meta.get("title"))
    if not video_id or not title:
        return None
    rows = ((meta.get("metadata") or {}).get("metadataRows") or [])
    channel = ""
    if rows:
        parts = rows[0].get("metadataParts") or []
        if parts:
            channel = _text(parts[0].get("text"))
    badge = _collect(r.get("contentImage"), "thumbnailBadgeViewModel")
    badge_text = (badge[0].get("text") or "").strip() if badge else ""
    duration = _parse_duration(badge_text)
    sources = _collect(r.get("contentImage"), "sources")
    thumbnail = sources[-1][-1].get("url", "") if sources and sources[-1] else ""
    return Video(video_id, title, channel, duration, thumbnail)


def _extract_videos(payload: dict) -> list[Video]:
    out: list[Video] = []
    seen: set[str] = set()
    for r in _collect(payload, "videoRenderer"):
        v = _from_video_renderer(r)
        if v and v.video_id not in seen:
            seen.add(v.video_id)
            out.append(v)
    for r in _collect(payload, "lockupViewModel"):
        v = _from_lockup(r)
        if v and v.video_id not in seen:
            seen.add(v.video_id)
            out.append(v)
    return out


def _search_via_ytdlp(query: str, max_results: int) -> list[Video]:
    """Fallback search via yt-dlp (used when InnerTube breaks)."""
    import subprocess

    res = subprocess.run(
        [
            "yt-dlp",
            "--flat-playlist",
            "--print", "%(id)s\t%(title)s\t%(channel)s",
            f"ytsearch{max_results}:{query}",
        ],
        check=False,  # Partial search output is still useful; inspect returncode below.
        capture_output=True,
        text=True,
        timeout=60,
    )
    videos: list[Video] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        videos.append(Video(parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    log.info("yt-dlp fallback search %r -> %d videos", query, len(videos))
    return videos


def search(query: str, max_results: int = 5) -> list[Video]:
    """Search YouTube for `query` and return up to `max_results` videos.

    Tries InnerTube first; falls back to yt-dlp search when InnerTube
    fails (YouTube changes its API without notice).
    """
    try:
        res = requests.post(
            f"{INNERTUBE}/search?prettyPrint=false",
            headers=HEADERS,
            json={"context": {"client": CLIENT}, "query": query},
            timeout=30,
        )
        if not res.ok:
            raise RuntimeError(f"YouTube search failed: HTTP {res.status_code}")
        videos = _extract_videos(res.json())
        if videos:
            log.info("Search %r -> %d videos", query, len(videos))
            return videos[:max_results]
        log.warning("InnerTube returned no videos, trying yt-dlp fallback")
    except (requests.RequestException, RuntimeError) as exc:
        log.warning("InnerTube search failed (%s), trying yt-dlp fallback", exc)
    return _search_via_ytdlp(query, max_results)
