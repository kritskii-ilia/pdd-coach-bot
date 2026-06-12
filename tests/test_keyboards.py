from pdd_coach_bot.keyboards import after_answer_keyboard


def test_after_answer_keyboard_skips_long_topic_callbacks() -> None:
    markup = after_answer_keyboard(
        "ticket",
        "next",
        topic_id="external_неисправности_и_условия_допуска_транспортных_средств_к_эксплуатации",
    )

    callback_data = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]

    assert callback_data == ["continue:ticket:next", "menu"]


def test_after_answer_keyboard_uses_question_remedy_when_available() -> None:
    markup = after_answer_keyboard(
        "ticket",
        "next",
        topic_id="priority_rules",
        question_id="ffd0c95b28a89bd4faff45a8874c4fb3",
    )

    callback_data = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]

    assert callback_data == [
        "continue:ticket:next",
        "topic:priority_rules",
        "remedy_question:ffd0c95b28a89bd4faff45a8874c4fb3",
        "menu",
    ]
