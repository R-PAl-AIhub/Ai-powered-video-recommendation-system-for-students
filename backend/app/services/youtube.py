"""YouTube access: playlist/video metadata, transcripts and search.

Two metadata backends share one interface:

* ``YtDlpBackend`` needs no credentials (default).
* ``DataApiBackend`` uses the official YouTube Data API v3 when ``YOUTUBE_API_KEY``
  is set. It is the more dependable choice on cloud hosts, where YouTube often
  blocks unauthenticated scraping.

Transcripts always come from YouTube's caption tracks. User input is reduced to a
validated playlist/video id before any request is made, so a pasted URL is never
fetched directly.
"""

from __future__ import annotations

import logging
import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PLAYLIST_ID = re.compile(r"^(PL|UU|LL|FL|OL|RD|UL)[A-Za-z0-9_-]{10,80}$")
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


class YouTubeError(Exception):
    """A YouTube request failed in a way worth showing to the student."""


class YouTubeBlocked(YouTubeError):
    """YouTube is refusing requests from this address (rate limit or bot check)."""


_pace_lock = threading.Lock()
_next_slot = 0.0


def pace() -> None:
    """Wait for this process's next request slot.

    One shared, jittered schedule for every YouTube request keeps the request
    rate low and irregular; a burst of a few hundred requests in a minute is
    enough for YouTube to block an address for hours.
    """
    global _next_slot
    interval = get_settings().youtube_request_interval
    if interval <= 0:
        return
    with _pace_lock:
        now = time.monotonic()
        wait = max(0.0, _next_slot - now)
        _next_slot = max(now, _next_slot) + interval * random.uniform(0.8, 1.4)
    if wait:
        time.sleep(wait)


@dataclass
class VideoMeta:
    youtube_id: str
    title: str = ""
    description: str = ""
    channel: str = ""
    duration_s: int = 0
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    published_at: datetime | None = None
    thumbnail_url: str = ""
    chapters: list[str] = field(default_factory=list)
    position: int = 0


@dataclass
class PlaylistMeta:
    youtube_id: str
    title: str
    channel: str
    videos: list[VideoMeta]


@dataclass
class TranscriptSegment:
    start: float
    duration: float
    text: str


@dataclass
class Transcript:
    language: str  # e.g. "en", or "hi→en" when machine-translated
    is_generated: bool
    segments: list[TranscriptSegment]


class YouTubeClient(Protocol):
    def fetch_playlist(self, playlist_id: str, limit: int) -> PlaylistMeta: ...
    def fetch_video(self, video_id: str) -> VideoMeta: ...
    def fetch_transcript(self, video_id: str) -> Transcript | None: ...
    def search(self, query: str, limit: int = 8) -> list[VideoMeta]: ...


# --------------------------------------------------------------------------- ids


def parse_playlist_id(value: str) -> str | None:
    """Extract a playlist id from a URL or a bare id. Returns None if there is none."""
    value = (value or "").strip()
    if _PLAYLIST_ID.match(value):
        return value
    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
    except ValueError:
        return None
    if (parsed.hostname or "").lower() not in _YT_HOSTS:
        return None
    candidate = (parse_qs(parsed.query).get("list") or [""])[0]
    return candidate if _PLAYLIST_ID.match(candidate) else None


def parse_video_id(value: str) -> str | None:
    """Extract a video id from a watch/short/embed URL or a bare id."""
    value = (value or "").strip()
    if _VIDEO_ID.match(value):
        return value
    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in _YT_HOSTS:
        return None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]
    else:
        match = re.match(r"^/(?:shorts|embed|live|v)/([A-Za-z0-9_-]{11})", parsed.path)
        candidate = match.group(1) if match else ""
    return candidate if _VIDEO_ID.match(candidate) else None


def thumbnail_for(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"


def watch_url(video_id: str, start_s: float = 0, playlist_id: str | None = None) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    if playlist_id:
        url += f"&list={playlist_id}"
    if start_s >= 1:
        url += f"&t={int(start_s)}s"
    return url


# ------------------------------------------------------------------- transcripts


def _fetch_transcript(video_id: str) -> Transcript | None:
    """Fetch captions in whatever language the video has.

    Order of preference: human-written English, auto-generated English, any other
    language machine-translated to English by YouTube, and finally the original
    language untouched (usable with a multilingual embedding model).
    Raises YouTubeBlocked when YouTube refuses the request.
    """
    from youtube_transcript_api import (
        IpBlocked,
        NoTranscriptFound,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
        YouTubeTranscriptApi,
    )
    from youtube_transcript_api.proxies import GenericProxyConfig

    settings = get_settings()
    proxy = settings.youtube_proxy
    api = YouTubeTranscriptApi(
        proxy_config=GenericProxyConfig(http_url=proxy, https_url=proxy) if proxy else None
    )
    pace()
    try:
        tracks = list(api.list(video_id))
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        return None
    except (IpBlocked, RequestBlocked) as exc:
        raise YouTubeBlocked("YouTube is temporarily refusing requests") from exc
    if not tracks:
        return None

    def is_english(track) -> bool:
        return track.language_code.lower().split("-")[0] == "en"

    chosen = next((t for t in tracks if is_english(t) and not t.is_generated), None)
    chosen = chosen or next((t for t in tracks if is_english(t)), None)
    language = chosen.language_code if chosen else ""
    generated = chosen.is_generated if chosen else True

    fetched = None
    try:
        if chosen is not None:
            fetched = chosen.fetch()
        else:
            original = next((t for t in tracks if not t.is_generated), tracks[0])
            if original.is_translatable:
                try:
                    pace()
                    fetched = original.translate("en").fetch()
                    language, generated = f"{original.language_code}→en", True
                except (IpBlocked, RequestBlocked):
                    raise
                except Exception as exc:  # translation is best-effort
                    log.info("translate failed for %s: %s", video_id, exc)
            if fetched is None:
                fetched = original.fetch()
                language, generated = original.language_code, original.is_generated
    except (IpBlocked, RequestBlocked) as exc:
        raise YouTubeBlocked("YouTube is temporarily refusing requests") from exc

    segments = [
        TranscriptSegment(start=float(s.start), duration=float(s.duration), text=s.text)
        for s in fetched
        if s.text and s.text.strip()
    ]
    if not segments:
        return None
    return Transcript(language=language, is_generated=generated, segments=segments)


# ------------------------------------------------------------------------ yt-dlp


def _to_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class YtDlpBackend:
    """Credential-free backend built on yt-dlp."""

    def _options(self, **extra) -> dict:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": False,
            "socket_timeout": 20,
            "retries": 2,
        }
        proxy = get_settings().youtube_proxy
        if proxy:
            options["proxy"] = proxy
        options.update(extra)
        return options

    def _extract(self, url: str, **extra) -> dict:
        import yt_dlp

        pace()
        try:
            with yt_dlp.YoutubeDL(self._options(**extra)) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            message = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).replace("ERROR: ", "")
            if "not a bot" in message or "429" in message:
                raise YouTubeBlocked(
                    "YouTube is temporarily refusing requests from this server. Try again later."
                ) from exc
            raise YouTubeError(message[:300]) from exc
        if not info:
            raise YouTubeError("YouTube returned no data")
        return info

    @staticmethod
    def _meta_from_flat(entry: dict, position: int) -> VideoMeta | None:
        video_id = entry.get("id") or ""
        if not _VIDEO_ID.match(video_id):
            return None
        title = entry.get("title") or ""
        if title in {"[Private video]", "[Deleted video]"}:
            return None
        return VideoMeta(
            youtube_id=video_id,
            title=title,
            description=entry.get("description") or "",
            channel=entry.get("channel") or entry.get("uploader") or "",
            duration_s=_to_int(entry.get("duration")) or 0,
            view_count=_to_int(entry.get("view_count")),
            thumbnail_url=thumbnail_for(video_id),
            position=position,
        )

    def fetch_playlist(self, playlist_id: str, limit: int) -> PlaylistMeta:
        info = self._extract(
            f"https://www.youtube.com/playlist?list={playlist_id}",
            extract_flat="in_playlist",
            playlistend=limit,
        )
        channel = info.get("channel") or info.get("uploader") or ""
        videos = []
        for position, entry in enumerate(info.get("entries") or []):
            meta = self._meta_from_flat(entry or {}, position)
            if meta:
                meta.channel = meta.channel or channel
                videos.append(meta)
        return PlaylistMeta(
            youtube_id=playlist_id,
            title=info.get("title") or "Untitled playlist",
            channel=channel,
            videos=videos,
        )

    def fetch_video(self, video_id: str) -> VideoMeta:
        info = self._extract(f"https://www.youtube.com/watch?v={video_id}")
        published = None
        if info.get("upload_date"):
            try:
                published = datetime.strptime(info["upload_date"], "%Y%m%d").replace(tzinfo=UTC)
            except ValueError:
                published = None
        return VideoMeta(
            youtube_id=video_id,
            title=info.get("title") or "",
            description=info.get("description") or "",
            channel=info.get("channel") or info.get("uploader") or "",
            duration_s=_to_int(info.get("duration")) or 0,
            view_count=_to_int(info.get("view_count")),
            like_count=_to_int(info.get("like_count")),
            comment_count=_to_int(info.get("comment_count")),
            published_at=published,
            thumbnail_url=thumbnail_for(video_id),
            chapters=[c.get("title", "") for c in (info.get("chapters") or []) if c.get("title")],
        )

    def fetch_transcript(self, video_id: str) -> Transcript | None:
        return _fetch_transcript(video_id)

    def search(self, query: str, limit: int = 8) -> list[VideoMeta]:
        info = self._extract(f"ytsearch{limit}:{query}", extract_flat=True)
        results = []
        for position, entry in enumerate(info.get("entries") or []):
            meta = self._meta_from_flat(entry or {}, position)
            if meta:
                results.append(meta)
        return results


# ---------------------------------------------------------------------- Data API


_ISO_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_iso_duration(value: str) -> int:
    match = _ISO_DURATION.match(value or "")
    if not match:
        return 0
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class DataApiBackend:
    """Metadata via the official YouTube Data API v3."""

    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None):
        self._key = api_key
        self._http = httpx.Client(timeout=20, transport=transport)

    def _get(self, path: str, **params) -> dict:
        try:
            response = self._http.get(f"{self.BASE}/{path}", params={**params, "key": self._key})
        except httpx.HTTPError as exc:
            raise YouTubeError(f"Could not reach the YouTube API: {exc}") from exc
        if response.status_code != 200:
            try:
                reason = response.json()["error"]["message"]
            except Exception:
                reason = f"HTTP {response.status_code}"
            raise YouTubeError(f"YouTube API error: {reason}"[:300])
        return response.json()

    def _videos(self, ids: list[str]) -> dict[str, VideoMeta]:
        out: dict[str, VideoMeta] = {}
        for start in range(0, len(ids), 50):
            data = self._get(
                "videos",
                part="snippet,contentDetails,statistics",
                id=",".join(ids[start : start + 50]),
                maxResults=50,
            )
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                published = None
                if snippet.get("publishedAt"):
                    try:
                        published = datetime.fromisoformat(
                            snippet["publishedAt"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        published = None
                out[item["id"]] = VideoMeta(
                    youtube_id=item["id"],
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    channel=snippet.get("channelTitle", ""),
                    duration_s=parse_iso_duration(
                        item.get("contentDetails", {}).get("duration", "")
                    ),
                    view_count=_to_int(stats.get("viewCount")),
                    like_count=_to_int(stats.get("likeCount")),
                    comment_count=_to_int(stats.get("commentCount")),
                    published_at=published,
                    thumbnail_url=thumbnail_for(item["id"]),
                )
        return out

    def fetch_playlist(self, playlist_id: str, limit: int) -> PlaylistMeta:
        head = self._get("playlists", part="snippet", id=playlist_id)
        if not head.get("items"):
            raise YouTubeError("Playlist not found or private")
        snippet = head["items"][0]["snippet"]
        ids: list[str] = []
        token: str | None = None
        while len(ids) < limit:
            params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if token:
                params["pageToken"] = token
            page = self._get("playlistItems", **params)
            ids.extend(i["contentDetails"]["videoId"] for i in page.get("items", []))
            token = page.get("nextPageToken")
            if not token:
                break
        ids = ids[:limit]
        details = self._videos(ids)
        videos = []
        for position, video_id in enumerate(ids):
            meta = details.get(video_id)  # private/deleted videos are absent
            if meta:
                meta.position = position
                videos.append(meta)
        return PlaylistMeta(
            youtube_id=playlist_id,
            title=snippet.get("title", "Untitled playlist"),
            channel=snippet.get("channelTitle", ""),
            videos=videos,
        )

    def fetch_video(self, video_id: str) -> VideoMeta:
        details = self._videos([video_id])
        if video_id not in details:
            raise YouTubeError("Video not found or private")
        return details[video_id]

    def fetch_transcript(self, video_id: str) -> Transcript | None:
        return _fetch_transcript(video_id)

    def search(self, query: str, limit: int = 8) -> list[VideoMeta]:
        data = self._get(
            "search", part="id", q=query, type="video", maxResults=min(limit, 25), safeSearch="strict"
        )
        ids = [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]
        details = self._videos(ids)
        return [details[i] for i in ids if i in details]


# ----------------------------------------------------------------------- factory

_override: YouTubeClient | None = None


def set_youtube_client(client: YouTubeClient | None) -> None:
    """Replace the client (tests use this to avoid network access)."""
    global _override
    _override = client


def get_youtube_client() -> YouTubeClient:
    if _override is not None:
        return _override
    settings = get_settings()
    if settings.youtube_api_key:
        return DataApiBackend(settings.youtube_api_key)
    return YtDlpBackend()
