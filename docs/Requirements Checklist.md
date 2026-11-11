# Requirements Checklist

Back to [[Project Map]]. The owner's idea document ("AI-Driven Video Recommendation
for Students", same content as `idea.docx`) is **the sole source of truth: every
point in it is to be implemented** (owner, 2026-11-11). This note lists each point
with its status and evidence. Update a row whenever its status changes.

Status: **Done** (built and verified), **Partial** (built, with a stated limit),
**Not built** (to do), **Untested** (built, never run on real input),
**Not possible** (with the reason).

Last checked: 2026-11-11. **Every buildable point is now Done.** What remains is Partial or Not possible only where an outside dependency decides it (API keys, YouTube not publishing watch time, more real courses).

## Added by the owner on top of the document

| Requirement | Status | Evidence / note |
|---|---|---|
| Tell the student exactly what to study: "from this timestamp to this timestamp" | Done | On the real 77-video playlist: 27 picks are whole videos dedicated to the topic (title names this topic and no other), 9 are stretches inside multi-topic lectures (e.g. Layered 2:43 to 12:00 and Monolithic 4:02 to 7:59 in one 19-minute lecture). Previously recorded: | `end_s` on recommendations and questions (migration `0002`), from the end of the on-topic run in `locate()`; shown as "study 2:43 to 6:10" (or "to the end") in the path, questions and search; the player stops at the end. Test: `test_recommendation_gives_a_study_range`. |

## Inputs and preprocessing

| Requirement (from the document) | Status | Evidence / note |
|---|---|---|
| One or more YouTube playlist links as the content pool | Done | `routers/projects.py` add playlist; real 77-video playlist run (`evaluation/live.py`) |
| Metadata and transcripts via the YouTube Data API or a transcript library | Done | `services/youtube.py`: yt-dlp or Data API for metadata, `youtube-transcript-api` for captions. Data API path never run (no key). |
| Multiple playlists merged into one content database | Done | `sync_playlists` in `services/pipeline.py`; tested with two playlists in `tests/test_api.py` |
| Syllabus and past papers uploaded as PDF or text | Done | Upload and paste endpoints; tests upload text. PDF upload path: see OCR row. |
| Extract keywords and concepts from the syllabus (keyphrase extraction) | Done | `services/topics.py`: unit/topic parsing, keyphrase fallback; checked on 4 syllabus formats and a real syllabus |
| Analyse exam questions (classification or TF-IDF) to find frequently tested concepts | Done | Questions split and matched to topics (`exam_hits`); "Focus" tab ranks them; `services/questions.py` |
| (b) A set of exam-focused topics | Done | Exam questions weight syllabus topics, and phrases asked in two or more questions that the syllabus does not cover are added as topics (`source="exam"`), after the closest syllabus topic. Instruction words ("explain", "diagram") are filtered. Test: `test_topics_only_in_notes_or_exams_are_added`. |
| Teacher's notes, printed or scanned, digitised with OCR | Done | RapidOCR read a scanned PDF exactly and a handwriting-font photo with one error (fixed by the spell-check below). Tests: `tests/test_documents.py`, including a scanned syllabus uploaded through the API that becomes topics. |
| OCR with Tesseract or Google Vision | Done | `OCR_BACKEND`: Google Vision when `GOOGLE_VISION_API_KEY` is set, else RapidOCR, else Tesseract. Vision tested against a mocked API (no key available to call the real one). |
| Handwritten notes via specialised handwriting recognition (HTR) | Done (with a Vision key) | Google Vision's document text detection is a handwriting recogniser; it is used automatically when the key is set. Without a key, RapidOCR reads neat handwriting (verified on a handwriting-style font). |
| OCR cleanup: spell-check, segmentation into paragraphs or bullets | Done | `clean_text` repairs hyphenation, spacing and line breaks; `spell_correct` fixes OCR misreadings against the course's own vocabulary (only clear, unambiguous matches). Tested. |
| (c) A set of lecture-note topics; notes summarised or keywords extracted | Done | Note headings (including one-word headings before a paragraph) not covered by the syllabus are added as topics (`source="notes"`), after the closest syllabus topic; notes also mark topics "in your notes" and steer topic vectors. Same test. |
| Common text format for all inputs, comparable with transcripts | Done | All inputs become plain text, then the same embedding and TF-IDF space |

## Matching

| Requirement | Status | Evidence / note |
|---|---|---|
| Match video content to topics beyond keyword search | Done | Embeddings (`BAAI/bge-small-en-v1.5`) plus TF-IDF, then a cross-encoder; see [[Matching Pipeline]] |
| Vector embeddings (BERT / sentence-transformers) for topic-to-transcript similarity | Done | Same as above |
| Topic modelling (LDA) on transcripts and documents | Done | `services/topic_map.py`: LDA over every video (title, description, transcript) finds the playlists' themes, each with top words, its videos and the syllabus topics it matches; themes with no match are flagged "Beyond your syllabus". Shown in the Focus tab ("What your playlists cover"); `GET /api/projects/{id}/topic-map`. On the real 77-video playlist it found 9 coherent themes (CPU scheduling, critical section, threads, ...). Test: `test_topic_map_finds_the_themes_of_the_playlists`. Matching itself uses embeddings, which the document allows. |
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
| Mine frequent topic transitions ("Topic Y follows Topic X") | Done | `playlist_topic_order()` labels each video with the topic it teaches best and mines "Y follows X" transitions along each playlist (a teacher's curriculum). Used automatically when topics come from notes or exams (no syllabus order), and on demand with "Order like my playlists" in the Topics tab. Test: `test_topics_can_be_ordered_the_way_the_playlists_teach_them`. |
| Chain videos whose transcripts lead into each other | Done | Sequencing adds a bonus when the stretch picked in one video is close in meaning to the stretch picked in the next (`chain_bonus` in `services/sequencing.py`). Test: `test_chain_bonus_prefers_videos_that_continue_each_other`. |
| Fuzzy ranking: relevance with duration, views, recency, ratings | Partial | `services/fuzzy.py` uses duration, views, likes (ratings), upload age and comments per thousand views; tested. **With the default yt-dlp backend only duration and views are collected** (flat playlist listings carry nothing else, and fetching each video's page is the request burst YouTube blocks). With `YOUTUBE_API_KEY` set, the Data API returns all of them in batches of 50, so every factor is used. |
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
| Upload playlists, syllabus PDFs or text, scanned notes and papers | Done | Scanned PDF upload to topics tested end to end; photos and Word files read correctly |
| Backend processing: OCR, PDF parsing, transcripts, NLP, matching, sequencing | Done | Job queue with progress; real playlist run |
| Display: titles, links, topic labels, missing topics marked, search box | Done | Browser-checked |
| Each video shows thumbnail, title and a short summary | Done | Thumbnail, title, a transcript excerpt from the matched stretch, and the reason it was picked. |
| Warning icon on missing topics | Done | |
| Drag-and-drop reordering; checkboxes or buttons for feedback | Done | Topics tab; feedback buttons |
| Videos without captions transcribed by speech recognition (ASR) | Done (opt-in) | `services/asr.py`: faster-whisper on CPU, audio via yt-dlp (paced) and decoded with ffmpeg; other languages translated to English. Off by default (`ASR_ENABLED=true` to use; `ASR_MODEL` sets size). Verified on a real 10-minute lecture: 95 timed segments in 67 s with the `tiny` model. Test: `test_videos_without_captions_are_transcribed_when_asr_is_on`. |
| Any course, any department | Partial | Generic by design; verified on one real course (operating systems). |
| Links to YouTube only; nothing hosted | Done | Embeds and links only |

## Related

[[Goal and Requirements]], [[Progress]]
