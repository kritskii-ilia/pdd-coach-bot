from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def _callback_button(text: str, callback_data: str) -> InlineKeyboardButton | None:
    if len(callback_data.encode("utf-8")) > 64:
        return None
    return InlineKeyboardButton(text, callback_data=callback_data)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Теория"), KeyboardButton("Тренировка по темам")],
            [KeyboardButton("Смешанный тест"), KeyboardButton("Билеты")],
            [KeyboardButton("Мои ошибки"), KeyboardButton("Прогресс")],
            [KeyboardButton("Повторить сегодня"), KeyboardButton("Настройки")],
        ],
        resize_keyboard=True,
    )


def theory_topic_keyboard(topic_ids: list[str], title_map: dict[str, str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(title_map[topic_id], callback_data=f"topic:{topic_id}")] for topic_id in topic_ids]
    rows.append([InlineKeyboardButton("В меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def practice_topic_keyboard(topic_ids: list[str], title_map: dict[str, str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(title_map[topic_id], callback_data=f"practice_topic:{topic_id}")] for topic_id in topic_ids]
    rows.append([InlineKeyboardButton("В меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def lesson_actions(lesson_id: str, topic_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Прочитал", callback_data=f"lesson_done:{lesson_id}"),
                InlineKeyboardButton("Непонятно", callback_data=f"lesson_hard:{lesson_id}"),
            ],
            [
                InlineKeyboardButton("Повторить позже", callback_data=f"lesson_later:{lesson_id}"),
                InlineKeyboardButton("Тест по теме", callback_data=f"practice:{topic_id}"),
            ],
            [InlineKeyboardButton("В меню", callback_data="menu")],
        ]
    )


def answer_keyboard(question_id: str, options: list[str]) -> InlineKeyboardMarkup:
    labels = ["A", "B", "C", "D", "E", "F"]
    rows = []
    for idx, _option in enumerate(options):
        label = labels[idx] if idx < len(labels) else str(idx + 1)
        button = _callback_button(label, f"answer:{question_id}:{idx}")
        if button:
            rows.append([button])
    menu_button = _callback_button("В меню", "menu")
    if menu_button:
        rows.append([menu_button])
    return InlineKeyboardMarkup(rows)


def after_answer_keyboard(
    mode: str,
    continue_token: str,
    topic_id: str | None = None,
    question_id: str | None = None,
    deep_question_id: str | None = None,
) -> InlineKeyboardMarkup:
    rows = []
    continue_button = _callback_button("Дальше", f"continue:{mode}:{continue_token}")
    if continue_button:
        rows.append([continue_button])
    if deep_question_id:
        deep_button = _callback_button("Разобрать глубже", f"deep_explain:{deep_question_id}")
        if deep_button:
            rows.append([deep_button])
    if topic_id:
        theory_button = _callback_button("Повторить теорию", f"topic:{topic_id}")
        if theory_button:
            rows.append([theory_button])
    remedy_data = f"remedy_question:{question_id}" if question_id else (f"remedy:{topic_id}" if topic_id else None)
    if remedy_data:
        remedy_button = _callback_button("Показать схему ещё раз", remedy_data)
        if remedy_button:
            rows.append([remedy_button])
    menu_button = _callback_button("В меню", "menu")
    if menu_button:
        rows.append([menu_button])
    return InlineKeyboardMarkup(rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Интенсивность: низкая", callback_data="intensity:low")],
            [InlineKeyboardButton("Интенсивность: средняя", callback_data="intensity:medium")],
            [InlineKeyboardButton("Интенсивность: высокая", callback_data="intensity:high")],
            [InlineKeyboardButton("Цель: быстро сдать", callback_data="goal:fast_track")],
            [InlineKeyboardButton("Цель: спокойно учить", callback_data="goal:steady")],
            [InlineKeyboardButton("Цель: добить ошибки", callback_data="goal:cram")],
            [InlineKeyboardButton("Экзамен через 14 дней", callback_data="exam_date:14")],
            [InlineKeyboardButton("Экзамен через 30 дней", callback_data="exam_date:30")],
            [InlineKeyboardButton("Сбросить дату экзамена", callback_data="exam_date:clear")],
            [InlineKeyboardButton("Недельный отчёт", callback_data="weekly_report")],
            [InlineKeyboardButton("Уведомления вкл/выкл", callback_data="toggle_notifications")],
            [InlineKeyboardButton("В меню", callback_data="menu")],
        ]
    )


def errors_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Тренировка ошибок", callback_data="practice_errors")],
            [InlineKeyboardButton("В меню", callback_data="menu")],
        ]
    )


def tickets_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Умный билет дня", callback_data="smart_ticket")],
            [InlineKeyboardButton("Экзамен 20 вопросов", callback_data="exam_mode")],
            [InlineKeyboardButton("Открыть билеты", callback_data="ticket_page:0")],
            [InlineKeyboardButton("Прогресс по билетам", callback_data="ticket_progress:all:0")],
            [InlineKeyboardButton("В меню", callback_data="menu")],
        ]
    )


def ticket_progress_keyboard(page: int, total_pages: int, filter_name: str) -> InlineKeyboardMarkup:
    rows = []
    rows.append(
        [
            InlineKeyboardButton("Все", callback_data="ticket_progress:all:0"),
            InlineKeyboardButton("Не начаты", callback_data="ticket_progress:new:0"),
            InlineKeyboardButton("В работе", callback_data="ticket_progress:learning:0"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("Почти готовы", callback_data="ticket_progress:almost:0"),
            InlineKeyboardButton("Без ошибок", callback_data="ticket_progress:perfect:0"),
        ]
    )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("←", callback_data=f"ticket_progress:{filter_name}:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("→", callback_data=f"ticket_progress:{filter_name}:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("К списку билетов", callback_data="ticket_page:0")])
    rows.append([InlineKeyboardButton("В меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def onboarding_goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Сдать как можно быстрее", callback_data="goal:fast_track")],
            [InlineKeyboardButton("Учить спокойно", callback_data="goal:steady")],
            [InlineKeyboardButton("Добить ошибки перед экзаменом", callback_data="goal:cram")],
        ]
    )


def onboarding_experience_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Начинаю с нуля", callback_data="experience:zero")],
            [InlineKeyboardButton("Что-то уже учил", callback_data="experience:partial")],
            [InlineKeyboardButton("Пересдача / уже решал", callback_data="experience:retake")],
        ]
    )


def onboarding_minutes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("10 минут", callback_data="study_minutes:10")],
            [InlineKeyboardButton("20 минут", callback_data="study_minutes:20")],
            [InlineKeyboardButton("30 минут", callback_data="study_minutes:30")],
        ]
    )
