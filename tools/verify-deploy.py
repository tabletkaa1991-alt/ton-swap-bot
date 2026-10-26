"""Проверка развёрнутого стенда: Telegram API, меню, локальные и публичные ручки.

Запуск из корня проекта:

    python tools/verify-deploy.py

Читает BOT_TOKEN/WEBAPP_URL/PORT из .env и ничего секретного не печатает.
Годится и для ноутбука, и для Render/Koyeb/Oracle: если WEBAPP_URL=None —
используется адрес, который бот вычислил сам (PUBLIC_URL/RENDER_EXTERNAL_URL/…).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK = "✓"
FAIL = "✗"


def load_env() -> dict[str, str]:
    """Минимальный парсер .env (BOM, комментарии, кавычки)."""
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            values[key.strip()] = value
    return values


def get_json(url: str, timeout: float = 15.0) -> tuple[int, dict | list | str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - наши адреса
            body = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as error:  # noqa: PERF203 - разные коды важны
        body = error.read().decode("utf-8", "replace")
        status = error.code
    except Exception as error:  # noqa: BLE001 - сеть
        return 0, str(error)
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


def main() -> int:
    env = load_env()
    token = (os.environ.get("BOT_TOKEN") or env.get("BOT_TOKEN") or "").strip()
    if ":" not in token:
        print(f"{FAIL} BOT_TOKEN не найден в .env")
        return 1

    api = f"https://api.telegram.org/bot{token}"
    failures = 0

    status, me = get_json(f"{api}/getMe")
    if status == 200 and isinstance(me, dict) and me.get("ok"):
        print(f"{OK} getMe: @{me['result']['username']} ({me['result'].get('full_name', '')})")
    else:
        print(f"{FAIL} getMe: {status} {me}")
        failures += 1

    status, info = get_json(f"{api}/getWebhookInfo")
    if status == 200 and isinstance(info, dict) and info.get("ok"):
        webhook = info["result"].get("url") or "(нет — polling)"
        print(f"{OK} getWebhookInfo: {webhook}, pending={info['result'].get('pending_update_count', 0)}")
    else:
        print(f"{FAIL} getWebhookInfo: {status} {info}")
        failures += 1

    status, menu = get_json(f"{api}/getChatMenuButton")
    if status == 200 and isinstance(menu, dict) and menu.get("ok"):
        button = menu["result"].get("menu_button") or menu["result"]
        print(f"{OK} кнопка меню: {button}")
    else:
        print(f"{FAIL} getChatMenuButton: {status} {menu}")
        failures += 1

    port = (os.environ.get("PORT") or env.get("PORT") or "8080").strip()
    status, health = get_json(f"http://127.0.0.1:{port}/api/health", timeout=5)
    if status == 200 and isinstance(health, dict) and health.get("ok"):
        print(f"{OK} локально /api/health: {health}")
    else:
        print(f"{FAIL} локально /api/health: {status} {health}")
        failures += 1

    public = (os.environ.get("WEBAPP_URL") or env.get("WEBAPP_URL") or "").strip().rstrip("/")
    if not public:
        print("… WEBAPP_URL пуст: публичные проверки пропущены (локальный режим без туннеля)")
        return 0 if failures == 0 else 1

    status, pub_health = get_json(f"{public}/api/health", timeout=20)
    if status == 200 and isinstance(pub_health, dict) and pub_health.get("ok"):
        print(f"{OK} публично /api/health: {pub_health}")
    else:
        print(f"{FAIL} публично /api/health: {status} {pub_health}")
        failures += 1

    status, manifest = get_json(f"{public}/tonconnect-manifest.json", timeout=20)
    if status == 200 and isinstance(manifest, dict):
        matches = str(manifest.get("url", "")).rstrip("/") == public
        mark = OK if matches else FAIL
        print(f"{mark} манифест TON Connect: url={manifest.get('url')} (ожидался {public}/)")
        if not matches:
            failures += 1
    else:
        print(f"{FAIL} манифест: {status} {manifest}")
        failures += 1

    status, index = get_json(f"{public}/", timeout=20)
    if status == 200 and isinstance(index, str) and "app.js" in index:
        print(f"{OK} мини-приложение отдаётся ({len(index)} байт)")
    else:
        print(f"{FAIL} мини-приложение: {status}")
        failures += 1

    print("ИТОГ: всё работает" if failures == 0 else f"ИТОГ: проблем — {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
