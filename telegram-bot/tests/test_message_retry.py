"""Unit tests for send_message / edit_message retry logic in handlers/commands.py.

Run with: python3 -m unittest telegram-bot/tests/test_message_retry.py -v
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "telegram-bot"))

from telegram.error import NetworkError, TimedOut

from handlers import commands
from handlers.commands import (
    MESSAGE_MAX_ATTEMPTS,
    MESSAGE_RETRY_BASE_DELAY,
    edit_message,
    send_message,
)


class _BaseRetryTest(unittest.IsolatedAsyncioTestCase):
    """Shared test scaffolding: patch global telegram_bot and fast retry delay."""

    async def asyncSetUp(self):
        # Patch global telegram_bot
        self._bot_patcher = patch.object(commands, "telegram_bot", MagicMock())
        self._bot_patcher.start()

        # Make retry delay essentially zero so tests run fast
        self._delay_patcher = patch.object(commands, "MESSAGE_RETRY_BASE_DELAY", 0.0)
        self._delay_patcher.start()

        # Capture log records
        self._log_records = []
        self._log_handler = MagicMock(level=0)
        self._log_handler.handle = MagicMock(side_effect=lambda r: self._log_records.append(r))
        logger = commands.logger
        logger.addHandler(self._log_handler)
        logger.setLevel("DEBUG")

    async def asyncTearDown(self):
        self._bot_patcher.stop()
        self._delay_patcher.stop()
        commands.logger.removeHandler(self._log_handler)


class SendMessageRetryTest(_BaseRetryTest):
    async def test_success_on_first_attempt(self):
        bot = commands.telegram_bot
        bot.send_message = AsyncMock(return_value="ok")
        result = await send_message(123, "hello")
        self.assertEqual(result, "ok")
        self.assertEqual(bot.send_message.await_count, 1)
        self.assertFalse(self._log_records, "no retry logs expected")

    async def test_retry_on_NetworkError_then_succeed(self):
        bot = commands.telegram_bot
        bot.send_message = AsyncMock(
            side_effect=[NetworkError("net1"), NetworkError("net2"), "ok"]
        )
        result = await send_message(123, "hi")
        self.assertEqual(result, "ok")
        self.assertEqual(bot.send_message.await_count, 3)
        # Should have 2 retry warnings
        warnings = [r for r in self._log_records if r.levelname == "WARNING"]
        self.assertEqual(len(warnings), 2, f"expected 2 retry logs, got {warnings}")

    async def test_retry_on_TimedOut_then_succeed(self):
        bot = commands.telegram_bot
        bot.send_message = AsyncMock(
            side_effect=[TimedOut(), "ok"]
        )
        result = await send_message(123, "hi")
        self.assertEqual(result, "ok")
        self.assertEqual(bot.send_message.await_count, 2)

    async def test_raise_after_max_attempts(self):
        bot = commands.telegram_bot
        bot.send_message = AsyncMock(side_effect=NetworkError("down"))
        with self.assertRaises(NetworkError):
            await send_message(123, "hi")
        self.assertEqual(bot.send_message.await_count, MESSAGE_MAX_ATTEMPTS)
        # Last log should be ERROR
        errors = [r for r in self._log_records if r.levelname == "ERROR"]
        self.assertEqual(len(errors), 1, "expected exactly 1 error log")

    async def test_non_network_error_not_retried(self):
        bot = commands.telegram_bot
        bot.send_message = AsyncMock(side_effect=ValueError("bug"))
        with self.assertRaises(ValueError):
            await send_message(123, "hi")
        self.assertEqual(bot.send_message.await_count, 1)

    async def test_uninitialized_bot_raises(self):
        with patch.object(commands, "telegram_bot", None):
            with self.assertRaises(RuntimeError):
                await send_message(123, "hi")


class EditMessageRetryTest(_BaseRetryTest):
    async def test_success_on_first_attempt(self):
        bot = commands.telegram_bot
        bot.edit_message_text = AsyncMock(return_value="ok")
        result = await edit_message(123, 456, "hello")
        self.assertEqual(result, "ok")
        self.assertEqual(bot.edit_message_text.await_count, 1)

    async def test_retry_on_NetworkError_then_succeed(self):
        bot = commands.telegram_bot
        bot.edit_message_text = AsyncMock(
            side_effect=[NetworkError("net1"), TimedOut(), "ok"]
        )
        result = await edit_message(123, 456, "hi")
        self.assertEqual(result, "ok")
        self.assertEqual(bot.edit_message_text.await_count, 3)
        warnings = [r for r in self._log_records if r.levelname == "WARNING"]
        self.assertEqual(len(warnings), 2)

    async def test_silently_return_after_max_attempts(self):
        """edit_message should NOT raise even after max retries; it logs and returns."""
        bot = commands.telegram_bot
        bot.edit_message_text = AsyncMock(side_effect=TimedOut())
        # Should NOT raise
        result = await edit_message(123, 456, "hi")
        self.assertIsNone(result)
        self.assertEqual(bot.edit_message_text.await_count, MESSAGE_MAX_ATTEMPTS)
        errors = [r for r in self._log_records if r.levelname == "ERROR"]
        self.assertEqual(len(errors), 1, "expected exactly 1 error log")

    async def test_non_network_error_logged_and_returned(self):
        bot = commands.telegram_bot
        bot.edit_message_text = AsyncMock(side_effect=ValueError("some bad req"))
        result = await edit_message(123, 456, "hi")
        self.assertIsNone(result)
        self.assertEqual(bot.edit_message_text.await_count, 1)
        warnings = [r for r in self._log_records if r.levelname == "WARNING"]
        self.assertEqual(len(warnings), 1, "expected 1 warning for non-network error")

    async def test_uninitialized_bot_returns_silently(self):
        with patch.object(commands, "telegram_bot", None):
            result = await edit_message(123, 456, "hi")
            self.assertIsNone(result)


class RetryPolicyTest(unittest.TestCase):
    """Verify retry policy constants."""

    def test_max_attempts(self):
        self.assertEqual(MESSAGE_MAX_ATTEMPTS, 3)

    def test_retry_base_delay_positive(self):
        self.assertGreater(MESSAGE_RETRY_BASE_DELAY, 0)


if __name__ == "__main__":
    unittest.main()
