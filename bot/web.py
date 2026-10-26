"""Единый HTTP-сервер: статика мини-приложения, /api/* и вебхук Telegram.

Почему один процесс и один порт: бесплатные хостинги (Render, Koyeb, Fly)
дают ровно один публичный https-порт на сервис. Здесь на нём живёт всё —
`/` отдаёт мини-приложение, `/api/config` и `/api/report` — его запросы,
`/api/health` — проверка живости, `/telegram/webhook` — апдейты Telegram
(если включён режим вебхука). Никакого node-сервера и Caddy для статики
больше не нужно, а значит меньше точек отказа.
"""
from __future__ import annotations

import hmac
import logging
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # для типов; в рантайме aiogram/aiohttp нужны только серверу
    from aiogram import Bot, Dispatcher
    from aiohttp import web

    from .config import Config

log = logging.getLogger("ton-swap-bot.web")

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"

# mimetypes на Windows знает не всё (например .webp в старых сборках Python),
# поэтому важные для мини-приложения типы заданы явно.
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
}

# Эти файлы меняются от площадки к площадке, кешировать их нельзя.
_NO_STORE = {"index.html", "tonconnect-manifest.json"}


def _content_type(path: Path) -> str:
    return _MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _manifest(public_url: str) -> dict:
    base = public_url.rstrip("/")
    if not base:
        base = "https://example.com"
    return {
        "url": f"{base}/",
        "name": "TON ⇄ USDT",
        "iconUrl": f"{base}/icon.svg",
    }


def create_app(
    config: "Config",
    bot: "Bot",
    bot_username: str = "",
    dispatcher: "Dispatcher | None" = None,
    webhook_secret: str = "",
) -> "web.Application":
    """Собрать aiohttp-приложение. `dispatcher` != None включает приём вебхука."""
    from aiohttp import web

    from .report import _send_success, _success_text, validate_init_data

    app = web.Application()
    public_base = config.public_base

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "bot": bot_username})

    async def public_config(_request: web.Request) -> web.Response:
        """Публичные параметры для мини-приложения: ссылка на бота и лимиты."""
        return web.json_response(
            {
                "botUsername": bot_username,
                "botUrl": f"https://t.me/{bot_username}" if bot_username else "",
                "feePercent": config.fee_percent,
                "minUsd": float(config.min_usd),
                "maxUsd": float(config.max_usd),
            }
        )

    async def report(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"ok": False, "error": "bad json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"ok": False, "error": "bad json"}, status=400)

        user = validate_init_data(str(payload.get("initData", "")), config.bot_token)
        if user is None:
            log.warning("отчёт отклонён: подпись initData не сошлась")
            return web.json_response({"ok": False, "error": "invalid initData"}, status=401)

        chat_id = int(user["id"])
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        try:
            await _send_success(bot, chat_id, _success_text(details), public_base)
        except Exception as error:  # noqa: BLE001 - сеть/лимиты Telegram
            log.exception("не удалось отправить уведомление: %s", error)
            return web.json_response({"ok": False, "error": "telegram failed"}, status=502)

        log.info("уведомление отправлено chat_id=%s details=%s", chat_id, details)
        return web.json_response({"ok": True})

    async def telegram_webhook(request: web.Request) -> web.Response:
        if webhook_secret:
            received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(received, webhook_secret):
                raise web.HTTPForbidden()
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"ok": False, "error": "bad json"}, status=400)

        from aiogram.types import Update

        try:
            update = Update.model_validate(body, context={"bot": bot})
            await dispatcher.feed_update(bot, update)
        except Exception:  # noqa: BLE001 - отвечаем 200, чтобы Telegram не ретраил
            log.exception("ошибка обработки апдейта")
        return web.json_response({"ok": True})

    async def static_files(request: web.Request) -> web.StreamResponse:
        relative = request.match_info.get("path", "").strip("/")
        target = (WEBAPP_DIR / relative).resolve() if relative else WEBAPP_DIR / "index.html"
        try:
            target.relative_to(WEBAPP_DIR)
        except ValueError:
            raise web.HTTPForbidden()
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            raise web.HTTPNotFound()

        # Манифест TON Connect собирается на лету: адрес меняется при каждом
        # переезде (туннель, onrender.com, свой домен), а файл в webapp/ статичен.
        if target.name == "tonconnect-manifest.json":
            return web.json_response(_manifest(public_base), headers={"cache-control": "no-store"})

        headers = {
            "cache-control": "no-store" if target.name in _NO_STORE else "public, max-age=3600",
            "x-content-type-options": "nosniff",
        }
        return web.FileResponse(target, headers=headers)

    app.router.add_get("/api/health", health)
    app.router.add_get("/health", health)
    app.router.add_get("/api/config", public_config)
    app.router.add_post("/api/report", report)
    if dispatcher is not None:
        app.router.add_post("/telegram/webhook", telegram_webhook)
    app.router.add_get("/{path:.*}", static_files)
    return app
