"""Export one real project as the snapshot behind the static demo (GitHub Pages).

The demo web app has no server; its API client answers from this file. Every
value comes from the real API functions run on a real database, so the demo
shows exactly what the product produced.

    DATABASE_URL=sqlite:///path/to/demo.db DATA_DIR=./data \
        python -m evaluation.export_demo ../frontend/src/demo-data.json
"""

from __future__ import annotations

import json
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Project, User
from app.routers import learning, projects

# Searches answered in the demo (search needs the models, which a static page lacks).
SEARCHES = [
    "deadlock",
    "paging",
    "round robin",
    "semaphores",
    "context switch",
    "system calls",
    "page replacement",
    "RAID",
]


def main() -> int:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "demo-data.json"
    with SessionLocal() as db:
        project = db.scalars(select(Project).order_by(Project.id)).first()
        if project is None:
            print("no project in this database")
            return 1
        user = db.get(User, project.user_id)
        dump = lambda model: model.model_dump(mode="json")  # noqa: E731
        snapshot = {
            # Never the real account: the snapshot is published.
            "user": {"id": 1, "email": "demo@example.com", "name": "Demo student"},
            "projects": [dump(p) for p in projects.list_projects(user=user, db=db) if p.id == project.id],
            "project": dump(projects.get_project(project=project, db=db)),
            "path": dump(learning.get_path(project=project, db=db)),
            "questions": dump(learning.get_questions(project=project, db=db)),
            "topic_map": [dump(t) for t in learning.get_topic_map(project=project, db=db)],
            "searches": {
                q: dump(learning.search(q=q, project=project, db=db)) for q in SEARCHES
            },
        }
    # Only what the interface shows: document previews are cut, the user's real
    # e-mail address is never exported.
    for document in snapshot["project"]["documents"]:
        document["preview"] = document["preview"][:200]
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, separators=(",", ":"))
    path = snapshot["path"]
    print(
        f"wrote {out_path}: {len(path['topics'])} topics, {path['stats']['matched']} matched, "
        f"{path['stats']['gaps']} gaps ({path['stats']['gaps_with_reading']} with a reading), "
        f"{snapshot['questions']['total']} questions, {len(snapshot['searches'])} searches"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
