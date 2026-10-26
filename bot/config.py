"""Конфигурация из переменных окружения (.env или env хостинга)."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


class ConfigError(RuntimeError):
    """Конфигурация неполная или некорректная."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    tonapi_key: str
    network: str
    fee_percent: float
    min_usd: Decimal
    max_usd: Decimal
    webapp_url: str
    proxy_url: str
    admin_chat_id: int | None
    host: str
    port: int
    webhook_url: str
    webhook_secret: str

    @property
    def tonapi_base(self) -> str:
        return "https://testnet.tonapi.io" if self.network == "testnet" else "https://tonapi.io"

    @property
    def limits_text(self) -> str:
        return f"{self.min_usd:g}–{self.max_usd:g} $ за сделку"

    @property
    def public_base(self) -> str:
        """Публичный адрес мини-приложения без завершающего слэша."""
        return self.webapp_url.rstrip("/")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _decimal(name: str, default: str) -> Decimal:
    raw = _env(name, default).replace(",", ".")
    try:
        return Decimal(raw)
    except Exception as exc:  # noqa: BLE001 - нужен один понятный текст ошибки
        raise ConfigError(f"{name} не число: {raw!r}") from exc


def _public_url() -> str:
    """Публичный https-адрес сервиса.

    Порядок: WEBAPP_URL из .env, затем адреса, которые бесплатные хостинги
    выдают сами (Render, Koyeb, Fly). Благодаря этому на новом сервере
    достаточно указать BOT_TOKEN/TONAPI_KEY — кнопка меню и манифест
    TON Connect соберутся от правильного домена без ручной правки.
    """
    for name in ("WEBAPP_URL", "PUBLIC_URL", "RENDER_EXTERNAL_URL", "KOYEB_PUBLIC_DOMAIN", "FLY_APP_NAME"):
        raw = _env(name)
        if not raw:
            continue
        if raw.startswith("https://") or raw.startswith("http://"):
            return raw.rstrip("/")
        if name == "FLY_APP_NAME":
            return f"https://{raw}.fly.dev"
        return f"https://{raw}"
    return ""


def _load_env_file() -> None:
    """Подхватить .env из корня проекта, не перетирая уже заданные переменные.

    Свой парсер вместо python-dotenv: нужен только формат KEY=VALUE, зато
    локальный запуск работает без лишней зависимости. Если ключ повторяется,
    побеждает последняя непустая строка — так правка значения в конце файла
    не «залипает» из-за пустой строки выше. BOM (его добавляет PowerShell
    при Set-Content -Encoding utf8) отрезается: иначе первый ключ не читается.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    parsed: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            parsed[key] = value
    for key, value in parsed.items():
        os.environ.setdefault(key, value)


def load_config() -> Config:
    _load_env_file()
    token = _env("BOT_TOKEN")
    if ":" not in token:
        raise ConfigError("BOT_TOKEN не задан или имеет неверный формат (ожидается 123456:AA...)")

    network = _env("NETWORK", "testnet").lower()
    if network not in {"mainnet", "testnet"}:
        raise ConfigError("NETWORK должен быть mainnet или testnet")

    raw_fee = _env("FEE_PERCENT", "1")
    try:
        fee = float(raw_fee.replace(",", "."))
    except ValueError as exc:
        raise ConfigError(f"FEE_PERCENT не число: {raw_fee!r}") from exc
    if not 0 <= fee <= 10:
        raise ConfigError("FEE_PERCENT должен быть в диапазоне 0–10")

    min_usd = _decimal("MIN_USD", "1")
    max_usd = _decimal("MAX_USD", "5000")
    if min_usd <= 0:
        raise ConfigError("MIN_USD должен быть больше нуля")
    if max_usd <= min_usd:
        raise ConfigError("MAX_USD должен быть больше MIN_USD")

    webapp = _public_url()
    if webapp and not webapp.startswith("https://"):
        raise ConfigError("WEBAPP_URL должен быть https:// — иначе Telegram не откроет WebApp")

    admin_raw = _env("ADMIN_CHAT_ID")
    admin = int(admin_raw) if admin_raw.lstrip("-").isdigit() else None

    raw_port = _env("PORT", "8080")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ConfigError(f"PORT не число: {raw_port!r}") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("PORT должен быть в диапазоне 1–65535")

    webhook_url = _env("WEBHOOK_URL")
    if webhook_url and not webhook_url.startswith("https://"):
        raise ConfigError("WEBHOOK_URL должен быть https:// — Telegram не примет другой")

    # Секрет вебхука Telegram: только A-Za-z0-9_- и не длиннее 256 символов.
    # Если не задан — выводим из токена бота, чтобы вебхук нельзя было дёргать
    # посторонним, даже когда .env минимальный.
    webhook_secret = _env("WEBHOOK_SECRET") or hashlib.sha256(token.encode()).hexdigest()[:32]

    return Config(
        bot_token=token,
        tonapi_key=_env("TONAPI_KEY"),
        network=network,
        fee_percent=fee,
        min_usd=min_usd,
        max_usd=max_usd,
        webapp_url=webapp,
        proxy_url=_env("PROXY_URL"),
        admin_chat_id=admin,
        host=_env("HOST", "0.0.0.0"),
        port=port,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
