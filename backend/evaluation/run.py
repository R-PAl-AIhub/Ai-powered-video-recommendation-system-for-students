"""Offline quality gate: ``python -m evaluation.run [--backend fastembed|hash]``.

Processes the labelled course with the real pipeline and exits non-zero when
matching quality falls below the thresholds, so a regression fails CI.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["fastembed", "hash"], default="fastembed")
    parser.add_argument("--min-top1", type=float, default=0.9)
    parser.add_argument("--min-gap-recall", type=float, default=1.0)
    parser.add_argument("--min-gap-precision", type=float, default=0.75)
    parser.add_argument("--min-start", type=float, default=0.75)
    args = parser.parse_args()

    # Settings are read at import time, so the environment is prepared first.
    workdir = tempfile.mkdtemp(prefix="eval-")
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(workdir, 'eval.db')}"
    os.environ.setdefault("DATA_DIR", workdir)
    os.environ["EMBEDDING_BACKEND"] = args.backend
    os.environ["RUN_WORKER"] = "false"
    os.environ["OCR_BACKEND"] = "none"
    if os.environ.get("MODEL_DIR") is None and args.backend == "fastembed":
        os.environ["MODEL_DIR"] = os.path.join(os.path.dirname(__file__), "..", "data", "models")

    from app.db import SessionLocal, init_db
    from app.services.embeddings import get_embedder

    from .harness import evaluate

    init_db()
    embedder = get_embedder()
    if args.backend == "fastembed" and not embedder.name.startswith("fastembed"):
        print("The embedding model could not be loaded; refusing to evaluate the fallback.")
        return 2
    with SessionLocal() as db:
        report = evaluate(db, embedder.name)
    print(report.summary())

    failures = []
    if report.split_topics:
        failures.append("topics one video already covers were split into parts: " + ", ".join(report.split_topics))
    if report.unlabelled:
        failures.append("the syllabus parser produced topics that have no expected answer")
    for label, value, minimum in (
        ("top-1 accuracy", report.top1_accuracy, args.min_top1),
        ("gap recall", report.gap_recall, args.min_gap_recall),
        ("gap precision", report.gap_precision, args.min_gap_precision),
        ("timestamp accuracy", report.start_accuracy, args.min_start),
    ):
        if value < minimum:
            failures.append(f"{label} {value:.3f} is below the required {minimum:.3f}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if not failures:
        print("PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
