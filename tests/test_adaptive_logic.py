from pdd_coach_bot.bot import render_ticket_map
from pdd_coach_bot.logic import QuestionSnapshot, question_priority
from pdd_coach_bot.content import load_content
from pathlib import Path


def test_question_priority_rewards_due_and_weak_question() -> None:
    _bundle = load_content(Path("/home/user/pdd-coach-bot/content"), Path("/home/user/pdd-coach-bot/assets"))
    question_rows = {
        "050bbd8d2ba901e0b895141adadf7a60": QuestionSnapshot(
            question_id="050bbd8d2ba901e0b895141adadf7a60",
            score=-2.0,
            correct_count=0,
            wrong_count=2,
            streak=0,
            next_review_at="2026-04-01T00:00:00+00:00",
        )
    }

    assert question_priority("050bbd8d2ba901e0b895141adadf7a60", question_rows) > question_priority("unknown", {})


def test_render_ticket_map_marks_priority_ticket() -> None:
    text = render_ticket_map(
        {"Билет 1": (20, 20), "Билет 2": (16, 20)},
        ["Билет 1", "Билет 2", "Билет 3"],
        "Билет 2",
    )

    assert "⭐🟥" in text
    assert "🟩" in text
    assert "⬜" in text
