# Decisions

Back to [[Project Map]]. Choices already made, with the reason, so they are not
re-argued. Change one only with new evidence.

| Decision | Reason |
|---|---|
| FastAPI rather than Flask or Django | Validation, async and OpenAPI built in. The idea document only suggested "a Python backend". |
| Session in an httpOnly, SameSite=Lax cookie | Not readable by scripts, unlike a token in localStorage. An Origin check is the second line against cross-site requests. |
| Jobs in a database table, not Redis or Celery | Durable and scalable with nothing extra to deploy. Workers can still be separate processes. |
| Vectors as blobs, exact search in memory | A course has at most tens of thousands of chunks. A vector database would add operations for no gain at this size. |
| Two-stage matching: embeddings shortlist, cross-encoder decides | Embeddings alone could not tell "disk scheduling" from a CPU "scheduling algorithms" lecture (0.83 relevance). The cross-encoder separates such pairs with AUC 0.99. |
| The reranker reads the title chunk plus three transcript chunks | With one chunk it wrongly rejected real matches. Three is where accuracy levelled off. |
| Cache raw reranker scores, calibrate on read | Cached calibrated scores went stale when the calibration changed. |
| The course subject is not blended into topic vectors | It made topics with no video look covered, because every video matches the subject. |
| Relevance passes linearly into the ranking score | A rule-based fuzzy combination flattened real differences, and continuity bonuses then picked worse videos. Fuzzy logic is kept for the quality score. |
| Path ordering solved as a whole (Viterbi) | Picking the best video per topic independently makes the path jump between playlists. |
| Videos under 2 minutes are never recommended | On a real playlist, 40 to 78 second promo clips were winning topics on their descriptions alone. |
| "X: Definition" is matched as "X"; abbreviations spelled out from the subject | Real syllabus wording that both models handled badly. |
| One caption request per video; details only when there are no captions | YouTube blocked this machine after a burst of about 300 requests. |
| Uploaded files are deleted once their text is extracted | Privacy, and it works on hosts with temporary disks. |
| English models by default, multilingual by configuration | Small and accurate for the common case; YouTube's own translation covers many other-language videos. To be revisited once tested on real non-English playlists. |
| Feedback is undone from a bar at the bottom of the screen, not from the row | Feedback can turn a row into a different video, a gap or a known topic, so a control inside the row would disappear with the change. |
| Landing page shows real components with real data | Fake screenshots are the most recognisable sign of generic AI design. |
| `idea.docx` and the link-list documents are not in git | The repository is public. |
| Study material is matched per passage with pages kept, and never creates topics | A student needs "pp. 11–12, §Reader-Writer Locks", not "this book". A whole textbook names far more than the course asks, so topic extraction stays with the syllabus, notes and papers. |
| Web pages are fetched only from public addresses, re-checked at every redirect, connecting to the checked IP | The server fetches addresses typed by users; without this it could be used to reach internal systems or cloud metadata (SSRF), including through DNS rebinding. |
| Not deployed on Vercel | Vercel runs serverless functions with a size limit far below the models plus onnxruntime, no long-lived worker for the job queue, and no persistent disk. The full app ships as a Docker image (GHCR) with `render.yaml` and `docker-compose.yml`; GitHub Pages hosts a static, read-only demo of the interface with real sample data. |
| Python 3.13 in the image and CI | Development uses 3.14, but every compiled dependency (onnxruntime, ctranslate2, OpenCV) has long-standing 3.13 wheels. |

## Related

[[Matching Pipeline]], [[Architecture]], [[Frontend]]
