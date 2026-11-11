"""End-to-end API tests: a student's whole journey through the product."""

from __future__ import annotations

import io

from app.config import get_settings
from app.services.youtube import VideoMeta

from .conftest import make_course, register, run_jobs, topic_by_name


def path_of(client, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/path")
    assert response.status_code == 200, response.text
    return response.json()


def primary_id(path: dict, topic: str) -> str | None:
    primary = topic_by_name(path, topic)["primary"]
    return primary["video"]["youtube_id"] if primary else None


# ----------------------------------------------------------------------- accounts


def test_account_lifecycle(client):
    assert client.get("/api/auth/me").status_code == 401
    user = register(client)
    assert client.get("/api/auth/me").json() == user

    duplicate = client.post(
        "/api/auth/register",
        json={"email": "STUDENT@example.com", "name": "Again", "password": "correct-horse-9"},
    )
    assert duplicate.status_code == 409

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    wrong = client.post(
        "/api/auth/login", json={"email": "student@example.com", "password": "not-the-password"}
    )
    assert wrong.status_code == 401
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "not-the-password"}
    )
    assert unknown.json() == wrong.json()  # same answer whether or not the email exists
    assert client.post(
        "/api/auth/login", json={"email": "student@example.com", "password": "correct-horse-9"}
    ).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_session_cookie_is_http_only(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "name": "A", "password": "correct-horse-9"},
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_short_password_is_rejected(client):
    response = client.post(
        "/api/auth/register", json={"email": "a@example.com", "name": "A", "password": "short"}
    )
    assert response.status_code == 422


def test_login_is_rate_limited(client):
    from app.routers import auth

    auth.limiter.limit = 3
    try:
        statuses = [
            client.post(
                "/api/auth/login", json={"email": "x@example.com", "password": "wrong-password"}
            ).status_code
            for _ in range(5)
        ]
    finally:
        auth.limiter.limit = 1000
    assert statuses[:3] == [401, 401, 401] and statuses[3:] == [429, 429]


def test_cross_site_requests_are_blocked(client):
    register(client)
    blocked = client.post(
        "/api/projects", json={"name": "Evil"}, headers={"Origin": "https://evil.example"}
    )
    assert blocked.status_code == 403
    same_site = client.post(
        "/api/projects", json={"name": "Mine"}, headers={"Origin": "http://testserver"}
    )
    assert same_site.status_code == 201


def test_other_users_projects_are_invisible(client, course):
    client.post("/api/auth/logout")
    register(client, "intruder@example.com")
    assert client.get("/api/projects").json() == []
    for request in (
        client.get(f"/api/projects/{course}"),
        client.get(f"/api/projects/{course}/path"),
        client.delete(f"/api/projects/{course}"),
        client.get(f"/api/projects/{course}/search", params={"q": "deadlock"}),
    ):
        assert request.status_code == 404


def test_deleting_an_account_removes_its_data(client, course, db):
    from app.models import Project, Video

    assert client.delete("/api/auth/me").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert db.query(Project).count() == 0
    assert db.query(Video).count() == 0


# ------------------------------------------------------------------ learning path


def test_path_matches_topics_to_the_right_videos(client, course):
    path = path_of(client, course)
    assert path["stats"]["topics"] == 28
    assert primary_id(path, "Banker's algorithm") == "osBankers08"
    assert primary_id(path, "Segmentation") == "rvSegment02"
    assert primary_id(path, "Process Control Block (PCB)") == "osProcess03"
    assert primary_id(path, "Threads") == "rvThreads04"


def test_uncovered_topics_are_flagged_as_gaps(client, course):
    path = path_of(client, course)
    for name in ("RAID levels", "Access control lists", "Public key cryptography"):
        topic = topic_by_name(path, name)
        assert topic["status"] == "gap" and topic["primary"] is None
    assert path["stats"]["gaps"] >= 3
    assert path["stats"]["matched"] + path["stats"]["gaps"] == path["stats"]["topics"]


def test_recommendation_points_inside_the_video(client, course):
    path = path_of(client, course)
    prevention = topic_by_name(path, "Deadlock prevention")["primary"]
    assert prevention["video"]["youtube_id"] == "osDeadlock7"
    assert prevention["start_s"] >= 100  # the second half of that lecture
    assert f"t={int(prevention['start_s'])}s" in prevention["url"]
    assert prevention["snippet"] and prevention["reasons"]


def test_video_without_captions_is_matched_on_its_description(client, course):
    files = topic_by_name(path_of(client, course), "File allocation methods")["primary"]
    assert files["video"]["youtube_id"] == "rvFiles0005"
    assert files["video"]["transcript_status"] == "none"
    assert "No captions" in files["reasons"][0]


def test_important_topics_come_from_exam_papers_and_notes(client, course):
    path = path_of(client, course)
    banker = topic_by_name(path, "Banker's algorithm")
    assert banker["exam_hits"] >= 2 and banker["in_notes"] is True
    assert banker["importance"] == max(t["importance"] for t in path["topics"])
    assert topic_by_name(path, "Segmentation")["importance"] == 0


def test_question_and_answer_section(client, course):
    body = client.get(f"/api/projects/{course}/questions").json()
    assert body["total"] >= 6 and body["answered"] >= 4
    by_text = {q["text"]: q for q in body["questions"]}
    banker = next(q for text, q in by_text.items() if "banker" in text.lower())
    assert banker["topic_name"] == "Banker's algorithm"
    assert banker["answer"]["video"]["youtube_id"] in {"osBankers08", "rvDeadlock1"}
    assert banker["answer"]["url"].startswith("https://www.youtube.com/watch?v=")
    assert banker["source"] == "Pasted exam"


# ------------------------------------------------------------------------- search


def test_search_finds_videos_for_a_topic(client, course):
    body = client.get(f"/api/projects/{course}/search", params={"q": "round robin time quantum"}).json()
    assert body["found"] is True
    assert body["results"][0]["video"]["youtube_id"] == "osRoundRob5"


def test_search_says_when_nothing_is_found(client, course):
    body = client.get(f"/api/projects/{course}/search", params={"q": "RAID levels"}).json()
    assert body["found"] is False and body["results"] == []
    assert body["message"] == "Video not found for “RAID levels”"


# ----------------------------------------------------------------------- feedback


def test_wrong_topic_feedback_replaces_the_video_and_can_be_undone(client, course):
    path = path_of(client, course)
    banker = topic_by_name(path, "Banker's algorithm")
    payload = {"topic_id": banker["id"], "video_id": banker["primary"]["video"]["id"]}

    after = client.post(f"/api/projects/{course}/feedback", json={**payload, "kind": "wrong_topic"}).json()
    assert primary_id(after, "Banker's algorithm") != "osBankers08"
    assert all(
        a["video"]["youtube_id"] != "osBankers08"
        for a in topic_by_name(after, "Banker's algorithm")["alternates"]
    )

    undone = client.request("DELETE", f"/api/projects/{course}/feedback", params=payload).json()
    assert primary_id(undone, "Banker's algorithm") == "osBankers08"


def test_correct_feedback_pins_a_video(client, course):
    path = path_of(client, course)
    conditions = topic_by_name(path, "Necessary conditions for deadlock")
    revision = next(
        a for a in [conditions["primary"], *conditions["alternates"]]
        if a["video"]["youtube_id"] == "rvDeadlock1"
    )
    after = client.post(
        f"/api/projects/{course}/feedback",
        json={"topic_id": conditions["id"], "video_id": revision["video"]["id"], "kind": "correct"},
    ).json()
    pinned = topic_by_name(after, "Necessary conditions for deadlock")["primary"]
    assert pinned["video"]["youtube_id"] == "rvDeadlock1"
    assert pinned["feedback"] == "correct"
    assert "You confirmed" in pinned["reasons"][0]


def test_irrelevant_feedback_removes_a_video_everywhere(client, course):
    path = path_of(client, course)
    paging = topic_by_name(path, "Paging")
    video_id = paging["primary"]["video"]["id"]
    after = client.post(
        f"/api/projects/{course}/feedback",
        json={"topic_id": paging["id"], "video_id": video_id, "kind": "irrelevant"},
    ).json()
    used = [
        rec["video"]["id"]
        for topic in after["topics"]
        for rec in ([topic["primary"]] if topic["primary"] else []) + topic["alternates"]
    ]
    assert video_id not in used


def test_already_covered_takes_a_topic_off_the_path(client, course):
    path = path_of(client, course)
    paging = topic_by_name(path, "Paging")
    payload = {"topic_id": paging["id"], "video_id": paging["primary"]["video"]["id"]}
    after = client.post(
        f"/api/projects/{course}/feedback", json={**payload, "kind": "already_covered"}
    ).json()
    assert topic_by_name(after, "Paging")["status"] == "covered"
    assert after["stats"]["covered"] == 1

    undone = client.request("DELETE", f"/api/projects/{course}/feedback", params=payload).json()
    assert topic_by_name(undone, "Paging")["status"] == "matched"


def test_feedback_adjusts_the_matching_threshold(client, course):
    path = path_of(client, course)
    before = path["relevance_threshold"]
    topic = min(
        (t for t in path["topics"] if t["primary"]), key=lambda t: t["primary"]["relevance"]
    )
    after = client.post(
        f"/api/projects/{course}/feedback",
        json={
            "topic_id": topic["id"],
            "video_id": topic["primary"]["video"]["id"],
            "kind": "wrong_topic",
        },
    ).json()
    assert after["relevance_threshold"] >= before


def test_watched_videos_count_towards_progress(client, course):
    path = path_of(client, course)
    video = topic_by_name(path, "Paging")["primary"]["video"]
    assert client.put(
        f"/api/projects/{course}/videos/{video['id']}/watched", json={"watched": True}
    ).status_code == 204
    after = path_of(client, course)
    assert after["stats"]["watched"] == 1
    assert after["stats"]["remaining_seconds"] == path["stats"]["total_seconds"] - video["duration_s"]


# ------------------------------------------------------------------------- topics


def test_topics_can_be_added_renamed_reordered_and_removed(client, course):
    path = path_of(client, course)
    paging = topic_by_name(path, "Paging")

    added = client.post(
        f"/api/projects/{course}/topics", json={"name": "Translation lookaside buffer", "after_id": paging["id"]}
    )
    assert added.status_code == 201
    path = added.json()
    names = [t["name"] for t in path["topics"]]
    assert names.index("Translation lookaside buffer") == names.index("Paging") + 1
    tlb = topic_by_name(path, "Translation lookaside buffer")
    assert tlb["unit"] == paging["unit"] and tlb["source"] == "manual"
    assert tlb["primary"]["video"]["youtube_id"] == "osPaging009"

    assert client.post(
        f"/api/projects/{course}/topics", json={"name": "paging"}
    ).status_code == 409

    renamed = client.patch(
        f"/api/projects/{course}/topics/{tlb['id']}", json={"name": "Shortest job first"}
    ).json()
    assert primary_id(renamed, "Shortest job first") == "osSched0004"

    order = [t["id"] for t in renamed["topics"]][::-1]
    reordered = client.put(f"/api/projects/{course}/topics/order", json={"ids": order}).json()
    assert [t["id"] for t in reordered["topics"]] == order

    removed = client.delete(f"/api/projects/{course}/topics/{tlb['id']}").json()
    assert all(t["id"] != tlb["id"] for t in removed["topics"])
    assert client.get(f"/api/projects/{course}").json()["topics_locked"] is True


def test_hand_edited_topics_survive_reprocessing(client, course):
    client.post(f"/api/projects/{course}/topics", json={"name": "Thrashing"})
    client.post(f"/api/projects/{course}/process")
    run_jobs()
    assert "Thrashing" in [t["name"] for t in path_of(client, course)["topics"]]


# ------------------------------------------------------------------------ sources


def test_project_requires_sources_before_processing(client):
    register(client)
    project_id = client.post("/api/projects", json={"name": "Empty"}).json()["id"]
    assert client.post(f"/api/projects/{project_id}/process").status_code == 422


def test_playlist_links_are_validated(client):
    register(client)
    project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
    url = f"/api/projects/{project_id}/playlists"
    assert client.post(url, json={"url": "https://example.com/playlist?list=PLabc1234567890"}).status_code == 422
    assert client.post(url, json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}).status_code == 422
    good = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLmainOperatingSystems0001"
    assert client.post(url, json={"url": good}).status_code == 201
    assert client.post(url, json={"url": good}).status_code == 409


def test_document_upload_is_read_during_processing(client):
    register(client)
    project_id = client.post("/api/projects", json={"name": "Uploads"}).json()["id"]
    syllabus = b"Unit 1: Memory\nPaging, Segmentation, Virtual memory\n"
    uploaded = client.post(
        f"/api/projects/{project_id}/documents",
        data={"kind": "syllabus"},
        files={"file": ("syllabus.txt", io.BytesIO(syllabus), "text/plain")},
    )
    assert uploaded.status_code == 201 and uploaded.json()["status"] == "pending"
    client.post(f"/api/projects/{project_id}/process")
    run_jobs()
    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["documents"][0]["status"] == "ready"
    assert detail["topics"] == 3
    assert not list(get_settings().upload_dir.iterdir())  # the upload is not kept


def test_unsupported_and_oversized_uploads_are_rejected(client):
    register(client)
    project_id = client.post("/api/projects", json={"name": "Uploads"}).json()["id"]
    url = f"/api/projects/{project_id}/documents"
    exe = client.post(url, data={"kind": "notes"}, files={"file": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")})
    assert exe.status_code == 415
    disguised = client.post(url, data={"kind": "notes"}, files={"file": ("notes.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")})
    assert disguised.status_code == 415

    settings = get_settings()
    original = settings.max_upload_mb
    settings.max_upload_mb = 0
    try:
        big = client.post(url, data={"kind": "notes"}, files={"file": ("notes.txt", b"x" * 5000, "text/plain")})
    finally:
        settings.max_upload_mb = original
    assert big.status_code == 413


def test_removing_a_playlist_removes_its_videos_from_the_path(client, course):
    detail = client.get(f"/api/projects/{course}").json()
    revision = next(p for p in detail["playlists"] if p["title"] == "OS Quick Revision")
    assert revision["video_count"] == 5
    assert client.delete(f"/api/projects/{course}/playlists/{revision['id']}").status_code == 204
    path = path_of(client, course)
    assert topic_by_name(path, "Segmentation")["status"] == "gap"
    assert client.get(f"/api/projects/{course}").json()["stale"] is True


def test_changes_are_refused_while_the_analysis_runs(client, course):
    assert client.post(f"/api/projects/{course}/process").status_code == 202  # queued, not run
    refused = client.post(f"/api/projects/{course}/topics", json={"name": "Thrashing"})
    assert refused.status_code == 409
    run_jobs()
    assert client.post(f"/api/projects/{course}/topics", json={"name": "Thrashing"}).status_code == 201


# ------------------------------------------------------------ YouTube robustness


def test_blocked_youtube_degrades_gracefully_and_schedules_a_retry(client, youtube):
    register(client)
    youtube.blocked = set(youtube.videos)
    project_id = make_course(client)

    job = client.get(f"/api/projects/{project_id}/job").json()
    assert job["status"] == "done"
    assert any("temporarily limiting" in warning for warning in job["warnings"])
    assert job["retry_at"] is not None
    # Titles alone still place the obvious topics.
    assert primary_id(path_of(client, project_id), "Segmentation") == "rvSegment02"
    # After the first refusals the remaining videos are not requested at all.
    transcript_calls = [c for c in youtube.calls if c[0] == "transcript"]
    assert len(transcript_calls) < len(youtube.videos)

    youtube.blocked = set()
    client.post(f"/api/projects/{project_id}/process")
    run_jobs()
    retried = client.get(f"/api/projects/{project_id}/job").json()
    assert retried["retry_at"] is None
    assert not any("temporarily limiting" in warning for warning in retried["warnings"])
    assert primary_id(path_of(client, project_id), "Banker's algorithm") == "osBankers08"


def test_reprocessing_does_not_refetch_transcripts(client, course, youtube):
    before = len([c for c in youtube.calls if c[0] == "transcript"])
    client.post(f"/api/projects/{course}/process")
    run_jobs()
    assert len([c for c in youtube.calls if c[0] == "transcript"]) == before


def test_gap_can_be_filled_from_a_youtube_search(client, course, youtube):
    from evaluation.os_course import LabelledPlaylist, LabelledVideo

    raid = LabelledVideo(
        "raidLevels1",
        "RAID Levels Explained",
        "\n".join(
            [
                "RAID stands for redundant array of independent disks.",
                "RAID level zero uses striping and gives no redundancy.",
                "RAID level one uses mirroring to keep a full copy of the data.",
                "RAID level five uses block striping with distributed parity.",
                "Different RAID levels trade performance against reliability.",
            ]
        ),
    )
    youtube.videos[raid.youtube_id] = (LabelledPlaylist("PLextra0000000001", "Other", "Storage Channel"), raid)
    youtube.search_results = [
        VideoMeta(youtube_id=raid.youtube_id, title=raid.title, channel="Storage Channel", duration_s=600)
    ]
    topic = topic_by_name(path_of(client, course), "RAID levels")

    found = client.post(f"/api/projects/{course}/youtube/search", json={"topic_id": topic["id"]}).json()
    assert found[0]["youtube_id"] == "raidLevels1" and found[0]["in_project"] is False

    added = client.post(
        f"/api/projects/{course}/videos",
        json={"video": f"https://youtu.be/{raid.youtube_id}", "topic_id": topic["id"]},
    )
    assert added.status_code == 201
    filled = topic_by_name(added.json(), "RAID levels")
    assert filled["status"] == "matched"
    assert filled["primary"]["video"]["youtube_id"] == "raidLevels1"
    assert filled["primary"]["video"]["source"] == "search"


# --------------------------------------------------------------------- operations


def test_health_readiness_and_metrics(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["status"] == "ready"
    client.get("/api/auth/me")
    metrics = client.get("/metrics").text
    assert 'route="/api/auth/me"' in metrics
    assert "pipeline_jobs_total" in metrics


def test_responses_carry_security_headers_and_a_request_id(client):
    response = client.get("/healthz")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]


def test_recommendation_gives_a_study_range(client, course):
    """The student is told what to watch: from one second to another."""
    pick = topic_by_name(path_of(client, course), "Critical section problem")["primary"]
    assert pick["video"]["youtube_id"] == "osSync00006"
    assert pick["start_s"] < pick["end_s"] < pick["video"]["duration_s"]
    questions = client.get(f"/api/projects/{course}/questions").json()["questions"]
    answered = [q["answer"] for q in questions if q["answer"]]
    assert all("end_s" in answer for answer in answered)


def test_comment_sentiment_feeds_the_ranking(client, youtube, db):
    from app.models import Video
    from app.services.fuzzy import QualityInputs, comment_sentiment, quality_score

    youtube.comments = {
        "osBankers08": ["Finally understood it, thank you!", "So clear and helpful"],
        "rvDeadlock1": ["Confusing and wrong in places", "bad audio, unclear"],
    }
    register(client)
    make_course(client)
    by_id = {v.youtube_id: v for v in db.query(Video)}
    assert by_id["osBankers08"].comment_sentiment > 0.5
    assert by_id["rvDeadlock1"].comment_sentiment < -0.5
    assert by_id["osIntro0001"].comment_sentiment is None  # no comments: no signal

    assert comment_sentiment(["meh"]) is None
    base = QualityInputs(duration_s=900, view_count=100_000, like_count=3_000)
    praised = QualityInputs(900, 100_000, 3_000, comment_sentiment=0.8)
    panned = QualityInputs(900, 100_000, 3_000, comment_sentiment=-0.8)
    assert quality_score(panned) < quality_score(base) < quality_score(praised)
    fresh = QualityInputs(900, 100_000, 3_000, age_years=1)
    ancient = QualityInputs(900, 100_000, 3_000, age_years=15)
    assert quality_score(ancient) < quality_score(fresh)



SYLLABUS_MEMORY = """Unit 1: Memory
Paging, Segmentation"""

NOTES_MEMORY = """Thrashing
A process thrashes when it spends more time paging than running.

Paging
Pages of a process map to frames of memory."""

EXAM_MEMORY = """1. Explain the working set model with a suitable example. [5]
2. How does the working set model prevent thrashing? [5]
3. Explain paging with a neat diagram. [5]"""


def test_topics_only_in_notes_or_exams_are_added(client):
    register(client)
    project_id = client.post("/api/projects", json={"name": "Memory"}).json()["id"]
    for kind, text in (("syllabus", SYLLABUS_MEMORY), ("notes", NOTES_MEMORY), ("exam", EXAM_MEMORY)):
        client.post(f"/api/projects/{project_id}/documents/text", json={"kind": kind, "text": text})
    client.post(f"/api/projects/{project_id}/process")
    run_jobs()
    topics = {t["name"]: t for t in client.get(f"/api/projects/{project_id}/path").json()["topics"]}
    assert topics["Thrashing"]["source"] == "notes"
    assert topics["Working set model"]["source"] == "exam"
    assert topics["Thrashing"]["unit"] == "Unit 1: Memory"
    assert not any("example" in name.lower() or "diagram" in name.lower() for name in topics)
    assert sum(1 for name in topics if name.lower() == "paging") == 1
