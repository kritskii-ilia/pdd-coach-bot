from __future__ import annotations

from pdd_coach_bot.config import load_settings


def test_load_settings_reads_proxy_and_timeouts(monkeypatch) -> None:
    monkeypatch.setenv("PDD_TELEGRAM_PROXY_URL", "socks5://127.0.0.1:1080")
    monkeypatch.setenv("PDD_TELEGRAM_CONNECT_TIMEOUT", "12")
    monkeypatch.setenv("PDD_TELEGRAM_READ_TIMEOUT", "18")
    monkeypatch.setenv("PDD_TELEGRAM_WRITE_TIMEOUT", "19")
    monkeypatch.setenv("PDD_TELEGRAM_POOL_TIMEOUT", "7")

    settings = load_settings()

    assert settings.telegram_proxy_url == "socks5://127.0.0.1:1080"
    assert settings.telegram_connect_timeout == 12.0
    assert settings.telegram_read_timeout == 18.0
    assert settings.telegram_write_timeout == 19.0
    assert settings.telegram_pool_timeout == 7.0
