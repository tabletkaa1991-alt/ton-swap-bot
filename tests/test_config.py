"""Конфигурация: определение публичного адреса, вебхук, порт."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor"))

from bot.config import ConfigError, _public_url, load_config  # noqa: E402

BASE_ENV = {
    "BOT_TOKEN": "123456789:AAtest",
    "TONAPI_KEY": "key",
    "NETWORK": "mainnet",
    "FEE_PERCENT": "2.5",
    "MIN_USD": "1",
    "MAX_USD": "10",
    "SERVICE_WALLET": "UQtest",
    "WEBAPP_URL": "",
    "PROXY_URL": "",
    "ADMIN_CHAT_ID": "",
    "PORT": "",
    "WEBHOOK_URL": "",
    "WEBHOOK_SECRET": "",
}


def load_with(**overrides):
    env = {**BASE_ENV, **overrides}
    with mock.patch.dict(os.environ, env, clear=True), mock.patch("bot.config._load_env_file"):
        return load_config()


class PublicUrlTest(unittest.TestCase):
    def test_webapp_url_wins_and_slash_stripped(self) -> None:
        with mock.patch.dict(os.environ, {"WEBAPP_URL": "https://swap.example.org/"}, clear=True):
            self.assertEqual(_public_url(), "https://swap.example.org")

    def test_render_external_url(self) -> None:
        with mock.patch.dict(os.environ, {"RENDER_EXTERNAL_URL": "https://bot-abc.onrender.com"}, clear=True):
            self.assertEqual(_public_url(), "https://bot-abc.onrender.com")

    def test_koyeb_domain_without_scheme(self) -> None:
        with mock.patch.dict(os.environ, {"KOYEB_PUBLIC_DOMAIN": "bot.koyeb.app"}, clear=True):
            self.assertEqual(_public_url(), "https://bot.koyeb.app")

    def test_empty_when_nothing_set(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_public_url(), "")


class LoadConfigTest(unittest.TestCase):
    def test_platform_url_used_for_webapp(self) -> None:
        config = load_with(RENDER_EXTERNAL_URL="https://bot-abc.onrender.com")
        self.assertEqual(config.webapp_url, "https://bot-abc.onrender.com")
        self.assertEqual(config.public_base, "https://bot-abc.onrender.com")

    def test_webhook_secret_derived_from_token(self) -> None:
        config = load_with(WEBAPP_URL="https://swap.example.org")
        self.assertEqual(len(config.webhook_secret), 32)
        self.assertTrue(config.webhook_secret.isalnum())

    def test_explicit_webhook_secret(self) -> None:
        config = load_with(WEBHOOK_SECRET="my_secret-123")
        self.assertEqual(config.webhook_secret, "my_secret-123")

    def test_http_webhook_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            load_with(WEBHOOK_URL="http://swap.example.org/telegram/webhook")

    def test_bad_port_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            load_with(PORT="not-a-port")

    def test_defaults(self) -> None:
        config = load_with(WEBAPP_URL="https://swap.example.org/")
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.webhook_url, "")


if __name__ == "__main__":
    unittest.main()
