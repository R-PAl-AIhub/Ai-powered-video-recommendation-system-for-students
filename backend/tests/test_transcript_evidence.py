"""What the transcript literally says corrects the relevance: a course-contents
read-out is not teaching, and a topic discussed by name inside a lecture with
another title is. Both cases were found on a real database-systems playlist."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.services.recommend import (
    NAMED_FLOOR,
    OUTLINE_PENALTY,
    apply_transcript_evidence,
    is_outline,
)

OUTLINE = (
    "let us now see the syllabus of this course in chapter 6 we will be focusing on "
    "relational algebra in chapter 7 we will be focusing on normalization and the "
    "functional dependency the partial dependency and in chapter 8 we will be focusing "
    "on storage and chapter number 9 is indexing and hashing"
)
LEVELS = (
    "the logical level deals with what data are stored and there exists physical data "
    "independence what do we mean by this"
)
LEVELS_MORE = (
    "there should exist physical data independence so that changes in the physical "
    "level do not affect the logical level"
)
PASSING = "the kernel also has page replacement demand paging virtual memory and so on"
OTHER = "a database administrator grants access and takes backups of the database"


def index_of(*videos: list[str]) -> SimpleNamespace:
    """A stand-in for the project index: per video, a title passage followed by
    its transcript passages."""
    texts: list[str] = []
    spans: list[tuple[int, int]] = []
    for passages in videos:
        spans.append((len(texts), len(texts) + len(passages)))
        texts.extend(passages)
    return SimpleNamespace(texts=texts, spans=spans)


def adjust(index, query: str, before: list[float]) -> list[float]:
    relevance = np.array([before], dtype=float)
    return [round(float(v), 3) for v in apply_transcript_evidence(index, [query], relevance)[0]]


def test_outline_passages_are_recognised():
    assert is_outline(OUTLINE)
    assert is_outline("the first chapter is an introduction the second chapter covers sql "
                      "and the third chapter covers design")
    # One reference to another lecture is ordinary teaching talk.
    assert not is_outline("as we saw in chapter 2 a process is a program in execution")
    assert not is_outline(LEVELS)


def test_topic_named_only_in_a_contents_list_loses_relevance():
    index = index_of(["Introduction to DBMS", "welcome to this playlist", OUTLINE])
    assert adjust(index, "Functional dependencies", [0.86]) == [round(0.86 * OUTLINE_PENALTY, 3)]
    # Also for one-word topics.
    assert adjust(index, "Normalization", [0.7]) == [round(0.7 * OUTLINE_PENALTY, 3)]


def test_outline_mention_does_not_hurt_a_video_that_also_teaches_the_topic():
    teaching = "a functional dependency is a constraint between two sets of attributes"
    index = index_of(["Introduction", OUTLINE, teaching])
    assert adjust(index, "Functional dependencies", [0.86]) == [0.86]


def test_topic_discussed_by_name_counts_whatever_the_title_says():
    index = index_of(["View of Data", "three levels of abstraction", LEVELS, LEVELS_MORE])
    # The reranker had scored this video 0; the transcript says otherwise.
    assert adjust(index, "Data independence", [0.0]) == [NAMED_FLOOR]
    # A video that already scores higher keeps its score.
    assert adjust(index, "Data independence", [0.9]) == [0.9]


def test_scattered_passing_mentions_are_not_enough():
    index = index_of(["Structures of Operating System", PASSING, OTHER, PASSING, OTHER, PASSING])
    assert adjust(index, "Virtual memory", [0.0]) == [0.0]


def test_single_word_topics_and_unmentioned_topics_are_left_alone():
    index = index_of(
        ["Paging", "paging divides memory into frames", "paging avoids external fragmentation"],
        ["Database Administrator", OTHER, OTHER],
    )
    # One word is too ambiguous to lift on its own.
    assert adjust(index, "Paging", [0.2, 0.0]) == [0.2, 0.0]
    # Not named anywhere: the meaning-based score stands.
    assert adjust(index, "Two-phase locking", [0.4, 0.3]) == [0.4, 0.3]


def test_the_title_passage_is_never_counted():
    # The title names the topic twice over; the transcript never does.
    index = index_of(["Data independence", OTHER], ["Data independence part 2", OTHER])
    assert adjust(index, "Data independence", [0.1, 0.1]) == [0.1, 0.1]
