"""Точка входа: HTTP-сервер мини-приложения + бот в режиме polling или webhook.

Запуск:  python -m bot.main   (нужен .env рядом с пакетом или переменные окружения)

Один процесс слушает PORT (по умолчанию 8080) и отдаёт мини-приложение,
/api/* и, если задан WEBHOOK_URL, /telegram/webhook. Без WEBHOOK_URL бот
работает через long polling — так он живёт за NAT и на бесплатных хостингах,
которым не нужен входящий вебхук.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from aiohttp import web

from .config import Config, ConfigError, load_config
from .rates import apply_fee, fetch_ton_usd, format_ton, format_usd, to_ton
from .web import create_app

log = logging.getLogger("ton-swap-bot")
router = Router()

WELCOME = (
    "👋 Это обменник <b>TON ⇄ USDT</b>.\n\n"
    "Комиссия сервиса — {fee}%, лимит сделки — {limits}.\n"
    "Обмен происходит в вашем кошельке: ключи остаются у вас, "
    "мы не храним средства."
)

NO_WEBAPP = (
    "Обменник ещё не подключён: администратору нужно указать WEBAPP_URL "
    "(https-адрес мини-приложения) и перезапустить бота."
)


def keyboard(config: Config) -> InlineKeyboardMarkup | None:
    if not config.webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💱 Открыть обменник", web_app=WebAppInfo(url=config.webapp_url))]]
    )


async def current_rate(config: Config, session: aiohttp.ClientSession) -> str:
    """Строка с курсом, лимитами и примером расчёта."""
    try:
        price = await fetch_ton_usd(session, config.tonapi_base, config.tonapi_key)
    except RuntimeError as exc:
        log.warning("курс недоступен: %s", exc)
        return "Курс сейчас недоступен, попробуйте через минуту."
    one_ton = apply_fee(1, config.fee_percent)
    min_ton = to_ton(config.min_usd, price)
    max_ton = to_ton(config.max_usd, price)
    return (
        f"1 TON ≈ <b>{format_usd(price)}</b>\n"
        f"Комиссия сервиса: {config.fee_percent:g}% "
        f"(с 1 TON: {format_ton(one_ton.fee, 6)} TON, на руки {format_ton(one_ton.net, 6)} TON)\n"
        f"Лимит сделки: {config.limits_text} ≈ "
        f"{format_ton(min_ton, 2)}–{format_ton(max_ton, 2)} TON"
    )


@router.message(CommandStart())
async def on_start(message: Message, config: Config, session: aiohttp.ClientSession) -> None:
    await message.answer(WELCOME.format(fee=f"{config.fee_percent:g}", limits=config.limits_text))
    if config.webapp_url:
        await message.answer("Нажмите кнопку, чтобы открыть обменник:", reply_markup=keyboard(config))
    else:
        await message.answer(NO_WEBAPP)
    await message.answer(await current_rate(config, session))


@router.message(Command("rate"))
async def on_rate(message: Message, config: Config, session: aiohttp.ClientSession) -> None:
    await message.answer(await current_rate(config, session))


@router.message(Command("fee"))
async def on_fee(message: Message, config: Config) -> None:
    await message.answer(
        f"Комиссия сервиса: <b>{config.fee_percent:g}%</b>\n"
        f"Лимит сделки: <b>{config.limits_text}</b>\n"
        f"Сеть: {config.network}\n"
        "Сделка подписывается вашим кошельком — бот не хранит средства."
    )


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(
        "/start — открыть обменник\n"
        "/rate — текущий курс TON/USD\n"
        "/fee — комиссия и сеть\n\n"
        "Бот не принимает фиат и не хранит ключи: обмен идёт в вашем кошельке."
    )


@router.message(F.text)
async def on_text(message: Message) -> None:
    await message.answer("Не понял. Нажмите /start или /help.")


async def _run_server(app: web.Application, config: Config) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.host, config.port)
    await site.start()
    return runner


def _install_stop_handlers(stop: asyncio.Event) -> None:
    """SIGTERM (docker stop / Render) и SIGINT (Ctrl+C) — мягкая остановка."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError, AttributeError):
            # Windows: SIGTERM через add_signal_handler не поддерживается —
            # там достаточно KeyboardInterrupt, его обрабатывает asyncio.run.
            pass


async def main() -> int:
    # Консоль Windows по умолчанию cp1251: без этого эмодзи в логах роняют процесс.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        config = load_config()
    except ConfigError as exc:
        log.error("конфигурация: %s", exc)
        return 2

    # api.telegram.org в РФ периодически недоступен: если сеть не пускает, бот
    # не сможет ни получить апдейты, ни ответить. Предупреждаем сразу.
    session_kwargs = {}
    if config.proxy_url:
        session_kwargs["session"] = AiohttpSession(proxy=config.proxy_url)
        log.info("Telegram API через прокси: %s", config.proxy_url.split("@")[-1])
    bot = Bot(
        config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        **session_kwargs,
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    app_session = aiohttp.ClientSession()
    dispatcher["config"] = config
    dispatcher["session"] = app_session

    try:
        me = await bot.get_me()
    except Exception as error:  # noqa: BLE001 - нет сети/прокси/токен отозван
        log.error(
            "не удалось связаться с Telegram API (%s). Если api.telegram.org недоступен, "
            "включите VPN/прокси и задайте PROXY_URL в .env",
            error,
        )
        await app_session.close()
        await bot.session.close()
        return 3

    log.info("запущен @%s (%s), сеть %s", me.username, me.full_name, config.network)

    app = create_app(
        config,
        bot,
        bot_username=me.username or "",
        dispatcher=dispatcher if config.webhook_url else None,
        webhook_secret=config.webhook_secret,
    )
    runner = await _run_server(app, config)
    log.info(
        "HTTP на %s:%s — мини-приложение и /api/*%s",
        config.host,
        config.port,
        f", публичный адрес {config.webapp_url}" if config.webapp_url else "",
    )

    # Кнопка меню в шапке чата ведёт в мини-приложение: адрес меняется при
    # каждом переезде (туннель или новый домен), поэтому ставим её на старте.
    if config.webapp_url:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Обмен", web_app=WebAppInfo(url=config.webapp_url))
            )
            log.info("кнопка меню: %s", config.webapp_url)
        except Exception as error:  # noqa: BLE001 - не критично для работы
            log.warning("кнопку меню выставить не удалось: %s", error)

    stop = asyncio.Event()
    _install_stop_handlers(stop)
    polling_task: asyncio.Task | None = None

    try:
        if config.webhook_url:
            await bot.set_webhook(
                config.webhook_url,
                secret_token=config.webhook_secret or None,
                drop_pending_updates=False,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
            log.info("режим webhook: %s", config.webhook_url)
            await stop.wait()
        else:
            # После переезда с вебхука на polling старый вебхук блокирует
            # getUpdates, поэтому снимаем его явно.
            with contextlib.suppress(Exception):
                await bot.delete_webhook(drop_pending_updates=False)
            log.info("режим polling")
            polling_task = asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False))
            await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if polling_task is not None:
            polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await polling_task
        if config.webhook_url:
            with contextlib.suppress(Exception):
                await bot.delete_webhook(drop_pending_updates=False)
        await runner.cleanup()
        await app_session.close()
        await bot.session.close()
        log.info("остановлен")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
