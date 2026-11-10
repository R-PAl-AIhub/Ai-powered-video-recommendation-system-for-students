"""Run the full pipeline against real YouTube playlists and print the result.

    python -m evaluation.live --name os --subject "Operating Systems" \
        --playlist https://www.youtube.com/playlist?list=... \
        --syllabus evaluation/samples/os_syllabus.txt [--exam file] [--notes file]

This talks to YouTube, so it is a manual tool rather than part of CI. Results are
cached in data/live-<name>.db, so a second run only repeats the matching - handy
when tuning calibration. ``--search "topic"`` runs extra topic searches.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--name", required=True, help="cache name")
    parser.add_argument("--subject", default="")
    parser.add_argument("--playlist", action="append", default=[], required=True)
    parser.add_argument("--syllabus", required=True)
    parser.add_argument("--exam")
    parser.add_argument("--notes")
    parser.add_argument("--limit", type=int, default=80, help="max videos per playlist")
    parser.add_argument("--search", action="append", default=[])
    parser.add_argument("--raw", action="store_true", help="show raw cosine diagnostics")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    data = root / "data"
    data.mkdir(exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{(data / f'live-{args.name}.db').as_posix()}"
    os.environ["DATA_DIR"] = str(data)
    os.environ["RUN_WORKER"] = "false"
    os.environ["MAX_VIDEOS_PER_PLAYLIST"] = str(args.limit)
    os.environ.setdefault("EMBEDDING_BACKEND", "fastembed")

    import numpy as np
    from sqlalchemy import select

    from app.db import SessionLocal, init_db
    from app.models import Document, Playlist, Project, RerankScore, User, Video, VideoChunk
    from app.services.embeddings import from_blob, get_embedder
    from app.services.matching import get_index, hybrid_scores, video_relevance
    from app.services.path import build_path
    from app.services.pipeline import run_pipeline
    from app.services.recommend import search_project, unit_title
    from app.services.youtube import parse_playlist_id

    init_db()
    with SessionLocal() as db:
        project = db.scalar(select(Project))
        if project is None:
            user = User(email="live@example.com", name="Live", password_hash="x")
            db.add(user)
            db.flush()
            project = Project(user_id=user.id, name=args.name, subject=args.subject)
            db.add(project)
            db.flush()
        known = {p.youtube_id for p in project.playlists}
        for url in args.playlist:
            playlist_id = parse_playlist_id(url)
            if playlist_id is None:
                print(f"not a playlist link: {url}")
                return 2
            if playlist_id not in known:
                db.add(Playlist(project_id=project.id, youtube_id=playlist_id, url=url, position=len(known)))
                known.add(playlist_id)
        for kind, path in (("syllabus", args.syllabus), ("exam", args.exam), ("notes", args.notes)):
            if not path:
                continue
            text = Path(path).read_text(encoding="utf-8")
            document = db.scalar(
                select(Document).where(Document.project_id == project.id, Document.kind == kind)
            )
            if document is None:
                document = Document(project_id=project.id, kind=kind, filename=Path(path).name)
                db.add(document)
            if document.text != text:
                document.text, document.status, document.size_bytes = text, "ready", len(text)
                project.topics_locked = False
        db.commit()
        db.refresh(project)

        started = time.monotonic()
        last = {"stage": ""}

        def report(stage: str, progress: float, message: str) -> None:
            if stage != last["stage"]:
                last["stage"] = stage
                print(f"  [{time.monotonic() - started:6.1f}s] {stage}: {message}", flush=True)

        warnings = run_pipeline(db, project, report, {"reextract": True})
        elapsed = time.monotonic() - started
        db.refresh(project)
        path = build_path(db, project)
        videos = db.scalars(select(Video).where(Video.project_id == project.id)).all()
        statuses: dict[str, int] = {}
        for video in videos:
            statuses[video.transcript_status] = statuses.get(video.transcript_status, 0) + 1
        languages = sorted({v.transcript_language for v in videos if v.transcript_language})

        print(f"\n=== {args.name}: {len(videos)} videos, {path.stats.topics} topics, {elapsed:.0f}s ===")
        print(f"transcripts: {statuses}   languages: {languages}")
        print(f"embedder: {get_embedder().name}   threshold: {project.relevance_threshold}")
        print(
            f"matched {path.stats.matched}, gaps {path.stats.gaps}; path uses {path.stats.videos} "
            f"videos, {path.stats.total_seconds / 3600:.1f} h"
        )
        for warning in warnings:
            print(f"warning: {warning}")

        index = get_index(db, project.id, get_embedder())

        def stages(topic_id: int, limit: int = 3) -> str:
            """First-stage (embedding) and second-stage (cross-encoder) scores of the
            best videos for a topic, to explain a match or a gap."""
            row = topic_rows[topic_id]
            parts = []
            for column in np.argsort(-first_stage[row])[:limit]:
                video = index.videos[int(column)]
                ce = second_stage.get((topic_id, video.id))
                parts.append(
                    f"#{video.playlist_position + 1} {video.title[:22]} "
                    f"s1={first_stage[row, column]:.2f} s2={'-' if ce is None else f'{ce:.2f}'}"
                )
            return "   {" + " | ".join(parts) + "}"

        first_stage = second_stage = topic_rows = None
        if args.raw:
            ordered = list(project.topics)
            topic_rows = {t.id: row for row, t in enumerate(ordered)}
            chunk_scores = hybrid_scores(
                get_embedder(),
                np.vstack([from_blob(t.embedding) for t in ordered]),
                [f"{t.name} {unit_title(t.unit)}".strip() for t in ordered],
                index.matrix,
                index.vectorizer,
                index.tfidf,
            )
            first_stage = video_relevance(index, chunk_scores)
            video_of_chunk = dict(db.execute(select(VideoChunk.id, VideoChunk.video_id)).all())
            second_stage = {}
            for cached in db.scalars(select(RerankScore).where(RerankScore.project_id == project.id)):
                key = (cached.topic_id, video_of_chunk.get(cached.chunk_id))
                second_stage[key] = max(second_stage.get(key, 0.0), cached.score)
        unit = None
        previous_video = None
        switches = 0
        for item in path.topics:
            if item.unit != unit:
                unit = item.unit
                print(f"\n[{unit or 'No unit'}]")
            flags = "".join(
                [" EXAM×%d" % item.exam_hits if item.exam_hits else "", " NOTES" if item.in_notes else ""]
            )
            if item.primary is None:
                print(f"  GAP   {item.name}{flags}{stages(item.id) if args.raw else ''}")
                continue
            rec = item.primary
            same = "  ↳" if previous_video == rec.video.id else "   "
            if previous_video is not None and previous_video != rec.video.id:
                switches += 1
            previous_video = rec.video.id
            raw = stages(item.id) if args.raw else ""
            alternates = (
                " | alt: " + "; ".join(f"{a.video.title[:28]} ({a.relevance:.2f})" for a in item.alternates[:2])
                if item.alternates and not args.raw
                else ""
            )
            print(
                f"{same} {rec.relevance:.2f}  {item.name[:44]:44s} → #{rec.video.playlist_position + 1:<3d}"
                f"{rec.video.title[:46]:46s} @{_fmt_time(rec.start_s):>6s}{raw}{flags}{alternates}"
            )
        print(f"\nvideo switches along the path: {switches}")

        if args.raw:
            vectors = np.vstack([from_blob(t.embedding) for t in project.topics])
            cosine = vectors @ index.matrix.T
            best = cosine.max(axis=1)
            print(
                "raw best-chunk cosine per topic: "
                f"min={best.min():.3f} p25={np.percentile(best, 25):.3f} median={np.median(best):.3f} "
                f"p75={np.percentile(best, 75):.3f} max={best.max():.3f}"
            )
            print(
                "raw cosine over all topic/chunk pairs: "
                f"p50={np.percentile(cosine, 50):.3f} p90={np.percentile(cosine, 90):.3f} "
                f"p99={np.percentile(cosine, 99):.3f}"
            )

        for query in args.search:
            outcome = search_project(db, project, query)
            print(f"\nsearch “{query}”: {'found' if outcome.found else 'Video not found'}")
            for match in outcome.matches or outcome.closest:
                video = db.get(Video, match.video_id)
                label = "   " if outcome.found else " ~ "
                print(f" {label}{match.relevance:.2f}  #{video.playlist_position + 1:<3d}{video.title[:60]:60s} @{_fmt_time(match.start_s)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
