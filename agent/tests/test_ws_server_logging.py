import asyncio
import logging

from agent.ws_server import JarvisServer


class _NoOpServeCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


def test_serve_forever_logs_that_it_started_listening(monkeypatch, caplog):
    def fake_serve(handler, host, port):
        return _NoOpServeCtx()

    monkeypatch.setattr("agent.ws_server.websockets.serve", fake_serve)

    async def noop(self):
        return None

    monkeypatch.setattr(JarvisServer, "_broadcast_system_info", noop)
    monkeypatch.setattr(JarvisServer, "_broadcast_weather", noop)

    server = JarvisServer(host="127.0.0.1", port=8765)

    with caplog.at_level(logging.INFO):
        asyncio.run(server.serve_forever())

    assert any("8765" in record.message for record in caplog.records)
