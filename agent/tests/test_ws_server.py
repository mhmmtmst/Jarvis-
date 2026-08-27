import asyncio
import json

import agent.ws_server as ws_server_module
from agent.ws_server import JarvisServer


class FakeLiveSession:
    def __init__(self, raise_on: set | None = None):
        self.calls = []
        self._raise_on = raise_on or set()

    async def send_text(self, text):
        self.calls.append(("send_text", text))
        if "send_text" in self._raise_on:
            raise ConnectionError("bağlantı koptu")

    async def start_activity(self):
        self.calls.append(("start_activity",))
        if "start_activity" in self._raise_on:
            raise ConnectionError("bağlantı koptu")

    async def send_audio_chunk(self, pcm_bytes):
        self.calls.append(("send_audio_chunk", pcm_bytes))
        if "send_audio_chunk" in self._raise_on:
            raise ConnectionError("bağlantı koptu")

    async def end_activity(self):
        self.calls.append(("end_activity",))
        if "end_activity" in self._raise_on:
            raise ConnectionError("bağlantı koptu")


class FakeWakeWordListener:
    def __init__(self):
        self.paused = False
        self.resumed = False
        self.turn_complete_notified = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.resumed = True

    def notify_turn_complete(self):
        self.turn_complete_notified = True


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(data)


def make_server(raise_on: set | None = None):
    server = JarvisServer(host="127.0.0.1", port=0)
    server.live_session = FakeLiveSession(raise_on=raise_on)
    server.wake_word_listener = FakeWakeWordListener()
    return server


def test_command_message_sends_text_and_skips_listening_status():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "command", "text": "merhaba"})))

    assert ("send_text", "merhaba") in server.live_session.calls
    statuses = [json.loads(m) for m in ws.sent if json.loads(m).get("type") == "status"]
    assert {"type": "status", "state": "thinking"} in statuses
    assert {"type": "status", "state": "listening"} not in statuses


def test_command_message_falls_back_to_idle_when_live_session_errors():
    server = make_server(raise_on={"send_text"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "command", "text": "merhaba"})))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "status", "state": "idle"} in messages
    assert any(m.get("type") == "error" for m in messages)


def test_ptt_start_pauses_wake_word_and_starts_activity():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_start"})))

    assert ("start_activity",) in server.live_session.calls
    assert server.wake_word_listener.paused is True


def test_ptt_end_ends_activity_resumes_wake_word_and_sends_thinking_status():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_end"})))

    assert ("end_activity",) in server.live_session.calls
    assert server.wake_word_listener.resumed is True
    statuses = [json.loads(m) for m in ws.sent if json.loads(m).get("type") == "status"]
    assert {"type": "status", "state": "thinking"} in statuses


def test_ptt_end_falls_back_to_idle_instead_of_getting_stuck_when_live_session_errors():
    server = make_server(raise_on={"end_activity"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_end"})))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "status", "state": "idle"} in messages
    assert {"type": "status", "state": "thinking"} not in messages
    assert any(m.get("type") == "error" for m in messages)
    assert server.wake_word_listener.resumed is True


def test_ptt_start_falls_back_to_idle_and_resumes_wake_word_when_live_session_errors():
    server = make_server(raise_on={"start_activity"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_start"})))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "status", "state": "idle"} in messages
    assert any(m.get("type") == "error" for m in messages)
    assert server.wake_word_listener.resumed is True


def test_binary_frame_with_tag_0x01_forwards_audio_chunk():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, b"\x01\xde\xad\xbe\xef"))

    assert ("send_audio_chunk", b"\xde\xad\xbe\xef") in server.live_session.calls


def test_binary_frame_does_not_crash_connection_when_live_session_errors():
    # PTT sirasinda saniyede onlarca ses parcasi akiyor; Live baglantisi tam
    # o anda yeniden baglaniyorsa burada patlamak TUM websocket baglantisini
    # (Electron<->agent) coktururdu — sessizce yutulmasi gerekiyor.
    server = make_server(raise_on={"send_audio_chunk"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, b"\x01\xde\xad\xbe\xef"))  # exception firlatmamali


def test_handle_live_event_audio_chunk_broadcasts_binary_frame_and_speaking_status():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "audio_chunk", "data": b"\x99\x88"}))

    assert b"\x02\x99\x88" in ws.sent
    statuses = [json.loads(m) for m in ws.sent if isinstance(m, str) and json.loads(m).get("type") == "status"]
    assert {"type": "status", "state": "speaking"} in statuses


def test_handle_live_event_turn_complete_broadcasts_turn_complete_and_idle():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "turn_complete"}))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "turn_complete"} in messages
    assert {"type": "status", "state": "idle"} in messages
    assert server.wake_word_listener.turn_complete_notified is True


def test_handle_wake_trigger_sends_system_nudge_for_greeting():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_wake_trigger())

    assert len(server.live_session.calls) == 1
    call_type, sent_text = server.live_session.calls[0]
    assert call_type == "send_text"
    assert sent_text.startswith("[SISTEM]")


def test_handle_conversation_end_sends_system_nudge_for_closing_remark():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_conversation_end())

    assert len(server.live_session.calls) == 1
    call_type, sent_text = server.live_session.calls[0]
    assert call_type == "send_text"
    assert sent_text.startswith("[SISTEM]")


def test_handle_live_event_transcript_broadcasts_transcript():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "transcript", "role": "agent", "text": "merhaba"}))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "transcript", "role": "agent", "text": "merhaba"} in messages


def test_handle_wake_command_starts_turn_and_sends_text():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_wake_command("saati söyle"))

    assert ("send_text", "saati söyle") in server.live_session.calls
    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "status", "state": "listening"} in messages
    assert {"type": "status", "state": "thinking"} in messages


def test_handle_wake_status_broadcasts_wake_status():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_wake_status(True))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "wake_status", "active": True} in messages


def test_location_message_stores_browser_location_and_refreshes_weather(monkeypatch):
    calls = []

    def fake_get_weather_summary(location="", default_location="", http_get=None):
        calls.append(default_location)
        return {"status": "ok", "city": "Safranbolu, Karabük", "temp_c": "27"}

    monkeypatch.setattr(ws_server_module, "get_weather_summary", fake_get_weather_summary)

    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "location", "lat": 41.2544, "lon": 32.6944})))

    assert server._browser_location == "41.2544,32.6944"
    assert calls[0] == "41.2544,32.6944"
    assert server._latest_weather == {"status": "ok", "city": "Safranbolu, Karabük", "temp_c": "27"}
    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "weather_info", "data": server._latest_weather} in messages


def test_location_message_ignores_non_numeric_coordinates():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "location", "lat": "yok", "lon": None})))

    assert server._browser_location is None
    assert ws.sent == []


def test_new_turn_while_speaking_broadcasts_interrupt_first():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)
    asyncio.run(server.handle_live_event({"type": "audio_chunk", "data": b"\x01"}))
    ws.sent.clear()

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_start"})))

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert messages[0] == {"type": "interrupt"}
