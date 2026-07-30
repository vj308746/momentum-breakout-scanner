from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from telegram_alert import validate_telegram_configuration


class TelegramConfigurationTests(unittest.TestCase):
    def test_bot_prefix_is_rejected_before_network_call(self) -> None:
        with (
            patch("telegram_alert.TELEGRAM_BOT_TOKEN", "bot123:ABC"),
            patch("telegram_alert.TELEGRAM_CHAT_ID", "123456"),
            patch("telegram_alert.requests.get") as request,
        ):
            with self.assertRaisesRegex(RuntimeError, "invalid format"):
                validate_telegram_configuration()
            request.assert_not_called()

    def test_valid_configuration_calls_get_me(self) -> None:
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "ok": True,
            "result": {"username": "scanner_bot"},
        }
        with (
            patch(
                "telegram_alert.TELEGRAM_BOT_TOKEN",
                "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_123",
            ),
            patch("telegram_alert.TELEGRAM_CHAT_ID", "-1001234567890"),
            patch(
                "telegram_alert.requests.get",
                return_value=response,
            ) as request,
        ):
            result = validate_telegram_configuration()
        self.assertTrue(result["ok"])
        self.assertIn("/getMe", request.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
