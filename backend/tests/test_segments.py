"""Topics taught across several stretches of video: the worst cases.

Each test builds a small course with its own playlists, processes it, and checks
the segments the student is sent to.
"""

from __future__ import annotations

from app.services.youtube import set_youtube_client
from evaluation.harness import LabelledYouTube
from evaluation.os_course import LabelledPlaylist, LabelledVideo

from .conftest import register, run_jobs

DETECTION = LabelledVideo(
    "deadDetect1",
    "Deadlock Detection",
    """
    Deadlock detection lets deadlocks happen and then finds them.
    For single instance resources deadlock detection uses a wait for graph.
    A cycle in the wait for graph means the processes are deadlocked.
    For multiple instances the detection algorithm works like the safety algorithm.
    The detection algorithm checks which processes can never finish.
    How often to run deadlock detection depends on how often deadlocks occur.
    """,
)
RECOVERY = LabelledVideo(
    "deadRecov01",
    "Deadlock Recovery",
    """
    Once a deadlock is found the system must recover from it.
    Deadlock recovery by process termination aborts the deadlocked processes.
    We can abort all of them or abort one process at a time until the cycle breaks.
    Deadlock recovery by resource preemption takes resources away from processes.
    A preempted process must be rolled back to a safe state and restarted.
    Recovery must avoid starvation so the same process is not always the victim.
    """,
)
BOTH = LabelledVideo(
    "deadBoth001",
    "Deadlock Detection and Recovery, Complete",
    """
    Deadlock detection uses a wait for graph and a detection algorithm to find cycles.
    A cycle in the wait for graph means the processes are deadlocked.
    Deadlock recovery then aborts deadlocked processes one at a time.
    Deadlock recovery can also preempt resources and roll processes back.
    Detection and recovery together let the system run without prevention.
    """,
)
PAGING_1 = LabelledVideo(
    "pagingPart1",
    "Paging Part 1",
    """
    Paging divides physical memory into fixed size frames.
    Paging divides the logical memory of a process into pages.
    The page table maps each page number to a frame number.
    A logical address is split into a page number and an offset.
    Paging removes external fragmentation completely.
    """,
)
PAGING_2 = LabelledVideo(
    "pagingPart2",
    "Paging Part 2",
    """
    In this second part on paging we look at the translation lookaside buffer.
    The TLB caches recent page table entries so paging is fast.
    A TLB miss means the page table must be read from memory.
    """,
)
SEGMENTATION = LabelledVideo(
    "segmentVid1",
    "Segmentation",
    """
    Segmentation divides a program into segments such as code data and stack.
    The segment table stores a base and a limit for each segment.
    A logical address has a segment number and an offset.
    Segmentation suffers from external fragmentation.
    Segmentation matches the way programmers think of a program.
    Segmentation with paging combines the two schemes.
    """,
)
TWICE = LabelledVideo(
    "memLecture1",
    "Memory Management Lecture",
    "\n".join(
        ["Paging splits memory into frames and the process into pages of the same size."] * 4
        + ["With paging, the page table maps every page of the process to a frame in memory."] * 4
        + ["Segmentation instead divides a program into code, data and stack segments."] * 4
        + ["The segment table keeps a base address and a limit for each segment."] * 4
        + ["Segments have different sizes, which causes external fragmentation."] * 4
        + ["Paging splits memory into frames and the process into pages of the same size."] * 4
        + ["With paging, the page table maps every page of the process to a frame in memory."] * 4
    ),
)


def course(client, playlists: list[LabelledPlaylist], syllabus: str) -> dict:
    """Process a course over the given playlists; return the path by topic name."""
    set_youtube_client(LabelledYouTube(playlists))
    register(client)
    project_id = client.post("/api/projects", json={"name": "Course"}).json()["id"]
    for playlist in playlists:
        client.post(
            f"/api/projects/{project_id}/playlists",
            json={"url": f"https://www.youtube.com/playlist?list={playlist.youtube_id}"},
        )
    client.post(f"/api/projects/{project_id}/documents/text", json={"kind": "syllabus", "text": syllabus})
    client.post(f"/api/projects/{project_id}/process")
    run_jobs()
    path = client.get(f"/api/projects/{project_id}/path").json()
    return {t["name"]: t for t in path["topics"]}


def ids(topic: dict) -> list[str]:
    return [s["video"]["youtube_id"] for s in topic["primary"]["segments"]]


def test_halves_of_a_topic_in_two_playlists_are_combined(client):
    topics = course(
        client,
        [
            LabelledPlaylist("PLdetectOnly000000001", "Detection", "Channel A", [DETECTION]),
            LabelledPlaylist("PLrecoverOnly00000002", "Recovery", "Channel B", [RECOVERY]),
        ],
        "Unit 1: Deadlocks\nDeadlock detection and recovery",
    )
    topic = topics["Deadlock detection and recovery"]
    assert sorted(ids(topic)) == sorted(["deadDetect1", "deadRecov01"])
    second = topic["primary"]["segments"][1]
    assert second["covers"]  # it says which part it adds
    assert topic["primary"]["uncovered"] == []
    assert topic["primary"]["reasons"][0].startswith("Taught in 2 parts across 2 videos")


def test_a_part_no_video_teaches_is_flagged(client):
    topics = course(
        client,
        [LabelledPlaylist("PLdetectOnly000000001", "Detection", "Channel A", [DETECTION])],
        "Unit 1: Deadlocks\nDeadlock detection and recovery",
    )
    topic = topics["Deadlock detection and recovery"]
    assert topic["primary"]["video"]["youtube_id"] == "deadDetect1"
    assert topic["primary"]["segments"] == []  # one stretch, nothing to combine
    assert topic["primary"]["uncovered"] == ["Deadlock recovery"]


def test_a_video_covering_the_whole_topic_is_not_split(client):
    topics = course(
        client,
        [
            LabelledPlaylist("PLbothCovered00000001", "Complete", "Channel A", [BOTH]),
            LabelledPlaylist("PLrecoverOnly00000002", "Recovery", "Channel B", [RECOVERY]),
        ],
        "Unit 1: Deadlocks\nDeadlock detection and recovery",
    )
    topic = topics["Deadlock detection and recovery"]
    assert topic["primary"]["video"]["youtube_id"] == "deadBoth001"
    assert topic["primary"]["segments"] == []
    assert topic["primary"]["uncovered"] == []


def test_a_part_series_is_taken_whole_and_in_order(client):
    topics = course(
        client,
        [LabelledPlaylist("PLmemorySeries0000001", "Memory", "Channel A", [PAGING_1, PAGING_2, SEGMENTATION])],
        "Unit 1: Memory\nPaging, Segmentation",
    )
    paging = topics["Paging"]
    assert ids(paging) == ["pagingPart1", "pagingPart2"]  # Part 2 is a short clip
    assert all(s["start_s"] == 0 and s["end_s"] == 0 for s in paging["primary"]["segments"])
    assert topics["Segmentation"]["primary"]["segments"] == []


def test_a_topic_taught_twice_in_one_video_gets_both_stretches(client):
    topics = course(
        client,
        [LabelledPlaylist("PLoneLecture000000001", "Lecture", "Channel A", [TWICE])],
        "Unit 1: Memory\nPaging",
    )
    segments = topics["Paging"]["primary"]["segments"]
    assert [s["video"]["youtube_id"] for s in segments] == ["memLecture1", "memLecture1"]
    first, second = segments
    assert first["start_s"] < first["end_s"] <= second["start_s"]
    assert second["start_s"] > 0


def test_time_left_counts_the_stretches_not_whole_videos(client):
    topics_path = course(
        client,
        [LabelledPlaylist("PLoneLecture000000001", "Lecture", "Channel A", [TWICE])],
        "Unit 1: Memory\nPaging",
    )
    assert topics_path["Paging"]["primary"]["segments"]
    path = client.get("/api/projects/1/path").json()
    assert path["stats"]["total_seconds"] < TWICE.seconds  # the middle is skipped
