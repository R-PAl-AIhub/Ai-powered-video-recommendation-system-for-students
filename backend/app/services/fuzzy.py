"""Fuzzy ranking of candidate videos.

Following the idea in Rishad et al. of combining content relevance with video
metadata: a small zero-order Sugeno fuzzy inference system turns length,
popularity and engagement into one quality value, and that quality then
discounts the content relevance. Relevance dominates; quality only decides
between videos that are already relevant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    """Membership that rises a→b, is 1 on b..c, and falls c→d."""
    if x <= a or x >= d:
        # Open shoulders: a == b means "everything at or below b", c == d the mirror.
        if x <= a and a == b:
            return 1.0
        if x >= d and c == d:
            return 1.0
        return 0.0
    if x < b:
        return (x - a) / (b - a)
    if x <= c:
        return 1.0
    return (d - x) / (d - c)


def triangle(x: float, a: float, b: float, c: float) -> float:
    return trapezoid(x, a, b, b, c)


def _weighted(rules: list[tuple[float, float]], default: float) -> float:
    """Sugeno defuzzification: firing-strength-weighted mean of rule outputs."""
    total = sum(strength for strength, _ in rules)
    if total <= 1e-9:
        return default
    return sum(strength * output for strength, output in rules) / total


@dataclass(frozen=True)
class QualityInputs:
    duration_s: int = 0
    view_count: int | None = None
    like_count: int | None = None
    has_transcript: bool = True
    age_years: float | None = None  # time since upload
    comment_count: int | None = None
    comment_sentiment: float | None = None  # -1 (negative) .. 1 (positive)


def quality_score(q: QualityInputs) -> float:
    """Metadata quality in 0..1. Unknown signals are skipped rather than penalised."""
    rules: list[tuple[float, float]] = []

    minutes = q.duration_s / 60 if q.duration_s else None
    if minutes is not None:
        too_short = trapezoid(minutes, 0, 0, 2, 6)
        good = trapezoid(minutes, 3, 8, 35, 60)
        long_ = trapezoid(minutes, 40, 90, 1e9, 1e9)
    else:
        too_short = good = long_ = 0.0

    if q.view_count is not None:
        magnitude = math.log10(max(q.view_count, 1))
        pop_low = trapezoid(magnitude, 0, 0, 2.5, 3.5)
        pop_mid = triangle(magnitude, 3.0, 4.0, 5.0)
        pop_high = trapezoid(magnitude, 4.5, 5.5, 99, 99)
    else:
        pop_low = pop_mid = pop_high = 0.0

    if minutes is not None:
        rules.append((too_short, 0.2))  # too short to explain a topic properly
        if q.view_count is not None:
            rules += [
                (min(good, pop_high), 0.95),
                (min(good, pop_mid), 0.75),
                (min(good, pop_low), 0.55),
                (min(long_, pop_high), 0.70),
                (min(long_, max(pop_mid, pop_low)), 0.50),
            ]
        else:
            rules += [(good, 0.7), (long_, 0.55)]
    elif q.view_count is not None:
        rules += [(pop_high, 0.85), (pop_mid, 0.65), (pop_low, 0.45)]

    if q.like_count is not None and q.view_count:
        like_pct = 100.0 * q.like_count / q.view_count
        rules += [
            (trapezoid(like_pct, 0, 0, 0.4, 1.2), 0.35),
            (triangle(like_pct, 0.8, 2.0, 3.5), 0.65),
            (trapezoid(like_pct, 2.5, 4.5, 100, 100), 0.90),
        ]

    if q.age_years is not None:
        # Teaching does not go stale quickly; recency is a gentle nudge only.
        rules += [
            (trapezoid(q.age_years, 0, 0, 3, 6), 0.72),
            (trapezoid(q.age_years, 5, 12, 1e9, 1e9), 0.55),
        ]

    if q.comment_count is not None and q.view_count:
        per_thousand = 1000.0 * q.comment_count / q.view_count
        rules += [
            (trapezoid(per_thousand, 0, 0, 0.2, 0.8), 0.45),  # few people discuss it
            (triangle(per_thousand, 0.4, 2.0, 6.0), 0.70),
            (trapezoid(per_thousand, 3.0, 8.0, 1e9, 1e9), 0.80),  # lively discussion
        ]

    if q.comment_sentiment is not None:
        rules += [
            (trapezoid(q.comment_sentiment, -1, -1, -0.3, 0.05), 0.25),  # viewers complain
            (triangle(q.comment_sentiment, -0.1, 0.15, 0.4), 0.60),
            (trapezoid(q.comment_sentiment, 0.2, 0.5, 1, 1), 0.88),  # viewers say it helped
        ]

    score = _weighted(rules, default=0.5)
    if not q.has_transcript:
        score *= 0.9  # matched on title/description only: slightly less certain
    return max(0.0, min(1.0, score))


QUALITY_WEIGHT = 0.25  # the most that poor metadata can discount a relevant video


def final_score(relevance: float, quality: float) -> float:
    """The ranking score (0..1): relevance, discounted by up to QUALITY_WEIGHT for
    poor metadata quality.

    Relevance passes through linearly on purpose. An earlier rule-based
    combination flattened clearly different relevances onto the same plateau, and
    the sequencing bonuses then picked the worse video for the sake of continuity.
    """
    relevance = max(0.0, min(1.0, relevance))
    quality = max(0.0, min(1.0, quality))
    return relevance * (1.0 - QUALITY_WEIGHT * (1.0 - quality))


_POSITIVE = frozenset(
    ["thank", "thanks", "thankyou", "helpful", "helped", "clear", "clearly", "best", "great", "awesome", "amazing", "excellent", "understood", "understand", "easy", "easily", "perfect", "love", "loved", "nice", "good", "brilliant", "superb", "wonderful", "saved", "lifesaver", "crisp", "concise", "simple", "simply", "finally", "useful", "informative"]
)
_NEGATIVE = frozenset(
    ["confusing", "confused", "wrong", "bad", "useless", "boring", "mistake", "mistakes", "error", "errors", "worst", "unclear", "incorrect", "misleading", "waste", "hard", "difficult", "poor", "terrible", "slow", "fast", "noisy", "lagging"]
)


def comment_sentiment(comments: list[str]) -> float | None:
    """Average lexicon sentiment of viewer comments, -1..1; None with no signal.

    A small hand-made lexicon of how students praise or criticise a lecture
    ("finally understood", "confusing"). Enough to separate well-received videos
    from ones viewers complain about, which is all the ranking needs.
    """
    import re

    scores = []
    for comment in comments:
        words = re.findall(r"[a-z]+", comment.lower())
        positive = sum(w in _POSITIVE for w in words)
        negative = sum(w in _NEGATIVE for w in words)
        if positive + negative:
            scores.append((positive - negative) / (positive + negative))
    return round(sum(scores) / len(scores), 3) if scores else None
