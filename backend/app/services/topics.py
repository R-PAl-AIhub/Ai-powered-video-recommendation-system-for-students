"""Extract an ordered list of topics from course documents.

The syllabus is the primary source: its unit headings and the comma/bullet
separated items under them become topics, in the order the syllabus gives them.
When there is no usable syllabus, headings or key phrases from the notes (or exam
papers) are used instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_TOPIC_WORDS = 16
MAX_TOPIC_CHARS = 140


@dataclass(frozen=True)
class ExtractedTopic:
    unit: str
    name: str


_ROMAN = r"[ivxlcdm]{1,6}"
_UNIT_HEADING = re.compile(
    rf"^\s*(unit|module|chapter|section|part|week|block)\s*[-–—:.#]?\s*(\d{{1,2}}|{_ROMAN})\b"
    r"\s*[-–—:.)\]]*\s*(.*)$",
    re.IGNORECASE,
)
_NUMBERED = re.compile(r"^\s*(\d{1,2})\s*[.)]\s+(\S.*)$")
_BULLET = re.compile(
    r"^\s*(?:[•·●▪■◦‣*○➢➤✓»-]|\(?[a-z]\)|\(?\d{1,2}[.)]|\d{1,2}\.\d{1,2}\.?)\s+", re.IGNORECASE
)
_STOP_SECTION = re.compile(
    r"^\s*(?:\d{1,2}\s*[.)]\s*)?(text\s*-?\s*books?|reference(s|\s+books?)?|suggested\s+read\w*|"
    r"recommended\s+\w+|books?\s+recommended|course\s+outcomes?|learning\s+outcomes?|"
    r"course\s+objectives?|objectives?|pre-?requisites?|evaluation(\s+scheme)?|assessment|"
    r"grading|bibliography|list\s+of\s+(experiments|practicals)|practicals?|laborator\w+|"
    r"lab\s+\w+|e-?resources?|web\s+(links|resources))\b\s*(.*)$",
    re.IGNORECASE,
)
_ADMIN = re.compile(
    r"\b(credits?|marks?|semester|l\s*-\s*t\s*-\s*p|course\s+code|subject\s+code|"
    r"paper\s+code|university|department|contact\s+hours|total\s+hours|syllabus|curriculum|"
    r"internal\s+assessment|end\s+sem\w*|time\s*:|max(imum)?\.?\s+marks|page\s+\d+)\b",
    re.IGNORECASE,
)
_HOURS = re.compile(
    r"[\[(]?\s*\d{1,3}\s*(hrs?|hours?|lectures?|periods?|classes|l|h)\.?\s*[\])]?\s*$",
    re.IGNORECASE,
)
_CODES = re.compile(r"[\[(]\s*(co|po|pso|k|bl|l)\s*-?\d[^\])]*[\])]", re.IGNORECASE)
_LEAD_NUMBERING = re.compile(
    rf"^\s*(?:\(?\d{{1,2}}(?:\.\d{{1,2}})*[.)]?|\(?[a-z][.)]|\(?{_ROMAN}[.)]|[•·●▪■◦‣*○➢➤✓»-])\s+",
    re.IGNORECASE,
)
_LEAD_FILLER = re.compile(
    r"^(e\.g\.|i\.e\.|viz\.|such as|like|including|and|or|&)[,:]?\s+", re.IGNORECASE
)
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "viz.", "fig.", "no.", "w.r.t.")
_CONTINUATION_WORDS = {"and", "of", "or", "the", "in", "for", "to", "with", "a", "an", "on"}
_GENERIC = {
    "definition", "definitions", "introduction", "overview", "concept", "concepts", "basics",
    "types", "examples", "applications", "properties", "advantages", "disadvantages",
    "characteristics", "features", "need", "importance", "classification", "fundamentals",
    "principles", "terminology", "preliminaries", "review", "motivation", "scope", "history",
    "benefits", "limitations", "operations", "representation", "implementation", "analysis",
    "comparison", "structure", "components", "functions", "goals", "issues", "problems",
    "solutions", "methods", "techniques", "algorithms", "models", "states", "uses", "merits",
    "demerits", "basic", "various", "different", "general", "its", "their", "and", "of", "&",
}  # fmt: skip


def _split_top_level(text: str, separators: str, *, sentences: bool) -> list[str]:
    """Split on separator characters (and optionally sentence ends) outside brackets."""
    protected = text
    for abbr in _ABBREVIATIONS:
        protected = re.sub(re.escape(abbr), abbr.replace(".", "․"), protected, flags=re.I)
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    length = len(protected)
    for i, char in enumerate(protected):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        split = depth == 0 and char in separators
        if not split and sentences and depth == 0 and char == ".":
            following = protected[i + 1 : i + 3]
            split = i == length - 1 or (following[:1] == " " and following[1:2].isupper())
        if split:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [p.replace("․", ".").strip() for p in parts if p.strip()]


def _split_head(item: str) -> tuple[str | None, str]:
    """"CPU scheduling: FCFS" or "Graphs - BFS" -> ("CPU scheduling", "FCFS")."""
    depth = 0
    for i, char in enumerate(item):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0 and char == ":":
            return item[:i].strip(), item[i + 1 :].strip()
    match = re.search(r"\s[-–—]\s|[–—]", item)
    if match and len(item[: match.start()].split()) <= 6:
        return item[: match.start()].strip(), item[match.end() :].strip()
    return None, item


def _is_generic(name: str) -> bool:
    words = re.findall(r"[a-z&]+", name.lower())
    return bool(words) and all(w in _GENERIC for w in words)


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{4,}", text.lower())}


def clean_topic(raw: str) -> str | None:
    """Normalise one candidate topic; return None if it is not a real topic."""
    text = _CODES.sub(" ", raw.strip())
    for _ in range(2):
        text = _LEAD_NUMBERING.sub("", text)
    text = _HOURS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" \t.:;,-–—•·|/\\")
    text = _LEAD_FILLER.sub("", text).strip()
    if text.count("(") != text.count(")"):
        text = re.sub(r"\s+", " ", text.replace("(", " ").replace(")", " ")).strip()
    is_acronym = len(text) == 2 and text.isalpha() and text.isupper()  # e.g. "RR"
    if (len(text) < 3 and not is_acronym) or len(text) > MAX_TOPIC_CHARS:
        return None
    words = text.split()
    if len(words) > MAX_TOPIC_WORDS or not re.search(r"[A-Za-z]{2,}", text):
        return None
    if _ADMIN.search(text) and len(words) <= 8:
        return None
    if text.isupper() and len(text) > 5:
        text = text.title()
    return text[0].upper() + text[1:]


def _qualify(child: str, head: str | None, unit_title: str) -> str | None:
    """Give short or generic items their context: "Definition" -> "Deadlocks: Definition"."""
    if _is_generic(child):
        context = head or unit_title
        return f"{context}: {child}" if context else None
    if head and len(child.split()) <= 3 and not (_stems(child) & _stems(head)):
        return f"{head}: {child}"
    return child


def _block_to_topics(block: str, unit_title: str) -> list[str]:
    topics: list[str] = []
    for group in _split_top_level(block, ";", sentences=True):
        head: str | None = None
        for item in _split_top_level(group, ",•·●▪|\n", sentences=False):
            found_head, rest = _split_head(item)
            children = [rest]
            if found_head is not None:
                head = clean_topic(found_head)
                if head and _is_generic(head):
                    head = None  # "Introduction: a, b" - the items stand on their own
                elif head:
                    topics.append(head)
                children = re.split(r"\s[-–—]\s|[–—]", rest) if rest else []
            for child in children:
                cleaned = clean_topic(child)
                if cleaned:
                    qualified = _qualify(cleaned, head, unit_title)
                    if qualified:
                        topics.append(qualified)
    return topics


def _wrap_width(lines: list[str]) -> int:
    lengths = sorted(len(ln.strip()) for ln in lines if ln.strip())
    return lengths[int(len(lengths) * 0.95) - 1] if len(lengths) >= 4 else 0


def _join_wrapped(lines: list[str], wrap_width: int) -> list[str]:
    """Re-join lines that were wrapped by the page layout; keep list items apart."""
    blocks: list[str] = []
    previous_wraps = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            previous_wraps = False
            continue
        if blocks and previous_wraps and not _BULLET.match(line):
            blocks[-1] = f"{blocks[-1]} {stripped}"
        else:
            blocks.append(stripped)
        last_word = stripped.split()[-1].lower()
        previous_wraps = not stripped.endswith(".") and (
            (wrap_width >= 50 and len(stripped) >= 0.72 * wrap_width)
            or stripped.endswith((",", "-", "–", ":", "(", "&", "/"))
            or last_word in _CONTINUATION_WORDS
        )
    return blocks


def _lines_to_topics(lines: list[str], unit_title: str, wrap_width: int) -> list[str]:
    topics: list[str] = []
    for block in _join_wrapped(lines, wrap_width):
        topics.extend(_block_to_topics(_LEAD_NUMBERING.sub("", block), unit_title))
    return topics


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _dedupe(topics: list[ExtractedTopic], limit: int) -> list[ExtractedTopic]:
    seen: set[str] = set()
    out: list[ExtractedTopic] = []
    for topic in topics:
        key = _key(topic.name)
        if key and key not in seen:
            seen.add(key)
            out.append(topic)
        if len(out) >= limit:
            break
    return out


def _is_stop_line(line: str) -> bool:
    """A heading such as "Text Books" or "Course Outcomes:" that starts a non-topic section."""
    match = _STOP_SECTION.match(line)
    if not match:
        return False
    rest = match.group(match.lastindex).strip()
    return not rest or rest[0] in ":-–—" or len(line.split()) <= 4


def _numbered_heading_title(line: str) -> str | None:
    """The title of a numbered line that looks like a heading, else None."""
    match = _NUMBERED.match(line)
    if not match:
        return None
    title = match.group(2).split(":")[0]
    return title if len(title.split()) <= 8 and "," not in title else None


def parse_syllabus(text: str, limit: int = 250) -> list[ExtractedTopic]:
    """Parse a syllabus into ordered topics grouped by unit."""
    lines = text.replace("\r", "").split("\n")
    wrap_width = _wrap_width(lines)
    has_units = sum(1 for line in lines if _UNIT_HEADING.match(line)) >= 2

    # Numbered lines are unit headings only when plain body lines follow them
    # ("1. Thermodynamics" / "Laws of thermodynamics, entropy, ..."). Otherwise a
    # numbered list is simply a list of topics.
    numbered_headings: set[int] = set()
    if not has_units:
        numbered = [i for i, line in enumerate(lines) if _NUMBERED.match(line)]
        for i in numbered:
            if _numbered_heading_title(lines[i]) is None:
                continue
            following = next((ln for ln in lines[i + 1 : i + 4] if ln.strip()), "")
            if following and not _NUMBERED.match(following) and not _is_stop_line(following):
                numbered_headings.add(i)
        if len(numbered_headings) < max(2, len(numbered) // 2):
            numbered_headings = set()

    sections: list[tuple[str, str, list[str]]] = []  # (unit name, unit title, body lines)
    loose: list[str] = []
    skipping = False
    for index, line in enumerate(lines):
        if not line.strip():
            (sections[-1][2] if sections else loose).append("")
            continue
        unit = _UNIT_HEADING.match(line) if has_units else None
        if unit or index in numbered_headings:
            skipping = False
            if unit:
                label = f"{unit.group(1).title()} {unit.group(2).upper()}"
                rest = unit.group(3).strip()
            else:
                label, rest = "", _NUMBERED.match(line).group(2).strip()
            title, body = rest, ""
            if ":" in rest and len(rest.split(":")[0].split()) <= 9:
                title, _, body = rest.partition(":")
            elif len(rest.split()) > 12:
                title, body = "", rest
            title = _HOURS.sub("", _CODES.sub(" ", title)).strip(" -–—:.")
            name = ": ".join(part for part in (label, title) if part)
            sections.append((name, title, [body.strip()] if body.strip() else []))
            continue
        if _is_stop_line(line):
            skipping = True
            continue
        if skipping and (sections or len(line.split()) > 12 or _NUMBERED.match(line)):
            continue
        skipping = False
        if sections:
            sections[-1][2].append(line)
        elif not _ADMIN.search(line):
            loose.append(line)

    topics: list[ExtractedTopic] = []
    if sections:
        for name, title, body in sections:
            unit_topics = _lines_to_topics(body, title, wrap_width)
            if not unit_topics:
                fallback = clean_topic(title or name)  # a bare heading is itself the topic
                unit_topics = [fallback] if fallback else []
            topics.extend(ExtractedTopic(unit=name, name=t) for t in unit_topics)
    else:
        topics.extend(ExtractedTopic(unit="", name=t) for t in _lines_to_topics(loose, "", wrap_width))
    return _dedupe(topics, limit)


# ------------------------------------------------------------ notes / exam papers

_STOPWORDS = frozenset(
    """a an the and or of in on at to for from by with without into over under between is are was
    were be been being it its this that these those as if then than so such not no can may will
    would should could we you they he she i our your their which what when where who how why do
    does did done has have had also each any all some more most other one two three first second
    using used use let us about above below there here very just only both either neither while
    during after before again further once same own too up down out off per via etc""".split()
)
_NOISE_WORDS = frozenset(
    """university college institute department semester credits marks hours code course outcomes
    books book edition publication publications press syllabus exam examination question paper
    answer time total page section group attempt""".split()
)

_QUESTION_START = re.compile(
    r"^\s*(?:q(?:uestion)?\.?\s*(?:no\.?)?\s*\d{1,2}\s*[.):-]?|\d{1,2}\s*[.)]|"
    r"\(?[a-h]\)|\(?(?:i{1,3}|iv|v|vi{0,3}|ix|x)\))\s+",
    re.IGNORECASE,
)
_MARKS_SUFFIX = re.compile(r"[\[(]\s*\d{1,3}\s*(marks?|m)?\s*[\])]\s*$", re.IGNORECASE)


def split_questions(text: str, limit: int = 600) -> list[str]:
    """Split an exam paper into individual questions."""
    questions: list[str] = []
    current: list[str] = []

    def flush() -> None:
        joined = re.sub(r"\s+", " ", " ".join(current)).strip()
        joined = _MARKS_SUFFIX.sub("", joined).strip()
        if len(joined.split()) >= 4 and not (_ADMIN.search(joined) and len(joined.split()) < 12):
            questions.append(joined[:600])
        current.clear()

    for line in text.split("\n"):
        if not line.strip():
            continue
        if _QUESTION_START.match(line):
            flush()
            body = line
            for _ in range(2):  # "1. (a) What is ..." carries two markers
                body = _QUESTION_START.sub("", body, count=1)
            current.append(body)
        elif current:
            current.append(line.strip())
    flush()

    if len(questions) < 3:  # no numbering detected: fall back to sentences
        sentences = re.split(r"(?<=[.?!])\s+", re.sub(r"\s+", " ", text))
        questions = [s.strip()[:600] for s in sentences if len(s.split()) >= 5]
    return questions[:limit]


def chunk_paragraphs(text: str, target_words: int = 110, limit: int = 1500) -> list[str]:
    """Group a long text into passages of roughly ``target_words`` words."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [ln.strip() for ln in text.split("\n") if ln.strip()]
    chunks: list[str] = []
    buffer: list[str] = []
    count = 0
    for paragraph in paragraphs:
        words = paragraph.split()
        while len(words) > target_words * 2:  # very long paragraph: hard split
            chunks.append(" ".join(words[:target_words]))
            words = words[target_words:]
        buffer.append(" ".join(words))
        count += len(words)
        if count >= target_words:
            chunks.append(" ".join(buffer))
            buffer, count = [], 0
    if buffer:
        chunks.append(" ".join(buffer))
    return [c for c in chunks if len(c.split()) >= 4][:limit]


def headings_from_notes(text: str, limit: int = 80) -> list[ExtractedTopic]:
    """Short title-like lines in lecture notes, in order of appearance."""
    topics: list[ExtractedTopic] = []
    for line in text.split("\n"):
        stripped = line.strip()
        words = stripped.split()
        if not 1 <= len(words) <= 9 or len(stripped) < 4:
            continue
        if stripped.endswith((".", ",", ";", "?")) or _ADMIN.search(stripped):
            continue
        body = _LEAD_NUMBERING.sub("", stripped).rstrip(":")
        alpha = [w for w in body.split() if w[:1].isalpha()]
        if not alpha:
            continue
        capitalised = sum(1 for w in alpha if w[:1].isupper())
        is_heading = (
            stripped.endswith(":")
            or body.isupper()
            or bool(_NUMBERED.match(stripped))
            or (capitalised >= max(1, round(len(alpha) * 0.6)) and len(alpha) >= 2)
        )
        if is_heading:
            cleaned = clean_topic(body)
            if cleaned and not _is_generic(cleaned) and cleaned.lower() not in _STOPWORDS:
                topics.append(ExtractedTopic(unit="", name=cleaned))
    return _dedupe(topics, limit)


def keyphrase_topics(text: str, limit: int = 25) -> list[ExtractedTopic]:
    """Frequent multi-word phrases, ordered by first appearance. Last-resort source
    of topics when a document has no headings to work from."""
    words = re.findall(r"[A-Za-z][A-Za-z'+#-]*", text.lower())
    counts: dict[tuple[str, ...], int] = {}
    first_seen: dict[tuple[str, ...], int] = {}
    for size in (3, 2):
        for i in range(len(words) - size + 1):
            gram = tuple(words[i : i + size])
            if gram[0] in _STOPWORDS or gram[-1] in _STOPWORDS:
                continue
            if any(len(w) < 3 or w in _NOISE_WORDS for w in gram):
                continue
            if sum(w in _STOPWORDS for w in gram) > 1:
                continue
            counts[gram] = counts.get(gram, 0) + 1
            first_seen.setdefault(gram, i)

    ranked = sorted(
        (g for g, c in counts.items() if c >= 2),
        key=lambda g: (-(counts[g] * (1.6 if len(g) == 3 else 1.0)), first_seen[g]),
    )
    chosen: list[tuple[str, ...]] = []
    for gram in ranked:
        joined = " ".join(gram)
        if any(joined in " ".join(c) or " ".join(c) in joined for c in chosen):
            continue
        chosen.append(gram)
        if len(chosen) >= limit:
            break
    chosen.sort(key=lambda g: first_seen[g])
    return [ExtractedTopic(unit="", name=" ".join(g).capitalize()) for g in chosen]


def extract_topics(
    syllabus_texts: list[str],
    notes_texts: list[str],
    exam_texts: list[str],
    limit: int = 250,
) -> tuple[list[ExtractedTopic], str]:
    """Pick the best available source. Returns (topics, source name)."""
    topics: list[ExtractedTopic] = []
    for text in syllabus_texts:
        topics.extend(parse_syllabus(text, limit))
    topics = _dedupe(topics, limit)
    if len(topics) >= 3:
        return topics, "syllabus"

    notes = "\n\n".join(notes_texts)
    if notes.strip():
        from_notes = headings_from_notes(notes)
        if len(from_notes) < 4:
            from_notes = keyphrase_topics(notes)
        if len(from_notes) >= 3:
            return _dedupe(topics + from_notes, limit), "notes"

    exams = "\n\n".join(exam_texts)
    if exams.strip():
        from_exams = keyphrase_topics(exams)
        if len(from_exams) >= 3:
            return _dedupe(topics + from_exams, limit), "exam"
    return topics, "syllabus"
