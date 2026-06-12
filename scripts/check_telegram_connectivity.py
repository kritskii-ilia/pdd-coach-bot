from __future__ import annotations

import asyncio
import logging
import sys

from telegram import Bot

from pdd_coach_bot.bot import build_httpx_request
from pdd_coach_bot.config import load_settings


async def _main() -> int:
    settings = load_settings()
    if not settings.bot_token:
        print("PDD_BOT_TOKEN is not set.", file=sys.stderr)
        return 1
    bot = Bot(token=settings.bot_token, request=build_httpx_request(settings))
    me = await bot.get_me()
    proxy_label = settings.telegram_proxy_url or "direct"
    print(f"Telegram OK via {proxy_label}: @{me.username}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(asyncio.run(_main()))
