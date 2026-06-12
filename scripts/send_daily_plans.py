from __future__ import annotations

import asyncio
import logging
import sys

from telegram import Bot

from pdd_coach_bot.bot import BotServices, build_httpx_request, dispatch_pending_daily_plans
from pdd_coach_bot.config import load_settings
from pdd_coach_bot.content import load_content
from pdd_coach_bot.storage import Storage


async def _main() -> int:
    settings = load_settings()
    if not settings.bot_token:
        print("PDD_BOT_TOKEN is not set.", file=sys.stderr)
        return 1
    storage = Storage(settings.db_path)
    content = load_content(settings.content_dir, settings.assets_dir)
    services = BotServices(settings=settings, storage=storage, content=content)
    bot = Bot(token=settings.bot_token, request=build_httpx_request(settings))
    sent_count = await dispatch_pending_daily_plans(bot, services)
    logging.getLogger(__name__).info("Daily plan dispatcher finished, sent=%s", sent_count)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(asyncio.run(_main()))
