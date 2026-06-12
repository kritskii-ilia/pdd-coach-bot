from __future__ import annotations

from pathlib import Path

from pdd_coach_bot.bot import BotServices, build_weekly_report_text, needs_onboarding
from pdd_coach_bot.coaching import derive_explanation_card, goal_touches
from pdd_coach_bot.content import ContentBundle
from pdd_coach_bot.models import Question, Topic
from pdd_coach_bot.storage import Storage, UserState


def test_goal_touches_scales_profile() -> None:
    intensity, touches = goal_touches("fast_track", 30)

    assert intensity == "high"
    assert touches >= 5


def test_derive_explanation_card_builds_standardized_hints() -> None:
    card = derive_explanation_card(
        "Кому уступить дорогу на перекрестке?",
        "На перекрестке действует правило помехи справа. Сначала смотри на приоритет, потом на траекторию.",
        ["priority_rules"],
    )

    assert card.short_why.startswith("На перекрестке действует")
    assert "Ловушка" in card.trap_hint
    assert "Как запомнить" in card.memory_hint
    assert "приоритет" in card.pattern_tags[0]


def test_needs_onboarding_detects_incomplete_profile() -> None:
    user = UserState(
        user_id=1,
        first_name="Test",
        timezone="Europe/Moscow",
        intensity="medium",
        touches_per_day=5,
        notifications_enabled=True,
        exam_date=None,
        goal=None,
        study_minutes=None,
        experience_level=None,
        onboarding_step="goal",
    )

    assert needs_onboarding(user) is True


def test_build_weekly_report_text_contains_summary(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "bot.sqlite3")
    storage.upsert_user(
        tg_user_id=42,
        first_name="Tester",
        timezone="Europe/Moscow",
        intensity="medium",
        touches_per_day=5,
        goal="steady",
        study_minutes=20,
        experience_level="partial",
        onboarding_step="done",
    )
    storage.record_attempt(42, "q1", "priority_rules", False)
    storage.record_attempt(42, "q1", "priority_rules", True)
    storage.record_completed_session(42, "exam", 18, 2, 20, ticket_id="Билет 1")
    services = BotServices(
        settings=None,  # type: ignore[arg-type]
        storage=storage,
        content=ContentBundle(
            topics={
                "priority_rules": Topic(
                    id="priority_rules",
                    title="Приоритет",
                    short_title="Приоритет",
                    stage="practice",
                    order=1,
                    summary="Приоритет проезда",
                    source_refs=["ПДД РФ"],
                )
            },
            lessons={},
            questions={
                "q1": Question(
                    id="q1",
                    topic_ids=["priority_rules"],
                    prompt="Кому уступить дорогу?",
                    options=["Легковому", "Никому"],
                    correct_index=0,
                    explanation="На перекрестке действует правило помехи справа.",
                    source="test",
                )
            },
            ticket_map={"Билет 1": ["q1"]},
            study_plan=[],
        ),
    )

    text = build_weekly_report_text(services, 42, "Europe/Moscow")

    assert "Недельный отчёт" in text
    assert "Точность" in text
    assert "Самый рискованный блок" in text
