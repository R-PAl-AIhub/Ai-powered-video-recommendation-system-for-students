"""A topic map of the student's playlists, found with LDA topic modelling.

Each video (title, description and transcript) is one document. Latent
Dirichlet Allocation finds the themes the playlists cover; each theme is
described by its top words, the videos that are mostly about it, and the
syllabus topics it corresponds to. Themes with no matching syllabus topic show
what the playlists teach beyond the syllabus; syllabus topics no theme covers
are the gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project, Video, VideoChunk

MIN_VIDEOS = 4
THEME_SHARE = 0.35  # a video belongs to a theme when this share of it is about the theme
SYLLABUS_MATCH = 0.12  # minimum word-distribution similarity for a syllabus topic


@dataclass
class Theme:
    words: list[str]
    video_ids: list[int] = field(default_factory=list)
    topic_ids: list[int] = field(default_factory=list)


def build_topic_map(db: Session, project: Project) -> list[Theme]:
    from sklearn.decomposition import LatentDirichletAllocation
    from sklearn.feature_extraction.text import CountVectorizer

    rows = db.execute(
        select(Video.id, VideoChunk.text)
        .join(VideoChunk, VideoChunk.video_id == Video.id)
        .where(Video.project_id == project.id)
        .order_by(Video.id, VideoChunk.idx)
    ).all()
    texts: dict[int, list[str]] = {}
    for video_id, text in rows:
        texts.setdefault(video_id, []).append(text)
    video_ids = list(texts)
    if len(video_ids) < MIN_VIDEOS:
        return []
    documents = [" ".join(parts) for parts in texts.values()]

    vectorizer = CountVectorizer(
        stop_words="english", max_df=0.6, min_df=2, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]{2,}\b"
    )
    try:
        counts = vectorizer.fit_transform(documents)
    except ValueError:  # too little vocabulary after filtering
        return []
    themes_wanted = int(np.clip(round(np.sqrt(len(video_ids))), 3, 12))
    lda = LatentDirichletAllocation(
        n_components=themes_wanted, learning_method="batch", max_iter=40, random_state=7
    )
    doc_topics = lda.fit_transform(counts)  # videos x themes, rows sum to 1
    words = vectorizer.get_feature_names_out()
    word_dist = lda.components_ / lda.components_.sum(axis=1, keepdims=True)

    topics = list(project.topics)
    topic_dist = None
    if topics:
        topic_counts = vectorizer.transform([f"{t.name} {t.unit}" for t in topics]).toarray()
        topic_dist = topic_counts / np.maximum(topic_counts.sum(axis=1, keepdims=True), 1)

    themes: list[Theme] = []
    for k in range(themes_wanted):
        top = [str(words[i]) for i in np.argsort(-lda.components_[k])[:6]]
        members = [video_ids[i] for i in np.flatnonzero(doc_topics[:, k] >= THEME_SHARE)]
        theme = Theme(words=top, video_ids=members)
        if topic_dist is not None:
            # Cosine between the theme's word distribution and each topic's words.
            norms = np.linalg.norm(topic_dist, axis=1) * np.linalg.norm(word_dist[k])
            similarity = (topic_dist @ word_dist[k]) / np.maximum(norms, 1e-12)
            theme.topic_ids = [
                topics[i].id for i in np.argsort(-similarity)[:4] if similarity[i] >= SYLLABUS_MATCH
            ]
        if theme.video_ids:
            themes.append(theme)
    themes.sort(key=lambda t: -len(t.video_ids))
    return themes
