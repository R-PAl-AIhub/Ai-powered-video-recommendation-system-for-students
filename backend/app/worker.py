"""Standalone job worker: ``python -m app.worker``.

Run the API with RUN_WORKER=false and start as many of these as the workload
needs; the queue hands each job to exactly one worker.
"""

from __future__ import annotations

import logging
import signal
import threading

from .config import get_settings
from .db import SessionLocal, init_db
from .observability import configure_logging
from .services import jobs

log = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.environment == "production")
    if settings.is_sqlite:
        init_db()
    with SessionLocal() as db:
        jobs.recover_interrupted(db)

    worker = jobs.Worker()
    stopping = threading.Event()

    def shutdown(signum, _frame):
        log.info("signal %s received, finishing the current job", signum)
        worker.stop()
        stopping.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    worker.start()
    while worker.is_alive() and not stopping.wait(0.5):
        pass
    worker.join()


if __name__ == "__main__":
    main()
