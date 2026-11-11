# Requirements Checklist

Back to [[Project Map]]. The owner's idea document ("AI-Driven Video Recommendation
for Students", same content as `idea.docx`) is **the sole source of truth: every
point in it is to be implemented** (owner, 2026-11-11). This note lists each point
with its status and evidence. Update a row whenever its status changes.

Status: **Done** (built and verified), **Partial** (built, with a stated limit),
**Not built** (to do), **Untested** (built, never run on real input),
**Not possible** (with the reason).

Last checked: 2026-11-11.

## Added by the owner on top of the document

| Requirement | Status | Evidence / note |
|---|---|---|
| Tell the student exactly what to study: "from this timestamp to this timestamp" | Done | `end_s` on recommendations and questions (migration `0002`), from the end of the on-topic run in `locate()`; shown as "study 2:43 to 6:10" (or "to the end") in the path, questions and search; the player stops at the end. Test: `test_recommendation_gives_a_study_range`. |

## Inputs and preprocessing

| Requirement (from the document) | Status | Evidence / note |
|---|---|---|
| One or more YouTube playlist links as the content pool | Done | `routers/projects.py` add playlist; real 77-video playlist run (`evaluation/live.py`) |
| Metadata and transcripts via the YouTube Data API or a transcript library | Done | `services/youtube.py`: yt-dlp or Data API for metadata, `youtube-transcript-api` for captions. Data API path never run (no key). |
| Multiple playlists merged into one content database | Done | `sync_playlists` in `services/pipeline.py`; tested with two playlists in `tests/test_api.py` |
| Syllabus and past papers uploaded as PDF or text | Done | Upload and paste endpoints; tests upload text. PDF upload path: see OCR row. |
| Extract keywords and concepts from the syllabus (keyphrase extraction) | Done | `services/topics.py`: unit/topic parsing, keyphrase fallback; checked on 4 syllabus formats and a real syllabus |
| Analyse exam questions (classification or TF-IDF) to find frequently tested concepts | Done | Questions split and matched to topics (`exam_hits`); "Focus" tab ranks them; `services/questions.py` |
| (b) A set of exam-focused topics | Partial | Exam questions weight syllabus topics; concepts asked in exams but missing from the syllabus are not added as topics. |
| Teacher's notes, printed or scanned, digitised with OCR | Untested | RapidOCR path in `services/documents.py` and `ocr.py`. Tests run with OCR off; never run on a real scan yet. |
| OCR with Tesseract or Google Vision | Partial | RapidOCR by default, Tesseract if installed. No Google Vision backend. |
| Handwritten notes via specialised handwriting recognition (HTR) | Not built | RapidOCR reads neat print and some handwriting. Options: Google Vision document text detection (handles handwriting, needs an API key), or a TrOCR handwriting model. |
| OCR cleanup: spell-check, segmentation into paragraphs or bullets | Partial | `clean_text` repairs hyphenation, spacing and line breaks; no spell-check. |
| (c) A set of lecture-note topics; notes summarised or keywords extracted | Partial | Notes mark topics "in your notes" and steer topic vectors. Topics found only in notes are not added unless the syllabus yields fewer than 3 topics. |
| Common text format for all inputs, comparable with transcripts | Done | All inputs become plain text, then the same embedding and TF-IDF space |

## Matching

| Requirement | Status | Evidence / note |
|---|---|---|
| Match video content to topics beyond keyword search | Done | Embeddings (`BAAI/bge-small-en-v1.5`) plus TF-IDF, then a cross-encoder; see [[Matching Pipeline]] |
| Vector embeddings (BERT / sentence-transformers) for topic-to-transcript similarity | Done | Same as above |
| Topic modelling (LDA) on transcripts and documents | Not built | Embeddings are used for matching. LDA could map the playlist's latent topics (for example, a "topics in your playlists" view and coverage check). |
| TF-IDF cosine similarity between topic queries and transcripts | Done | Part of stage 1 |
| Find which time segments of a video cover a topic | Done | Start and end second per recommendation; see the owner's addition above. |
| A threshold for "relevant" | Done | Default 0.5, learned from feedback (`learn_threshold`) |

## Sequencing and ranking

| Requirement | Status | Evidence / note |
|---|---|---|
| Follow syllabus (or notes) topic order | Done | Path follows topic order; student can reorder |
| Playlist continuity: stay with one playlist or channel | Done | Viterbi with playlist, channel and same-video bonuses; earlier playlists preferred (`services/sequencing.py`) |
| Part 1 before part 2; follow a playlist's own order | Done | Forward-in-playlist bonus, backward penalty |
| Topics as a graph, path covering all nodes in order | Done | Viterbi over topics in order, one chosen video per topic |
| Mine frequent topic transitions ("Topic Y follows Topic X") | Not built | A single course has no corpus of syllabi, but the playlists' own video order is a teacher's ordering and can be mined for transitions. |
| Chain videos whose transcripts lead into each other | Not built | Add a sequencing bonus when the end of one pick is similar in content to the start of the next. |
| Fuzzy ranking: relevance with duration, views, recency, ratings | Done | `services/fuzzy.py`: duration, views, likes (ratings), upload age, comments per thousand views. Tested. |
| Fuzzy ranking: comment sentiment | Done (with the Data API) | Top 30 comments per video via `commentThreads` (one request), scored with a study-specific lexicon (`comment_sentiment()`), stored as `videos.comment_sentiment` (migration `0003`). Runs only when `YOUTUBE_API_KEY` is set, because scraping comments is the request pattern YouTube blocks. Tested with a fake client. |
| Fuzzy ranking: watch time | Not possible | YouTube does not publish watch time for other people's videos; no API returns it. Likes per view is the nearest public signal. |
| Pick the top video per topic, with alternatives | Done | Primary plus up to 3 alternates per topic |
| Flag topics with no video ("No recommended video for Topic X") | Done | "Video not found for ..."; checked in the browser |
| No video in the playlists: look on YouTube | Done (manual) | "Find on YouTube" on each gap. Manual on purpose: automatic searches for every gap are request bursts, which got this machine blocked. |
| Output: ordered list of video links labelled by topic | Done | Path tab |

## Interaction and feedback

| Requirement | Status | Evidence / note |
|---|---|---|
| Manual topic search returning a sequenced list (by subtopic or depth) | Done | Search tab; results grouped by playlist in playlist order; browser-checked |
| "Video not found for [Topic]" in search | Done | Browser-checked |
| Feedback: Correct, Wrong topic, Irrelevant | Done | Path tab; tested and browser-checked, with undo |
| Feedback: "Already in my playlist" / "Video exists in my playlist" | Done | Button labelled "Already in my playlist"; marks the topic covered and takes it off the path. |
| Feedback updates data and adjusts matching thresholds | Done | Threshold re-learned on every feedback; tested |

## Web app

| Requirement | Status | Evidence / note |
|---|---|---|
| Web app: single-page React front end, Python back end | Done | React + FastAPI |
| Login and project setup | Done | Browser-checked |
| Upload playlists, syllabus PDFs or text, scanned notes and papers | Partial | Built; uploads of real PDFs and images not yet run end to end (see OCR row) |
| Backend processing: OCR, PDF parsing, transcripts, NLP, matching, sequencing | Done | Job queue with progress; real playlist run |
| Display: titles, links, topic labels, missing topics marked, search box | Done | Browser-checked |
| Each video shows thumbnail, title and a short summary | Done | Thumbnail, title, a transcript excerpt from the matched stretch, and the reason it was picked. |
| Warning icon on missing topics | Done | |
| Drag-and-drop reordering; checkboxes or buttons for feedback | Done | Topics tab; feedback buttons |
| Videos without captions transcribed by speech recognition (ASR) | Not built | Matched on title and description instead. Option: faster-whisper; needs audio downloads, the request pattern YouTube blocks most, so it must be paced. |
| Any course, any department | Partial | Generic by design; verified on one real course (operating systems). |
| Links to YouTube only; nothing hosted | Done | Embeds and links only |

## Related

[[Goal and Requirements]], [[Progress]]
