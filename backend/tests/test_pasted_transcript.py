"""Transcripts pasted by the student (copied from YouTube's "Show transcript"):
the parser in ``app/services/pasted.py`` and the route that applies one."""

from __future__ import annotations

from app.services.pasted import guess_language, parse_pasted_transcript
from tests.conftest import make_course, register, run_jobs
from tests.test_api import path_of, primary_id

PANEL = """Transcript
Search transcript
0:00
0 seconds
Hello friends, today we're going to discuss normalization.
0:04
4 seconds
Normalization is a very important concept of DBMS.
1:09
1 minute, 9 seconds
It is a technique to remove or reduce
the redundancy from a table.
1:02:15
1 hour, 2 minutes, 15 seconds
Thank you.
"""


def test_the_copied_panel_text_becomes_timed_segments():
    transcript = parse_pasted_transcript(PANEL, duration_s=3750)
    assert transcript.language == "en" and transcript.is_generated is False
    assert [s.start for s in transcript.segments] == [0.0, 4.0, 69.0, 3735.0]
    assert transcript.segments[0].duration == 4.0
    assert (
        transcript.segments[2].text
        == "It is a technique to remove or reduce the redundancy from a table."
    )
    assert transcript.segments[-1].duration == 15.0  # up to the end of the video
    assert not any("second" in s.text or "Transcript" in s.text for s in transcript.segments)


def test_time_and_words_on_one_line():
    transcript = parse_pasted_transcript("0:00 first point\n[0:30] second point\n1:00 - third point")
    assert [(s.start, s.text) for s in transcript.segments] == [
        (0.0, "first point"),
        (30.0, "second point"),
        (60.0, "third point"),
    ]


def test_text_without_times_is_spread_over_the_video():
    text = "Paging divides memory into frames. A page table maps pages to frames. That is all."
    transcript = parse_pasted_transcript(text, duration_s=300)
    assert len(transcript.segments) == 3
    assert transcript.segments[0].start == 0.0
    assert 0 < transcript.segments[1].start < transcript.segments[2].start < 300
    end = transcript.segments[-1].start + transcript.segments[-1].duration
    assert abs(end - 300) < 1


def test_prose_that_merely_mentions_a_time_is_not_a_timeline():
    text = "We met the teacher.\n10:30\nwas the hour.\n9:15\nwas when the lecture began."
    transcript = parse_pasted_transcript(text)
    starts = [s.start for s in transcript.segments]
    assert starts[0] == 0.0 and starts == sorted(starts)


def test_nothing_to_use():
    assert parse_pasted_transcript("Transcript\nSearch transcript\n0:00\n0 seconds\n") is None
    assert parse_pasted_transcript("   \n\n") is None


def test_language_is_read_from_the_script():
    assert guess_language("Normalization removes redundancy from a table") == "en"
    assert guess_language("ओके लेट्स सी द क्वेश्चन क्वेश्चन इज ऑन नॉर्मलाइजेशन") == "hi"
    assert guess_language("নরমালাইজেশন একটি গুরুত্বপূর্ণ ধারণা") == "bn"
    mixed = "DBMS में normalization बहुत ज़रूरी कॉन्सेप्ट है जो टेबल से redundancy हटाता है"
    assert guess_language(mixed) == "hi"
    hindi = parse_pasted_transcript("0:00\nओके लेट्स सी द क्वेश्चन\n0:05\nक्वेश्चन इज ऑन नॉर्मलाइजेशन")
    assert hindi.language == "hi"


# ------------------------------------------------------------------ the route


def _video_id(path: dict, youtube_id: str) -> int:
    for topic in path["topics"]:
        for pick in [topic["primary"], *topic["alternates"]]:
            if pick and pick["video"]["youtube_id"] == youtube_id:
                return pick["video"]["id"]
    raise AssertionError(f"{youtube_id} is not in the path")


def test_a_pasted_transcript_rescues_a_video_youtube_refused(client, youtube):
    """Blocked: the Banker's lecture is known by its title only. After the student
    pastes its transcript, the path uses what the lecture says."""
    youtube.blocked = set(youtube.videos)
    register(client)
    project_id = make_course(client)
    video_id = _video_id(path_of(client, project_id), "osBankers08")
    sentences = youtube.videos["osBankers08"][1].sentences
    pasted = "\n".join(f"{i // 2}:{(i % 2) * 30:02d}\n{line}" for i, line in enumerate(sentences))

    response = client.put(
        f"/api/projects/{project_id}/videos/{video_id}/transcript", json={"text": pasted}
    )
    assert response.status_code == 200, response.text
    topics = response.json()["topics"]
    pick = next(t for t in topics if t["name"] == "Banker's algorithm")["primary"]
    assert pick["video"]["youtube_id"] == "osBankers08"
    assert pick["video"]["transcript_status"] == "ok"
    assert pick["snippet"]  # words from the transcript, not just the title

    # It is no longer listed among the videos that still need a transcript.
    waiting = client.get(f"/api/projects/{project_id}/videos/untranscribed").json()
    assert waiting and "osBankers08" not in {v["youtube_id"] for v in waiting}
    assert all(v["transcript_status"] != "ok" for v in waiting)

    # The pasted transcript is kept: the automatic retry does not ask YouTube again.
    youtube.blocked = set()
    youtube.calls.clear()
    client.post(f"/api/projects/{project_id}/process")
    run_jobs()
    assert ("transcript", "osBankers08") not in youtube.calls
    assert primary_id(path_of(client, project_id), "Banker's algorithm") == "osBankers08"


def test_paste_route_refuses_empty_text_and_other_peoples_videos(client, course):
    video_id = _video_id(path_of(client, course), "osBankers08")
    url = f"/api/projects/{course}/videos/{video_id}/transcript"
    no_words = "0:00\n0 seconds\n0:05\n5 seconds\n0:09\n9 seconds\n"
    assert client.put(url, json={"text": no_words}).status_code == 422
    assert client.put(url, json={"text": "short"}).status_code == 422
    missing = f"/api/projects/{course}/videos/999999/transcript"
    assert client.put(missing, json={"text": "x" * 50}).status_code == 404
    client.post("/api/auth/logout")
    register(client, email="other@example.com", name="Other")
    theirs = client.put(url, json={"text": "A page table maps pages to frames. " * 3})
    assert theirs.status_code == 404
