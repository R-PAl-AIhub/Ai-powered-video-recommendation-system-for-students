"""YouTube access without the network: id parsing, request pacing, the yt-dlp
backend, the Data API backend (against a fake HTTP transport), caption choice,
and the client factory."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.config import get_settings
from app.services import youtube
from app.services.youtube import (
    DataApiBackend,
    YouTubeBlocked,
    YouTubeError,
    YtDlpBackend,
    parse_iso_duration,
    parse_playlist_id,
    parse_video_id,
    watch_url,
)

VIDEO = "dQw4w9WgXcQ"
PLAYLIST = "PLBlnK6fEyqRiVhbXDGLXDk_OQAeuVcp2O"
WATCH = f"https://www.youtube.com/watch?v={VIDEO}"


# ------------------------------------------------------------------------- ids


@pytest.mark.parametrize(
    "value",
    [
        PLAYLIST,
        f"https://www.youtube.com/playlist?list={PLAYLIST}",
        f"youtube.com/watch?v={VIDEO}&list={PLAYLIST}",
        f"  https://m.youtube.com/playlist?list={PLAYLIST}&si=abc  ",
    ],
)
def test_parse_playlist_id_accepts_urls_and_bare_ids(value):
    assert parse_playlist_id(value) == PLAYLIST


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        "not a playlist",
        f"https://evil.example.com/playlist?list={PLAYLIST}",  # only YouTube hosts
        "https://www.youtube.com/playlist?list=../../etc/passwd",
        WATCH,  # no list parameter
        "http://[broken",
    ],
)
def test_parse_playlist_id_rejects_everything_else(value):
    assert parse_playlist_id(value) is None


@pytest.mark.parametrize(
    "value",
    [
        VIDEO,
        f"{WATCH}&t=42s",
        f"https://youtu.be/{VIDEO}?si=xyz",
        f"https://www.youtube.com/shorts/{VIDEO}",
        f"https://www.youtube.com/embed/{VIDEO}",
        f"https://www.youtube.com/live/{VIDEO}",
        f"m.youtube.com/watch?v={VIDEO}",
    ],
)
def test_parse_video_id_accepts_every_common_link_form(value):
    assert parse_video_id(value) == VIDEO


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        "short",
        f"https://vimeo.com/{VIDEO}",
        "https://www.youtube.com/watch?v=bad",
        "https://www.youtube.com/channel/abc",
        "http://[broken",
    ],
)
def test_parse_video_id_rejects_everything_else(value):
    assert parse_video_id(value) is None


def test_watch_url_adds_the_playlist_and_start_time():
    assert watch_url(VIDEO) == WATCH
    assert watch_url(VIDEO, 0.4) == WATCH
    assert watch_url(VIDEO, 95.7, PLAYLIST) == f"{WATCH}&list={PLAYLIST}&t=95s"
    assert youtube.thumbnail_for(VIDEO) == f"https://i.ytimg.com/vi/{VIDEO}/mqdefault.jpg"


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("PT1H2M3S", 3723),
        ("PT15M", 900),
        ("PT45S", 45),
        ("P1DT1S", 86401),
        ("", 0),
        ("nonsense", 0),
        (None, 0),
    ],
)
def test_parse_iso_duration(value, seconds):
    assert parse_iso_duration(value) == seconds


# ---------------------------------------------------------------------- pacing


def test_pace_spaces_requests_out(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(youtube.time, "sleep", sleeps.append)
    monkeypatch.setattr(youtube, "_next_slot", 0.0)
    monkeypatch.setattr(get_settings(), "youtube_request_interval", 5.0)

    youtube.pace()  # the first request goes at once
    assert sleeps == []
    youtube.pace()  # the second waits for its slot: 5 s, jittered between 0.8x and 1.4x
    assert len(sleeps) == 1 and 3.9 <= sleeps[0] <= 7.0


def test_pace_does_nothing_when_the_interval_is_zero(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(youtube.time, "sleep", sleeps.append)
    youtube.pace()
    youtube.pace()
    assert sleeps == []


# ---------------------------------------------------------------------- yt-dlp


def test_ytdlp_playlist_skips_private_deleted_and_malformed_entries(monkeypatch):
    info = {
        "title": "Operating Systems",
        "channel": "Neso Academy",
        "entries": [
            {"id": "aaaaaaaaaaa", "title": "Intro", "duration": "600", "view_count": 1200},
            {"id": "bbbbbbbbbbb", "title": "[Private video]"},
            {"id": "ccccccccccc", "title": "[Deleted video]"},
            {"id": "bad", "title": "Malformed id"},
            None,
            {"id": "ddddddddddd", "title": "Paging", "uploader": "Guest", "duration": None},
        ],
    }
    calls = {}

    def fake_extract(self, url, **extra):
        calls["url"], calls["extra"] = url, extra
        return info

    monkeypatch.setattr(YtDlpBackend, "_extract", fake_extract)
    playlist = YtDlpBackend().fetch_playlist(PLAYLIST, limit=50)

    assert calls["url"].endswith(f"list={PLAYLIST}") and calls["extra"]["playlistend"] == 50
    assert playlist.title == "Operating Systems" and playlist.channel == "Neso Academy"
    assert [(v.youtube_id, v.position) for v in playlist.videos] == [
        ("aaaaaaaaaaa", 0),
        ("ddddddddddd", 5),
    ]
    first, last = playlist.videos
    assert first.duration_s == 600 and first.view_count == 1200
    assert first.channel == "Neso Academy"
    assert last.duration_s == 0 and last.channel == "Guest"


def test_ytdlp_video_reads_statistics_date_and_chapters(monkeypatch):
    info = {
        "title": "Deadlock",
        "description": "Banker's algorithm",
        "uploader": "Gate Smashers",
        "duration": 754,
        "view_count": "90000",
        "like_count": 4100,
        "comment_count": "not a number",
        "upload_date": "20240315",
        "chapters": [{"title": "Conditions"}, {"title": ""}, {"title": "Avoidance"}],
    }
    monkeypatch.setattr(YtDlpBackend, "_extract", lambda self, url, **extra: info)
    video = YtDlpBackend().fetch_video(VIDEO)
    assert video.title == "Deadlock" and video.channel == "Gate Smashers"
    assert (video.duration_s, video.view_count, video.like_count) == (754, 90000, 4100)
    assert video.comment_count is None
    assert video.published_at == datetime(2024, 3, 15, tzinfo=UTC)
    assert video.chapters == ["Conditions", "Avoidance"]

    info["upload_date"] = "garbage"
    assert YtDlpBackend().fetch_video(VIDEO).published_at is None


def test_ytdlp_search_returns_valid_results_in_order(monkeypatch):
    info = {
        "entries": [
            {"id": "aaaaaaaaaaa", "title": "One"},
            {"id": "", "title": "No id"},
            {"id": "bbbbbbbbbbb", "title": "Two"},
        ]
    }
    seen = {}

    def fake_extract(self, url, **extra):
        seen["url"] = url
        return info

    monkeypatch.setattr(YtDlpBackend, "_extract", fake_extract)
    results = YtDlpBackend().search("virtual memory", limit=5)
    assert seen["url"] == "ytsearch5:virtual memory"
    assert [v.title for v in results] == ["One", "Two"]


class _FakeYdl:
    """Stands in for yt_dlp.YoutubeDL."""

    outcome: object = None
    options: dict = {}

    def __init__(self, options):
        type(self).options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_ytdlp_extract_turns_errors_into_messages_for_the_student(monkeypatch):
    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYdl)
    monkeypatch.setattr(get_settings(), "youtube_proxy", "http://proxy.example:8080")
    backend = YtDlpBackend()

    _FakeYdl.outcome = {"title": "ok"}
    assert backend._extract(WATCH, playlistend=3) == {"title": "ok"}
    assert _FakeYdl.options["proxy"] == "http://proxy.example:8080"
    assert _FakeYdl.options["skip_download"] is True and _FakeYdl.options["playlistend"] == 3

    _FakeYdl.outcome = yt_dlp.utils.DownloadError("ERROR: Sign in to confirm you are not a bot")
    with pytest.raises(YouTubeBlocked):
        backend._extract(WATCH)

    _FakeYdl.outcome = yt_dlp.utils.DownloadError("ERROR: HTTP Error 429: Too Many Requests")
    with pytest.raises(YouTubeBlocked):
        backend._extract(WATCH)

    _FakeYdl.outcome = yt_dlp.utils.DownloadError(
        "\x1b[0;31mERROR: \x1b[0mThe playlist does not exist."
    )
    with pytest.raises(YouTubeError) as caught:
        backend._extract(WATCH)
    assert not isinstance(caught.value, YouTubeBlocked)
    assert str(caught.value) == "The playlist does not exist."

    _FakeYdl.outcome = None
    with pytest.raises(YouTubeError, match="no data"):
        backend._extract(WATCH)


# -------------------------------------------------------------------- Data API


def _video_item(video_id: str, title: str, duration: str = "PT10M") -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": "d",
            "channelTitle": "Channel",
            "publishedAt": "2023-05-01T10:00:00Z",
        },
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": "1000", "likeCount": "50", "commentCount": "7"},
    }


def _playlist_item(video_id: str) -> dict:
    return {"contentDetails": {"videoId": video_id}}


def _echo_videos(request: httpx.Request) -> dict:
    """Answers a videos request with details for every id asked for."""
    return {"items": [_video_item(i, f"Title {i}") for i in request.url.params["id"].split(",")]}


def data_api(routes: dict, requests: list | None = None) -> DataApiBackend:
    """A Data API backend whose HTTP calls are answered from ``routes``
    (last path segment -> JSON, a Response, or a function of the request)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        assert request.url.params["key"] == "test-key"
        answer = routes[request.url.path.rsplit("/", 1)[-1]]
        if callable(answer):
            answer = answer(request)
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)

    return DataApiBackend("test-key", transport=httpx.MockTransport(handler))


def test_data_api_playlist_follows_pages_and_drops_private_videos():
    def playlist_items(request):
        if "pageToken" not in request.url.params:
            return {
                "items": [_playlist_item("aaaaaaaaaaa"), _playlist_item("private0000")],
                "nextPageToken": "page2",
            }
        assert request.url.params["pageToken"] == "page2"
        return {"items": [_playlist_item("bbbbbbbbbbb")]}

    backend = data_api(
        {
            "playlists": {"items": [{"snippet": {"title": "DBMS", "channelTitle": "Jenny"}}]},
            "playlistItems": playlist_items,
            # the private video is simply missing from the details
            "videos": {
                "items": [
                    _video_item("aaaaaaaaaaa", "Keys", "PT1H2M3S"),
                    _video_item("bbbbbbbbbbb", "Joins"),
                ]
            },
        }
    )
    playlist = backend.fetch_playlist(PLAYLIST, limit=10)
    assert (playlist.title, playlist.channel) == ("DBMS", "Jenny")
    assert [(v.youtube_id, v.position) for v in playlist.videos] == [
        ("aaaaaaaaaaa", 0),
        ("bbbbbbbbbbb", 2),
    ]
    first = playlist.videos[0]
    assert (first.duration_s, first.view_count, first.like_count) == (3723, 1000, 50)
    assert first.comment_count == 7
    assert first.published_at == datetime(2023, 5, 1, 10, 0, tzinfo=UTC)


def test_data_api_playlist_respects_the_limit_and_reports_a_missing_playlist():
    requests: list[httpx.Request] = []
    backend = data_api(
        {
            "playlists": {"items": [{"snippet": {}}]},
            "playlistItems": {
                "items": [_playlist_item(f"video{i:06d}") for i in range(5)],
                "nextPageToken": "more",
            },
            "videos": _echo_videos,
        },
        requests,
    )
    playlist = backend.fetch_playlist(PLAYLIST, limit=3)
    assert len(playlist.videos) == 3 and playlist.title == "Untitled playlist"
    # limit reached on the first page: the second page is never requested
    assert [r.url.path.rsplit("/", 1)[-1] for r in requests] == [
        "playlists",
        "playlistItems",
        "videos",
    ]

    with pytest.raises(YouTubeError, match="not found or private"):
        data_api({"playlists": {"items": []}}).fetch_playlist(PLAYLIST, limit=3)


def test_data_api_video_search_and_comments():
    def videos(request):
        found = _echo_videos(request)["items"]
        return {"items": [item for item in found if item["id"] != "gone0000000"]}

    def comment(text: str | None) -> dict:
        inner = {} if text is None else {"textDisplay": text}
        return {"snippet": {"topLevelComment": {"snippet": inner}}}

    backend = data_api(
        {
            "videos": videos,
            "search": {
                "items": [
                    {"id": {"videoId": "aaaaaaaaaaa"}},
                    {"id": {"kind": "youtube#channel"}},
                    {"id": {"videoId": "gone0000000"}},
                    {"id": {"videoId": "bbbbbbbbbbb"}},
                ]
            },
            "commentThreads": {"items": [comment("Great explanation"), comment(None)]},
        }
    )
    assert backend.fetch_video("aaaaaaaaaaa").title == "Title aaaaaaaaaaa"
    with pytest.raises(YouTubeError, match="not found or private"):
        backend.fetch_video("gone0000000")
    found = backend.search("paging", limit=4)
    assert [v.youtube_id for v in found] == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert backend.fetch_comments("aaaaaaaaaaa") == ["Great explanation", ""]


def test_data_api_errors_are_reported_and_comments_fail_soft():
    quota = httpx.Response(
        403, json={"error": {"message": "You have exceeded your quota."}}
    )
    backend = data_api(
        {"videos": quota, "commentThreads": quota, "search": httpx.Response(500, text="oops")}
    )
    with pytest.raises(YouTubeError, match="exceeded your quota"):
        backend.fetch_video(VIDEO)
    with pytest.raises(YouTubeError, match="HTTP 500"):
        backend.search("anything")
    # comments off or over quota: no comments, no failure
    assert backend.fetch_comments(VIDEO) == []

    def unreachable(request):
        raise httpx.ConnectError("no route to host")

    offline = DataApiBackend("test-key", transport=httpx.MockTransport(unreachable))
    with pytest.raises(YouTubeError, match="Could not reach"):
        offline.fetch_video(VIDEO)


def test_data_api_fetches_details_in_batches_of_fifty():
    batches: list[int] = []

    def videos(request):
        batches.append(len(request.url.params["id"].split(",")))
        return _echo_videos(request)

    ids = [f"v{i:010d}" for i in range(120)]
    assert len(data_api({"videos": videos})._videos(ids)) == 120
    assert batches == [50, 50, 20]


# ------------------------------------------------------------------- captions


class _Track:
    def __init__(
        self, code, generated=False, translatable=False, lines=("hello there",), translation=None
    ):
        self.language_code = code
        self.is_generated = generated
        self.is_translatable = translatable
        self._lines = lines
        self._translation = translation
        self.fetched = False

    def fetch(self):
        self.fetched = True
        if isinstance(self._lines, Exception):
            raise self._lines
        return [
            SimpleNamespace(start=i * 2, duration=2, text=text)
            for i, text in enumerate(self._lines)
        ]

    def translate(self, language):
        if isinstance(self._translation, Exception):
            raise self._translation
        return _Track(language, generated=True, lines=self._translation)


def fake_captions(monkeypatch, outcome):
    """Make YouTubeTranscriptApi().list() return ``outcome`` (tracks, or raise it)."""
    import youtube_transcript_api

    class Api:
        proxy_config = None

        def __init__(self, proxy_config=None):
            Api.proxy_config = proxy_config

        def list(self, video_id):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", Api)
    return Api


def test_transcript_prefers_human_english_over_generated(monkeypatch):
    generated = _Track("en", generated=True, lines=("auto captions",))
    human = _Track("en-GB", lines=("written captions", "   ", "second line"))
    fake_captions(monkeypatch, [_Track("hi"), generated, human])

    transcript = youtube._fetch_transcript(VIDEO)
    assert transcript.language == "en-GB" and transcript.is_generated is False
    # blank lines are dropped
    assert [s.text for s in transcript.segments] == ["written captions", "second line"]
    assert transcript.segments[1].start == 4.0
    assert not generated.fetched


def test_transcript_falls_back_to_generated_english(monkeypatch):
    fake_captions(monkeypatch, [_Track("de"), _Track("en", generated=True, lines=("auto",))])
    transcript = youtube._fetch_transcript(VIDEO)
    assert transcript.language == "en" and transcript.is_generated is True


def test_transcript_translates_other_languages_to_english(monkeypatch):
    track = _Track("hi", translatable=True, lines=("मूल",), translation=("translated line",))
    fake_captions(monkeypatch, [track])
    transcript = youtube._fetch_transcript(VIDEO)
    assert transcript.language == "hi→en" and transcript.is_generated is True
    assert transcript.segments[0].text == "translated line"


def test_transcript_keeps_the_original_language_when_translation_fails(monkeypatch):
    track = _Track(
        "hi", translatable=True, lines=("मूल पाठ",), translation=RuntimeError("no translation")
    )
    fake_captions(monkeypatch, [track])
    transcript = youtube._fetch_transcript(VIDEO)
    assert transcript.language == "hi" and transcript.is_generated is False
    assert transcript.segments[0].text == "मूल पाठ"

    fake_captions(monkeypatch, [_Track("ta", generated=True, lines=("தமிழ்",))])
    assert youtube._fetch_transcript(VIDEO).language == "ta"


def test_transcript_is_none_when_there_are_no_usable_captions(monkeypatch):
    from youtube_transcript_api import TranscriptsDisabled

    fake_captions(monkeypatch, TranscriptsDisabled(VIDEO))
    assert youtube._fetch_transcript(VIDEO) is None
    fake_captions(monkeypatch, [])
    assert youtube._fetch_transcript(VIDEO) is None
    fake_captions(monkeypatch, [_Track("en", lines=("  ", ""))])
    assert youtube._fetch_transcript(VIDEO) is None


def test_transcript_reports_a_block_at_any_step(monkeypatch):
    from youtube_transcript_api import IpBlocked, RequestBlocked

    fake_captions(monkeypatch, IpBlocked(VIDEO))
    with pytest.raises(YouTubeBlocked):
        youtube._fetch_transcript(VIDEO)

    fake_captions(monkeypatch, [_Track("en", lines=RequestBlocked(VIDEO))])
    with pytest.raises(YouTubeBlocked):
        youtube._fetch_transcript(VIDEO)

    fake_captions(monkeypatch, [_Track("hi", translatable=True, translation=IpBlocked(VIDEO))])
    with pytest.raises(YouTubeBlocked):
        youtube._fetch_transcript(VIDEO)


def test_transcript_uses_the_configured_proxy(monkeypatch):
    api = fake_captions(monkeypatch, [_Track("en")])
    youtube._fetch_transcript(VIDEO)
    assert api.proxy_config is None
    monkeypatch.setattr(get_settings(), "youtube_proxy", "http://proxy.example:8080")
    youtube._fetch_transcript(VIDEO)
    assert api.proxy_config is not None


# --------------------------------------------------------------------- factory


def test_factory_picks_the_backend_from_the_settings(monkeypatch):
    youtube.set_youtube_client(None)
    assert isinstance(youtube.get_youtube_client(), YtDlpBackend)
    monkeypatch.setattr(get_settings(), "youtube_api_key", "a-key")
    assert isinstance(youtube.get_youtube_client(), DataApiBackend)

    sentinel = object()
    youtube.set_youtube_client(sentinel)
    assert youtube.get_youtube_client() is sentinel
