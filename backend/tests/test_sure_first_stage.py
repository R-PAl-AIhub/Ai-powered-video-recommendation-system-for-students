"""The reranker leads, but it may not turn a video into a gap when the first
stage is nearly certain, the transcript itself backs it, and none of the topic's
words is missing. Found on a real playlist taught in Hindi: the reranker scored
0 for "Insertion deletion and update anomalies" against the lecture titled
"Insertion, Deletion & Updation Anomaly" that teaches exactly that."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.services.recommend import NAMED_FLOOR, rerank_relevance
from app.services.rerank import set_reranker


class Rejecting:
    """A cross-encoder that finds nothing relevant."""

    name = "rejecting"

    def raw_scores(self, query, passages):
        return [-5.0 for _ in passages]

    def calibrate(self, raw):
        return 0.0


@pytest.fixture
def rejecting():
    set_reranker(Rejecting())
    yield
    set_reranker(None)


TITLE = "Lec-24: Introduction to Normalization | Insertion, Deletion & Updation Anomaly"
SAID = (
    "these are the three operations insertion deletion and update so let us start with "
    "the update anomaly then the insertion anomaly and the deletion anomalies"
)
QUERY = "Insertion deletion and update anomalies"


def relevance_of(passages: list[str], first: float, chunk_scores: list[float], query=QUERY):
    index = SimpleNamespace(
        texts=passages,
        spans=[(0, len(passages))],
        videos=[SimpleNamespace(english=True)],
    )
    out = rerank_relevance(
        None,
        1,
        index,
        [(None, query)],
        np.array([chunk_scores], dtype=float),
        np.array([[first]], dtype=float),
    )
    return float(out[0, 0])


def test_a_sure_match_backed_by_the_transcript_is_not_made_a_gap(rejecting):
    assert relevance_of([TITLE, SAID], 0.95, [0.9, 0.7]) == NAMED_FLOOR


def test_the_reranker_still_decides_when_the_first_stage_is_not_sure(rejecting):
    assert relevance_of([TITLE, SAID], 0.83, [0.8, 0.7]) == 0.0


def test_a_title_alone_is_not_enough(rejecting):
    # Nothing in what is said scores by itself.
    assert relevance_of([TITLE, "today we revise the previous lecture"], 0.95, [0.95, 0.2]) == 0.0
    # No transcript at all.
    assert relevance_of([TITLE], 0.95, [0.95]) == 0.0


def test_a_missing_word_of_the_topic_blocks_the_rule(rejecting):
    # "Classification of DBMS" must not take "DBMS - Definition" (seen on a real playlist).
    said = "a dbms is a database management system which stores the data of an organisation"
    assert relevance_of(["DBMS - Definition", said], 0.93, [0.9, 0.6], "Classification of DBMS") == 0.0
