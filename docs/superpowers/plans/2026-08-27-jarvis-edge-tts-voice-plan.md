# Jarvis Edge-TTS Doğal Türkçe Ses Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jarvis'in sesini Gemini Live'ın built-in seslerinden, `edge-tts` ile
sentezlenen gerçek Azure nöral bir Türkçe sese (Ahmet/Emel) çevirmek —
tamamen ücretsiz, tarayıcının `speechSynthesis`'i güvenlik ağı olarak.

**Architecture:** Gemini Live artık ses değil sadece metin üretiyor
(`response_modalities=["TEXT"]`). Turn tamamlanınca tam metin yeni
`agent/tools/tts.py` ile Edge-TTS+ffmpeg üzerinden PCM16 24kHz sese
çevriliyor ve mevcut `audio_chunk` binary protokolüyle client'a akıtılıyor
— client tarafında ses oynatma kodu DEĞİŞMİYOR. Sentez başarısız olursa
client'a `tts_failed` sinyali gidiyor, renderer tarayıcının kendi
`speechSynthesis`'iyle son çare olarak seslendiriyor.

**Tech Stack:** `edge-tts` (Python, PyPI), `ffmpeg` (zaten kurulu, subprocess
ile çağrılıyor), mevcut WebSocket binary protokolü.

## Global Constraints

- Python testleri kök dizinden: `./agent/venv/Scripts/python.exe -m pytest agent/tests/<dosya>.py -v`.
- JS testleri kök dizinden: `node --test shell/<dosya>.test.js`.
- PCM formatı sabit: 16-bit signed little-endian, 24000 Hz, mono (client'ın
  `AudioContext({ sampleRate: 24000 })` varsayımıyla birebir eşleşmeli).
- Edge-TTS'in gerçek çıktı formatı (`audio-24khz-48kbitrate-mono-mp3`) ve
  `google-genai` SDK'sının `Part.text` alanı, bu planı yazmadan önce kurulu
  paketlerin kaynak kodundan ve gerçek bir sentez çağrısından doğrulandı —
  aşağıdaki kod bu doğrulanmış gerçek şekilleri kullanıyor.
- Sesli seçenekler sadece Ahmet (`tr-TR-AhmetNeural`, varsayılan) ve Emel
  (`tr-TR-EmelNeural`) — Edge'in resmi sunduğu iki Türkçe nöral ses.

---

### Task 1: `agent/tools/tts.py` — Edge-TTS + ffmpeg sentezi

**Files:**
- Create: `agent/tools/tts.py`
- Test: `agent/tests/test_tts.py`
- Modify: `agent/requirements.txt`

**Interfaces:**
- Produces: `async def synthesize_speech(text: str, voice: str = "tr-TR-AhmetNeural", communicate_cls=None, ffmpeg_runner=None) -> bytes` — PCM16 24kHz mono bytes döner, hata durumunda exception fırlatır (çağıran taraf, Task 3'te, bunu yakalayıp fallback'e düşecek).

- [ ] **Step 1: Failing testleri ekle**

`agent/tests/test_tts.py` (yeni dosya):

```python
import asyncio

from agent.tools.tts import synthesize_speech


class FakeCommunicate:
    def __init__(self, text, voice):
        self.text = text
        self.voice = voice

    async def stream(self):
        yield {"type": "audio", "data": b"raw-mp3-bytes-1"}
        yield {"type": "WordBoundary", "offset": 0, "duration": 100, "text": "x"}
        yield {"type": "audio", "data": b"raw-mp3-bytes-2"}


def test_synthesize_speech_passes_text_and_voice_to_communicate():
    captured = {}

    class CapturingCommunicate(FakeCommunicate):
        def __init__(self, text, voice):
            captured["text"] = text
            captured["voice"] = voice
            super().__init__(text, voice)

    result = asyncio.run(
        synthesize_speech(
            "merhaba",
            voice="tr-TR-AhmetNeural",
            communicate_cls=CapturingCommunicate,
            ffmpeg_runner=lambda raw: b"\x00\x01" * 4,
        )
    )

    assert captured == {"text": "merhaba", "voice": "tr-TR-AhmetNeural"}
    assert result == b"\x00\x01" * 4


def test_synthesize_speech_concatenates_only_audio_chunks_before_ffmpeg():
    seen_raw = {}

    def fake_ffmpeg(raw_audio):
        seen_raw["value"] = raw_audio
        return b"pcm-output"

    result = asyncio.run(
        synthesize_speech("merhaba", communicate_cls=FakeCommunicate, ffmpeg_runner=fake_ffmpeg)
    )

    assert seen_raw["value"] == b"raw-mp3-bytes-1raw-mp3-bytes-2"
    assert result == b"pcm-output"


def test_synthesize_speech_uses_default_voice_when_not_given():
    captured = {}

    class CapturingCommunicate(FakeCommunicate):
        def __init__(self, text, voice):
            captured["voice"] = voice
            super().__init__(text, voice)

    asyncio.run(
        synthesize_speech(
            "merhaba", communicate_cls=CapturingCommunicate, ffmpeg_runner=lambda raw: b""
        )
    )

    assert captured["voice"] == "tr-TR-AhmetNeural"


def test_synthesize_speech_real_edge_tts_and_ffmpeg_produce_even_length_pcm():
    """Gerçek edge-tts + ffmpeg entegrasyonunun bozulmadığını kontrol eden
    tek canlı test (ağ + ffmpeg gerektirir) — test_terminal.py'nin gerçek
    subprocess testiyle aynı desen."""
    result = asyncio.run(synthesize_speech("merhaba dünya"))

    assert len(result) > 0
    assert len(result) % 2 == 0  # PCM16 = örnek başına 2 bayt
```

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_tts.py -v`
Expected: tümü FAIL (`ModuleNotFoundError: No module named 'agent.tools.tts'`)

- [ ] **Step 3: `agent/requirements.txt`'e ekle**

`agent/requirements.txt`'in sonuna ekle:

```
edge-tts>=6.1.0
```

Run: `./agent/venv/Scripts/python.exe -m pip install edge-tts`

- [ ] **Step 4: `agent/tools/tts.py`'yi oluştur**

```python
import asyncio
import subprocess

import edge_tts

_SAMPLE_RATE_HZ = 24000
_DEFAULT_VOICE = "tr-TR-AhmetNeural"


async def synthesize_speech(
    text: str,
    voice: str = _DEFAULT_VOICE,
    communicate_cls=None,
    ffmpeg_runner=None,
) -> bytes:
    """Edge-TTS ile `text`'i sentezler, ffmpeg ile PCM16 24kHz mono bayta
    çevirip döner. Edge-TTS'in gerçek çıktısı audio-24khz-48kbitrate-mono-mp3
    (kaynak koddan doğrulandı); ffmpeg girdi formatını otomatik algıladığı
    için burada codec'i ayrıca belirtmeye gerek yok.
    `communicate_cls`/`ffmpeg_runner` testte enjekte edilir."""
    if communicate_cls is None:
        communicate_cls = edge_tts.Communicate
    if ffmpeg_runner is None:
        ffmpeg_runner = _run_ffmpeg

    communicate = communicate_cls(text, voice)
    raw_audio = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            raw_audio.extend(chunk["data"])

    return await asyncio.to_thread(ffmpeg_runner, bytes(raw_audio))


def _run_ffmpeg(raw_audio: bytes) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-ar", str(_SAMPLE_RATE_HZ), "-ac", "1", "pipe:1"],
        input=raw_audio,
        capture_output=True,
        check=True,
    )
    return result.stdout
```

- [ ] **Step 5: Testleri çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_tts.py -v`
Expected: PASS (4 passed) — son test gerçek ağ+ffmpeg çağrısı yaptığı için birkaç saniye sürebilir

- [ ] **Step 6: Commit**

```bash
git add agent/tools/tts.py agent/tests/test_tts.py agent/requirements.txt
git commit -m "feat(agent): Edge-TTS + ffmpeg ile PCM16 ses sentezi ekle"
```

---

### Task 2: `agent/gemini/live_session.py` — Gemini'yi TEXT moduna al

**Files:**
- Modify: `agent/gemini/live_session.py`
- Modify: `agent/tests/test_live_session.py`

**Interfaces:**
- Produces: `LiveSession.__init__` artık `voice` parametresi ALMIYOR (ses artık Task 3'te `JarvisServer` tarafında yönetiliyor). Turn tamamlanınca, biriken ajan metni tek bir `{"type": "agent_text_complete", "text": str}` olayıyla `on_event`'e gönderiliyor (mevcut per-parça `{"type": "transcript", "role": "agent", "text": str}` olayları AYNEN, ek olarak devam ediyor).

- [ ] **Step 1: Artık geçersiz olan testleri sil**

`agent/tests/test_live_session.py`'den şu iki test fonksiyonunu TAMAMEN
sil (Gemini artık ses üretmiyor, bu davranış kalkıyor):
- `test_run_emits_audio_chunk_event_from_model_turn_inline_data`
- `test_run_ignores_model_turn_parts_without_inline_data`

- [ ] **Step 2: `voice=` argümanını tüm `LiveSession(...)` çağrılarından kaldır**

Dosyada birebir `voice="Kore", ` (virgül+boşluk dahil) dizgesi TAM OLARAK
20 kez geçiyor — hepsini sil (bulmak için: `grep -n 'voice="Kore"'
agent/tests/test_live_session.py`). İki tanesi zaten Step 3/4'te tüm
fonksiyonu değiştirirken ayrıca kayboluyor, onlarda burada tek başına
silmek zararsız/gereksiz olur ama sorun çıkarmaz. `model=`, `tools=`,
`on_event=`, `memory_loader=`, `mode=` argümanları olduğu gibi kalıyor.

- [ ] **Step 3: `test_run_connects_with_configured_model_and_voice`'u güncelle**

Bu testi:

```python
def test_run_connects_with_configured_model_and_voice():
    session = FakeSession(messages=[])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(client=client, model="gemini-live-2.5-flash-preview", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert client.aio.live.connect_calls[0]["model"] == "gemini-live-2.5-flash-preview"
    config = client.aio.live.connect_calls[0]["config"]
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Kore"
    assert config.realtime_input_config.automatic_activity_detection.disabled is True
```

şununla değiştir:

```python
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
```

- [ ] **Step 4: `test_run_emits_agent_transcript_and_turn_complete`'i TEXT moduna göre güncelle**

Bu testi:

```python
def test_run_emits_agent_transcript_and_turn_complete():
    content = make_server_content(output_transcription=SimpleNamespace(text="merhaba"), turn_complete=True)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "transcript", "role": "agent", "text": "merhaba"} in events
    assert {"type": "turn_complete"} in events
```

şununla değiştir:

```python
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
```

- [ ] **Step 5: Yeni davranış testlerini ekle**

`test_run_emits_agent_transcript_from_model_turn_text_and_turn_complete`
fonksiyonunun hemen altına ekle:

```python
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
```

- [ ] **Step 6: Testleri çalıştır, başarısız olduklarını doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: Step 3-5'te eklenen/değiştirilen testler FAIL (`TypeError:
__init__() got an unexpected keyword argument 'voice'` ve/veya
`response_modalities`/`agent_text_complete` ile ilgili AssertionError'lar)

- [ ] **Step 7: `agent/gemini/live_session.py`'yi güncelle**

`__init__`'i:

```python
    def __init__(
        self, client, model: str, voice: str, tools: dict[str, ToolSpec], on_event,
        memory_loader=None, mode: str = "rahat",
    ):
        self._client = client
        self._model = model
        self._voice = voice
        self._tools = tools
        self._on_event = on_event
        self._memory_loader = memory_loader if memory_loader is not None else load_memory
        self._mode = mode
        self._session = None
```

şununla değiştir:

```python
    def __init__(
        self, client, model: str, tools: dict[str, ToolSpec], on_event,
        memory_loader=None, mode: str = "rahat",
    ):
        self._client = client
        self._model = model
        self._tools = tools
        self._on_event = on_event
        self._memory_loader = memory_loader if memory_loader is not None else load_memory
        self._mode = mode
        self._session = None
        self._pending_agent_text = ""
```

`_build_config`'i:

```python
    def _build_config(self) -> types.LiveConnectConfig:
        tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=spec.name,
                    description=spec.description,
                    parameters_json_schema=spec.parameters,
                )
                for spec in self._tools.values()
            ]
        )
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self._build_system_instruction(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._voice)
                )
            ),
            tools=[tool],
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
        )
```

şununla değiştir:

```python
    def _build_config(self) -> types.LiveConnectConfig:
        tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=spec.name,
                    description=spec.description,
                    parameters_json_schema=spec.parameters,
                )
                for spec in self._tools.values()
            ]
        )
        return types.LiveConnectConfig(
            response_modalities=["TEXT"],
            system_instruction=self._build_system_instruction(),
            tools=[tool],
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
        )
```

`_handle_message`'ı:

```python
    async def _handle_message(self, message) -> None:
        if message.tool_call is not None:
            await self._handle_tool_call(message.tool_call)
            return

        content = message.server_content
        if content is None:
            return

        if content.interrupted:
            await self._on_event({"type": "interrupted"})

        if content.input_transcription is not None and content.input_transcription.text:
            await self._on_event({"type": "transcript", "role": "user", "text": content.input_transcription.text})

        if content.output_transcription is not None and content.output_transcription.text:
            await self._on_event({"type": "transcript", "role": "agent", "text": content.output_transcription.text})

        if content.model_turn is not None:
            for part in content.model_turn.parts or []:
                if part.inline_data is not None and part.inline_data.data:
                    await self._on_event({"type": "audio_chunk", "data": part.inline_data.data})

        if content.turn_complete:
            await self._on_event({"type": "turn_complete"})
```

şununla değiştir:

```python
    async def _handle_message(self, message) -> None:
        if message.tool_call is not None:
            await self._handle_tool_call(message.tool_call)
            return

        content = message.server_content
        if content is None:
            return

        if content.interrupted:
            await self._on_event({"type": "interrupted"})

        if content.input_transcription is not None and content.input_transcription.text:
            await self._on_event({"type": "transcript", "role": "user", "text": content.input_transcription.text})

        if content.model_turn is not None:
            for part in content.model_turn.parts or []:
                if part.text:
                    self._pending_agent_text += part.text
                    await self._on_event({"type": "transcript", "role": "agent", "text": part.text})

        if content.turn_complete:
            if self._pending_agent_text:
                await self._on_event({"type": "agent_text_complete", "text": self._pending_agent_text})
            self._pending_agent_text = ""
            await self._on_event({"type": "turn_complete"})
```

- [ ] **Step 8: Tüm dosyanın testlerini çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: PASS, tüm testler yeşil

- [ ] **Step 9: Commit**

```bash
git add agent/gemini/live_session.py agent/tests/test_live_session.py
git commit -m "feat(agent): Gemini Live'ı TEXT moduna al, agent_text_complete olayı ekle"
```

---

### Task 3: `agent/ws_server.py` — sentezi tetikle, fallback, kesme

**Files:**
- Modify: `agent/ws_server.py`
- Modify: `agent/tests/test_ws_server.py`

**Interfaces:**
- Consumes: `agent.tools.tts.synthesize_speech(text, voice)` (Task 1); `{"type": "agent_text_complete", "text": str}` olayı (Task 2).
- Produces: `JarvisServer.__init__` yeni `tts_voice: str = "tr-TR-AhmetNeural"` ve `tts_synthesizer=None` (verilmezse gerçek `synthesize_speech`) parametreleri alıyor. Sentez başarısız olursa client'a `{"type": "tts_failed", "text": str}` gönderiliyor.

- [ ] **Step 1: Failing testleri ekle**

`agent/tests/test_ws_server.py`'nin başında `import asyncio` zaten var,
ek bir import gerekmiyor. `make_server` fonksiyonunu:

```python
def make_server(raise_on: set | None = None):
    server = JarvisServer(host="127.0.0.1", port=0)
    server.live_session = FakeLiveSession(raise_on=raise_on)
```

şununla değiştir:

```python
def make_server(raise_on: set | None = None, tts_synthesizer=None):
    server = JarvisServer(host="127.0.0.1", port=0, tts_synthesizer=tts_synthesizer)
    server.live_session = FakeLiveSession(raise_on=raise_on)
```

(devamındaki `server.wake_word_listener = ...` ve `return server` satırları
olduğu gibi kalıyor.)

`test_handle_live_event_transcript_broadcasts_transcript` fonksiyonunun
hemen üstüne ekle:

```python
def test_handle_live_event_agent_text_complete_synthesizes_and_broadcasts_audio():
    async def fake_synth(text, voice):
        assert text == "merhaba"
        return b"\x01\x02\x03\x04"

    server = make_server(tts_synthesizer=fake_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "agent_text_complete", "text": "merhaba"}))

    binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
    assert binary_sent == [b"\x02\x01\x02\x03\x04"]
    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "status", "state": "speaking"} in messages
    assert {"type": "turn_complete"} in messages
    assert {"type": "status", "state": "idle"} in messages
    assert server.wake_word_listener.turn_complete_notified is True


def test_handle_live_event_agent_text_complete_sends_tts_failed_on_synthesis_error():
    async def failing_synth(text, voice):
        raise RuntimeError("edge-tts kırıldı")

    server = make_server(tts_synthesizer=failing_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "agent_text_complete", "text": "merhaba"}))

    binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
    assert binary_sent == []
    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "tts_failed", "text": "merhaba"} in messages


def test_handle_live_event_agent_text_complete_chunks_large_audio():
    async def fake_synth(text, voice):
        return b"\xab" * 25000

    server = make_server(tts_synthesizer=fake_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "agent_text_complete", "text": "uzun bir cevap"}))

    binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
    assert len(binary_sent) == 3
    assert sum(len(chunk) - 1 for chunk in binary_sent) == 25000
    assert all(chunk[0:1] == b"\x02" for chunk in binary_sent)


def test_agent_text_complete_result_discarded_after_interrupt():
    async def slow_synth(text, voice):
        await asyncio.sleep(0)
        return b"\x01\x02"

    server = make_server(tts_synthesizer=slow_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        task = asyncio.create_task(
            server.handle_live_event({"type": "agent_text_complete", "text": "merhaba"})
        )
        await asyncio.sleep(0)
        await server._maybe_interrupt()
        await task

    asyncio.run(scenario())

    binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
    assert binary_sent == []
    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert not any(m.get("type") == "status" and m.get("state") == "speaking" for m in messages)


```

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_ws_server.py -v`
Expected: yeni 4 test FAIL (`TypeError: __init__() got an unexpected
keyword argument 'tts_synthesizer'`)

- [ ] **Step 3: `agent/ws_server.py`'yi güncelle**

Dosyanın en üstüne ekle:

```python
from agent.tools.tts import synthesize_speech
```

`_TTS_CHUNK_BYTES` sabitini `WEATHER_REFRESH_SECONDS`'ın altına ekle:

```python
_TTS_CHUNK_BYTES = 9600  # 24kHz, 16-bit mono'da ~200ms
```

`__init__`'i:

```python
    def __init__(self, host: str, port: int, weather_default_location: str = ""):
        self._host = host
        self._port = port
        self._weather_default_location = weather_default_location
        self._clients: set = set()
        self._speaking = False
        self.live_session = None
        self.wake_word_listener = None
        self._latest_weather = None
        self._browser_location: str | None = None
        self._briefed = False
```

şununla değiştir:

```python
    def __init__(
        self, host: str, port: int, weather_default_location: str = "",
        tts_voice: str = "tr-TR-AhmetNeural", tts_synthesizer=None,
    ):
        self._host = host
        self._port = port
        self._weather_default_location = weather_default_location
        self._clients: set = set()
        self._speaking = False
        self.live_session = None
        self.wake_word_listener = None
        self._latest_weather = None
        self._browser_location: str | None = None
        self._briefed = False
        self._tts_voice = tts_voice
        self._tts_synthesizer = tts_synthesizer if tts_synthesizer is not None else synthesize_speech
        self._tts_generation = 0
```

`_maybe_interrupt`'ı:

```python
    async def _maybe_interrupt(self) -> None:
        """Yeni bir kullanıcı turu başlıyor (ptt basıldı, yazılı komut ya da
        wake-word). Jarvis hâlâ konuşuyorsa shell'e anında kesme sinyali
        gönderilir."""
        if self._speaking:
            await self._broadcast_json({"type": "interrupt"})
        self._speaking = False
```

şununla değiştir:

```python
    async def _maybe_interrupt(self) -> None:
        """Yeni bir kullanıcı turu başlıyor (ptt basıldı, yazılı komut ya da
        wake-word). Jarvis hâlâ konuşuyorsa shell'e anında kesme sinyali
        gönderilir. Devam eden bir TTS sentezi varsa (nesil sayacı artırılarak)
        sonucu geldiğinde sessizce atılır."""
        self._tts_generation += 1
        if self._speaking:
            await self._broadcast_json({"type": "interrupt"})
        self._speaking = False
```

`handle_live_event`'i:

```python
    async def handle_live_event(self, event: dict) -> None:
        etype = event["type"]
        if etype == "session_ready":
            await self.handle_startup_briefing()
        elif etype == "audio_chunk":
            if not self._speaking:
                self._speaking = True
                await self._broadcast_json({"type": "status", "state": "speaking"})
            await self._broadcast_binary(b"\x02" + event["data"])
        elif etype == "transcript":
            await self._broadcast_json({"type": "transcript", "role": event["role"], "text": event["text"]})
        elif etype == "interrupted":
            await self._broadcast_json({"type": "interrupt"})
        elif etype == "turn_complete":
            self._speaking = False
            await self._broadcast_json({"type": "turn_complete"})
            await self._broadcast_json({"type": "status", "state": "idle"})
            self.wake_word_listener.notify_turn_complete()
        elif etype == "error":
            await self._broadcast_json({"type": "error", "message": event["message"]})
```

şununla değiştir:

```python
    async def handle_live_event(self, event: dict) -> None:
        etype = event["type"]
        if etype == "session_ready":
            await self.handle_startup_briefing()
        elif etype == "agent_text_complete":
            await self._synthesize_and_broadcast(event["text"])
        elif etype == "transcript":
            await self._broadcast_json({"type": "transcript", "role": event["role"], "text": event["text"]})
        elif etype == "interrupted":
            self._tts_generation += 1
            await self._broadcast_json({"type": "interrupt"})
        elif etype == "error":
            await self._broadcast_json({"type": "error", "message": event["message"]})
```

(NOT: `audio_chunk` ve eski `turn_complete` dalları kaldırıldı — Gemini
artık ses üretmiyor, `turn_complete` artık `_synthesize_and_broadcast`
içinden tetikleniyor.)

`_maybe_interrupt`'ın hemen altına yeni metodu ekle:

```python
    async def _synthesize_and_broadcast(self, text: str) -> None:
        self._tts_generation += 1
        my_generation = self._tts_generation
        try:
            pcm = await self._tts_synthesizer(text, self._tts_voice)
        except Exception:
            if my_generation == self._tts_generation:
                await self._broadcast_json({"type": "tts_failed", "text": text})
            return

        if my_generation != self._tts_generation:
            return

        self._speaking = True
        await self._broadcast_json({"type": "status", "state": "speaking"})
        for i in range(0, len(pcm), _TTS_CHUNK_BYTES):
            if my_generation != self._tts_generation:
                return
            await self._broadcast_binary(b"\x02" + pcm[i : i + _TTS_CHUNK_BYTES])

        self._speaking = False
        await self._broadcast_json({"type": "turn_complete"})
        await self._broadcast_json({"type": "status", "state": "idle"})
        self.wake_word_listener.notify_turn_complete()
```

- [ ] **Step 4: Tüm dosyanın testlerini çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_ws_server.py -v`
Expected: PASS, tüm testler (eskiler dahil) yeşil

- [ ] **Step 5: Commit**

```bash
git add agent/ws_server.py agent/tests/test_ws_server.py
git commit -m "feat(agent): agent_text_complete'i Edge-TTS'e bağla, fallback+kesme mantığı ekle"
```

---

### Task 4: `agent/config.py` + `agent/main.py` — `JARVIS_TTS_VOICE`

**Files:**
- Modify: `agent/config.py`
- Modify: `agent/tests/test_config.py`
- Modify: `agent/main.py`
- Modify: `agent/.env.example`
- Modify: `agent/.env`

**Interfaces:**
- Produces: `JarvisConfig.tts_voice: str` — tam Azure ses ID'si (`tr-TR-AhmetNeural`/`tr-TR-EmelNeural`), `.env`'deki kısa isimden (`Ahmet`/`Emel`) çözülüyor.

- [ ] **Step 1: Failing testleri ekle (ve `gemini_voice`'u kaldıran testleri güncelle)**

`agent/tests/test_config.py`'nin tamamını şu içerikle değiştir:

```python
from agent.config import load_config


def test_load_config_reads_provided_env_mapping():
    env = {
        "GEMINI_API_KEY": "test-key-123",
        "JARVIS_WS_HOST": "0.0.0.0",
        "JARVIS_WS_PORT": "9999",
        "JARVIS_GEMINI_MODEL": "gemini-test-model",
        "JARVIS_WEATHER_LOCATION": "Safranbolu, Karabük",
        "JARVIS_REPORT_PROJECTS": "Odakla:C:/Odakla,Jarvis:C:/jarvis",
        "JARVIS_MODE": "calisma",
        "JARVIS_SEARCH_ROOT": "C:/Users/x/Documents",
        "JARVIS_TTS_VOICE": "Emel",
    }

    config = load_config(env=env)

    assert config.gemini_api_key == "test-key-123"
    assert config.ws_host == "0.0.0.0"
    assert config.ws_port == 9999
    assert config.gemini_model == "gemini-test-model"
    assert config.weather_location == "Safranbolu, Karabük"
    assert config.report_projects == "Odakla:C:/Odakla,Jarvis:C:/jarvis"
    assert config.mode == "calisma"
    assert config.search_root == "C:/Users/x/Documents"
    assert config.tts_voice == "tr-TR-EmelNeural"


def test_load_config_has_sane_defaults_when_env_is_empty():
    config = load_config(env={})

    assert config.gemini_api_key == ""
    assert config.ws_host == "127.0.0.1"
    assert config.ws_port == 8765
    assert config.gemini_model == "gemini-3.1-flash-live-preview"
    assert config.weather_location == ""
    assert config.report_projects == ""
    assert config.mode == "rahat"
    assert config.search_root == ""
    assert config.tts_voice == "tr-TR-AhmetNeural"


def test_load_config_falls_back_to_ahmet_for_unknown_tts_voice_name():
    config = load_config(env={"JARVIS_TTS_VOICE": "BilinmeyenSes"})

    assert config.tts_voice == "tr-TR-AhmetNeural"


def test_load_config_reads_env_file_from_jarvis_env_path(tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "GEMINI_API_KEY=from-custom-path\nJARVIS_TTS_VOICE=Emel\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_TTS_VOICE", raising=False)
    monkeypatch.setenv("JARVIS_ENV_PATH", str(env_file))

    config = load_config()

    assert config.gemini_api_key == "from-custom-path"
    assert config.tts_voice == "tr-TR-EmelNeural"
```

(Bu, eski `gemini_voice`/`JARVIS_GEMINI_VOICE` referanslarını tamamen
kaldırıyor — alan `tts_voice`'a taşınıyor, `config.py`'de de kaldırılacak.)

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_config.py -v`
Expected: `tts_voice` kullanan testler FAIL (`AttributeError: 'JarvisConfig'
object has no attribute 'tts_voice'`); `gemini_voice`'suz hale gelen diğer
testler de `TypeError: load_config() got an unexpected keyword` DEĞİL ama
`JarvisConfig.__init__()` hâlâ `gemini_voice` zorunlu alanı istediği için
FAIL olabilir — bu beklenen, Step 3 düzeltecek.

- [ ] **Step 3: `agent/config.py`'yi güncelle**

Dosyanın en üstüne, `from dotenv import load_dotenv` satırının altına ekle:

```python

_TTS_VOICE_IDS = {
    "Ahmet": "tr-TR-AhmetNeural",
    "Emel": "tr-TR-EmelNeural",
}
_DEFAULT_TTS_VOICE_ID = _TTS_VOICE_IDS["Ahmet"]
```

`JarvisConfig`'teki `gemini_voice: str` satırını SİL, `search_root: str`
satırının altına `tts_voice: str` ekle:

```python
@dataclass
class JarvisConfig:
    gemini_api_key: str
    ws_host: str
    ws_port: int
    gemini_model: str
    weather_location: str
    report_projects: str
    mode: str
    search_root: str
    tts_voice: str
```

`load_config`'in return'ündeki `gemini_voice=env.get("JARVIS_GEMINI_VOICE", "Kore"),`
satırını SİL, `search_root=env.get(...)` satırının altına ekle:

```python
        tts_voice=_TTS_VOICE_IDS.get(env.get("JARVIS_TTS_VOICE", "Ahmet"), _DEFAULT_TTS_VOICE_ID),
```

- [ ] **Step 4: Testleri çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_config.py -v`
Expected: PASS, tüm testler yeşil

- [ ] **Step 5: `agent/main.py`'yi güncelle**

`build_components`'taki `JarvisServer(...)` çağrısını:

```python
    server = JarvisServer(
        host=config.ws_host,
        port=config.ws_port,
        weather_default_location=config.weather_location,
    )
```

şununla değiştir:

```python
    server = JarvisServer(
        host=config.ws_host,
        port=config.ws_port,
        weather_default_location=config.weather_location,
        tts_voice=config.tts_voice,
    )
```

`LiveSession(...)` çağrısındaki `voice=config.gemini_voice,` satırını SİL:

```python
    live_session = LiveSession(
        client=client,
        model=config.gemini_model,
        voice=config.gemini_voice,
        tools=tools,
        on_event=server.handle_live_event,
        mode=config.mode,
    )
```

şununla değiştir:

```python
    live_session = LiveSession(
        client=client,
        model=config.gemini_model,
        tools=tools,
        on_event=server.handle_live_event,
        mode=config.mode,
    )
```

- [ ] **Step 6: Syntax kontrolü**

Run: `./agent/venv/Scripts/python.exe -c "import agent.main"`
Expected: hata yok (import zinciri bozulmamış)

- [ ] **Step 7: `agent/.env.example` ve `agent/.env`'i güncelle**

Her iki dosyada da `JARVIS_GEMINI_VOICE=Kore` satırını
`JARVIS_TTS_VOICE=Ahmet` ile değiştir.

- [ ] **Step 8: Commit**

```bash
git add agent/config.py agent/tests/test_config.py agent/main.py agent/.env.example
git commit -m "feat(agent): JARVIS_TTS_VOICE config alanı + main.py wiring"
```

(`agent/.env` gitignore'da, commit'e dahil olmuyor — elle kaydedildi.)

---

### Task 5: `shell/settings.js` — `MANAGED_KEYS` güncellemesi

**Files:**
- Modify: `shell/settings.js`
- Modify: `shell/settings.test.js`

- [ ] **Step 1: Failing testi ekle**

`shell/settings.test.js`'de `test('MANAGED_KEYS includes JARVIS_MODE', ...)`
testinin hemen altına ekle:

```js
test('MANAGED_KEYS includes JARVIS_TTS_VOICE', () => {
  assert.ok(MANAGED_KEYS.includes('JARVIS_TTS_VOICE'));
});
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `node --test shell/settings.test.js`
Expected: yeni test FAIL

- [ ] **Step 3: `shell/settings.js`'i güncelle**

`MANAGED_KEYS` dizisindeki `'JARVIS_GEMINI_VOICE',` satırını
`'JARVIS_TTS_VOICE',` ile değiştir (diğer anahtarların sırası/varlığı
aynı kalıyor).

- [ ] **Step 4: Tüm dosyanın testlerini çalıştır, geçtiğini doğrula**

Run: `node --test shell/settings.test.js`
Expected: PASS, tüm testler (eskiler dahil) yeşil

- [ ] **Step 5: Commit**

```bash
git add shell/settings.js shell/settings.test.js
git commit -m "feat(shell): MANAGED_KEYS'te JARVIS_GEMINI_VOICE'u JARVIS_TTS_VOICE ile değiştir"
```

---

### Task 6: SETTINGS SES dropdown + tarayıcı TTS fallback

**Files:**
- Modify: `shell/renderer/index.html`
- Modify: `shell/renderer/renderer.js`

**Bu görevde otomatik test yok** (DOM/renderer kodu, mevcut renderer.js
deseniyle aynı). Elle doğrulama adımları aşağıda.

- [ ] **Step 1: `shell/renderer/index.html`'i güncelle**

"SES" dropdown'ının içeriğini:

```html
        <select id="settings-voice">
          <option value="">—</option>
          <option value="Charon">Charon</option>
          <option value="Puck">Puck</option>
          <option value="Aoede">Aoede</option>
          <option value="Kore">Kore</option>
          <option value="Fenrir">Fenrir</option>
          <option value="Leda">Leda</option>
          <option value="Orus">Orus</option>
          <option value="Zephyr">Zephyr</option>
        </select>
```

şununla değiştir:

```html
        <select id="settings-voice">
          <option value="Ahmet">Ahmet</option>
          <option value="Emel">Emel</option>
        </select>
```

- [ ] **Step 2: `shell/renderer/renderer.js`'i güncelle**

`loadSettingsForm`'daki satırı:

```js
  settingsVoice.value = settings.JARVIS_GEMINI_VOICE || '';
```

şununla değiştir:

```js
  settingsVoice.value = settings.JARVIS_TTS_VOICE || 'Ahmet';
```

`settingsSave`'in `saveSettings` çağrısındaki satırı:

```js
    JARVIS_GEMINI_VOICE: settingsVoice.value,
```

şununla değiştir:

```js
    JARVIS_TTS_VOICE: settingsVoice.value,
```

Dosyanın sonunda, `const UPDATE_STATUS_TEXT = {` bloğunun ÜSTÜNE yeni bir
fonksiyon ekle:

```js
function speakWithBrowserFallback(text) {
  if (!('speechSynthesis' in window) || !text) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'tr-TR';
  window.speechSynthesis.speak(utterance);
}
```

WebSocket mesaj handler'ındaki (`socket.addEventListener('message', ...)`)
if/else zincirini:

```js
  } else if (msg.type === 'weather_info') {
    updateWeather(msg.data);
  }
});
```

şununla değiştir:

```js
  } else if (msg.type === 'weather_info') {
    updateWeather(msg.data);
  } else if (msg.type === 'tts_failed') {
    speakWithBrowserFallback(msg.text);
  }
});
```

- [ ] **Step 3: Syntax kontrolü**

Run: `node -c shell/renderer/renderer.js`
Expected: hata yok (çıktı boş)

- [ ] **Step 4: Elle doğrula (uçtan uca canlı test)**

1. Gerçek bir `GEMINI_API_KEY` girilmiş `agent/.env` ile
   `cd shell && npm start`.
2. "asistan" de veya yazılı komutla bir şey sor.
3. Cevabın artık Ahmet'in doğal sesiyle geldiğini doğrula (Gemini'nin eski
   robotik sesiyle KARŞILAŞTIR — fark net duyulmalı).
4. DEBUG panelinden SETTINGS'e geç, "SES" dropdown'ının Ahmet/Emel
   gösterdiğini, Emel'e çevirip kaydedince (agent restart sonrası) yeni
   sorularda Emel'in sesiyle cevap geldiğini doğrula.
5. Fallback'i test etmek için (opsiyonel ama önerilir): `agent/tools/tts.py`
   içindeki `_run_ffmpeg`'i geçici olarak `raise RuntimeError("test")`
   yapıp bir soru sor — konuşma metninin hâlâ transcript panelde göründüğünü
   VE tarayıcının kendi (daha robotik) sesiyle seslendirildiğini doğrula,
   sonra değişikliği geri al.
6. Konuşurken araya girip (yeni bir komut söyleyip) sesin anında kesildiğini,
   eski cevabın kalıntısının duyulmadığını doğrula.

- [ ] **Step 5: Commit**

```bash
git add shell/renderer/index.html shell/renderer/renderer.js
git commit -m "feat(shell): SES dropdown'ını Ahmet/Emel'e çevir, tts_failed için tarayıcı fallback'i ekle"
```
