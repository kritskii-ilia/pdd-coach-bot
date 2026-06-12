from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _resolve_path(raw_value: str, root: Path) -> Path:
    path = Path(raw_value)
    if path.is_absolute():
        return path
    return root / path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    bot_token: str
    db_path: Path
    content_dir: Path
    assets_dir: Path
    telegram_proxy_url: str | None
    default_timezone: str
    notification_window_start: int
    notification_window_end: int
    default_intensity: str
    default_touches_per_day: int
    telegram_connect_timeout: float
    telegram_read_timeout: float
    telegram_write_timeout: float
    telegram_pool_timeout: float


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent.parent
    bot_token = os.getenv("PDD_BOT_TOKEN", "").strip()
    telegram_proxy_url = os.getenv("PDD_TELEGRAM_PROXY_URL", "").strip() or None
    return Settings(
        project_root=project_root,
        bot_token=bot_token,
        db_path=_resolve_path(os.getenv("PDD_DB_PATH", "./data/pdd_coach.sqlite3"), project_root),
        content_dir=_resolve_path(os.getenv("PDD_CONTENT_DIR", "./content"), project_root),
        assets_dir=_resolve_path(os.getenv("PDD_ASSETS_DIR", "./assets"), project_root),
        telegram_proxy_url=telegram_proxy_url,
        default_timezone=os.getenv("PDD_DEFAULT_TIMEZONE", "Europe/Moscow"),
        notification_window_start=int(os.getenv("PDD_NOTIFICATION_WINDOW_START", "8")),
        notification_window_end=int(os.getenv("PDD_NOTIFICATION_WINDOW_END", "22")),
        default_intensity=os.getenv("PDD_DEFAULT_INTENSITY", "medium"),
        default_touches_per_day=int(os.getenv("PDD_DEFAULT_TOUCHES_PER_DAY", "5")),
        telegram_connect_timeout=float(os.getenv("PDD_TELEGRAM_CONNECT_TIMEOUT", "20")),
        telegram_read_timeout=float(os.getenv("PDD_TELEGRAM_READ_TIMEOUT", "30")),
        telegram_write_timeout=float(os.getenv("PDD_TELEGRAM_WRITE_TIMEOUT", "30")),
        telegram_pool_timeout=float(os.getenv("PDD_TELEGRAM_POOL_TIMEOUT", "20")),
    )
