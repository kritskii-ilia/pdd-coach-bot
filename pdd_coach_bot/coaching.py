from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta


GOAL_LABELS = {
    "fast_track": "сдать как можно быстрее",
    "steady": "учить спокойно и без перегруза",
    "cram": "добить ошибки перед экзаменом",
}

EXPERIENCE_LABELS = {
    "zero": "с нуля",
    "partial": "что-то уже учил",
    "retake": "пересдача / уже решал билеты",
}


@dataclass(slots=True)
class ExplanationCard:
    short_why: str
    trap_hint: str
    memory_hint: str
    pattern_tags: list[str] = field(default_factory=list)
    difficulty: str = "medium"


@dataclass(slots=True)
class ReadinessSnapshot:
    percent: int
    band: str
    advice: str


@dataclass(slots=True)
class WeeklySummary:
    accuracy_percent: int
    question_count: int
    session_count: int
    exam_count: int
    streak_days: int
    top_patterns: list[str]
    regressions: list[str]
    best_topic: str | None
    risk_topic: str | None


def goal_touches(goal: str, study_minutes: int) -> tuple[str, int]:
    if goal == "cram":
        return "high", max(6, min(9, study_minutes // 4))
    if goal == "fast_track":
        return "high" if study_minutes >= 25 else "medium", max(5, min(8, study_minutes // 5))
    if study_minutes <= 15:
        return "low", 3
    return "medium", max(4, min(6, study_minutes // 5))


def classify_question_patterns(prompt: str, topic_ids: list[str]) -> list[str]:
    text = prompt.lower().replace("ё", "е")
    patterns: list[str] = []
    if any(token in text for token in ["уступить", "главн", "перекрест", "обгон", "разъезд", "маневр", "приоритет"]):
        patterns.append("приоритет и очередность")
    if any(token in text for token in ["разметк", "сплошн", "прерывист", "стоп-лини"]):
        patterns.append("разметка и ориентиры")
    if any(token in text for token in ["останов", "стоянк", "парков", "5 м"]):
        patterns.append("остановка и стоянка")
    if any(token in text for token in ["пешеход", "маршрутн", "автобус", "переход"]):
        patterns.append("пешеходы и маршрутный транспорт")
    if any(token in text for token in ["светофор", "стрелк", "регулировщик", "сигнал"]):
        patterns.append("сигналы и приоритет указаний")
    if any(token in text for token in ["железнодорож", "переезд", "шлагбаум", "рельс"]):
        patterns.append("железнодорожные переезды")
    if any(token in text for token in ["кровотеч", "пострадавш", "дыхани", "первая помощь"]):
        patterns.append("первая помощь")
    if not patterns:
        for topic_id in topic_ids:
            if topic_id in {"controller_signals", "traffic_lights"}:
                patterns.append("сигналы и приоритет указаний")
            elif topic_id == "priority_rules":
                patterns.append("приоритет и очередность")
            elif topic_id == "road_markings":
                patterns.append("разметка и ориентиры")
            elif topic_id == "stopping_parking":
                patterns.append("остановка и стоянка")
            elif topic_id == "pedestrians":
                patterns.append("пешеходы и маршрутный транспорт")
            elif topic_id == "railroad":
                patterns.append("железнодорожные переезды")
            elif topic_id == "first_aid":
                patterns.append("первая помощь")
    return patterns or ["смешанные ловушки"]


def derive_explanation_card(prompt: str, explanation: str, topic_ids: list[str]) -> ExplanationCard:
    clean = explanation.strip().replace("\n", " ")
    first_sentence = clean.split(". ")[0].strip()
    if first_sentence and not first_sentence.endswith("."):
        first_sentence += "."
    patterns = classify_question_patterns(prompt, topic_ids)
    difficulty = "hard" if len(clean) > 220 or len(patterns) > 1 else ("easy" if len(clean) < 120 else "medium")
    trap_hint = f"Ловушка: чаще всего здесь путают блок «{patterns[0]}»."
    memory_hint = f"Как запомнить: сначала проверь правило из блока «{patterns[0]}», потом уже варианты ответа."
    return ExplanationCard(
        short_why=first_sentence or "Смотри на правило и контекст вопроса, а не на самый знакомый вариант.",
        trap_hint=trap_hint,
        memory_hint=memory_hint,
        pattern_tags=patterns,
        difficulty=difficulty,
    )


def readiness_band(percent: int) -> ReadinessSnapshot:
    if percent >= 85:
        return ReadinessSnapshot(percent=percent, band="высокая", advice="Уже можно давить на экзаменационный режим и билеты без ошибок.")
    if percent >= 65:
        return ReadinessSnapshot(percent=percent, band="средняя", advice="База уже есть, но слабые темы ещё способны завалить попытку.")
    if percent >= 40:
        return ReadinessSnapshot(percent=percent, band="ниже средней", advice="Пока важнее стабилизировать слабые темы, а не гнаться за количеством билетов.")
    return ReadinessSnapshot(percent=percent, band="низкая", advice="Сначала добери теорию и повтор проблемных вопросов, иначе экзамен будет случайным.")


def recommend_daily_mode(goal: str, days_left: int) -> str:
    if days_left <= 7 or goal == "cram":
        return "антикризисный режим: ошибки, слабые темы, экзамены"
    if goal == "fast_track":
        return "ускоренный режим: новые вопросы + ежедневный билет"
    return "ровный режим: теория, смешанная практика и мягкий повтор"


def monday_bounds(now: datetime) -> tuple[str, str]:
    local_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    local_end = local_start + timedelta(days=7)
    return local_start.astimezone(UTC).isoformat(), local_end.astimezone(UTC).isoformat()
