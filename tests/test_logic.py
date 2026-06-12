from pdd_coach_bot.logic import lesson_status_label


def test_lesson_status_label() -> None:
    assert lesson_status_label("weak") == "усвоено слабо"
    assert lesson_status_label("strong") == "усвоено хорошо"

