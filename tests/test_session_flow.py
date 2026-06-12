from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pdd_coach_bot.bot import (
    BotServices,
    continue_session,
    process_answer,
    render_question_text,
    send_current_question,
    start_quiz_session,
)
from pdd_coach_bot.content import ContentBundle
from pdd_coach_bot.models import Question, Topic
from pdd_coach_bot.storage import Storage


class _FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, object]] = []

    async def send_message(self, chat_id: int, text: str, reply_markup=None, parse_mode=None):
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
                "parse_mode": parse_mode,
            }
        )
        return SimpleNamespace(message_id=len(self.sent_messages))


class _FakeMessage:
    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id
        self.replies: list[dict[str, object]] = []

    async def reply_text(self, text: str, reply_markup=None) -> None:
        self.replies.append({"text": text, "reply_markup": reply_markup})


class _FakeQuery:
    def __init__(self, user_id: int, chat_id: int) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _FakeMessage(chat_id)
        self.edits: list[dict[str, object]] = []

    async def edit_message_text(self, text: str, reply_markup=None) -> None:
        self.edits.append({"text": text, "reply_markup": reply_markup})


def _services(tmp_path: Path) -> BotServices:
    storage = Storage(tmp_path / "bot.sqlite3")
    storage.upsert_user(
        tg_user_id=42,
        first_name="Tester",
        timezone="Europe/Moscow",
        intensity="medium",
        touches_per_day=5,
    )
    content = ContentBundle(
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
            ),
            "q2": Question(
                id="q2",
                topic_ids=["priority_rules"],
                prompt="Можно ли продолжать движение?",
                options=["Да", "Нет"],
                correct_index=1,
                explanation="Продолжать движение нельзя до изменения условий.",
                source="test",
            ),
        },
        ticket_map={"1": ["q1", "q2"]},
        study_plan=[],
    )
    return BotServices(settings=None, storage=storage, content=content)  # type: ignore[arg-type]


def test_continue_session_reuses_review_message_for_next_question(tmp_path: Path) -> None:
    async def scenario() -> None:
        services = _services(tmp_path)
        bot = _FakeBot()
        context = SimpleNamespace(bot=bot)

        await start_quiz_session(42, 99, context, services, "topic", ["q1", "q2"], ["priority_rules"])
        await send_current_question(99, 42, context, services)

        assert len(bot.sent_messages) == 1
        assert bot.sent_messages[0]["text"] == render_question_text(
            "Кому уступить дорогу?",
            ["Легковому", "Никому"],
            1,
            2,
        )

        query = _FakeQuery(user_id=42, chat_id=99)
        await process_answer(query, context, services, "q1", 0)

        assert len(query.edits) == 1
        assert "Верно." in str(query.edits[0]["text"])
        callback_data = [
            button.callback_data
            for row in query.edits[0]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data is not None
        ]
        assert "continue:topic:next" in callback_data
        assert "deep_explain:q1" in callback_data

        mode, payload = services.storage.get_session(42)
        assert mode == "topic"
        assert payload["position"] == 1

        await continue_session(42, 99, context, services, "topic", "next", query=query)

        assert len(bot.sent_messages) == 1
        assert len(query.edits) == 2
        assert query.edits[1]["text"] == render_question_text(
            "Можно ли продолжать движение?",
            ["Да", "Нет"],
            2,
            2,
        )

    asyncio.run(scenario())
