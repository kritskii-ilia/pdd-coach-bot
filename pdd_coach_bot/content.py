from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .coaching import derive_explanation_card
from .models import Lesson, Question, StudyPlanDay, Topic


@dataclass(slots=True)
class ContentBundle:
    topics: dict[str, Topic]
    lessons: dict[str, Lesson]
    questions: dict[str, Question]
    ticket_map: dict[str, list[str]]
    study_plan: list[StudyPlanDay]


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_content(content_dir: Path, assets_dir: Path) -> ContentBundle:
    topics_raw = _load_json(content_dir / "topics.json")
    lessons_raw = _load_json(content_dir / "lessons.json")
    question_files = [
        content_dir / "questions_starter.json",
        content_dir / "generated" / "imported_questions.json",
    ]
    plan_raw = _load_json(content_dir / "study_plan_april_2026.json")

    topics = {
        item["id"]: Topic(
            id=item["id"],
            title=item["title"],
            short_title=item["short_title"],
            stage=item["stage"],
            order=item["order"],
            summary=item["summary"],
            source_refs=item.get("source_refs", []),
        )
        for item in topics_raw
    }
    lessons = {
        item["id"]: Lesson(
            id=item["id"],
            topic_id=item["topic_id"],
            title=item["title"],
            reading_time_min=item["reading_time_min"],
            theory=item["theory"],
            mistakes=item["mistakes"],
            memory_hook=item["memory_hook"],
            summary=item["summary"],
            image_path=(assets_dir / item["image_path"]) if item.get("image_path") else None,
            image_paths=[assets_dir / path for path in item.get("image_paths", [])],
        )
        for item in lessons_raw
    }

    questions: dict[str, Question] = {}
    ticket_map: dict[str, list[str]] = {}
    for file_path in question_files:
        if not file_path.exists():
            continue
        for item in _load_json(file_path):
            image_path = None
            raw_image = item.get("image_path")
            if raw_image:
                image_path = assets_dir / raw_image
            explanation_card = derive_explanation_card(
                item["prompt"],
                item["explanation"],
                item["topic_ids"],
            )
            question = Question(
                id=item["id"],
                topic_ids=item["topic_ids"],
                prompt=item["prompt"],
                options=item["options"],
                correct_index=item["correct_index"],
                explanation=item["explanation"],
                source=item["source"],
                exam_ticket=item.get("exam_ticket"),
                image_path=image_path,
                remedy_image_path=(assets_dir / item["remedy_image_path"]) if item.get("remedy_image_path") else None,
                pattern_tags=explanation_card.pattern_tags,
                difficulty=explanation_card.difficulty,
                trap_hint=explanation_card.trap_hint,
                memory_hint=explanation_card.memory_hint,
            )
            questions[question.id] = question
            if question.exam_ticket:
                ticket_map.setdefault(question.exam_ticket, []).append(question.id)

    study_plan = [
        StudyPlanDay(
            day=item["day"],
            focus=item["focus"],
            lessons=item["lessons"],
            practice=item["practice"],
            evening=item["evening"],
        )
        for item in plan_raw
    ]
    return ContentBundle(
        topics=topics,
        lessons=lessons,
        questions=questions,
        ticket_map=ticket_map,
        study_plan=study_plan,
    )
