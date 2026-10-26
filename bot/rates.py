"""Курс TON/USD и расчёт комиссии.

Чистые функции (apply_fee, quote) не зависят от сети и покрыты тестами;
fetch_ton_usd — сетевой вызов tonapi.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # aiohttp нужен только сетевому вызову, не расчётам
    import aiohttp

RATES_PATH = "/v2/rates"


@dataclass(frozen=True)
class Quote:
    """Результат расчёта: сколько получит пользователь и сколько забирает сервис."""

    gross: Decimal
    fee: Decimal
    net: Decimal
    fee_percent: float

    def as_dict(self) -> dict:
        return {
            "gross": str(self.gross),
            "fee": str(self.fee),
            "net": str(self.net),
            "fee_percent": self.fee_percent,
        }


def apply_fee(amount: Decimal | float | str, fee_percent: float) -> Quote:
    """Отделить комиссию сервиса от суммы сделки.

    Комиссия округляется вверх до 9 знаков, остаток — вниз: пользователь
    никогда не получает больше, чем позволяет сумма.
    """
    total = Decimal(str(amount))
    if total <= 0:
        raise ValueError("сумма должна быть положительной")
    if not 0 <= fee_percent <= 100:
        raise ValueError("комиссия должна быть в диапазоне 0–100")

    fee = (total * Decimal(str(fee_percent)) / Decimal(100)).quantize(Decimal("0.000000001"))
    net = (total - fee).quantize(Decimal("0.000000001"), rounding=ROUND_DOWN)
    return Quote(gross=total, fee=fee, net=net, fee_percent=fee_percent)


def to_usd(ton_amount: Decimal | float | str, ton_usd: Decimal | float | str) -> Decimal:
    """Перевести TON в USD по курсу."""
    return (Decimal(str(ton_amount)) * Decimal(str(ton_usd))).quantize(Decimal("0.01"))


def to_ton(usd_amount: Decimal | float | str, ton_usd: Decimal | float | str) -> Decimal:
    """Перевести USD в TON по курсу."""
    price = Decimal(str(ton_usd))
    if price <= 0:
        raise ValueError("курс должен быть положительным")
    return (Decimal(str(usd_amount)) / price).quantize(Decimal("0.0001"))


class LimitError(ValueError):
    """Сумма вне разрешённого диапазона."""


def check_limits(
    usd_value: Decimal | float | str,
    min_usd: Decimal | float | str,
    max_usd: Decimal | float | str,
) -> Decimal:
    """Проверить сумму сделки в долларовом эквиваленте.

    Возвращает сумму, если она в диапазоне, иначе бросает LimitError с готовым
    текстом для пользователя (бот и мини-приложение показывают его как есть).
    """
    value = Decimal(str(usd_value))
    low, high = Decimal(str(min_usd)), Decimal(str(max_usd))
    if value <= 0:
        raise LimitError("Сумма должна быть больше нуля.")
    if value < low:
        raise LimitError(f"Минимальная сумма сделки — {low:g} $.")
    if value > high:
        raise LimitError(f"Максимальная сумма сделки — {high:g} $. Разбейте обмен на несколько.")
    return value


def format_ton(value: Decimal | float | str, digits: int = 4) -> str:
    """Отформатировать количество TON: 1234.5 → «1 234.5»."""
    text = f"{Decimal(str(value)):,.{digits}f}".replace(",", " ")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_usd(value: Decimal | float | str) -> str:
    return f"{Decimal(str(value)):,.2f}".replace(",", " ") + " $"


async def fetch_ton_usd(
    session: "aiohttp.ClientSession",
    base_url: str,
    api_key: str = "",
    *,
    timeout: float = 8.0,
) -> Decimal:
    """Получить цену TON в USD с tonapi.

    Бросает RuntimeError при сетевой ошибке или неожиданном ответе — вызывающий
    код обязан показать пользователю понятное сообщение, а не «0.00».
    """
    import aiohttp

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{base_url}{RATES_PATH}?tokens=ton&currencies=usd"
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status != 200:
                raise RuntimeError(f"tonapi вернул {response.status}")
            payload = await response.json()
    except aiohttp.ClientError as exc:  # сеть, TLS, таймаут
        raise RuntimeError(f"не удалось получить курс: {exc}") from exc

    try:
        price = payload["rates"]["TON"]["prices"]["USD"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("неожиданный формат ответа tonapi") from exc
    if not price:
        raise RuntimeError("tonapi не вернул цену TON")
    return Decimal(str(price))
