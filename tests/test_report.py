"""Тесты проверки initData мини-приложения. Запуск: python -m unittest discover -s tests"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.report import _success_text, validate_init_data  # noqa: E402

TOKEN = "123456:TEST-TOKEN-for-unit-tests"


def make_init_data(token: str, user: dict, auth_date: int | None = None) -> str:
    """Собрать initData так, как это делает Telegram."""
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAF123",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode({**fields, "hash": digest})


class ValidateInitDataTest(unittest.TestCase):
    def setUp(self):
        self.user = {"id": 42, "first_name": "Тест", "username": "tester"}

    def test_valid(self):
        result = validate_init_data(make_init_data(TOKEN, self.user), TOKEN)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 42)

    def test_wrong_token(self):
        self.assertIsNone(validate_init_data(make_init_data(TOKEN, self.user), "999:other"))

    def test_tampered_user(self):
        data = make_init_data(TOKEN, self.user)
        self.assertIsNone(validate_init_data(data.replace("tester", "hacker"), TOKEN))

    def test_expired(self):
        old = int(time.time()) - 3 * 24 * 60 * 60
        self.assertIsNone(validate_init_data(make_init_data(TOKEN, self.user, old), TOKEN))

    def test_missing(self):
        self.assertIsNone(validate_init_data("", TOKEN))
        self.assertIsNone(validate_init_data("auth_date=1&user=%7B%7D", TOKEN))


class SuccessTextTest(unittest.TestCase):
    def test_ton_to_usdt(self):
        text = _success_text({"direction": "ton-usdt", "amount": 1, "receive": 1.2638})
        self.assertIn("Обмен завершился успешно", text)
        self.assertIn("1 TON", text)
        self.assertIn("1.26 USDT", text)

    def test_usdt_to_ton(self):
        text = _success_text({"direction": "usdt-ton", "amount": 2, "receive": 1.58})
        self.assertIn("2 USDT", text)
        self.assertIn("1.58 TON", text)


if __name__ == "__main__":
    unittest.main()
