from __future__ import annotations

import logging
import os
import sys

from .bot import BotServices, create_application
from .config import load_settings
from .content import load_content
from .storage import Storage


def main() -> int:
    logging.basicConfig(
        level=getattr(logging, os.getenv("PDD_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    if not settings.bot_token:
        print("PDD_BOT_TOKEN is not set. Copy .env.example to .env and fill the token.", file=sys.stderr)
        return 1
    storage = Storage(settings.db_path)
    content = load_content(settings.content_dir, settings.assets_dir)
    app = create_application(BotServices(settings=settings, storage=storage, content=content))
    app.run_polling()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
