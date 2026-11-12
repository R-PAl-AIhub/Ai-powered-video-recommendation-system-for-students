"""A past question that no video answers directly is still answered where its
topic is taught (the path's own pick), and stays unanswered when the topic is a
gap. See ``link_questions`` in ``app/services/questions.py``."""

from __future__ import annotations

from sqlalchemy import delete, select

from app.models import Project, Question, Recommendation
from app.services.questions import link_questions


def _relink_without_direct_answers(db, project_id: int) -> tuple[list[Question], dict]:
    """Re-link the questions with a bar no direct search can clear, so only the
    fallback can supply answers. Nothing is committed."""
    project = db.get(Project, project_id)
    project.relevance_threshold = 2.0
    count = link_questions(db, project)
    questions = list(db.scalars(select(Question).where(Question.project_id == project_id)))
    assert count == len(questions) > 0
    picks = {
        pick.topic_id: pick
        for pick in db.scalars(
            select(Recommendation).where(
                Recommendation.project_id == project_id, Recommendation.rank == 0
            )
        )
    }
    return questions, picks


def test_question_without_direct_answer_points_to_where_its_topic_is_taught(client, course, db):
    questions, picks = _relink_without_direct_answers(db, course)
    taught = [q for q in questions if q.topic_id in picks]
    assert taught, "the labelled course has exam questions on taught topics"
    for question in taught:
        pick = picks[question.topic_id]
        assert question.video_id == pick.video_id
        assert question.start_s == pick.start_s and question.end_s == pick.end_s
        assert question.snippet == pick.snippet
        assert question.relevance == round(pick.relevance, 4)


def test_question_on_an_untaught_topic_stays_unanswered(client, course, db):
    # Turn one examined topic into a gap: no video is recommended for it.
    examined = db.scalar(
        select(Question.topic_id).where(Question.project_id == course, Question.topic_id.is_not(None))
    )
    assert examined is not None
    db.execute(delete(Recommendation).where(Recommendation.topic_id == examined))
    questions, picks = _relink_without_direct_answers(db, course)
    untaught = [q for q in questions if q.topic_id not in picks]
    assert any(q.topic_id == examined for q in untaught)
    for question in untaught:
        assert question.video_id is None
        assert question.relevance == 0.0 and question.snippet == ""


def test_direct_answer_is_kept_over_the_fallback(client, course, db):
    """With the normal bar, a question the videos answer keeps its own answer."""
    before = {
        q.text: (q.video_id, q.start_s)
        for q in db.scalars(select(Question).where(Question.project_id == course))
        if q.video_id is not None
    }
    assert before
    link_questions(db, db.get(Project, course))
    after = {
        q.text: (q.video_id, q.start_s)
        for q in db.scalars(select(Question).where(Question.project_id == course))
    }
    for text, answer in before.items():
        assert after[text] == answer
