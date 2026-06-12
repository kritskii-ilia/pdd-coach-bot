from pathlib import Path
import sys

sys.path.append(str(Path("/home/user/pdd-coach-bot/scripts")))

from import_external_tickets import map_topics


def test_map_topics_normalizes_external_rules_to_internal_topic() -> None:
    topic_ids = map_topics(["Общие обязанности водителей"], "Что обязан сделать водитель перед началом движения?")

    assert "priority_rules" in topic_ids


def test_map_topics_keeps_first_aid_internal_topic() -> None:
    topic_ids = map_topics(["Оказание доврачебной медицинской помощи"], "Как остановить кровотечение?")

    assert topic_ids == ["first_aid"]
