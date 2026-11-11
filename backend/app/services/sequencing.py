"""Order the chosen videos into a smooth learning path.

Topics are visited in syllabus order. For each topic there are a few candidate
videos; picking the best-scoring one independently makes the path jump between
playlists and backwards within a playlist. Instead the path is solved as a whole
with dynamic programming (Viterbi): each choice earns its own score plus a bonus
for continuing the same video, the same playlist (moving forwards), or the same
channel as the previous choice.
"""

from __future__ import annotations

from dataclasses import dataclass

SAME_VIDEO = 0.09  # equal to moving forward in a playlist, so relevance breaks the tie
SAME_PLAYLIST = 0.06
FORWARD_IN_PLAYLIST = 0.03
BACKWARD_IN_PLAYLIST = -0.02
SAME_CHANNEL = 0.03
PLAYLIST_PRIORITY = 0.015  # per rank: earlier playlists in the student's list are preferred
CHAIN = 0.03  # most a content hand-over between two different videos can add
CHAIN_FROM, CHAIN_FULL = 0.60, 0.85  # cosine range over which the bonus grows
PINNED = 10.0  # a video the student confirmed always wins its topic


@dataclass
class Candidate:
    video_id: int
    score: float
    playlist_id: int | None = None
    playlist_rank: int = 0  # 0 = the student's first playlist
    playlist_position: int = 0
    channel: str = ""
    pinned: bool = False
    # Embedding of the stretch that teaches the topic; used to chain videos whose
    # content leads into each other.
    vector: object | None = None


def chain_bonus(previous: Candidate, current: Candidate) -> float:
    """Bonus when the next video's material continues the previous one's (by meaning)."""
    if previous.vector is None or current.vector is None:
        return 0.0
    similarity = float(previous.vector @ current.vector)
    return CHAIN * min(1.0, max(0.0, (similarity - CHAIN_FROM) / (CHAIN_FULL - CHAIN_FROM)))


def transition(previous: Candidate, current: Candidate) -> float:
    if previous.video_id == current.video_id:
        return SAME_VIDEO
    return _continuity(previous, current) + chain_bonus(previous, current)


def _continuity(previous: Candidate, current: Candidate) -> float:
    if previous.playlist_id is not None and previous.playlist_id == current.playlist_id:
        step = (
            FORWARD_IN_PLAYLIST
            if current.playlist_position > previous.playlist_position
            else BACKWARD_IN_PLAYLIST
        )
        return SAME_PLAYLIST + step
    if previous.channel and previous.channel == current.channel:
        return SAME_CHANNEL
    return 0.0


def _emission(candidate: Candidate) -> float:
    value = candidate.score - PLAYLIST_PRIORITY * min(candidate.playlist_rank, 4)
    return value + (PINNED if candidate.pinned else 0.0)


def choose_path(candidates: list[list[Candidate]]) -> list[int | None]:
    """Pick one candidate index per topic (None where a topic has no candidates).

    ``candidates[t]`` lists the options for the t-th topic in path order. Topics
    without candidates are skipped; continuity carries across the gap.
    """
    chosen: list[int | None] = [None] * len(candidates)
    steps = [t for t, options in enumerate(candidates) if options]
    if not steps:
        return chosen

    best: list[list[float]] = []
    back: list[list[int]] = []
    for step_index, t in enumerate(steps):
        options = candidates[t]
        if step_index == 0:
            best.append([_emission(c) for c in options])
            back.append([-1] * len(options))
            continue
        previous_options = candidates[steps[step_index - 1]]
        previous_best = best[-1]
        row: list[float] = []
        pointers: list[int] = []
        for option in options:
            value, pointer = max(
                (previous_best[j] + transition(prev, option), j)
                for j, prev in enumerate(previous_options)
            )
            row.append(value + _emission(option))
            pointers.append(pointer)
        best.append(row)
        back.append(pointers)

    index = max(range(len(best[-1])), key=lambda i: best[-1][i])
    for step_index in range(len(steps) - 1, -1, -1):
        chosen[steps[step_index]] = index
        index = back[step_index][index]
    return chosen
