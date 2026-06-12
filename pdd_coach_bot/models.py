from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Topic:
    id: str
    title: str
    short_title: str
    stage: str
    order: int
    summary: str
    source_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Lesson:
    id: str
    topic_id: str
    title: str
    reading_time_min: int
    theory: list[str]
    mistakes: list[str]
    memory_hook: str
    summary: str
    image_path: Path | None = None
    image_paths: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class Question:
    id: str
    topic_ids: list[str]
    prompt: str
    options: list[str]
    correct_index: int
    explanation: str
    source: str
    exam_ticket: str | None = None
    image_path: Path | None = None
    remedy_image_path: Path | None = None
    pattern_tags: list[str] = field(default_factory=list)
    difficulty: str = "medium"
    trap_hint: str = ""
    memory_hint: str = ""


@dataclass(slots=True)
class StudyPlanDay:
    day: str
    focus: str
    lessons: list[str]
    practice: str
    evening: str
