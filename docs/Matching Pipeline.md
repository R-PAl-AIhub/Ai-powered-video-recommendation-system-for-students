# Matching Pipeline

Back to [[Project Map]]. This is the core of the product. It is tuned and measured;
change it only with the tools in [[Evaluation and Testing]].

## Steps

1. **Topics** (`services/topics.py`). The syllabus is parsed into units and topics:
   unit headings, comma and bullet lists, "Heading: a, b, c" groups. Generic items
   get context ("Deadlocks: Definition"). Fallbacks: headings in the notes, then key
   phrases.
2. **Video text** (`services/pipeline.py`). Each video becomes chunks: chunk 0 is
   title, chapters and description; the rest are windows of about 75 seconds of
   transcript.
3. **Topic wording** (`query_text()` in `services/recommend.py`). "X: Definition" is
   matched as "X". Abbreviations are spelled out from the course subject ("OS").
4. **Stage 1, shortlist** (`services/matching.py`). Embedding cosine
   (`BAAI/bge-small-en-v1.5`) plus a TF-IDF boost scores every chunk. Chunk scores
   roll up to one relevance per video. The best six videos per topic go on.
5. **Stage 2, rerank** (`rerank_relevance()`). A cross-encoder
   (`Xenova/ms-marco-MiniLM-L-6-v2`) reads the topic against each shortlisted video's
   title chunk and its top three transcript chunks. Its score becomes the relevance:
   `relevance = s2 * (1 - 0.15 * (1 - s1))`.
6. **Quality** (`services/fuzzy.py`). A small fuzzy inference system turns length,
   views and likes into a quality value that can discount relevance by up to 25%.
7. **Tie-breakers.** Bonus when the video title names the topic; small penalty for
   worked-problem videos so the concept lecture comes first.
8. **Sequencing** (`services/sequencing.py`). Viterbi over topics in syllabus order,
   with bonuses for staying in the same video, playlist or channel.
9. **Study range** (`locate()` in `services/matching.py`, `rebuild_recommendations`).
   If the video's title names this topic and no other topic of the course, the
   student studies the whole video. Otherwise: start where chunks score within 75%
   of the best chunk, then continue while they stay above 55%, tolerating one
   off-topic chunk; an end within 60 s of the video's end means "to the end".
   **Key terms:** a topic's distinctive words that never appear in a video lower its
   relevance (up to 30%), so "disk scheduling" does not match a CPU-scheduling
   lecture. **Transcript evidence** (`apply_transcript_evidence`, spoken words only,
   never the title): a video that names a topic only inside a course-contents
   read-out (three or more "chapter N" references in one passage) keeps half its
   relevance, so the topic stays a gap; a video that names a topic of two or more
   words in two passages in a row is discussing it and gets at least 0.6, whatever
   its title says. Scattered passing mentions do not count. **Sure first stage**
   (in `rerank_relevance`, since 2026-11-12): when the first stage is nearly
   certain (0.9 or more), a transcript passage scores 0.5 or more by itself, and
   none of the topic's distinctive words is missing from the video, the reranker
   cannot turn the video into a gap (relevance at least 0.6). Found on a real
   Hindi-taught playlist: the reranker gave 0 to "Insertion deletion and update
   anomalies" against the lecture titled "Insertion, Deletion & Updation Anomaly"
   that teaches exactly that. Checked on the three cached real courses: only that
   topic changes (the "no word missing" condition is what keeps "Classification
   of DBMS" a gap). **Chaining:** sequencing adds a small bonus when the next pick's
   stretch is close in meaning to the previous one's. **Transitions:** topic order
   can be mined from the playlists' own video order (`playlist_topic_order`).
   **Extra topics:** headings found only in notes, and phrases asked in two or more
   past questions, become topics after the closest syllabus topic. **Quality** also
   uses upload age, comment volume and (with the Data API) comment sentiment.
9a. **Several stretches** (`plan_segments`). When one stretch does not cover the
   topic: a "Part 1 / Part 2" series around the chosen video; a second stretch of the
   same video that is as strong (90% of the best chunk at its peak, 80% on average);
   then greedy set cover over the topic's parts ("X and Y" halves, past questions and
   notes passages that match it at 0.6 or more), adding the fewest stretches from any
   playlist; same playlist wins ties; near-duplicate stretches (cosine 0.95) are
   skipped. At most 4 segments; uncovered parts are listed. Short captioned clips
   stay in the index only to continue a series.
10. **Signals from documents.** Past questions are counted per topic (`exam_hits`);
    notes passages mark topics as `in_notes`. Importance is 75% exam frequency, 25%
    notes. Each past question is also searched like a topic to find its answering
    moment (`services/questions.py`).
11. **Feedback** (`load_feedback()`, `learn_threshold()`). Correct pins a video;
    wrong topic blocks the pair; irrelevant blocks the video everywhere; already
    known removes the topic. The relevance threshold moves to separate confirmed
    from rejected picks.

## Measured numbers (do not guess new ones; re-measure)

- BGE cosine on lecture text: off-topic but same subject 0.55 to 0.62; topics with
  no video peak near 0.60; true matches 0.72 to 0.89. Calibration window 0.60 to 0.85.
- Cross-encoder logit, best of four passages, 60 labelled real pairs: look-alikes
  peak at 2.72, true matches p10 3.42 and median 7.19, AUC 0.991. Window 0.8 to 4.9
  puts the best split (2.84) at 0.5.
- Default relevance threshold 0.5.

## Results

- Synthetic labelled course: 25/25 topics, 3/3 gaps (real models).
- Real 77-video playlist: all 38 coverable topics matched, 20 uncovered topics
  reported as gaps, 6 of 8 past questions answered and the other 2 correctly not.
- Real 15-video database-systems playlist (Neso Academy, "Introduction to DBMS |
  Chapter 1"), 15 syllabus topics, checked against the transcripts by hand
  (2026-11-11): 9 matched, 6 gaps. Two errors found and fixed by the transcript
  evidence rules: "Functional dependencies" had matched the intro video where the
  teacher reads out the course contents (now a gap); "Data independence" was a gap
  although "View of Data" teaches it from 5:17 (now matched there). The real
  operating-systems course is unchanged by the rules (58 of 58 topics identical).
  Still wrong: "Three-schema architecture" picks "Three Tier Architecture" from
  0:00; the three levels are really taught in "View of Data" from 2:41 (the words
  "three schema" are never spoken, so only meaning can find it, and the reranker
  prefers the look-alike title).
- Real 15-lecture playlist taught in Hindi (Gate Smashers, normalization, lectures
  24 to 38), 21 syllabus topics, checked against the transcripts by hand
  (2026-11-12). Words: 10 lectures from the English captions shown on YouTube
  (YouTube refused every caption download from this PC, so they were copied from
  "Show transcript"), 5 lectures heard by Whisper `small` on this PC and
  translated from Hindi to English (about 91 minutes of audio in 36 minutes).
  The heard English is correct and readable.
  Result: 15 topics matched, 6 gaps.
  - Gaps: 5 are right (the whole second unit, transactions and storage, is not
    in the playlist). 1 is wrong: "Need for normalization" is taught in lecture
    24 from 0:00, but the words "need for" are never said and both stages score
    it low.
  - Matches: all 15 point to a lecture that teaches the topic. 11 start at the
    right place. 4 start late inside the right lecture: "Insertion deletion and
    update anomalies" at 5:31 (taught from 4:06), "Trivial and non-trivial
    functional dependency" at 10:05 (from 7:12), "Partial dependency" at 17:00
    of the 2NF lecture (defined at 7:00), "Lossless join decomposition" at 18:33
    (the whole lecture is about it; its title also names the fifth normal form,
    so the "whole video" rule does not apply).
  Three errors were found by this check and fixed (each has tests):
  - "Insertion deletion and update anomalies" was a gap: the reranker gave 0 to
    the lecture titled with exactly that. Fixed by the "sure first stage" rule.
  - "Closure of a set of attributes" was a gap: Whisper wrote "closer" 28 times
    and never "closure". Fixed by `restore_title_terms` in `services/asr.py` (a
    title word of six letters or more that is never heard, while one sound-alike
    word is heard three times or more, is put back). Giving Whisper the title as
    a hint did not fix this word, but it did fix "CVMS" to "DBMS". The cached
    transcripts were corrected with the same function, not listened to again.
  - "First normal form (1NF)" pointed to a worked example (lecture 36) instead
    of the lecture on it (25). Fixed: a title that names the whole topic gets
    the full title bonus (`_rank_score`), however long the title is.
  The other two real courses are unchanged by the three fixes (operating systems
  58 of 58 topics, English database playlist 15 of 15).

## Known limits

- Topics taught under different words than the syllabus uses can still be
  matched to a look-alike title (see the three-schema case above).

- An English-only embedding model by default. A lecture spoken in another
  language is matched through English: its English captions when it has them,
  otherwise Whisper listens and translates (verified on a real Hindi playlist,
  see "Results"). A multilingual `EMBEDDING_MODEL` would use other-language
  captions directly; that path is still not verified on real videos.
- Study ranges can start late inside the right lecture (4 of 15 on the Hindi
  playlist), and a topic worded abstractly ("Need for ...") can be missed.
- The lexical fallback (`EMBEDDING_BACKEND=hash`) has no reranker and is weaker.

## Related

[[Architecture]], [[Decisions]], [[Evaluation and Testing]]
