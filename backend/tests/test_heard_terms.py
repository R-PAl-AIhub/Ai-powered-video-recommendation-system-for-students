"""A term of the lecture's title that speech recognition wrote as a sound-alike
word is put back (``restore_title_terms`` in ``app/services/asr.py``). Found on
a real lecture in Hindi: "closure" was heard as "closer" 28 times."""

from __future__ import annotations

from app.services.asr import restore_title_terms

TITLE = "Lec-26: Finding Closure of Functional dependency in DBMS. Database Management Systems"
HEARD = [
    "Closer method is very important in DBMS because it finds all the candidate keys.",
    "So let us start with the closer of A. A can determine B.",
    "Many times we check their closer by combining two attributes.",
]


def test_a_title_term_heard_as_a_sound_alike_is_restored():
    fixed = restore_title_terms(HEARD, TITLE)
    assert fixed[0].startswith("Closure method")
    assert "the closure of A" in fixed[1]
    assert "closer" not in " ".join(fixed).lower()


def test_a_term_that_is_heard_correctly_is_left_alone():
    heard = [*HEARD, "This is called the closure of the set."]
    assert restore_title_terms(heard, TITLE) == heard


def test_a_rare_sound_alike_is_not_touched():
    heard = ["We move closer to the answer.", "The functional dependency is given."]
    assert restore_title_terms(heard, TITLE) == heard


def test_short_title_words_are_never_swapped():
    # "form" and "from" sound alike here, and "from" is said often.
    heard = ["Take it from here.", "Remove it from the table.", "Read from the left."]
    assert restore_title_terms(heard, "Second Normal Form") == heard
