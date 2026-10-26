"""Проверка конфигурации без запуска бота: python tools/check-config.py

Печатает только несекретные поля; токен и ключ маскируются.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Консоль Windows по умолчанию cp1251 — без этого кириллица и «✓» роняют вывод.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from bot.config import ConfigError, load_config  # noqa: E402
from bot.rates import apply_fee, format_ton, to_ton  # noqa: E402


def mask(value: str) -> str:
    return f"{value[:4]}…{value[-3:]} ({len(value)} симв.)" if value else "НЕТ"


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"✗ конфигурация: {exc}")
        return 1

    price = 1.2626  # только для примера расчёта, живой курс берётся с tonapi
    one = apply_fee(1, config.fee_percent)
    print("✓ конфигурация загружена")
    print(f"  BOT_TOKEN   = {mask(config.bot_token)}")
    print(f"  TONAPI_KEY  = {mask(config.tonapi_key)}")
    print(f"  NETWORK     = {config.network} ({config.tonapi_base})")
    print(f"  FEE         = {config.fee_percent:g}%")
    print(f"  Лимиты      = {config.limits_text}")
    print(f"  WEBAPP_URL  = {config.webapp_url or 'не задан (кнопка WebApp скрыта)'}")
    print(f"  Пример: 1 TON → комиссия {format_ton(one.fee, 6)} TON, на руки {format_ton(one.net, 6)} TON")
    print(
        f"  Лимит в TON при курсе {price}: "
        f"{format_ton(to_ton(config.min_usd, price), 2)}–{format_ton(to_ton(config.max_usd, price), 2)} TON"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
