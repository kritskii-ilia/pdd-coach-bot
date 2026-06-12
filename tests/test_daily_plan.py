from __future__ import annotations

from datetime import UTC, datetime

from pdd_coach_bot.bot import BotServices, should_send_daily_plan
from pdd_coach_bot.storage import UserState


class _StorageStub:
    def __init__(self, pinned_date: str | None = None, sent_count: int = 0) -> None:
        self.pinned_date = pinned_date
        self.sent_count = sent_count

    def get_daily_plan_pin_state(self, tg_user_id: int) -> tuple[int | None, str | None]:
        del tg_user_id
        return None, self.pinned_date

    def notifications_sent_between(
        self,
        tg_user_id: int,
        start_iso: str,
        end_iso: str,
        notification_type: str | None = None,
    ) -> int:
        del tg_user_id, start_iso, end_iso, notification_type
        return self.sent_count


def _services(storage: _StorageStub) -> BotServices:
    return BotServices(settings=None, storage=storage, content=None)  # type: ignore[arg-type]


def _user() -> UserState:
    return UserState(
        user_id=397756202,
        first_name="Ilusha",
        timezone="Europe/Moscow",
        intensity="medium",
        touches_per_day=5,
        notifications_enabled=True,
        exam_date=None,
        goal="steady",
        study_minutes=20,
        experience_level="partial",
        onboarding_step="done",
    )


def test_should_send_daily_plan_allows_daytime_catchup() -> None:
    services = _services(_StorageStub())
    now = datetime(2026, 4, 13, 12, 30, tzinfo=UTC)

    assert should_send_daily_plan(services, _user(), now=now) is True


def test_should_send_daily_plan_skips_if_already_pinned_today() -> None:
    services = _services(_StorageStub(pinned_date="2026-04-13"))
    now = datetime(2026, 4, 13, 8, 0, tzinfo=UTC)

    assert should_send_daily_plan(services, _user(), now=now) is False


def test_should_send_daily_plan_skips_after_evening_cutoff() -> None:
    services = _services(_StorageStub())
    now = datetime(2026, 4, 13, 19, 5, tzinfo=UTC)

    assert should_send_daily_plan(services, _user(), now=now) is False
