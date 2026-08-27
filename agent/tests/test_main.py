import asyncio
import logging

from agent.main import _attempt_live_session


def test_attempt_live_session_reports_error_and_returns_on_failure():
    class FailingLiveSession:
        async def run(self):
            raise RuntimeError("bağlantı koptu")

    errors = []
    async def on_error(message):
        errors.append(message)

    asyncio.run(_attempt_live_session(FailingLiveSession(), on_error, backoff_seconds=0))

    assert errors == ["bağlantı koptu"]


def test_attempt_live_session_reports_nothing_on_clean_return():
    class CleanLiveSession:
        async def run(self):
            return

    errors = []
    async def on_error(message):
        errors.append(message)

    asyncio.run(_attempt_live_session(CleanLiveSession(), on_error, backoff_seconds=0))

    assert errors == []


def test_attempt_live_session_logs_a_warning_on_failure(caplog):
    class FailingLiveSession:
        async def run(self):
            raise RuntimeError("bağlantı koptu")

    async def on_error(message):
        pass

    with caplog.at_level(logging.WARNING):
        asyncio.run(_attempt_live_session(FailingLiveSession(), on_error, backoff_seconds=0))

    assert any("bağlantı koptu" in record.message for record in caplog.records)
