import asyncio
import logging
from types import SimpleNamespace

from agent.gemini.live_session import LiveSession


class FakeSession:
    def __init__(self, messages):
        self._messages = messages
        self.sent = []

    async def send_client_content(self, *, turns, turn_complete=True):
        self.sent.append(("send_client_content", turns, turn_complete))

    async def send_realtime_input(self, **kwargs):
        self.sent.append(("send_realtime_input", kwargs))

    async def send_tool_response(self, *, function_responses):
        self.sent.append(("send_tool_response", function_responses))

    async def receive(self):
        await asyncio.sleep(0)
        for message in self._messages:
            yield message


class FakeLiveConnection:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeLive:
    def __init__(self, session):
        self._session = session
        self.connect_calls = []

    def connect(self, *, model, config):
        self.connect_calls.append({"model": model, "config": config})
        return FakeLiveConnection(self._session)


class FakeClient:
    def __init__(self, session):
        self.aio = SimpleNamespace(live=FakeLive(session))


def make_message(tool_call=None, server_content=None):
    return SimpleNamespace(tool_call=tool_call, server_content=server_content)


def make_server_content(
    model_turn=None,
    turn_complete=False,
    interrupted=False,
    input_transcription=None,
):
    return SimpleNamespace(
        model_turn=model_turn,
        turn_complete=turn_complete,
        interrupted=interrupted,
        input_transcription=input_transcription,
    )


def test_run_connects_with_configured_model_and_uses_text_modality():
    session = FakeSession(messages=[])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(client=client, model="gemini-live-2.5-flash-preview", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert client.aio.live.connect_calls[0]["model"] == "gemini-live-2.5-flash-preview"
    config = client.aio.live.connect_calls[0]["config"]
    assert config.response_modalities == ["TEXT"]
    assert config.realtime_input_config.automatic_activity_detection.disabled is True


def test_run_emits_agent_transcript_from_model_turn_text_and_turn_complete():
    part = SimpleNamespace(text="merhaba")
    content = make_server_content(model_turn=SimpleNamespace(parts=[part]), turn_complete=True)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "transcript", "role": "agent", "text": "merhaba"} in events
    assert {"type": "agent_text_complete", "text": "merhaba"} in events
    assert {"type": "turn_complete"} in events


def test_run_accumulates_multiple_text_parts_into_single_agent_text_complete():
    part1 = SimpleNamespace(text="merhaba, ")
    part2 = SimpleNamespace(text="nasılsın?")
    content = make_server_content(model_turn=SimpleNamespace(parts=[part1, part2]), turn_complete=True)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "agent_text_complete", "text": "merhaba, nasılsın?"} in events


def test_run_does_not_emit_agent_text_complete_when_turn_has_no_text():
    content = make_server_content(turn_complete=True)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert not any(e["type"] == "agent_text_complete" for e in events)
    assert {"type": "turn_complete"} in events


def test_run_resets_accumulated_text_between_turns():
    part_a = SimpleNamespace(text="ilk tur")
    content_a = make_server_content(model_turn=SimpleNamespace(parts=[part_a]), turn_complete=True)
    part_b = SimpleNamespace(text="ikinci tur")
    content_b = make_server_content(model_turn=SimpleNamespace(parts=[part_b]), turn_complete=True)
    session = FakeSession(messages=[make_message(server_content=content_a), make_message(server_content=content_b)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    text_complete_events = [e for e in events if e["type"] == "agent_text_complete"]
    assert text_complete_events == [
        {"type": "agent_text_complete", "text": "ilk tur"},
        {"type": "agent_text_complete", "text": "ikinci tur"},
    ]


def test_run_emits_user_transcript_from_input_transcription():
    content = make_server_content(input_transcription=SimpleNamespace(text="saat kaç"))
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "transcript", "role": "user", "text": "saat kaç"} in events


def test_run_does_not_emit_turn_complete_when_false():
    content = make_server_content(turn_complete=False)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "turn_complete"} not in events


def test_send_text_sends_client_content_with_user_role():
    async def scenario():
        session = FakeSession(messages=[])
        client = FakeClient(session)
        async def on_event(event):
            pass

        live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
        run_task = asyncio.create_task(live.run())
        await asyncio.sleep(0)

        await live.send_text("merhaba")
        await run_task

        assert session.sent[0][0] == "send_client_content"
        _, turns, turn_complete = session.sent[0]
        assert turns.role == "user"
        assert turns.parts[0].text == "merhaba"
        assert turn_complete is True

    asyncio.run(scenario())


def test_send_audio_chunk_sends_pcm_blob_with_correct_mime_type():
    async def scenario():
        session = FakeSession(messages=[])
        client = FakeClient(session)
        async def on_event(event):
            pass

        live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
        run_task = asyncio.create_task(live.run())
        await asyncio.sleep(0)

        await live.start_activity()
        await live.send_audio_chunk(b"\x01\x02\x03\x04")
        await live.end_activity()
        await run_task

        kinds = [entry[0] for entry in session.sent]
        assert kinds == ["send_realtime_input", "send_realtime_input", "send_realtime_input"]

        _, start_kwargs = session.sent[0]
        assert start_kwargs["activity_start"] is not None

        _, audio_kwargs = session.sent[1]
        assert audio_kwargs["audio"].data == b"\x01\x02\x03\x04"
        assert audio_kwargs["audio"].mime_type == "audio/pcm;rate=16000"

        _, end_kwargs = session.sent[2]
        assert end_kwargs["activity_end"] is not None

    asyncio.run(scenario())


from agent.tools.registry import ToolSpec


def make_tool(name="get_system_info", result=None, handler=None):
    result = result if result is not None else {"status": "ok"}
    return ToolSpec(
        name=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
        handler=handler if handler is not None else (lambda **kwargs: result),
    )


def test_run_executes_tool_handler_and_sends_function_response():
    call = SimpleNamespace(id="call-1", name="get_system_info", args={})
    tool_call = SimpleNamespace(function_calls=[call])
    session = FakeSession(messages=[make_message(tool_call=tool_call)])
    client = FakeClient(session)
    async def on_event(event):
        pass

    tool = make_tool(result={"status": "ok", "cpu_percent": 5})
    live = LiveSession(client=client, model="m", tools={"get_system_info": tool}, on_event=on_event)
    asyncio.run(live.run())

    kind, function_responses = session.sent[0]
    assert kind == "send_tool_response"
    assert len(function_responses) == 1
    response = function_responses[0]
    assert response.id == "call-1"
    assert response.name == "get_system_info"
    assert response.response == {"status": "ok", "cpu_percent": 5}


def test_run_passes_call_args_to_handler():
    received_args = {}

    def handler(**kwargs):
        received_args.update(kwargs)
        return {"status": "ok"}

    call = SimpleNamespace(id="call-2", name="open_app", args={"isim": "not defteri"})
    tool_call = SimpleNamespace(function_calls=[call])
    session = FakeSession(messages=[make_message(tool_call=tool_call)])
    client = FakeClient(session)
    async def on_event(event):
        pass

    tool = make_tool(name="open_app", handler=handler)
    live = LiveSession(client=client, model="m", tools={"open_app": tool}, on_event=on_event)
    asyncio.run(live.run())

    assert received_args == {"isim": "not defteri"}


def test_run_reports_error_for_unknown_tool_without_calling_any_handler():
    call = SimpleNamespace(id="call-3", name="does_not_exist", args={})
    tool_call = SimpleNamespace(function_calls=[call])
    session = FakeSession(messages=[make_message(tool_call=tool_call)])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    _, function_responses = session.sent[0]
    assert function_responses[0].response["status"] == "error"


def test_run_emits_interrupted_event():
    content = make_server_content(interrupted=True)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "interrupted"} in events


def test_run_does_not_emit_interrupted_when_false():
    content = make_server_content(interrupted=False)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "interrupted"} not in events


def test_run_handles_exception_from_tool_handler_without_crashing_session():
    def handler(**kwargs):
        raise ValueError("boom")

    call = SimpleNamespace(id="call-4", name="run_command", args={})
    tool_call = SimpleNamespace(function_calls=[call])
    session = FakeSession(messages=[make_message(tool_call=tool_call)])
    client = FakeClient(session)
    async def on_event(event):
        pass

    tool = make_tool(name="run_command", handler=handler)
    live = LiveSession(client=client, model="m", tools={"run_command": tool}, on_event=on_event)
    asyncio.run(live.run())

    kind, function_responses = session.sent[0]
    assert kind == "send_tool_response"
    assert len(function_responses) == 1
    assert function_responses[0].response["status"] == "error"
    assert "run_command" in function_responses[0].response["message"]


def test_run_handles_exception_from_unexpected_handler_kwarg_without_crashing_session():
    def handler(**kwargs):
        raise TypeError("unexpected keyword argument 'opener'")

    call = SimpleNamespace(id="call-5", name="open_browser", args={"opener": "some string"})
    tool_call = SimpleNamespace(function_calls=[call])
    session = FakeSession(messages=[make_message(tool_call=tool_call)])
    client = FakeClient(session)
    async def on_event(event):
        pass

    tool = make_tool(name="open_browser", handler=handler)
    live = LiveSession(client=client, model="m", tools={"open_browser": tool}, on_event=on_event)
    asyncio.run(live.run())

    kind, function_responses = session.sent[0]
    assert kind == "send_tool_response"
    assert function_responses[0].response["status"] == "error"


def test_run_connects_with_jarvis_persona_as_system_instruction_when_memory_empty():
    from agent.persona import JARVIS_PERSONA

    session = FakeSession(messages=[])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(
        client=client, model="m", tools={}, on_event=on_event,
        memory_loader=lambda: {},
    )
    asyncio.run(live.run())

    config = client.aio.live.connect_calls[0]["config"]
    assert config.system_instruction == JARVIS_PERSONA


def test_run_appends_formatted_memory_to_system_instruction_when_present():
    from agent.persona import JARVIS_PERSONA

    session = FakeSession(messages=[])
    client = FakeClient(session)
    async def on_event(event):
        pass

    memory = {"identity": {"isim": {"value": "Muhammet", "timestamp": "x"}}}
    live = LiveSession(
        client=client, model="m", tools={}, on_event=on_event,
        memory_loader=lambda: memory,
    )
    asyncio.run(live.run())

    config = client.aio.live.connect_calls[0]["config"]
    assert config.system_instruction.startswith(JARVIS_PERSONA)
    assert "identity/isim: Muhammet" in config.system_instruction


def test_run_uses_work_mode_persona_when_mode_is_calisma():
    from agent.persona import build_persona

    session = FakeSession(messages=[])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(
        client=client, model="m", tools={}, on_event=on_event,
        memory_loader=lambda: {}, mode="calisma",
    )
    asyncio.run(live.run())

    config = client.aio.live.connect_calls[0]["config"]
    assert config.system_instruction == build_persona("calisma")


def test_run_emits_session_ready_event_after_connecting():
    session = FakeSession(messages=[])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "session_ready"} in events


def test_run_logs_when_live_session_connects(caplog):
    session = FakeSession(messages=[])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(client=client, model="gemini-test-model", tools={}, on_event=on_event)

    with caplog.at_level(logging.INFO):
        asyncio.run(live.run())

    assert any("gemini-test-model" in record.message for record in caplog.records)
