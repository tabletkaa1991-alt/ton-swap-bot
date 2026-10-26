"""Проверка initData мини-приложения и текст уведомления об успешном обмене.

Здесь только чистая логика без HTTP-сервера: сам сервер (статика, /api/*,
вебхук Telegram) живёт в bot/web.py. Так оба слоя тестируются по отдельности
(unittest не тянет aiohttp/aiogram).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # зависимости нужны только для типов
    from aiogram import Bot

log = logging.getLogger("ton-swap-bot.report")

MAX_AUTH_AGE = 24 * 60 * 60  # сутки: дольше подпись считаем просроченной


def validate_init_data(init_data: str, bot_token: str, max_age: int = MAX_AUTH_AGE) -> dict | None:
    """Проверить подпись initData и вернуть объект пользователя.

    Возвращает None, если данных нет, подпись не сходится или она просрочена.
    """
    if not init_data:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", "")
    if not received_hash:
        return None

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        return None

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        return None
    if auth_date and time.time() - auth_date > max_age:
        return None

    try:
        user = json.loads(parsed.get("user", "{}"))
    except json.JSONDecodeError:
        return None
    return user if isinstance(user, dict) and "id" in user else None


def _format_number(value: float | int, digits: int) -> str:
    text = f"{float(value):,.{digits}f}".replace(",", " ")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _success_text(details: dict) -> str:
    """Текст уведомления: первая строка — результат, дальше детали."""
    direction = details.get("direction", "ton-usdt")
    amount = float(details.get("amount") or 0)
    receive = float(details.get("receive") or 0)
    if direction == "ton-usdt":
        sent, got = f"{_format_number(amount, 4)} TON", f"≈{_format_number(receive, 2)} USDT"
    else:
        sent, got = f"{_format_number(amount, 2)} USDT", f"≈{_format_number(receive, 4)} TON"

    return (
        "✅ <b>Обмен завершился успешно</b>\n\n"
        f"Отправлено: {sent}\n"
        f"К получению: {got}\n\n"
        "Перевод уже ушёл в сеть TON. USDT поступят на ваш кошелёк в течение минуты, "
        "обычно быстрее. Повторно отправлять не нужно — просто дождитесь зачисления.\n\n"
        "Если через 5 минут баланс не изменился, напишите сюда — проверим по хешу транзакции."
    )


async def _send_success(bot: "Bot", chat_id: int, text: str, base_url: str) -> None:
    """Отправить результат ОДНИМ сообщением: галочка-анимация + подпись.

    Telegram не умеет вкладывать стикер в текстовое сообщение, поэтому медиа с
    подписью — единственный способ получить один пузырь с картинкой и текстом.
    """
    if base_url:
        try:
            await bot.send_animation(chat_id, f"{base_url}/check.gif", caption=text)
            return
        except Exception as error:  # noqa: BLE001 - пробуем статичную картинку
            log.warning("анимация не отправилась (%s), пробуем фото", error)
        try:
            await bot.send_photo(chat_id, f"{base_url}/check.png", caption=text)
            return
        except Exception as error:  # noqa: BLE001 - остаётся текст
            log.warning("фото не отправилось (%s), отправляем текст", error)
    await bot.send_message(chat_id, text)
