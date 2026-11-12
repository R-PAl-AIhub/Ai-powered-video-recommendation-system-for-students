"""A transcript the student copied from YouTube ("Show transcript") and pasted in.

This is the source of last resort when YouTube refuses caption requests and the
video cannot be listened to either: the text on the student's own screen is
always available. The copied text looks like

    0:00
    0 seconds
    Hello friends, today we are going to discuss normalization.
    0:04
    4 seconds
    ...

with or without the spoken-time lines, sometimes with the time and the words on
one line, sometimes with no times at all.
"""

from __future__ import annotations

import re

from .youtube import Transcript, TranscriptSegment

_TIME = re.compile(r"^\[?((?:\d{1,2}:)?\d{1,2}:\d{2})\]?(?:\s+[-–]?\s*(.*))?$")
# The screen-reader copy of a timestamp: "4 seconds", "1 minute, 2 seconds".
_SPOKEN_TIME = re.compile(
    r"^\d+\s+(?:hours?|minutes?|seconds?)(?:,?\s+\d+\s+(?:hours?|minutes?|seconds?))*$", re.I
)
_FURNITURE = {"transcript", "search transcript", "search in video", "show transcript"}
_SENTENCE = re.compile(r"(?<=[.!?।])\s+")
WORDS_PER_SECOND = 2.5  # ordinary lecture speech, for text pasted without times

# Unicode blocks of the scripts lecture captions are commonly written in.
_SCRIPTS = (
    ("hi", 0x0900, 0x097F),  # Devanagari
    ("bn", 0x0980, 0x09FF),
    ("pa", 0x0A00, 0x0A7F),
    ("gu", 0x0A80, 0x0AFF),
    ("ta", 0x0B80, 0x0BFF),
    ("te", 0x0C00, 0x0C7F),
    ("kn", 0x0C80, 0x0CFF),
    ("ml", 0x0D00, 0x0D7F),
    ("ar", 0x0600, 0x06FF),
    ("ru", 0x0400, 0x04FF),
    ("zh", 0x4E00, 0x9FFF),
    ("ja", 0x3040, 0x30FF),
    ("ko", 0xAC00, 0xD7AF),
)


def _seconds(stamp: str) -> float:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return float(total)


def guess_language(text: str) -> str:
    """"en" for text in Latin letters, a language code for the commonest other
    scripts, "und" (undetermined) for anything else that is not Latin.

    Latin-script text in another language (Spanish, romanised Hindi) is reported
    as "en": only the script can be told apart reliably without a model, and the
    English embedding model degrades gently on such text rather than failing.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "en"
    latin = sum(1 for ch in letters if ch < "ɐ")
    if latin >= 0.6 * len(letters):
        return "en"
    counts = {
        code: sum(1 for ch in letters if low <= ord(ch) <= high) for code, low, high in _SCRIPTS
    }
    code, count = max(counts.items(), key=lambda item: item[1])
    return code if count >= 0.3 * len(letters) else "und"


def parse_pasted_transcript(text: str, duration_s: float = 0) -> Transcript | None:
    """Turn pasted transcript text into timed segments, or None if it has no words."""
    timed: list[tuple[float, list[str]]] = []
    loose: list[str] = []  # words seen before any timestamp, or text without times
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line or line.lower() in _FURNITURE or _SPOKEN_TIME.match(line):
            continue
        stamp = _TIME.match(line)
        if stamp:
            timed.append((_seconds(stamp.group(1)), [stamp.group(2)] if stamp.group(2) else []))
        elif timed:
            timed[-1][1].append(line)
        else:
            loose.append(line)

    segments: list[TranscriptSegment] = []
    spoken = [(start, " ".join(words).strip()) for start, words in timed]
    spoken = [(start, words) for start, words in spoken if words]
    # A real transcript's times only go forward; anything else is prose that
    # happens to contain a time ("at 10:30 we met"), so treat it as plain text.
    in_order = all(a[0] <= b[0] for a, b in zip(spoken, spoken[1:], strict=False))
    if len(spoken) >= 2 and in_order:
        for number, (start, words) in enumerate(spoken):
            if number + 1 < len(spoken):
                length = spoken[number + 1][0] - start
            else:
                length = max(duration_s - start, 0.0) or len(words.split()) / WORDS_PER_SECOND
            segments.append(TranscriptSegment(start=start, duration=max(length, 1.0), text=words))
    else:
        # No usable times: spread the sentences over the video at speaking pace,
        # or over its real length when that is known.
        body = " ".join(loose + [words for _, words in spoken])
        sentences = [s.strip() for s in _SENTENCE.split(body) if s.strip()]
        total_words = sum(len(s.split()) for s in sentences)
        if not total_words:
            return None
        length = duration_s or total_words / WORDS_PER_SECOND
        start = 0.0
        for sentence in sentences:
            share = length * len(sentence.split()) / total_words
            segments.append(TranscriptSegment(start=start, duration=max(share, 0.5), text=sentence))
            start += share
    if not segments:
        return None
    language = guess_language(" ".join(segment.text for segment in segments[:200]))
    return Transcript(language=language, is_generated=False, segments=segments)
