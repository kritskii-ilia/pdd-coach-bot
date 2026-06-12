from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime

from .content import ContentBundle


@dataclass(slots=True)
class TopicSnapshot:
    topic_id: str
    score: float
    status: str
    correct_count: int
    wrong_count: int
    next_review_at: str | None


@dataclass(slots=True)
class QuestionSnapshot:
    question_id: str
    score: float
    correct_count: int
    wrong_count: int
    streak: int
    next_review_at: str | None


def lesson_status_label(status: str) -> str:
    return {
        "new": "не начато",
        "reading": "изучается",
        "weak": "усвоено слабо",
        "solid": "усвоено нормально",
        "strong": "усвоено хорошо",
    }.get(status, status)


def normalize_topic_rows(rows: dict[str, object]) -> dict[str, TopicSnapshot]:
    normalized: dict[str, TopicSnapshot] = {}
    for topic_id, row in rows.items():
        normalized[topic_id] = TopicSnapshot(
            topic_id=topic_id,
            score=float(row["score"]),
            status=str(row["status"]),
            correct_count=int(row["correct_count"]),
            wrong_count=int(row["wrong_count"]),
            next_review_at=row["next_review_at"],
        )
    return normalized


def normalize_question_rows(rows: dict[str, object]) -> dict[str, QuestionSnapshot]:
    normalized: dict[str, QuestionSnapshot] = {}
    for question_id, row in rows.items():
        normalized[question_id] = QuestionSnapshot(
            question_id=question_id,
            score=float(row["score"]),
            correct_count=int(row["correct_count"]),
            wrong_count=int(row["wrong_count"]),
            streak=int(row["streak"]),
            next_review_at=row["next_review_at"],
        )
    return normalized


def choose_topic_questions(
    bundle: ContentBundle,
    topic_id: str,
    limit: int,
    question_rows: dict[str, QuestionSnapshot] | None = None,
) -> list[str]:
    scored: list[tuple[float, str]] = []
    for question in bundle.questions.values():
        if topic_id not in question.topic_ids:
            continue
        relevance = topic_question_score(topic_id, question.prompt)
        if relevance <= 0:
            continue
        priority = question_priority(question.id, question_rows) + (relevance * 4.0)
        scored.append((priority, question.id))
    random.shuffle(scored)
    scored.sort(key=lambda item: item[0], reverse=True)
    return unique_ordered_ids([question_id for _, question_id in scored], limit)


def choose_mixed_questions(
    bundle: ContentBundle,
    topic_ids: list[str],
    limit: int,
    question_rows: dict[str, QuestionSnapshot] | None = None,
) -> list[str]:
    scored: list[tuple[float, str]] = []
    focus = set(topic_ids)
    for question in bundle.questions.values():
        overlap = len(focus & set(question.topic_ids))
        if not overlap:
            continue
        priority = question_priority(question.id, question_rows) + (overlap * 3.0)
        scored.append((priority, question.id))
    random.shuffle(scored)
    scored.sort(key=lambda item: item[0], reverse=True)
    mixed = interleave_by_topic(bundle, [question_id for _, question_id in scored], limit)
    return unique_ordered_ids(mixed, limit)


def choose_exam_questions(
    bundle: ContentBundle,
    limit: int,
    question_rows: dict[str, QuestionSnapshot] | None = None,
) -> list[str]:
    ticket_questions = [question for question in bundle.questions.values() if question.exam_ticket]
    scored: list[tuple[float, str]] = []
    for question in ticket_questions:
        priority = question_priority(question.id, question_rows) + (0.5 * len(question.topic_ids))
        scored.append((priority, question.id))
    random.shuffle(scored)
    scored.sort(key=lambda item: item[0], reverse=True)
    return unique_ordered_ids(interleave_by_topic(bundle, [question_id for _, question_id in scored], limit), limit)


def topic_question_score(topic_id: str, prompt: str) -> int:
    text = prompt.lower().replace("ё", "е")
    if topic_id == "controller_signals":
        if any(token in text for token in ["регулировщик", "рука поднята", "руки в стороны", "правая рука", "жест", "сигнал регулировщика"]):
            return 5
        if "светофор" in text:
            return 0
        return 1
    if topic_id == "traffic_lights":
        if any(token in text for token in ["светофор", "дополнительн", "стрелк", "зелен", "желт", "красн", "реверсив"]):
            return 5
        if "регулировщик" in text:
            return 0
        return 1
    if topic_id == "priority_rules":
        if any(token in text for token in ["главн", "уступить", "перекрест", "помех", "налево", "разворот", "встречн"]):
            return 5
        return 1
    if topic_id == "road_markings":
        if any(token in text for token in ["разметк", "сплошн", "прерывист", "стоп-лини", "лини"]):
            return 5
        return 1
    if topic_id == "stopping_parking":
        if any(token in text for token in ["останов", "стоянк", "5 м", "парков", "пешеходн переход"]):
            return 5
        return 1
    if topic_id == "pedestrians":
        if any(token in text for token in ["пешеход", "маршрутн", "автобус", "остановк", "переход"]):
            return 5
        return 1
    if topic_id == "railroad":
        if any(token in text for token in ["железнодорож", "переезд", "шлагбаум", "рельс", "поезд"]):
            return 5
        return 1
    if topic_id == "first_aid":
        if any(token in text for token in ["кровотеч", "пострадавш", "дыхани", "сердеч", "первая помощь"]):
            return 5
        return 1
    return 1


def choose_due_topic_ids(bundle: ContentBundle, topic_rows: dict[str, TopicSnapshot], limit: int) -> list[str]:
    now = datetime.now(UTC)
    due: list[tuple[float, str]] = []
    for topic_id in bundle.topics:
        snapshot = topic_rows.get(topic_id)
        if snapshot is None:
            due.append((-10.0, topic_id))
            continue
        if snapshot.next_review_at:
            try:
                parsed = datetime.fromisoformat(snapshot.next_review_at)
            except ValueError:
                parsed = now
            if parsed <= now:
                due.append((snapshot.score, topic_id))
        elif snapshot.status in {"weak", "learning"}:
            due.append((snapshot.score, topic_id))
    due.sort(key=lambda item: item[0])
    return [topic_id for _, topic_id in due[:limit]]


def question_priority(question_id: str, question_rows: dict[str, QuestionSnapshot] | None) -> float:
    if not question_rows or question_id not in question_rows:
        return 12.0
    row = question_rows[question_id]
    base = max(0.0, 6.0 - row.score)
    weakness = max(0, row.wrong_count - row.correct_count) * 1.5
    streak_penalty = min(row.streak, 5) * 0.8
    due_bonus = 0.0
    if row.next_review_at:
        try:
            due_at = datetime.fromisoformat(row.next_review_at)
        except ValueError:
            due_at = datetime.now(UTC)
        if due_at <= datetime.now(UTC):
            due_bonus = 6.0
    return base + weakness + due_bonus - streak_penalty


def interleave_by_topic(bundle: ContentBundle, question_ids: list[str], limit: int) -> list[str]:
    selected: list[str] = []
    topic_counts: dict[str, int] = {}
    for question_id in question_ids:
        question = bundle.questions[question_id]
        dominant_topic = question.topic_ids[0] if question.topic_ids else "mixed"
        if topic_counts.get(dominant_topic, 0) >= max(1, limit // 3):
            continue
        selected.append(question_id)
        topic_counts[dominant_topic] = topic_counts.get(dominant_topic, 0) + 1
        if len(selected) >= limit:
            return selected
    return selected


def unique_ordered_ids(question_ids: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for question_id in question_ids:
        if question_id in result:
            continue
        result.append(question_id)
        if len(result) >= limit:
            break
    return result


def next_lessons_for_user(bundle: ContentBundle, lesson_progress: dict[str, object], limit: int = 3) -> list[str]:
    ordered = sorted(bundle.lessons.values(), key=lambda item: (bundle.topics[item.topic_id].order, item.id))
    result: list[str] = []
    for lesson in ordered:
        row = lesson_progress.get(lesson.id)
        if row is None or row["status"] in {"new", "reading", "weak"}:
            result.append(lesson.id)
        if len(result) >= limit:
            break
    return result


def plan_for_today(bundle: ContentBundle) -> str:
    today = date.today().isoformat()
    for day_plan in bundle.study_plan:
        if day_plan.day == today:
            return (
                f"Сегодня: {day_plan.focus}\n"
                f"Уроки: {', '.join(day_plan.lessons)}\n"
                f"Практика: {day_plan.practice}\n"
                f"Вечером: {day_plan.evening}"
            )
    return "Сегодня работаем по адаптивному плану: новая теория, короткая тренировка, затем повтор слабых тем."
