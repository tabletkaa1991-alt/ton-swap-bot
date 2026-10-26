"""Проверки единого HTTP-сервера без Telegram: маршруты, манифест, статика."""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor"))

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from bot.config import Config  # noqa: E402
from bot.web import create_app  # noqa: E402


class DummyBot:
    """Боту в этих тестах нечего отправлять — проверяем только HTTP-слой."""

    async def send_message(self, *args, **kwargs):
        return None


def make_config(webapp_url: str = "https://swap.example.org") -> Config:
    return Config(
        bot_token="123456789:AAtest",
        tonapi_key="",
        network="testnet",
        fee_percent=2.5,
        min_usd=Decimal("1"),
        max_usd=Decimal("10"),
        webapp_url=webapp_url,
        proxy_url="",
        admin_chat_id=None,
        host="127.0.0.1",
        port=8080,
        webhook_url="",
        webhook_secret="secret",
    )


class HttpAppTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.config = make_config()
        self.client = TestClient(TestServer(create_app(self.config, DummyBot(), bot_username="test_bot")))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_health(self) -> None:
        response = await self.client.get("/api/health")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"ok": True, "bot": "test_bot"})

    async def test_health_alias(self) -> None:
        response = await self.client.get("/health")
        self.assertEqual(response.status, 200)

    async def test_public_config(self) -> None:
        response = await self.client.get("/api/config")
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertEqual(payload["botUsername"], "test_bot")
        self.assertEqual(payload["botUrl"], "https://t.me/test_bot")
        self.assertEqual(payload["feePercent"], 2.5)

    async def test_manifest_built_from_public_url(self) -> None:
        response = await self.client.get("/tonconnect-manifest.json")
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertEqual(payload["url"], "https://swap.example.org/")
        self.assertEqual(payload["iconUrl"], "https://swap.example.org/icon.svg")

    async def test_index_served(self) -> None:
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        text = await response.text()
        self.assertIn("telegram-web-app.js", text.lower())
        self.assertIn("tonconnect", text.lower())

    async def test_report_rejects_missing_init_data(self) -> None:
        response = await self.client.post("/api/report", json={"details": {}})
        self.assertEqual(response.status, 401)

    async def test_unknown_file_not_found(self) -> None:
        response = await self.client.get("/no-such-file.js")
        self.assertEqual(response.status, 404)

    async def test_no_webapp_url_leaves_manifest_default(self) -> None:
        client = TestClient(TestServer(create_app(make_config(""), DummyBot())))
        await client.start_server()
        try:
            response = await client.get("/tonconnect-manifest.json")
            payload = await response.json()
            self.assertEqual(payload["url"], "https://example.com/")
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
