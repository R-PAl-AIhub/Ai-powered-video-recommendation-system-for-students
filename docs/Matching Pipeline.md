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
   its title says. Scattered passing mentions do not count. **Chaining:** sequencing adds a small bonus when the next pick's
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

## Known limits

- Topics taught under different words than the syllabus uses can still be
  matched to a look-alike title (see the three-schema case above).

- An English-only embedding model by default. Captions in other languages are
  translated to English by YouTube when possible; otherwise the video is matched on
  its title and marked `foreign`. A multilingual `EMBEDDING_MODEL` uses them
  directly. Not yet verified on real non-English playlists.
- The lexical fallback (`EMBEDDING_BACKEND=hash`) has no reranker and is weaker.

## Related

[[Architecture]], [[Decisions]], [[Evaluation and Testing]]
