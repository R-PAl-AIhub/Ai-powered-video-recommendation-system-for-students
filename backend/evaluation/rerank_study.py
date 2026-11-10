"""Compare cross-encoder rerankers and query phrasings on labelled real pairs.

    python -m evaluation.rerank_study [--models a,b] [--passages 3]

Uses the cached database from ``python -m evaluation.live --name os ...`` (the
Neso Academy operating-systems playlist). Each labelled pair says whether video
#N of that playlist really teaches the topic. For every model and phrasing the
study reports how well the score separates the positives from the negatives.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# (topic, playlist position (1-based), is the video really about the topic?)
PAIRS: list[tuple[str, int, bool]] = [
    ("Concept of Operating Systems", 1, True),
    ("OS Services", 7, True),
    ("System Calls", 9, True),
    ("Structure of an OS", 13, True),
    ("Structure of an OS: Layered", 13, True),
    ("Structure of an OS: Monolithic", 13, True),
    ("Structure of an OS: Microkernel Operating Systems", 13, True),
    ("Concept of Virtual Machine", 14, True),
    ("Processes", 16, True),
    ("Processes: Definition", 16, True),
    ("Process states", 17, True),
    ("Process Control Block (PCB)", 18, True),
    ("Processes: Context switching", 20, True),
    ("Processes: Interprocess communication", 23, True),
    ("Threads", 31, True),
    ("Threads: Definition", 31, True),
    ("Benefits of threads", 31, True),
    ("Types of threads", 32, True),
    ("Threads: Multithreading models", 32, True),
    ("Scheduling criteria", 39, True),
    ("Scheduling algorithms: FCFS", 40, True),
    ("Scheduling algorithms: SJF", 43, True),
    ("Priority scheduling", 46, True),
    ("Scheduling algorithms: Round Robin", 49, True),
    ("Multilevel queue scheduling", 53, True),
    ("Multilevel feedback queue scheduling", 54, True),
    ("Critical section problem", 57, True),
    ("Peterson's solution", 58, True),
    ("Test and set lock", 59, True),
    ("Semaphores", 60, True),
    ("Bounded buffer problem", 62, True),
    ("Readers writers problem", 63, True),
    ("Dining philosophers problem", 64, True),
    ("Classical problems of synchronization: Monitors", 65, True),
    # hard negatives: similar wording, different subject
    ("Disk scheduling algorithms", 55, False),
    ("Disk scheduling algorithms", 49, False),
    ("Disk scheduling algorithms", 46, False),
    ("Virtual memory", 14, False),
    ("Virtual memory: Demand paging", 14, False),
    ("Logical and physical address space", 56, False),
    ("Deadlock avoidance", 61, False),
    ("Deadlock avoidance: Banker's algorithm", 64, False),
    ("Deadlock prevention", 61, False),
    ("Deadlock characterization", 64, False),
    ("Directory structure", 6, False),
    ("Directory structure", 13, False),
    ("Resource allocation graph", 7, False),
    ("Contiguous memory allocation", 24, False),
    ("File allocation methods", 13, False),
    ("Paging", 18, False),
    ("Segmentation", 18, False),
    ("RAID levels", 3, False),
    ("Free space management", 13, False),
    ("Virtual memory: Page replacement algorithms", 13, False),
    # ordinary negatives: a real topic against the wrong lecture
    ("Semaphores", 40, False),
    ("Process states", 49, False),
    ("Dining philosophers problem", 63, False),
    ("Scheduling criteria", 60, False),
    ("System Calls", 31, False),
    ("Peterson's solution", 64, False),
]

PHRASINGS = {
    "name": lambda topic: topic,
    "natural": lambda topic: _natural(topic),
    "question": lambda topic: f"What is {_natural(topic)}?",
}


def _natural(topic: str) -> str:
    """"Processes: Definition" -> "Definition of Processes"."""
    if ": " in topic:
        head, tail = topic.split(": ", 1)
        return f"{tail} of {head}" if len(tail.split()) <= 2 and tail[:1].isupper() and head.lower() not in tail.lower() else f"{tail} ({head})"
    return topic


def _auc(positives: list[float], negatives: list[float]) -> float:
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def _best_split(positives: list[float], negatives: list[float]) -> tuple[float, float]:
    best = (0.0, 0.0)
    for threshold in sorted(set(positives + negatives)):
        correct = sum(p >= threshold for p in positives) + sum(n < threshold for n in negatives)
        accuracy = correct / (len(positives) + len(negatives))
        if accuracy > best[0]:
            best = (accuracy, threshold)
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "--models",
        default="Xenova/ms-marco-MiniLM-L-6-v2,Xenova/ms-marco-MiniLM-L-12-v2,jinaai/jina-reranker-v1-turbo-en",
    )
    parser.add_argument("--passages", type=int, default=3, help="transcript chunks read per video")
    parser.add_argument("--detail", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    database = root / "data" / "live-os.db"
    if not database.exists():
        print("Run `python -m evaluation.live --name os ...` first to build the cache.")
        return 2
    os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    os.environ["DATA_DIR"] = str(root / "data")
    os.environ["RUN_WORKER"] = "false"
    os.environ["MIN_VIDEO_SECONDS"] = "0"

    import numpy as np
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Project, Video
    from app.services.embeddings import get_embedder
    from app.services.matching import get_index, hybrid_scores

    embedder = get_embedder()
    with SessionLocal() as db:
        project = db.scalar(select(Project))
        index = get_index(db, project.id, embedder)
        position = {
            v.id: v.playlist_position + 1
            for v in db.scalars(select(Video).where(Video.project_id == project.id))
        }
    column_of = {position[v.id]: c for c, v in enumerate(index.videos)}
    names = sorted({topic for topic, _, _ in PAIRS})
    row_of = {name: row for row, name in enumerate(names)}
    chunk_scores = hybrid_scores(
        embedder, embedder.embed_queries(names), names, index.matrix, index.vectorizer, index.tfidf
    )

    # The passages a reranker would read for each pair: meta + best transcript chunks.
    passages: list[list[str]] = []
    for topic, number, _ in PAIRS:
        start, end = index.spans[column_of[number]]
        rows = [start]
        if end - start > 1:
            ranked = np.argsort(-chunk_scores[row_of[topic], start + 1 : end])[: args.passages]
            rows += [start + 1 + int(r) for r in ranked]
        passages.append([index.texts[r][:1200] for r in rows])

    for model_name in args.models.split(","):
        started = time.monotonic()
        try:
            model = TextCrossEncoder(model_name=model_name, cache_dir=str(root / "data" / "models"))
        except Exception as exc:
            print(f"\n=== {model_name}: unavailable ({exc})")
            continue
        load = time.monotonic() - started
        for label, phrase in PHRASINGS.items():
            started = time.monotonic()
            scores = [
                max(model.rerank(phrase(topic), texts)) for (topic, _, _), texts in zip(PAIRS, passages, strict=True)
            ]
            elapsed = time.monotonic() - started
            positives = [s for s, (_, _, ok) in zip(scores, PAIRS, strict=True) if ok]
            negatives = [s for s, (_, _, ok) in zip(scores, PAIRS, strict=True) if not ok]
            accuracy, threshold = _best_split(positives, negatives)
            pairs_scored = sum(len(p) for p in passages)
            print(
                f"\n=== {model_name} [{label}]  AUC={_auc(positives, negatives):.3f}  "
                f"best accuracy={accuracy:.3f} at {threshold:.2f}  "
                f"({pairs_scored / elapsed:.0f} pairs/s, load {load:.0f}s)"
            )
            print(
                f"    positives: min={min(positives):.2f} p10={np.percentile(positives, 10):.2f} "
                f"median={np.median(positives):.2f}   negatives: median={np.median(negatives):.2f} "
                f"p90={np.percentile(negatives, 90):.2f} max={max(negatives):.2f}"
            )
            if args.detail:
                for score, (topic, number, ok) in sorted(zip(scores, PAIRS, strict=True)):
                    wrong = (ok and score < threshold) or (not ok and score >= threshold)
                    print(f"    {'!!' if wrong else '  '} {score:7.2f}  {'POS' if ok else 'neg'}  {phrase(topic)[:52]:52s} #{number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
