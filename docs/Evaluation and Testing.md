# Evaluation and Testing

Back to [[Project Map]].

## Commands (run in `backend/`)

```bash
.venv/Scripts/python -m pytest                              # 181 tests, no network, about a minute
.venv/Scripts/python -m ruff check app evaluation tests     # lint
.venv/Scripts/python -m evaluation.run --backend fastembed  # quality gate with the real models
.venv/Scripts/python -m evaluation.run --backend hash       # quality gate with the lexical fallback
```

In `frontend/`: `npm run build` (type-check and build).

## What each thing is

- **`tests/test_api.py`**: the whole product over HTTP against a fake YouTube
  (`evaluation.harness.LabelledYouTube`) and the lexical embedder: accounts, security
  (rate limit, cross-site block, ownership), path, gaps, importance, questions,
  search, all four kinds of feedback, topic editing, uploads, YouTube blocking and
  retry, health and metrics.
- **`tests/test_jobs.py`**: the job queue on its own: one active job per course,
  retries after a YouTube block (30 min, 2 h, 6 h, then stop), claiming, recovery of
  interrupted jobs, failures, the worker thread.
- **`tests/test_youtube.py`**: link and id parsing, request pacing, the yt-dlp
  backend, the Data API backend against a fake HTTP transport (paging, limits,
  private videos, quota errors, comments), caption choice (human English, generated
  English, translated, original language), block detection.
- **`tests/test_ocr.py`**: image preparation, reading order from text boxes, each
  OCR engine with a fake model, and which engine is chosen for each setting.
- **`tests/test_document_formats.py`**: file-type detection from content, text
  cleanup, PDFs with a text layer and bookmarks, Word headings and tables, text
  encodings, web pages.
- Together: 90% line coverage of `app/` (`documents.py` 97%, `ocr.py` 100%,
  `jobs.py` 95%, `youtube.py` 99%).
- **`evaluation/os_course.py`**: a small labelled course (original transcripts, a
  syllabus, an exam, notes) with the expected video for every topic and the topics
  that must be gaps.
- **`evaluation/run.py`**: runs the real pipeline over that course and fails if
  top-1 accuracy, gap recall, gap precision or timestamp accuracy drop below their
  thresholds. This is the regression gate for matching; run it after any change in
  [[Matching Pipeline]].
- **`evaluation/live.py`**: runs the real pipeline on real YouTube playlists and
  prints the path. Caches into `backend/data/live-<name>.db`, so re-runs do not
  contact YouTube. `--raw` shows both stages' scores per topic.
- **`evaluation/rerank_study.py`**: compares rerankers and phrasings on 60 labelled
  pairs from the cached real playlist.
- **`evaluation/samples/os_syllabus.txt`**: a realistic syllabus to try.

## Real-data cache

`backend/data/live-os.db` holds a full run of Neso Academy's "Operating System"
playlist (77 videos, 69 with captions). It is not in git. Keep it: it lets matching
be tuned offline. A database from an older code version may lack newer columns;
see the note in [[Backend]].

## Not yet covered

- The YouTube Data API backend is tested against a fake transport only; it has
  never run against the real API (no key).
- PostgreSQL runs in CI only (GitHub Actions); every test passes there.
- More real playlists in other subjects, and non-English playlists. Blocked so far
  by YouTube rate-limiting this machine.
- The frontend has no automated tests.

## Related

[[Progress]], [[Backend]]
