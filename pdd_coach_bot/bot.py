from __future__ import annotations

import asyncio
import html
import logging
import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .content import ContentBundle
from .coaching import (
    EXPERIENCE_LABELS,
    GOAL_LABELS,
    classify_question_patterns,
    derive_explanation_card,
    goal_touches,
    monday_bounds,
    readiness_band,
    recommend_daily_mode,
)
from .keyboards import (
    after_answer_keyboard,
    answer_keyboard,
    errors_keyboard,
    lesson_actions,
    main_menu_keyboard,
    onboarding_experience_keyboard,
    onboarding_goal_keyboard,
    onboarding_minutes_keyboard,
    practice_topic_keyboard,
    settings_keyboard,
    ticket_progress_keyboard,
    tickets_hub_keyboard,
    theory_topic_keyboard,
)
from .logic import choose_due_topic_ids, choose_mixed_questions, choose_topic_questions, next_lessons_for_user, normalize_topic_rows, plan_for_today
from .logic import choose_exam_questions, normalize_question_rows
from .storage import Storage
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)

MENU_LABELS = {
    "Теория": "theory",
    "Тренировка по темам": "topic_practice",
    "Смешанный тест": "mixed",
    "Билеты": "tickets",
    "Мои ошибки": "errors",
    "Прогресс": "progress",
    "Повторить сегодня": "repeat",
    "Настройки": "settings",
}

INTENSITY_TOUCHES = {"low": 3, "medium": 5, "high": 7}
DAILY_PLAN_START_HOUR = 7
DAILY_PLAN_END_HOUR = 21
SEND_RETRY_ATTEMPTS = 3


@dataclass(slots=True)
class BotServices:
    settings: Settings
    storage: Storage
    content: ContentBundle


def create_application(services: BotServices) -> Application:
    application = (
        Application.builder()
        .token(services.settings.bot_token)
        .request(build_httpx_request(services.settings))
        .get_updates_request(build_httpx_request(services.settings))
        .build()
    )
    application.bot_data["services"] = services
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_menu))
    application.add_handler(CommandHandler("examdate", set_exam_date_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(handle_error)
    application.job_queue.run_repeating(notification_tick, interval=1800, first=30)
    application.job_queue.run_repeating(daily_plan_tick, interval=300, first=45)
    application.job_queue.run_once(daily_plan_tick, when=10)
    return application


def get_services(context: ContextTypes.DEFAULT_TYPE) -> BotServices:
    return context.application.bot_data["services"]


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled bot error while processing update=%r", update, exc_info=context.error)


def build_httpx_request(settings: Settings) -> HTTPXRequest:
    return HTTPXRequest(
        proxy_url=settings.telegram_proxy_url,
        connect_timeout=settings.telegram_connect_timeout,
        read_timeout=settings.telegram_read_timeout,
        write_timeout=settings.telegram_write_timeout,
        pool_timeout=settings.telegram_pool_timeout,
    )


def needs_onboarding(user) -> bool:
    return not (user.goal and user.study_minutes and user.experience_level and user.onboarding_step == "done")


async def send_onboarding_prompt(chat_id: int, context: ContextTypes.DEFAULT_TYPE, services: BotServices, user) -> None:
    step = user.onboarding_step or "goal"
    if not user.goal or step == "goal":
        await context.bot.send_message(
            chat_id=chat_id,
            text="1/3. Какая у тебя цель сейчас?",
            reply_markup=onboarding_goal_keyboard(),
        )
        return
    if not user.experience_level or step == "experience":
        await context.bot.send_message(
            chat_id=chat_id,
            text="2/3. С каким бэкграундом заходишь в подготовку?",
            reply_markup=onboarding_experience_keyboard(),
        )
        return
    await context.bot.send_message(
        chat_id=chat_id,
        text="3/3. Сколько минут в день реально готов уделять без самообмана?",
        reply_markup=onboarding_minutes_keyboard(),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user = update.effective_user
    if user is None or update.effective_chat is None:
        return
    existing = services.storage.get_user(user.id)
    services.storage.upsert_user(
        tg_user_id=user.id,
        first_name=user.first_name or "Ученик",
        timezone=services.settings.default_timezone,
        intensity=services.settings.default_intensity,
        touches_per_day=services.settings.default_touches_per_day,
        onboarding_step="goal" if existing is None else None,
    )
    current = services.storage.get_user(user.id)
    if current and needs_onboarding(current):
        await update.effective_chat.send_message(
            text=(
                "Я соберу короткий профиль подготовки и сразу подстрою план под тебя.\n\n"
                "Это займёт три касания."
            )
        )
        await send_onboarding_prompt(update.effective_chat.id, context, services, current)
        return
    text = (
        "Это не чат-бот и не зубрёжка 800 вопросов подряд.\n\n"
        "Я веду тебя по коротким урокам, тематическим тренировкам, повторяю слабые места и постепенно вывожу к билетам.\n\n"
        f"{plan_for_today(services.content)}"
    )
    await update.effective_chat.send_message(text=text, reply_markup=main_menu_keyboard())


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    await chat.send_message("Главное меню.", reply_markup=main_menu_keyboard())


async def set_exam_date_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None:
        return
    services = get_services(context)
    current = services.storage.get_user(user.id)
    if current is None:
        await start(update, context)
        current = services.storage.get_user(user.id)
        if current is None:
            return
    if not context.args:
        current_label = current.exam_date or "не задана"
        await chat.send_message(
            f"Текущая дата экзамена: {current_label}\nИспользуй /examdate YYYY-MM-DD или кнопки в настройках.",
            reply_markup=settings_keyboard(),
        )
        return
    raw = context.args[0].strip().lower()
    if raw in {"clear", "reset", "none"}:
        services.storage.set_exam_date(user.id, None)
        await chat.send_message("Дата экзамена сброшена.", reply_markup=settings_keyboard())
        return
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        await chat.send_message("Формат даты: YYYY-MM-DD. Например: /examdate 2026-05-20")
        return
    services.storage.set_exam_date(user.id, parsed.isoformat())
    await chat.send_message(f"Дата экзамена сохранена: {parsed.isoformat()}.", reply_markup=settings_keyboard())


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    services = get_services(context)
    current = services.storage.get_user(update.effective_user.id)
    if current and needs_onboarding(current):
        await update.effective_chat.send_message("Сначала быстро завершим профиль подготовки.")
        await send_onboarding_prompt(update.effective_chat.id, context, services, current)
        return
    target = MENU_LABELS.get(text)
    if target is None:
        await update.effective_chat.send_message(
            "Используй кнопки меню. Здесь всё рассчитано на короткие касания без ручного ввода.",
            reply_markup=main_menu_keyboard(),
        )
        return
    if target == "theory":
        await send_theory_hub(update, context, services)
    elif target == "topic_practice":
        await send_topic_practice_hub(update, context, services)
    elif target == "mixed":
        await start_mixed_test(update, context, services, from_notification=False)
    elif target == "tickets":
        await send_tickets_hub(update, context, services)
    elif target == "errors":
        await send_errors_view(update, context, services)
    elif target == "progress":
        await send_progress_view(update, context, services)
    elif target == "repeat":
        await send_repeat_today(update, context, services)
    elif target == "settings":
        await send_settings_view(update, context, services)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    services = get_services(context)
    data = query.data
    if data == "menu":
        await query.message.reply_text("Главное меню.", reply_markup=main_menu_keyboard())
        return
    if data == "noop":
        return
    if data.startswith("topic:"):
        await send_topic_lesson(query.from_user.id, query.message.chat_id, data.split(":", 1)[1], context, services)
        return
    if data.startswith("practice_topic:"):
        topic_id = data.split(":", 1)[1]
        await launch_quiz(query.from_user.id, query.message.chat_id, "topic", context, services, topic_id=topic_id)
        return
    if data.startswith("lesson_done:"):
        await mark_lesson_and_follow(query, context, services, data.split(":", 1)[1], "solid", 2, 24)
        return
    if data.startswith("lesson_hard:"):
        await mark_lesson_and_follow(query, context, services, data.split(":", 1)[1], "weak", -1, 8)
        return
    if data.startswith("lesson_later:"):
        await mark_lesson_and_follow(query, context, services, data.split(":", 1)[1], "reading", 0, 12)
        return
    if data.startswith("practice:"):
        topic_id = data.split(":", 1)[1]
        await launch_quiz(query.from_user.id, query.message.chat_id, "topic", context, services, topic_id=topic_id)
        return
    if data == "practice_errors":
        await launch_error_quiz(query.from_user.id, query.message.chat_id, context, services)
        return
    if data.startswith("answer:"):
        _, question_id, option_index = data.split(":")
        await process_answer(query, context, services, question_id, int(option_index))
        return
    if data.startswith("remedy:"):
        topic_id = data.split(":", 1)[1]
        await send_remedy_card(query.message.chat_id, services, context, topic_id=topic_id)
        return
    if data.startswith("remedy_question:"):
        question_id = data.split(":", 1)[1]
        question = services.content.questions.get(question_id)
        topic_id = question.topic_ids[0] if question and question.topic_ids else None
        await send_remedy_card(query.message.chat_id, services, context, topic_id=topic_id, question_id=question_id)
        return
    if data.startswith("deep_explain:"):
        question_id = data.split(":", 1)[1]
        await send_deep_explanation(query.message.chat_id, services, context, question_id)
        return
    if data.startswith("continue:"):
        _, mode, token = data.split(":")
        await continue_session(query.from_user.id, query.message.chat_id, context, services, mode, token, query=query)
        return
    if data.startswith("ticket:"):
        await launch_quiz(query.from_user.id, query.message.chat_id, "ticket", context, services, ticket_id=data.split(":", 1)[1])
        return
    if data == "smart_ticket":
        await send_smart_ticket(query.message.chat_id, context, services, query.from_user.id)
        return
    if data == "exam_mode":
        await launch_quiz(query.from_user.id, query.message.chat_id, "exam", context, services)
        return
    if data.startswith("ticket_page:"):
        await send_tickets_page(query.message.chat_id, context, services, int(data.split(":", 1)[1]))
        return
    if data.startswith("ticket_progress:"):
        _, filter_name, page_raw = data.split(":")
        await send_ticket_progress_page(query.message.chat_id, context, services, query.from_user.id, int(page_raw), filter_name)
        return
    if data.startswith("intensity:"):
        level = data.split(":", 1)[1]
        user = services.storage.get_user(query.from_user.id)
        if user:
            services.storage.upsert_user(
                tg_user_id=user.user_id,
                first_name=user.first_name,
                timezone=user.timezone,
                intensity=level,
                touches_per_day=INTENSITY_TOUCHES[level],
            )
        await query.message.reply_text(f"Интенсивность установлена: {level}.", reply_markup=settings_keyboard())
        return
    if data.startswith("goal:"):
        goal = data.split(":", 1)[1]
        user = services.storage.get_user(query.from_user.id)
        minutes = user.study_minutes if user and user.study_minutes else 20
        intensity, touches = goal_touches(goal, minutes)
        services.storage.update_profile(
            query.from_user.id,
            goal=goal,
            intensity=intensity,
            touches_per_day=touches,
            onboarding_step="experience" if user and needs_onboarding(user) else "done",
        )
        current = services.storage.get_user(query.from_user.id)
        if current and needs_onboarding(current):
            await send_onboarding_prompt(query.message.chat_id, context, services, current)
        else:
            await query.message.reply_text(
                f"Цель обновлена: {GOAL_LABELS.get(goal, goal)}.",
                reply_markup=settings_keyboard(),
            )
        return
    if data.startswith("experience:"):
        level = data.split(":", 1)[1]
        services.storage.update_profile(
            query.from_user.id,
            experience_level=level,
            onboarding_step="minutes",
        )
        current = services.storage.get_user(query.from_user.id)
        if current:
            await send_onboarding_prompt(query.message.chat_id, context, services, current)
        return
    if data.startswith("study_minutes:"):
        minutes = int(data.split(":", 1)[1])
        user = services.storage.get_user(query.from_user.id)
        goal = user.goal if user and user.goal else "steady"
        intensity, touches = goal_touches(goal, minutes)
        services.storage.update_profile(
            query.from_user.id,
            study_minutes=minutes,
            intensity=intensity,
            touches_per_day=touches,
            onboarding_step="done",
        )
        current = services.storage.get_user(query.from_user.id)
        message = (
            f"Профиль сохранён.\n"
            f"• Цель: {GOAL_LABELS.get(goal, goal)}\n"
            f"• Подготовка: {minutes} мин/день\n"
            f"• Режим: {intensity}"
        )
        if current and current.experience_level:
            message += f"\n• Бэкграунд: {EXPERIENCE_LABELS.get(current.experience_level, current.experience_level)}"
        await query.message.reply_text(message, reply_markup=main_menu_keyboard())
        await query.message.reply_text(build_today_plan_text(services, query.from_user.id, current.timezone if current else services.settings.default_timezone))
        return
    if data.startswith("exam_date:"):
        value = data.split(":", 1)[1]
        user = services.storage.get_user(query.from_user.id)
        timezone_name = user.timezone if user else services.settings.default_timezone
        if value == "clear":
            services.storage.set_exam_date(query.from_user.id, None)
            await query.message.reply_text("Дата экзамена сброшена.", reply_markup=settings_keyboard())
            return
        try:
            days = int(value)
        except ValueError:
            return
        exam_date = (user_local_now(timezone_name).date() + timedelta(days=days)).isoformat()
        services.storage.set_exam_date(query.from_user.id, exam_date)
        await query.message.reply_text(f"Дата экзамена установлена: {exam_date}.", reply_markup=settings_keyboard())
        return
    if data == "toggle_notifications":
        user = services.storage.get_user(query.from_user.id)
        if user:
            services.storage.set_notifications_enabled(user.user_id, not user.notifications_enabled)
            current = services.storage.get_user(user.user_id)
            state = "включены" if current and current.notifications_enabled else "выключены"
            await query.message.reply_text(f"Уведомления {state}.", reply_markup=settings_keyboard())
        return
    if data == "weekly_report":
        user = services.storage.get_user(query.from_user.id)
        timezone_name = user.timezone if user else services.settings.default_timezone
        await query.message.reply_text(build_weekly_report_text(services, query.from_user.id, timezone_name), reply_markup=settings_keyboard())


async def send_theory_hub(update: Update, context: ContextTypes.DEFAULT_TYPE, services: BotServices) -> None:
    lesson_progress = services.storage.get_lesson_progress(update.effective_user.id)
    lesson_ids = next_lessons_for_user(services.content, lesson_progress, limit=10)
    topic_ids = []
    for lesson_id in lesson_ids:
        topic_id = services.content.lessons[lesson_id].topic_id
        if topic_id not in topic_ids:
            topic_ids.append(topic_id)
    if not topic_ids:
        topic_ids = [topic_id for topic_id, _ in sorted(services.content.topics.items(), key=lambda item: item[1].order)]
    title_map = {topic_id: services.content.topics[topic_id].short_title for topic_id in topic_ids}
    await update.effective_chat.send_message(
        "Теория разбита на короткие блоки по 1-3 минуты. Начни с ближайшей темы:",
        reply_markup=theory_topic_keyboard(topic_ids, title_map),
    )


async def send_topic_practice_hub(update: Update, context: ContextTypes.DEFAULT_TYPE, services: BotServices) -> None:
    topic_ids = [topic_id for topic_id, _ in sorted(services.content.topics.items(), key=lambda item: item[1].order)]
    title_map = {topic_id: services.content.topics[topic_id].short_title for topic_id in topic_ids}
    await update.effective_chat.send_message(
        "Выбери тему. Тренировка идёт только по ней, с пояснениями после ошибок.",
        reply_markup=practice_topic_keyboard(topic_ids, title_map),
    )


async def start_mixed_test(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    from_notification: bool,
) -> None:
    topic_rows = normalize_topic_rows(services.storage.get_topic_progress(update.effective_user.id))
    question_rows = normalize_question_rows(services.storage.get_question_progress(update.effective_user.id))
    topic_ids = choose_due_topic_ids(services.content, topic_rows, limit=5)
    if not topic_ids:
        topic_ids = list(services.content.topics)[:5]
    question_ids = choose_mixed_questions(services.content, topic_ids, limit=5, question_rows=question_rows)
    if not question_ids:
        await update.effective_chat.send_message("Для смешанного теста пока нет вопросов. Сначала запусти импорт билетов или используй базовые темы.")
        return
    await start_quiz_session(update.effective_user.id, update.effective_chat.id, context, services, "mixed", question_ids, topic_ids)
    if not from_notification:
        await update.effective_chat.send_message("Запускаю смешанный мини-тест на 5 вопросов.")
    await send_current_question(update.effective_chat.id, update.effective_user.id, context, services)


async def send_tickets_hub(update: Update, context: ContextTypes.DEFAULT_TYPE, services: BotServices) -> None:
    if not services.content.ticket_map:
        await update.effective_chat.send_message(
            "Полные билеты появятся после импорта внешней базы. Пока можно учиться на тематических и смешанных вопросах."
        )
        return
    await update.effective_chat.send_message(
        "Раздел билетов. Можно открыть билет, посмотреть карту прогресса или включить экзаменационный режим.",
        reply_markup=tickets_hub_keyboard(),
    )
    await send_smart_ticket(update.effective_chat.id, context, services, update.effective_user.id)


async def send_tickets_page(chat_id: int, context: ContextTypes.DEFAULT_TYPE, services: BotServices, page: int) -> None:
    ticket_ids = sorted(services.content.ticket_map, key=ticket_sort_key)
    page_size = 10
    total_pages = max(1, (len(ticket_ids) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    current = ticket_ids[page * page_size:(page + 1) * page_size]
    rows = []
    for index in range(0, len(current), 2):
        rows.append(
            [
                InlineKeyboardButton(ticket_id.replace("Билет ", "№"), callback_data=f"ticket:{ticket_id}")
                for ticket_id in current[index:index + 2]
            ]
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("←", callback_data=f"ticket_page:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("→", callback_data=f"ticket_page:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("Прогресс по билетам", callback_data="ticket_progress:all:0")])
    rows.append([InlineKeyboardButton("В меню", callback_data="menu")])
    await context.bot.send_message(chat_id=chat_id, text="Выбери билет:", reply_markup=InlineKeyboardMarkup(rows))


async def send_ticket_progress_page(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    user_id: int,
    page: int,
    filter_name: str = "all",
) -> None:
    ticket_ids = sorted(services.content.ticket_map, key=ticket_sort_key)
    page_size = 10
    best_rows = {
        str(row["ticket_id"]): (int(row["best_correct"] or 0), int(row["total_questions"] or 0))
        for row in services.storage.get_per_ticket_best_scores(user_id)
        if row["ticket_id"]
    }
    filtered_ticket_ids = [ticket_id for ticket_id in ticket_ids if ticket_matches_filter(ticket_id, best_rows.get(ticket_id), filter_name)]
    total_pages = max(1, (len(filtered_ticket_ids) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    current = filtered_ticket_ids[page * page_size:(page + 1) * page_size]
    lines = [f"Прогресс по билетам · {ticket_filter_label(filter_name)}", render_ticket_map(best_rows, ticket_ids, recommend_ticket(services, user_id)["ticket_id"]), ""]
    if not current:
        lines.append("По этому фильтру пока пусто.")
        await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            reply_markup=ticket_progress_keyboard(page, total_pages, filter_name),
        )
        return
    for ticket_id in current:
        best = best_rows.get(ticket_id)
        label = ticket_id.replace("Билет ", "№")
        if not best:
            status = "не начат"
        elif best[1] >= 20 and best[0] >= best[1]:
            status = f"{best[0]}/{best[1]}  без ошибок"
        elif best[1] >= 20 and best[0] >= 18:
            status = f"{best[0]}/{best[1]}  почти готов"
        else:
            status = f"лучший результат {best[0]}/{best[1]}"
        lines.append(f"• {label}: {status}")
    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        reply_markup=ticket_progress_keyboard(page, total_pages, filter_name),
    )


async def send_smart_ticket(chat_id: int, context: ContextTypes.DEFAULT_TYPE, services: BotServices, user_id: int) -> None:
    recommendation = recommend_ticket(services, user_id)
    ticket_id = recommendation["ticket_id"]
    score_text = recommendation["why"]
    if not ticket_id:
        await context.bot.send_message(chat_id=chat_id, text=score_text, reply_markup=main_menu_keyboard())
        return
    markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"Открыть {ticket_id.replace('Билет ', '№')}", callback_data=f"ticket:{ticket_id}")],
            [InlineKeyboardButton("Прогресс по билетам", callback_data="ticket_progress:all:0")],
            [InlineKeyboardButton("В меню", callback_data="menu")],
        ]
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Умный билет дня: {ticket_id.replace('Билет ', '№')}\n{score_text}\n\n{render_ticket_map({str(row['ticket_id']): (int(row['best_correct'] or 0), int(row['total_questions'] or 0)) for row in services.storage.get_per_ticket_best_scores(user_id) if row['ticket_id']}, sorted(services.content.ticket_map, key=ticket_sort_key), ticket_id)}",
        reply_markup=markup,
    )


async def send_errors_view(update: Update, context: ContextTypes.DEFAULT_TYPE, services: BotServices) -> None:
    rows = services.storage.get_recent_errors(update.effective_user.id, limit=10)
    if not rows:
        await update.effective_chat.send_message("Пока ошибок нет. Это временно, но приятно.")
        return
    lines = ["Последние ошибки:"]
    seen_topics: set[str] = set()
    for row in rows[:6]:
        topic_id = row["topic_id"] or "mixed"
        if topic_id in services.content.topics:
            title = services.content.topics[topic_id].short_title
        else:
            title = "Смешанный блок"
        seen_topics.add(topic_id)
        lines.append(f"• {title}")
    pattern_counts = summarize_error_patterns(rows, services)
    if pattern_counts:
        lines.append("")
        lines.append("Ошибки по паттернам:")
        for label, count in pattern_counts[:4]:
            lines.append(f"• {label}: {count}")
    due_topics = [topic_id for topic_id in seen_topics if topic_id in services.content.topics]
    title_map = {topic_id: services.content.topics[topic_id].short_title for topic_id in due_topics}
    if due_topics:
        await update.effective_chat.send_message(
            "\n".join(lines) + "\n\nНиже можно добить их отдельной тренировкой.",
            reply_markup=errors_keyboard(),
        )
        await update.effective_chat.send_message(
            "Быстрый переход к теории слабых тем:",
            reply_markup=theory_topic_keyboard(due_topics, title_map),
        )
        return
    await update.effective_chat.send_message("\n".join(lines), reply_markup=errors_keyboard())


async def send_progress_view(update: Update, context: ContextTypes.DEFAULT_TYPE, services: BotServices) -> None:
    user = services.storage.get_user(update.effective_user.id)
    if user is None:
        await start(update, context)
        return
    await update.effective_chat.send_message(build_progress_text(services, user.user_id, user.timezone))


async def send_repeat_today(update: Update, context: ContextTypes.DEFAULT_TYPE, services: BotServices) -> None:
    user = services.storage.get_user(update.effective_user.id)
    if user is None:
        await start(update, context)
        return
    topic_rows = normalize_topic_rows(services.storage.get_topic_progress(update.effective_user.id))
    due_topics = choose_due_topic_ids(services.content, topic_rows, limit=4)
    if not due_topics:
        next_lesson_ids = next_lessons_for_user(services.content, services.storage.get_lesson_progress(update.effective_user.id), 1)
        if next_lesson_ids:
            due_topics = [services.content.lessons[next_lesson_ids[0]].topic_id]
        else:
            due_topics = [topic_id for topic_id, _ in sorted(services.content.topics.items(), key=lambda item: item[1].order)[:3]]
    title_map = {topic_id: services.content.topics[topic_id].short_title for topic_id in due_topics}
    await update.effective_chat.send_message(build_today_plan_text(services, user.user_id, user.timezone))
    await update.effective_chat.send_message(
        "Сегодня к повторению уже готовы эти темы:",
        reply_markup=theory_topic_keyboard(due_topics, title_map),
    )


async def send_settings_view(update: Update, context: ContextTypes.DEFAULT_TYPE, services: BotServices) -> None:
    user = services.storage.get_user(update.effective_user.id)
    if user is None:
        await start(update, context)
        return
    await update.effective_chat.send_message(
        f"Настройки:\n• Интенсивность: {user.intensity}\n• Касаний в день: {user.touches_per_day}\n• Уведомления: {'вкл' if user.notifications_enabled else 'выкл'}\n• Дата экзамена: {user.exam_date or 'не задана'}\n• Цель: {GOAL_LABELS.get(user.goal or '', user.goal or 'не задана')}\n• Время в день: {f'{user.study_minutes} мин' if user.study_minutes else 'не задано'}\n• Бэкграунд: {EXPERIENCE_LABELS.get(user.experience_level or '', user.experience_level or 'не задан')}\n\n"
        "Команда для ручной установки: /examdate YYYY-MM-DD",
        reply_markup=settings_keyboard(),
    )


async def send_topic_lesson(user_id: int, chat_id: int, topic_id: str, context: ContextTypes.DEFAULT_TYPE, services: BotServices) -> None:
    lessons = [lesson for lesson in services.content.lessons.values() if lesson.topic_id == topic_id]
    lessons.sort(key=lambda item: item.id)
    lesson = lessons[0]
    text = render_lesson(services.content, lesson.id)
    image_paths = [path for path in lesson.image_paths if path.exists()]
    if not image_paths and lesson.image_path and lesson.image_path.exists():
        image_paths = [lesson.image_path]
    for index, image_path in enumerate(image_paths, start=1):
        caption = f"{lesson.title} · карточка {index}/{len(image_paths)}" if len(image_paths) > 1 else None
        with image_path.open("rb") as fh:
            await context.bot.send_photo(chat_id=chat_id, photo=fh, caption=caption)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=lesson_actions(lesson.id, topic_id),
    )
    services.storage.mark_lesson(user_id, lesson.id, "reading", 0, (datetime.now(UTC) + timedelta(hours=6)).replace(microsecond=0).isoformat())


def render_lesson(bundle: ContentBundle, lesson_id: str) -> str:
    lesson = bundle.lessons[lesson_id]
    topic = bundle.topics[lesson.topic_id]
    theory_lines = "\n".join(f"• {html.escape(line)}" for line in lesson.theory)
    mistake_lines = "\n".join(f"• {html.escape(line)}" for line in lesson.mistakes)
    refs = ", ".join(topic.source_refs)
    return (
        f"<b>{html.escape(topic.title)}</b>\n"
        f"<b>{html.escape(lesson.title)}</b> · {lesson.reading_time_min} мин\n\n"
        f"{html.escape(lesson.summary)}\n\n"
        f"{theory_lines}\n\n"
        f"<b>Где чаще ошибаются:</b>\n{mistake_lines}\n\n"
        f"<b>Как запомнить:</b> {html.escape(lesson.memory_hook)}\n\n"
        f"<i>Опора: {html.escape(refs)}</i>"
    )


async def mark_lesson_and_follow(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    lesson_id: str,
    status: str,
    confidence_delta: int,
    due_in_hours: int,
) -> None:
    next_review = (datetime.now(UTC) + timedelta(hours=due_in_hours)).replace(microsecond=0).isoformat()
    services.storage.mark_lesson(query.from_user.id, lesson_id, status, confidence_delta, next_review)
    lesson = services.content.lessons[lesson_id]
    topic = services.content.topics[lesson.topic_id]
    if status == "solid":
        text = f"Урок отмечен как прочитанный. Сразу закрепим тему «{topic.short_title}» короткой тренировкой."
    elif status == "weak":
        text = f"Тему «{topic.short_title}» верну раньше. Пока закрепим её позже, без спешки."
    else:
        text = f"Окей, верну тему «{topic.short_title}» позже."
    await query.message.reply_text(text, reply_markup=main_menu_keyboard())
    if status == "solid":
        await launch_quiz(query.from_user.id, query.message.chat_id, "topic", context, services, topic_id=lesson.topic_id)


async def launch_quiz(
    user_id: int,
    chat_id: int,
    mode: str,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    topic_id: str | None = None,
    ticket_id: str | None = None,
) -> None:
    question_rows = normalize_question_rows(services.storage.get_question_progress(user_id))
    if mode == "topic" and topic_id is not None:
        question_ids = choose_topic_questions(services.content, topic_id, limit=7, question_rows=question_rows)
    elif mode == "ticket" and ticket_id is not None:
        question_ids = services.content.ticket_map.get(ticket_id, [])
    elif mode == "exam":
        question_ids = choose_exam_questions(services.content, limit=20, question_rows=question_rows)
    else:
        question_ids = []
    if not question_ids:
        await context.bot.send_message(chat_id=chat_id, text="Для этого режима пока нет вопросов.")
        return
    await start_quiz_session(
        user_id,
        chat_id,
        context,
        services,
        mode,
        question_ids,
        [topic_id] if topic_id else [],
        ticket_id=ticket_id,
    )
    if mode == "exam":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Экзаменационный режим: 20 вопросов, лимит 20 минут, допускается не больше 2 ошибок. После ответа бот сразу переводит к следующему вопросу.",
        )
    await send_current_question(chat_id, user_id, context, services)


async def launch_error_quiz(
    user_id: int,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
) -> None:
    question_rows = normalize_question_rows(services.storage.get_question_progress(user_id))
    question_ids = [
        qid
        for qid in services.storage.get_recent_error_question_ids(user_id, limit=20)
        if qid in services.content.questions
    ]
    question_ids.sort(key=lambda qid: question_priority_for_error_quiz(question_rows.get(qid)), reverse=True)
    question_ids = question_ids[:7]
    if not question_ids:
        await context.bot.send_message(chat_id=chat_id, text="Свежих ошибок для отдельной тренировки пока нет.")
        return
    await start_quiz_session(user_id, chat_id, context, services, "errors", question_ids, [])
    await context.bot.send_message(chat_id=chat_id, text="Запускаю короткую тренировку по последним ошибкам.")
    await send_current_question(chat_id, user_id, context, services)


async def start_quiz_session(
    user_id: int,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    mode: str,
    question_ids: list[str],
    topic_ids: list[str],
    ticket_id: str | None = None,
) -> None:
    payload = {
        "chat_id": chat_id,
        "question_ids": question_ids,
        "position": 0,
        "mode": mode,
        "topic_ids": topic_ids,
        "ticket_id": ticket_id,
        "correct": 0,
        "wrong": 0,
        "answers": [],
        "started_at": utc_iso_now(),
        "time_limit_sec": 20 * 60 if mode == "exam" else None,
        "max_wrong": 2 if mode == "exam" else None,
    }
    services.storage.save_session(user_id, mode, payload)


async def send_current_question(
    chat_id: int,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    edit_query=None,
) -> None:
    session = services.storage.get_session(user_id)
    if session is None:
        await context.bot.send_message(chat_id=chat_id, text="Сессия не найдена.")
        return
    mode, payload = session
    question_ids = payload["question_ids"]
    position = int(payload["position"])
    if position >= len(question_ids):
        await finish_session(chat_id, user_id, context, services)
        return
    if mode == "exam" and exam_session_expired(payload):
        await finish_session(chat_id, user_id, context, services, forced_reason="Время вышло.")
        return
    question = services.content.questions[question_ids[position]]
    if question.image_path and question.image_path.exists():
        with question.image_path.open("rb") as fh:
            await context.bot.send_photo(chat_id=chat_id, photo=fh)
    text = render_question_text(
        question.prompt,
        question.options,
        position + 1,
        len(question_ids),
        exam_remaining_label(payload) if mode == "exam" else None,
    )
    reply_markup = answer_keyboard(question.id, question.options)
    if edit_query is not None and not question.image_path:
        try:
            await edit_query.edit_message_text(text=text, reply_markup=reply_markup)
            return
        except BadRequest:
            pass
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def process_answer(query, context: ContextTypes.DEFAULT_TYPE, services: BotServices, question_id: str, option_index: int) -> None:
    session = services.storage.get_session(query.from_user.id)
    if session is None:
        await query.message.reply_text("Сессия уже завершена. Запусти новую тренировку из меню.")
        return
    mode, payload = session
    position = int(payload["position"])
    expected_question_id = payload["question_ids"][position]
    if expected_question_id != question_id:
        await query.message.reply_text("Этот ответ уже неактуален. Открой текущий вопрос.")
        return
    question = services.content.questions[question_id]
    is_correct = option_index == question.correct_index
    payload["correct"] = int(payload["correct"]) + (1 if is_correct else 0)
    payload["wrong"] = int(payload["wrong"]) + (0 if is_correct else 1)
    payload["position"] = int(payload["position"]) + 1
    payload.setdefault("answers", []).append(
        {"question_id": question_id, "selected_index": option_index, "is_correct": is_correct}
    )
    services.storage.save_session(query.from_user.id, mode, payload)
    primary_topic = question.topic_ids[0] if question.topic_ids else None
    theory_topic_id = primary_topic if primary_topic in services.content.topics else None
    remedy_question_id = question.id if question.remedy_image_path and question.remedy_image_path.exists() else None
    services.storage.record_attempt(query.from_user.id, question.id, primary_topic, is_correct)
    if mode == "exam":
        await render_exam_answer_feedback(query, question, option_index, is_correct, payload)
        if exam_session_expired(payload):
            await finish_session(query.message.chat_id, query.from_user.id, context, services, forced_reason="Время вышло.")
            return
        if payload.get("max_wrong") is not None and int(payload["wrong"]) > int(payload["max_wrong"]):
            await finish_session(query.message.chat_id, query.from_user.id, context, services, forced_reason="Лимит ошибок исчерпан.")
            return
        await send_current_question(query.message.chat_id, query.from_user.id, context, services)
        return
    if not is_correct:
        await send_remedy_card(query.message.chat_id, services, context, topic_id=primary_topic, question_id=question.id)
    short_explanation = build_short_explanation(question, is_correct, option_index)
    await render_standard_answer_feedback(
        query,
        question,
        option_index,
        short_explanation,
        reply_markup=after_answer_keyboard(
            mode,
            "next",
            topic_id=theory_topic_id,
            question_id=remedy_question_id,
            deep_question_id=question.id,
        ),
    )


async def continue_session(
    user_id: int,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    mode: str,
    token: str,
    query=None,
) -> None:
    del mode, token
    await send_current_question(chat_id, user_id, context, services, edit_query=query)


async def finish_session(
    chat_id: int,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    forced_reason: str | None = None,
) -> None:
    session = services.storage.get_session(user_id)
    if session is None:
        return
    mode, payload = session
    correct = int(payload["correct"])
    wrong = int(payload["wrong"])
    total = correct + wrong
    topic_ids = payload.get("topic_ids") or []
    topic_id = topic_ids[0] if topic_ids else None
    ticket_id = payload.get("ticket_id")
    services.storage.record_completed_session(
        tg_user_id=user_id,
        mode=mode,
        correct_answers=correct,
        wrong_answers=wrong,
        total_questions=total,
        topic_id=topic_id,
        ticket_id=ticket_id,
    )
    services.storage.clear_session(user_id)
    if mode == "exam":
        time_label = exam_spent_label(payload)
        passed = wrong <= 2 and forced_reason is None
        pattern_lines = summarize_session_patterns(payload.get("answers", []), services)
        header = "Экзамен сдан." if passed else "Экзамен не сдан."
        lines = [
            header,
            f"• Правильно: {correct}/{total}",
            f"• Ошибок: {wrong}",
            f"• Время: {time_label}",
        ]
        if forced_reason:
            lines.append(f"• Причина остановки: {forced_reason}")
        if pattern_lines:
            lines.append("")
            lines.append("Что чаще всего ломало попытку:")
            lines.extend(f"• {line}" for line in pattern_lines[:4])
        lines.append("")
        lines.append("Дальше: добей слабые паттерны или открой рекомендованный билет.")
        text = "\n".join(lines)
    else:
        text = (
            f"Сессия завершена.\n"
            f"• Правильно: {correct}/{total}\n"
            f"• Ошибок: {wrong}\n\n"
            f"Дальше логично сделать либо повтор слабых тем, либо смешанный тест."
        )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=main_menu_keyboard())


async def send_remedy_card(
    chat_id: int,
    services: BotServices,
    context: ContextTypes.DEFAULT_TYPE,
    topic_id: str | None,
    question_id: str | None = None,
) -> None:
    selected = None
    caption = "Подсказка по теме"
    if question_id and question_id in services.content.questions:
        question = services.content.questions[question_id]
        if question.remedy_image_path and question.remedy_image_path.exists():
            selected = question.remedy_image_path
            if topic_id and topic_id in services.content.topics:
                caption = f"Подсказка по ошибке: {services.content.topics[topic_id].short_title}"
            else:
                caption = "Подсказка по ошибке"
    if selected is None and (topic_id is None or topic_id not in services.content.topics):
        return
    if selected is None and topic_id is not None:
        lessons = [lesson for lesson in services.content.lessons.values() if lesson.topic_id == topic_id]
        if not lessons:
            return
        lesson = sorted(lessons, key=lambda item: item.id)[0]
        image_paths = [path for path in lesson.image_paths if path.exists()]
        selected = image_paths[0] if image_paths else (lesson.image_path if lesson.image_path and lesson.image_path.exists() else None)
        if selected is None:
            return
        caption = f"Подсказка по теме «{services.content.topics[topic_id].short_title}»"
    with selected.open("rb") as fh:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=fh,
            caption=caption,
        )


def render_question_text(prompt: str, options: list[str], number: int, total: int, extra_header: str | None = None) -> str:
    labels = ["A", "B", "C", "D", "E", "F"]
    lines = [f"Вопрос {number}/{total}", "", prompt, ""]
    if extra_header:
        lines = [f"Вопрос {number}/{total}", extra_header, "", prompt, ""]
    for idx, option in enumerate(options):
        label = labels[idx] if idx < len(labels) else str(idx + 1)
        lines.append(f"{label}. {option}")
    lines.append("")
    lines.append("Нажми букву с правильным вариантом.")
    return "\n".join(lines)


def utc_iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def exam_session_expired(payload: dict[str, object]) -> bool:
    started_at = payload.get("started_at")
    time_limit_sec = payload.get("time_limit_sec")
    if not started_at or not time_limit_sec:
        return False
    try:
        started = datetime.fromisoformat(str(started_at))
    except ValueError:
        return False
    elapsed = (datetime.now(UTC) - started).total_seconds()
    return elapsed >= int(time_limit_sec)


def exam_remaining_label(payload: dict[str, object]) -> str:
    started_at = payload.get("started_at")
    time_limit_sec = payload.get("time_limit_sec")
    if not started_at or not time_limit_sec:
        return "Экзамен"
    try:
        started = datetime.fromisoformat(str(started_at))
    except ValueError:
        return "Экзамен"
    elapsed = max(0, int((datetime.now(UTC) - started).total_seconds()))
    remaining = max(0, int(time_limit_sec) - elapsed)
    return f"Экзамен · осталось {remaining // 60:02d}:{remaining % 60:02d}"


def exam_spent_label(payload: dict[str, object]) -> str:
    started_at = payload.get("started_at")
    if not started_at:
        return "00:00"
    try:
        started = datetime.fromisoformat(str(started_at))
    except ValueError:
        return "00:00"
    elapsed = max(0, int((datetime.now(UTC) - started).total_seconds()))
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"


def build_short_explanation(question, is_correct: bool, option_index: int) -> str:
    labels = ["A", "B", "C", "D", "E", "F"]
    chosen = labels[option_index] if option_index < len(labels) else str(option_index + 1)
    correct = labels[question.correct_index] if question.correct_index < len(labels) else str(question.correct_index + 1)
    intro = "Верно." if is_correct else f"Неверно. Ты выбрал {chosen}, правильный ответ {correct}."
    card = derive_explanation_card(question.prompt, question.explanation, question.topic_ids)
    return f"{intro}\n\nПочему: {card.short_why}\n{card.trap_hint}"


async def render_standard_answer_feedback(query, question, option_index: int, short_explanation: str, reply_markup) -> None:
    try:
        await query.edit_message_text(
            text=render_answer_review_text(question, option_index, short_explanation),
            reply_markup=reply_markup,
        )
    except BadRequest:
        await query.message.reply_text(short_explanation, reply_markup=reply_markup)


async def render_exam_answer_feedback(query, question, option_index: int, is_correct: bool, payload: dict[str, object]) -> None:
    labels = ["A", "B", "C", "D", "E", "F"]
    chosen = labels[option_index] if option_index < len(labels) else str(option_index + 1)
    status = "Принято: верно." if is_correct else f"Принято: ошибка, выбран вариант {chosen}."
    try:
        await query.edit_message_text(
            text=render_answer_review_text(question, option_index, f"{status}\n\nПереходим к следующему вопросу."),
            reply_markup=None,
        )
    except BadRequest:
        await query.message.reply_text(status)


async def send_deep_explanation(chat_id: int, services: BotServices, context: ContextTypes.DEFAULT_TYPE, question_id: str) -> None:
    question = services.content.questions.get(question_id)
    if question is None:
        return
    card = derive_explanation_card(question.prompt, question.explanation, question.topic_ids)
    topic_titles = [
        services.content.topics[topic_id].short_title
        for topic_id in question.topic_ids
        if topic_id in services.content.topics
    ]
    extra = f"\n\nЛовушка:\n{question.trap_hint or card.trap_hint}\n\nКак запомнить:\n{question.memory_hint or card.memory_hint}"
    if topic_titles:
        extra += f"\n\nТемы: {', '.join(topic_titles)}."
    await context.bot.send_message(chat_id=chat_id, text=f"Подробный разбор:\n\n{question.explanation.strip()}{extra}")


def render_answer_review_text(question, option_index: int, summary: str) -> str:
    labels = ["A", "B", "C", "D", "E", "F"]
    lines = [question.prompt, ""]
    for idx, option in enumerate(question.options):
        label = labels[idx] if idx < len(labels) else str(idx + 1)
        prefix = "✅" if idx == question.correct_index else ("👉" if idx == option_index else "•")
        lines.append(f"{prefix} {label}. {option}")
    lines.append("")
    lines.append(summary)
    return "\n".join(lines)


def summarize_error_patterns(rows: list[object], services: BotServices) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        question = services.content.questions.get(str(row["question_id"]))
        if question is None:
            continue
        for pattern in classify_question_patterns(question.prompt, question.topic_ids):
            counts[pattern] = counts.get(pattern, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def summarize_session_patterns(answers: list[dict[str, object]], services: BotServices) -> list[str]:
    counts: dict[str, int] = {}
    for answer in answers:
        if answer.get("is_correct"):
            continue
        question = services.content.questions.get(str(answer["question_id"]))
        if question is None:
            continue
        for pattern in classify_question_patterns(question.prompt, question.topic_ids):
            counts[pattern] = counts.get(pattern, 0) + 1
    return [f"{label}: {count}" for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def question_priority_for_error_quiz(row) -> float:
    if row is None:
        return 0.0
    return max(0.0, 8.0 - float(row.score)) + max(0, int(row.wrong_count) - int(row.correct_count))


def render_ticket_map(best_rows: dict[str, tuple[int, int]], ticket_ids: list[str], highlighted_ticket_id: str | None) -> str:
    marks: list[str] = []
    for ticket_id in ticket_ids:
        best = best_rows.get(ticket_id)
        if best is None:
            marker = "⬜"
        elif best[1] >= 20 and best[0] >= best[1]:
            marker = "🟩"
        elif best[1] >= 20 and best[0] >= 18:
            marker = "🟨"
        else:
            marker = "🟥"
        if highlighted_ticket_id == ticket_id:
            marker = f"⭐{marker}"
        marks.append(marker)
    rows = ["Карта билетов:"]
    for index in range(0, len(marks), 5):
        rows.append(" ".join(marks[index:index + 5]))
    rows.append("⬜ новый · 🟥 в работе · 🟨 почти готов · 🟩 закрыт")
    if highlighted_ticket_id:
        rows.append(f"Сейчас приоритет: {highlighted_ticket_id.replace('Билет ', '№')}")
    return "\n".join(rows)


def ticket_sort_key(ticket_id: str) -> tuple[int, str]:
    parts = ticket_id.split()
    if parts and parts[-1].isdigit():
        return int(parts[-1]), ticket_id
    return 10**9, ticket_id


def ticket_matches_filter(ticket_id: str, best: tuple[int, int] | None, filter_name: str) -> bool:
    del ticket_id
    if filter_name == "all":
        return True
    if filter_name == "new":
        return best is None
    if best is None:
        return False
    correct, total = best
    if filter_name == "perfect":
        return total >= 20 and correct >= total
    if filter_name == "almost":
        return total >= 20 and 18 <= correct < total
    if filter_name == "learning":
        return correct < max(total, 20) and correct < 18
    return True


def ticket_filter_label(filter_name: str) -> str:
    return {
        "all": "все",
        "new": "не начаты",
        "learning": "в работе",
        "almost": "почти готовы",
        "perfect": "без ошибок",
    }.get(filter_name, filter_name)


def render_bar(numerator: int | float, denominator: int | float, width: int = 10) -> str:
    if denominator <= 0:
        return f"[{'-' * width}] 0%"
    ratio = max(0.0, min(1.0, float(numerator) / float(denominator)))
    filled = int(round(ratio * width))
    return f"[{'#' * filled}{'-' * (width - filled)}] {int(round(ratio * 100))}%"


def user_local_now(timezone_name: str) -> datetime:
    now = datetime.now(UTC)
    try:
        return now.astimezone(ZoneInfo(timezone_name))
    except Exception:
        return now


def day_bounds_utc(timezone_name: str) -> tuple[str, str, datetime]:
    local_now = user_local_now(timezone_name)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(UTC).isoformat(), local_end.astimezone(UTC).isoformat(), local_now


def resolve_exam_deadline(services: BotServices, user_id: int, fallback_today: date) -> date:
    user = services.storage.get_user(user_id)
    if user and user.exam_date:
        try:
            return date.fromisoformat(user.exam_date)
        except ValueError:
            pass
    return max(fallback_today, date(2026, 4, 30))


def weakest_topics(topic_rows, services: BotServices) -> list[str]:
    ranked = sorted(topic_rows.values(), key=lambda row: (row.score, row.correct_count - row.wrong_count))
    titles: list[str] = []
    for row in ranked:
        if row.topic_id not in services.content.topics:
            continue
        titles.append(services.content.topics[row.topic_id].short_title)
    return titles


def detect_regressions(services: BotServices, user_id: int) -> list[str]:
    attempts = services.storage.get_recent_attempts(user_id, limit=30)
    topic_totals: dict[str, list[int]] = {}
    for index, row in enumerate(reversed(attempts)):
        topic_id = row["topic_id"]
        if not topic_id or topic_id not in services.content.topics:
            continue
        bucket = 0 if index < len(attempts) // 2 else 1
        topic_totals.setdefault(topic_id, [0, 0, 0, 0])
        topic_totals[topic_id][bucket * 2] += int(row["is_correct"])
        topic_totals[topic_id][bucket * 2 + 1] += 1
    regressed: list[str] = []
    for topic_id, values in topic_totals.items():
        early_correct, early_total, late_correct, late_total = values
        if early_total < 2 or late_total < 2:
            continue
        early_ratio = early_correct / early_total
        late_ratio = late_correct / late_total
        if early_ratio - late_ratio >= 0.35:
            regressed.append(services.content.topics[topic_id].short_title)
    return regressed


def build_weekly_summary(services: BotServices, user_id: int, timezone_name: str):
    local_now = user_local_now(timezone_name)
    start_iso, end_iso = monday_bounds(local_now)
    attempts = services.storage.get_question_attempts_between(user_id, start_iso, end_iso)
    sessions = services.storage.get_session_history_between(user_id, start_iso, end_iso)
    correct = sum(int(row["is_correct"]) for row in attempts)
    total = len(attempts)
    day_marks = {str(row["answered_at"])[:10] for row in attempts}
    patterns = summarize_error_patterns([row for row in attempts if not int(row["is_correct"])], services)
    regressions = detect_regressions(services, user_id)

    topic_delta: dict[str, list[int]] = {}
    for row in attempts:
        topic_id = row["topic_id"]
        if not topic_id or topic_id not in services.content.topics:
            continue
        topic_delta.setdefault(topic_id, [0, 0])
        topic_delta[topic_id][0] += int(row["is_correct"])
        topic_delta[topic_id][1] += 1
    best_topic = None
    risk_topic = None
    if topic_delta:
        best_topic = max(topic_delta.items(), key=lambda item: item[1][0] / max(item[1][1], 1))[0]
        risk_topic = min(topic_delta.items(), key=lambda item: item[1][0] / max(item[1][1], 1))[0]
    return {
        "accuracy_percent": int(round((correct / max(total, 1)) * 100)),
        "question_count": total,
        "session_count": len(sessions),
        "exam_count": sum(1 for row in sessions if row["mode"] == "exam"),
        "streak_days": len(day_marks),
        "top_patterns": [f"{label}: {count}" for label, count in patterns[:3]],
        "regressions": regressions[:3],
        "best_topic": services.content.topics[best_topic].short_title if best_topic else None,
        "risk_topic": services.content.topics[risk_topic].short_title if risk_topic else None,
    }


def build_weekly_report_text(services: BotServices, user_id: int, timezone_name: str) -> str:
    summary = build_weekly_summary(services, user_id, timezone_name)
    lines = [
        "Недельный отчёт",
        f"• Точность: {summary['accuracy_percent']}%",
        f"• Ответов: {summary['question_count']}",
        f"• Сессий: {summary['session_count']}",
        f"• Экзаменов: {summary['exam_count']}",
        f"• Активных дней: {summary['streak_days']}",
    ]
    if summary["best_topic"]:
        lines.append(f"• Самая уверенная тема: {summary['best_topic']}")
    if summary["risk_topic"]:
        lines.append(f"• Самый рискованный блок: {summary['risk_topic']}")
    if summary["top_patterns"]:
        lines.append(f"• Частые ловушки: {', '.join(summary['top_patterns'])}")
    if summary["regressions"]:
        lines.append(f"• Где просел: {', '.join(summary['regressions'])}")
    return "\n".join(lines)


def should_send_weekly_report(services: BotServices, user, now: datetime | None = None) -> bool:
    current_utc = now or datetime.now(UTC)
    try:
        local_now = current_utc.astimezone(ZoneInfo(user.timezone))
    except Exception:
        local_now = current_utc
    if local_now.weekday() != 0 or local_now.hour < 8:
        return False
    start_iso, end_iso = monday_bounds(local_now)
    sent = services.storage.notifications_sent_between(user.user_id, start_iso, end_iso, notification_type="weekly_report")
    return sent == 0


def should_send_daily_plan(services: BotServices, user, now: datetime | None = None) -> bool:
    current_utc = now or datetime.now(UTC)
    try:
        local_now = current_utc.astimezone(ZoneInfo(user.timezone))
    except Exception:
        local_now = current_utc
    if not (DAILY_PLAN_START_HOUR <= local_now.hour < DAILY_PLAN_END_HOUR):
        return False
    today_iso = local_now.date().isoformat()
    _message_id, pinned_date = services.storage.get_daily_plan_pin_state(user.user_id)
    if pinned_date == today_iso:
        return False
    start_iso, end_iso, _ = day_bounds_utc(user.timezone)
    already_sent = services.storage.notifications_sent_between(
        user.user_id,
        start_iso,
        end_iso,
        notification_type="daily_plan",
    )
    return already_sent == 0


def build_progress_text(services: BotServices, user_id: int, timezone_name: str) -> str:
    lesson_rows = services.storage.get_lesson_progress(user_id)
    topic_rows = normalize_topic_rows(services.storage.get_topic_progress(user_id))
    question_rows = normalize_question_rows(services.storage.get_question_progress(user_id))
    question_stats = services.storage.get_question_stats(user_id)
    ticket_stats = services.storage.get_ticket_stats(user_id)
    per_ticket = services.storage.get_per_ticket_best_scores(user_id)
    last_ticket = services.storage.get_last_ticket_session(user_id)
    exam_question_ids = {q.id for q in services.content.questions.values() if q.exam_ticket}
    seen_questions = services.storage.get_seen_question_ids(user_id) & exam_question_ids
    correct_questions = services.storage.get_correct_question_ids(user_id) & exam_question_ids

    total_lessons = len(services.content.lessons)
    completed_lessons = sum(1 for row in lesson_rows.values() if row["status"] in {"solid", "strong"})
    total_topics = len(services.content.topics)
    weak_topics = sum(1 for row in topic_rows.values() if row.status == "weak")
    strong_topics = sum(1 for row in topic_rows.values() if row.status == "strong")
    total_exam_questions = len(exam_question_ids)
    solved_questions = len(correct_questions)
    covered_questions = len(seen_questions)
    problem_questions = min(services.storage.get_problem_question_count(user_id), max(covered_questions, 0))
    total_attempts = int(question_stats["total_attempts"] or 0)

    solved_ticket_count = int(ticket_stats["unique_tickets"] or 0)
    avg_ticket_percent = float(ticket_stats["avg_percent"] or 0.0)
    perfect_ticket_count = sum(1 for row in per_ticket if int(row["best_correct"] or 0) >= int(row["total_questions"] or 0) and int(row["total_questions"] or 0) >= 20)

    theory_ratio = completed_lessons / max(total_lessons, 1)
    question_ratio = solved_questions / max(total_exam_questions, 1)
    ticket_ratio = ((solved_ticket_count / 40.0) * 0.6) + ((perfect_ticket_count / 40.0) * 0.4)
    mastery_ratio = (strong_topics + max(0, total_topics - weak_topics - strong_topics) * 0.5) / max(total_topics, 1)
    readiness_ratio = (
        0.20 * theory_ratio
        + 0.35 * min(question_ratio, theory_ratio * 0.5)
        + 0.35 * min(ticket_ratio, question_ratio + 0.05)
        + 0.10 * max(0.0, mastery_ratio - 0.4)
    )
    readiness = int(round(max(0.0, min(1.0, readiness_ratio)) * 100))
    readiness_snapshot = readiness_band(readiness)
    user = services.storage.get_user(user_id)
    weekly_summary = build_weekly_summary(services, user_id, timezone_name)

    lines = [
        "Прогресс подготовки",
        f"Теория: {render_bar(completed_lessons, total_lessons)}  ({completed_lessons}/{total_lessons} уроков уверенно)",
        f"Темы: {render_bar(strong_topics, total_topics)}  ({strong_topics} сильных, {weak_topics} слабых)",
        f"Вопросы: {render_bar(solved_questions, total_exam_questions)}  ({solved_questions}/{total_exam_questions} уникальных экзаменационных вопросов решены хотя бы раз)",
        f"Покрытие базы: {render_bar(covered_questions, total_exam_questions)}  ({covered_questions}/{total_exam_questions} уникальных уже видел)",
        f"Всего ответов: {total_attempts}",
        f"Проблемные вопросы: {problem_questions}",
        f"Билеты: {render_bar(solved_ticket_count, 40)}  ({solved_ticket_count}/40 решено, {perfect_ticket_count} без ошибок)",
        f"Средний билет: {int(round(avg_ticket_percent))}%",
        f"Готовность к экзамену: {render_bar(readiness, 100)}  ({readiness_snapshot.band})",
    ]
    if last_ticket:
        lines.append(
            f"Последний билет: {last_ticket['ticket_id'].replace('Билет ', '№')}  ({last_ticket['correct_answers']}/{last_ticket['total_questions']})"
        )
    weakest = weakest_topics(topic_rows, services)
    if weakest:
        lines.append(f"Слабые темы сейчас: {', '.join(weakest)}")
    regressions = detect_regressions(services, user_id)
    if regressions:
        lines.append(f"Регресс за последние попытки: {', '.join(regressions)}")
    due_questions = sum(
        1
        for row in question_rows.values()
        if row.next_review_at and datetime.fromisoformat(row.next_review_at) <= datetime.now(UTC)
    )
    lines.append(f"Вопросов пора повторить: {due_questions}")
    if user and user.goal:
        lines.append(f"Текущий режим цели: {GOAL_LABELS.get(user.goal, user.goal)}")
    lines.append(f"Вывод по готовности: {readiness_snapshot.advice}")
    lines.append("")
    lines.append("Срез за неделю:")
    lines.append(
        f"• {weekly_summary['accuracy_percent']}% точности, {weekly_summary['question_count']} ответов, {weekly_summary['session_count']} сессий"
    )
    if weekly_summary["risk_topic"]:
        lines.append(f"• Риск недели: {weekly_summary['risk_topic']}")
    lines.append("")
    lines.append(build_deadline_text(services, user_id, timezone_name))
    return "\n".join(lines)


def build_today_plan_text(services: BotServices, user_id: int, timezone_name: str) -> str:
    lesson_rows = services.storage.get_lesson_progress(user_id)
    topic_rows = normalize_topic_rows(services.storage.get_topic_progress(user_id))
    question_rows = normalize_question_rows(services.storage.get_question_progress(user_id))
    start_iso, end_iso, local_now = day_bounds_utc(timezone_name)
    today = services.storage.get_today_activity(user_id, start_iso, end_iso)
    exam_question_ids = {q.id for q in services.content.questions.values() if q.exam_ticket}
    covered_questions = services.storage.get_seen_question_ids(user_id) & exam_question_ids

    total_lessons = len(services.content.lessons)
    completed_lessons = sum(1 for row in lesson_rows.values() if row["status"] in {"solid", "strong"})
    remaining_lessons = max(0, total_lessons - completed_lessons)
    deadline = resolve_exam_deadline(services, user_id, local_now.date())
    days_left = max(1, (deadline - local_now.date()).days + 1)
    user = services.storage.get_user(user_id)
    weak_topics = sum(1 for row in topic_rows.values() if row.status == "weak")
    due_question_count = sum(
        1 for row in question_rows.values()
        if row.next_review_at and datetime.fromisoformat(row.next_review_at) <= datetime.now(UTC)
    )

    lesson_target = 0 if remaining_lessons == 0 else min(2, max(1, math.ceil(remaining_lessons / max(1, min(days_left, 7)))))
    question_target = min(35, max(10, math.ceil((max(0, len(exam_question_ids) - len(covered_questions)) + due_question_count) / days_left)))
    practice_target = 1
    ticket_target = 1 if (completed_lessons >= 5 or local_now.date() >= date(2026, 4, 15)) else 0
    repeat_target = 1 if weak_topics > 0 else 0

    progress_values: list[float] = []
    tasks = []
    if lesson_target > 0:
        progress_values.append(min(today["lessons_today"] / lesson_target, 1.0))
        tasks.append(f"• Уроки: {today['lessons_today']}/{lesson_target}")
    else:
        tasks.append("• Уроки: база уже закрыта, можно упираться в практику")
    progress_values.append(min(today["questions_today"] / question_target, 1.0))
    tasks.append(f"• Вопросы: {today['questions_today']}/{question_target}")
    if due_question_count:
        tasks.append(f"• Вопросы к повтору сегодня: {due_question_count}")
    progress_values.append(min(today["practice_today"] / practice_target, 1.0))
    tasks.append(f"• Закрепляющая сессия: {today['practice_today']}/{practice_target}")
    if ticket_target > 0:
        progress_values.append(min(today["tickets_today"] / ticket_target, 1.0))
        tasks.append(f"• Билет: {today['tickets_today']}/{ticket_target}")
    else:
        tasks.append("• Билет: сегодня не обязателен")
    if repeat_target > 0:
        progress_values.append(min(today["practice_today"] / repeat_target, 1.0))
        tasks.append(f"• Повтор слабых мест: {min(today['practice_today'], repeat_target)}/{repeat_target}")

    daily_percent = int(round((sum(progress_values) / max(len(progress_values), 1)) * 100))
    lines = [
        "План на сегодня",
        f"Дневная цель: {render_bar(daily_percent, 100)}",
        f"Режим дня: {recommend_daily_mode(user.goal if user and user.goal else 'steady', days_left)}",
        *tasks,
        *(f"• Фокус: {title}" for title in weakest_topics(topic_rows, services)[:3]),
        "",
        build_deadline_text(services, user_id, timezone_name),
        "",
        build_smart_ticket_line(services, user_id),
        "",
        plan_for_today(services.content),
    ]
    return "\n".join(lines)


def build_deadline_text(services: BotServices, user_id: int, timezone_name: str) -> str:
    local_now = user_local_now(timezone_name)
    deadline = resolve_exam_deadline(services, user_id, local_now.date())
    days_left = max(0, (deadline - local_now.date()).days + 1)
    lesson_rows = services.storage.get_lesson_progress(user_id)
    ticket_stats = services.storage.get_ticket_stats(user_id)
    exam_question_ids = {q.id for q in services.content.questions.values() if q.exam_ticket}
    covered_questions = services.storage.get_seen_question_ids(user_id) & exam_question_ids
    completed_lessons = sum(1 for row in lesson_rows.values() if row["status"] in {"solid", "strong"})
    remaining_lessons = max(0, len(services.content.lessons) - completed_lessons)
    solved_tickets = int(ticket_stats["unique_tickets"] or 0)
    remaining_tickets = max(0, 40 - solved_tickets)
    remaining_questions = max(0, len(exam_question_ids) - len(covered_questions))
    lesson_pace = math.ceil(remaining_lessons / max(days_left, 1)) if remaining_lessons else 0
    question_pace = math.ceil(remaining_questions / max(days_left, 1)) if remaining_questions else 0
    ticket_pace = math.ceil(remaining_tickets / max(days_left, 1)) if remaining_tickets else 0
    user = services.storage.get_user(user_id)
    mode_hint = recommend_daily_mode(user.goal if user and user.goal else "steady", days_left)
    return (
        f"До экзамена ({deadline.isoformat()}) осталось {days_left} дн. "
        f"Чтобы успеть, держи темп примерно: {lesson_pace} урок/день, {question_pace} новых вопросов/день, {ticket_pace} билет/день. "
        f"Текущий режим: {mode_hint}."
    )


def build_smart_ticket_line(services: BotServices, user_id: int) -> str:
    recommendation = recommend_ticket(services, user_id)
    if not recommendation["ticket_id"]:
        return "Рекомендованный билет сейчас: сначала импортируй полную базу билетов."
    return f"Рекомендованный билет сейчас: {recommendation['ticket_id'].replace('Билет ', '№')} — {recommendation['short_why']}"


def recommend_ticket(services: BotServices, user_id: int) -> dict[str, str]:
    ticket_ids = sorted(services.content.ticket_map, key=ticket_sort_key)
    if not ticket_ids:
        return {"ticket_id": "", "why": "Билеты ещё не импортированы.", "short_why": "полная база ещё не подключена"}
    topic_rows = normalize_topic_rows(services.storage.get_topic_progress(user_id))
    best_rows = {
        str(row["ticket_id"]): (int(row["best_correct"] or 0), int(row["total_questions"] or 0))
        for row in services.storage.get_per_ticket_best_scores(user_id)
        if row["ticket_id"]
    }

    weak_weights: dict[str, float] = {}
    for topic_id, snapshot in topic_rows.items():
        if snapshot.status == "weak":
            weak_weights[topic_id] = 3.0
        elif snapshot.status == "learning":
            weak_weights[topic_id] = 2.0
        elif snapshot.status == "solid":
            weak_weights[topic_id] = 0.8
        elif snapshot.status == "strong":
            weak_weights[topic_id] = 0.2

    scored: list[tuple[float, str, str, str]] = []
    for ticket_id in ticket_ids:
        qids = services.content.ticket_map[ticket_id]
        ticket_topics = {topic for qid in qids for topic in services.content.questions[qid].topic_ids}
        overlap = [topic for topic in ticket_topics if topic in weak_weights and topic in services.content.topics]
        overlap_score = sum(weak_weights[topic] for topic in overlap)
        best = best_rows.get(ticket_id)
        if best is None:
            freshness_bonus = 4.0
            progress_penalty = 0.0
            short_why = "не начат и хорошо подходит для нового прохода"
        else:
            correct, total = best
            if total > 0 and correct >= total:
                freshness_bonus = -4.0
                progress_penalty = 3.0
                short_why = "уже закрыт без ошибок"
            elif correct >= 18:
                freshness_bonus = 1.0
                progress_penalty = 0.5
                short_why = "почти закрыт, можно добить до идеала"
            else:
                freshness_bonus = 2.0
                progress_penalty = 0.0
                short_why = "в работе, но ещё не закрыт"

        score = overlap_score + freshness_bonus - progress_penalty
        if not overlap and best is None:
            short_why = "новый билет для расширения покрытия базы"
        elif overlap:
            readable = ", ".join(services.content.topics[topic].short_title for topic in overlap[:3])
            short_why = f"бьёт по темам: {readable}"
        why = short_why
        if best is not None and best[1] > 0:
            why += f". Лучший результат пока {best[0]}/{best[1]}."
        scored.append((score, ticket_id, why, short_why))

    scored.sort(key=lambda item: (item[0], -ticket_sort_key(item[1])[0]), reverse=True)
    _, ticket_id, why, short_why = scored[0]
    return {"ticket_id": ticket_id, "why": why, "short_why": short_why}


async def notification_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    now = datetime.now(UTC)
    for user in services.storage.list_users():
        if not user.notifications_enabled:
            continue
        try:
            try:
                local_now = now.astimezone(ZoneInfo(user.timezone))
            except Exception:
                local_now = now
            local_hour = local_now.hour
            if local_hour < services.settings.notification_window_start or local_hour >= services.settings.notification_window_end:
                continue
            if should_send_weekly_report(services, user, now):
                await context.bot.send_message(
                    chat_id=user.user_id,
                    text=build_weekly_report_text(services, user.user_id, user.timezone),
                    reply_markup=settings_keyboard(),
                )
                services.storage.log_notification(user.user_id, "weekly_report")
                continue
            local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            local_day_end = local_day_start + timedelta(days=1)
            sent_today = services.storage.notifications_sent_between(
                user.user_id,
                local_day_start.astimezone(UTC).isoformat(),
                local_day_end.astimezone(UTC).isoformat(),
            )
            if sent_today >= user.touches_per_day:
                continue
            should_send = random.random() < 0.12
            if not should_send:
                continue
            await send_micro_lesson(context, services, user.user_id)
        except Exception:
            logger.exception("Micro-lesson tick failed for user_id=%s", user.user_id)


async def daily_plan_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    await dispatch_pending_daily_plans(context.bot, services, now=datetime.now(UTC))


async def send_micro_lesson(context: ContextTypes.DEFAULT_TYPE, services: BotServices, user_id: int) -> None:
    user = services.storage.get_user(user_id)
    if user is None:
        return
    topic_rows = normalize_topic_rows(services.storage.get_topic_progress(user_id))
    due_topics = choose_due_topic_ids(services.content, topic_rows, limit=1)
    if due_topics:
        topic_id = due_topics[0]
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Короткое касание на сегодня: верни тему «{services.content.topics[topic_id].short_title}».",
            reply_markup=theory_topic_keyboard([topic_id], {topic_id: services.content.topics[topic_id].short_title}),
        )
        services.storage.log_notification(user_id, "repeat_topic")
        return
    lesson_progress = services.storage.get_lesson_progress(user_id)
    lesson_ids = next_lessons_for_user(services.content, lesson_progress, limit=1)
    if lesson_ids:
        lesson = services.content.lessons[lesson_ids[0]]
        await context.bot.send_message(
            chat_id=user_id,
            text=f"5 минут сейчас: новый блок «{lesson.title}».",
            reply_markup=theory_topic_keyboard([lesson.topic_id], {lesson.topic_id: services.content.topics[lesson.topic_id].short_title}),
        )
        services.storage.log_notification(user_id, "new_lesson")
        return
    question_ids = choose_mixed_questions(services.content, list(services.content.topics)[:5], 1)
    if question_ids:
        question = services.content.questions[question_ids[0]]
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Вопрос дня:\n\n{question.prompt}",
            reply_markup=answer_keyboard(question.id, question.options),
        )
        services.storage.log_notification(user_id, "question_of_day")


async def dispatch_pending_daily_plans(bot, services: BotServices, now: datetime | None = None) -> int:
    sent_count = 0
    current_utc = now or datetime.now(UTC)
    for user in services.storage.list_users():
        if not user.notifications_enabled:
            continue
        try:
            if not should_send_daily_plan(services, user, now=current_utc):
                continue
            await send_daily_plan_via_bot(bot, services, user.user_id, user.timezone)
            sent_count += 1
        except Exception:
            logger.exception("Daily plan tick failed for user_id=%s", user.user_id)
    return sent_count


async def send_daily_plan_via_bot(bot, services: BotServices, user_id: int, timezone_name: str) -> None:
    _start_iso, _end_iso, local_now = day_bounds_utc(timezone_name)
    text = build_today_plan_text(services, user_id, timezone_name)
    sent = None
    for attempt in range(1, SEND_RETRY_ATTEMPTS + 1):
        try:
            sent = await bot.send_message(chat_id=user_id, text=text)
            break
        except (TimedOut, NetworkError):
            if attempt == SEND_RETRY_ATTEMPTS:
                raise
            logger.warning(
                "Retrying daily plan send for user_id=%s after network failure, attempt=%s/%s",
                user_id,
                attempt,
                SEND_RETRY_ATTEMPTS,
            )
            await asyncio.sleep(float(attempt))
    if sent is None:
        raise RuntimeError(f"Daily plan send did not return a message for user_id={user_id}")
    old_message_id, old_date = services.storage.get_daily_plan_pin_state(user_id)
    try:
        if old_message_id and old_date != local_now.date().isoformat():
            await bot.unpin_chat_message(chat_id=user_id, message_id=old_message_id)
    except Exception:
        pass
    try:
        await bot.pin_chat_message(chat_id=user_id, message_id=sent.message_id, disable_notification=True)
        services.storage.set_daily_plan_pin_state(user_id, sent.message_id, local_now.date().isoformat())
    except Exception:
        services.storage.set_daily_plan_pin_state(user_id, None, local_now.date().isoformat())
    services.storage.log_notification(user_id, "daily_plan")
    logger.info("Sent daily plan to user_id=%s for %s", user_id, local_now.date().isoformat())


async def send_daily_plan_message(
    context: ContextTypes.DEFAULT_TYPE,
    services: BotServices,
    user_id: int,
    timezone_name: str,
) -> None:
    await send_daily_plan_via_bot(context.bot, services, user_id, timezone_name)
