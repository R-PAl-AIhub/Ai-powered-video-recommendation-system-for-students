"""Past exam questions: which topic each one is about, and where a video answers it.

This powers the question-and-answer section. Every question from the uploaded
exam papers is matched to its syllabus topic and then searched for in the video
pool exactly like a typed topic search, so the student can jump straight to the
explanation.
"""

from __future__ import annotations

import re

import numpy as np
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models import Project, Question
from .embeddings import from_blob, get_embedder
from .matching import get_index, hybrid_scores, locate, video_relevance
from .recommend import (
    EXAM_HIT,
    acronym_map,
    load_feedback,
    query_text,
    rerank_relevance,
    unit_title,
)
from .topics import split_questions

MAX_QUESTIONS = 300


def _words(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4}


def _overlap(question: str, topic_text: str) -> float:
    """Share of the topic's significant words that appear in the question."""
    topic_words = _words(topic_text)
    if not topic_words:
        return 0.0
    return len(topic_words & _words(question)) / len(topic_words)


def link_questions(db: Session, project: Project) -> int:
    """Rebuild the project's questions from its exam papers. Returns the count."""
    db.execute(delete(Question).where(Question.project_id == project.id))
    papers = [
        d for d in project.documents if d.kind == "exam" and d.status == "ready" and d.text.strip()
    ]
    items: list[tuple[int, int, str]] = []  # (document id, position, text)
    for paper in papers:
        for position, text in enumerate(split_questions(paper.text)):
            items.append((paper.id, position, text))
    items = items[:MAX_QUESTIONS]
    if not items:
        db.flush()
        return 0

    embedder = get_embedder()
    texts = [text for _, _, text in items]
    vectors = embedder.embed_queries(texts)

    # Which topic is each question about? Compare in the same space the topics
    # live in; the best topic wins if it clears the bar used for exam weighting.
    topics = [t for t in project.topics if t.embedding is not None]
    best_topic: list[int | None] = [None] * len(items)
    if topics:
        acronyms = acronym_map(project)
        topic_vectors = np.vstack([from_blob(t.embedding) for t in topics])
        topic_texts = [f"{query_text(t, acronyms)} {unit_title(t.unit)}".strip() for t in topics]
        low, high = embedder.calibration
        semantic = np.clip((vectors @ topic_vectors.T - low) / (high - low), 0.0, 1.0)
        for row in range(len(items)):
            lexical = np.asarray([_overlap(texts[row], topic_text) for topic_text in topic_texts])
            combined = semantic[row] + 0.35 * lexical * (1.0 - semantic[row])
            column = int(np.argmax(combined))
            if combined[column] >= EXAM_HIT:
                best_topic[row] = topics[column].id

    # Where is each question answered? Same two-stage search as a typed query.
    index = get_index(db, project.id, embedder)
    answers: list[tuple[int, float, float, float, str] | None] = [None] * len(items)
    if not index.empty:
        scores = hybrid_scores(
            embedder, vectors, texts, index.matrix, index.vectorizer, index.tfidf
        )
        relevance = rerank_relevance(
            None,
            project.id,
            index,
            [(None, text) for text in texts],
            scores,
            video_relevance(index, scores),
        )
        blocked = load_feedback(db, project.id).blocked_videos
        for row in range(len(items)):
            for column in np.argsort(-relevance[row]):
                column = int(column)
                if relevance[row, column] < project.relevance_threshold:
                    break
                if index.videos[column].id in blocked:
                    continue
                match = locate(index, column, scores[row], float(relevance[row, column]))
                answers[row] = (match.video_id, match.relevance, match.start_s, match.end_s, match.snippet)
                break

    for row, (document_id, position, text) in enumerate(items):
        answer = answers[row]
        db.add(
            Question(
                project_id=project.id,
                document_id=document_id,
                position=position,
                text=text,
                topic_id=best_topic[row],
                video_id=answer[0] if answer else None,
                relevance=round(answer[1], 4) if answer else 0.0,
                start_s=answer[2] if answer else 0.0,
                end_s=answer[3] if answer else 0.0,
                snippet=answer[4] if answer else "",
            )
        )
    db.flush()
    return len(items)
