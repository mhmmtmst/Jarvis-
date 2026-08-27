# Jarvis Canlı Sesli Etkileşim (Live Voice) Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jarvis'i tek seferlik metin (`generate_content`) + offline Whisper mimarisinden, Gemini'nin gerçek zamanlı ses↔ses **Live API**'sine geçirmek; hem push-to-talk hem "jarvis" wake-word ile tetiklenebilen, kendi sesiyle (Türkçe dahil) cevap veren bir asistan hâline getirmek.

**Architecture:** `agent/` (Python) açılışta tek bir kalıcı Gemini Live oturumu (`agent/gemini/live_session.py`) ve bağımsız bir arka plan wake-word döngüsü (`agent/wake_word.py`) başlatır; `agent/ws_server.py` bu ikisini shell'e bağlayan JSON+binary WebSocket köprüsüdür. `shell/` (Electron) push-to-talk sırasında mikrofonu bir AudioWorklet ile PCM16'ya çevirip binary frame olarak akıtır, gelen ses frame'lerini Web Audio ile çalar; yazılı komutlar ve durum/metin hâlâ JSON frame.

**Tech Stack:** Python 3.13, `google-genai>=2.19.0` (Live API doğrulandı: `client.aio.live.connect`, `AsyncSession.send_realtime_input/send_client_content/send_tool_response/receive`), `SpeechRecognition>=3.14.0` + `PyAudio>=0.2.14` (ikisi de bu makinede Python 3.13 için hazır wheel ile kuruldu, doğrulandı — sounddevice alternatifine gerek yok), `websockets`, Electron/Chromium Web Audio API (`AudioWorkletProcessor`, `AudioContext`).

## Global Constraints

- Model adı: `gemini-live-2.5-flash-preview` (google-genai 2.19.0'ın kendi `live.py` docstring örneklerinden doğrulandı, Vertex/enterprise değil, standart Developer API client için).
- Ses formatı: giden mikrofon `audio/pcm;rate=16000` (16-bit little-endian PCM, mono), gelen model sesi her zaman 24kHz PCM (ai.google.dev/gemini-api/docs/live-guide'dan doğrulandı).
- Varsayılan ses adı: `Kore` (resmi dokümandaki örnek), `.env`'de `JARVIS_GEMINI_VOICE` ile değiştirilebilir olmalı.
- Otomatik ses algılama (`automatic_activity_detection.disabled`) kapatılmalı — push-to-talk/wake-word manuel `activity_start`/`activity_end` ile tetikler, sürekli dinleme yapılmaz (wake-word'ün kendi ayrı ses hattı hariç).
- Python tarafında async testler `pytest-asyncio` eklemeden düz `asyncio.run(...)` ile yazılır (yeni bağımlılık yok, YAGNI).
- Mevcut `agent/tools/registry.py`, `agent/tools/open_app.py`, `agent/tools/system_info.py` hiç değişmiyor.
- Tüm testler jarvis kök dizininden çalıştırılır: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_X.py -v`. JS testleri: `node --test shell/renderer/protocol.test.js`.

---

## Dosya Yapısı

**Silinecek:**
- `agent/gemini/backend.py`, `agent/gemini/client.py`
- `agent/dispatch.py`
- `agent/stt/` (tüm klasör: `__init__.py`, `whisper_stt.py`)
- `agent/tests/test_gemini_backend.py`, `agent/tests/test_gemini_client.py`, `agent/tests/test_dispatch.py`, `agent/tests/test_whisper_stt.py`

**Yeni:**
- `agent/gemini/live_session.py` + `agent/tests/test_live_session.py`
- `agent/wake_word.py` + `agent/tests/test_wake_word.py`
- `agent/tests/test_ws_server.py`
- `shell/renderer/pcm-worklet.js`

**Değişecek:**
- `agent/config.py`, `agent/tests/test_config.py`
- `agent/requirements.txt`, `agent/.env.example`
- `agent/main.py`
- `agent/ws_server.py`
- `shell/renderer/protocol.js`, `shell/renderer/protocol.test.js`
- `shell/renderer/renderer.js`
- `shell/renderer/index.html`, `shell/renderer/styles.css`

**Değişmeyen:** `agent/tools/registry.py`, `agent/tools/open_app.py`, `agent/tools/system_info.py` ve testleri.

---

### Task 1: Config + bağımlılıklar

**Files:**
- Modify: `agent/config.py`
- Modify: `agent/tests/test_config.py`
- Modify: `agent/requirements.txt`
- Modify: `agent/.env.example`

**Interfaces:**
- Produces: `JarvisConfig` dataclass artık `gemini_voice: str` alanına sahip, `whisper_model` alanı yok. `load_config(env=None) -> JarvisConfig` imzası aynı.

- [ ] **Step 1: Test dosyasını güncelle (whisper_model kalksın, gemini_voice eklensin)**

`agent/tests/test_config.py` tam içeriği:

```python
from agent.config import load_config


def test_load_config_reads_provided_env_mapping():
    env = {
        "GEMINI_API_KEY": "test-key-123",
        "JARVIS_WS_HOST": "0.0.0.0",
        "JARVIS_WS_PORT": "9999",
        "JARVIS_GEMINI_MODEL": "gemini-test-model",
        "JARVIS_GEMINI_VOICE": "Puck",
    }

    config = load_config(env=env)

    assert config.gemini_api_key == "test-key-123"
    assert config.ws_host == "0.0.0.0"
    assert config.ws_port == 9999
    assert config.gemini_model == "gemini-test-model"
    assert config.gemini_voice == "Puck"


def test_load_config_has_sane_defaults_when_env_is_empty():
    config = load_config(env={})

    assert config.gemini_api_key == ""
    assert config.ws_host == "127.0.0.1"
    assert config.ws_port == 8765
    assert config.gemini_model == "gemini-live-2.5-flash-preview"
    assert config.gemini_voice == "Kore"
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_config.py -v`
Expected: FAIL (`AttributeError: 'JarvisConfig' object has no attribute 'gemini_voice'` veya benzeri, `whisper_model` alanı zaten default değerle eşleşmeyecek şekilde test değişti)

- [ ] **Step 3: `agent/config.py`'yi güncelle**

Tam içerik:

```python
from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass
class JarvisConfig:
    gemini_api_key: str
    ws_host: str
    ws_port: int
    gemini_model: str
    gemini_voice: str


def load_config(env: dict | None = None) -> JarvisConfig:
    """Build a JarvisConfig. Pass `env` in tests to avoid touching real
    environment variables or the .env file."""
    if env is None:
        load_dotenv()
        env = os.environ

    return JarvisConfig(
        gemini_api_key=env.get("GEMINI_API_KEY", ""),
        ws_host=env.get("JARVIS_WS_HOST", "127.0.0.1"),
        ws_port=int(env.get("JARVIS_WS_PORT", "8765")),
        gemini_model=env.get("JARVIS_GEMINI_MODEL", "gemini-live-2.5-flash-preview"),
        gemini_voice=env.get("JARVIS_GEMINI_VOICE", "Kore"),
    )
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: `requirements.txt` ve `.env.example`'ı güncelle**

`agent/requirements.txt` tam içerik:

```
google-genai>=2.19.0
SpeechRecognition>=3.14.0
PyAudio>=0.2.14
websockets>=13.0
psutil>=6.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

`agent/.env.example` tam içerik:

```
GEMINI_API_KEY=buraya-kendi-anahtarini-yaz
JARVIS_WS_HOST=127.0.0.1
JARVIS_WS_PORT=8765
JARVIS_GEMINI_MODEL=gemini-live-2.5-flash-preview
JARVIS_GEMINI_VOICE=Kore
```

- [ ] **Step 6: Commit**

```bash
git add agent/config.py agent/tests/test_config.py agent/requirements.txt agent/.env.example
git commit -m "feat(agent): config için whisper_model yerine gemini_voice"
```

---

### Task 2: Eski metin/STT pipeline'ını kaldır

**Files:**
- Delete: `agent/gemini/backend.py`, `agent/gemini/client.py`
- Delete: `agent/dispatch.py`
- Delete: `agent/stt/__init__.py`, `agent/stt/whisper_stt.py` (klasörün tamamı)
- Delete: `agent/tests/test_gemini_backend.py`, `agent/tests/test_gemini_client.py`, `agent/tests/test_dispatch.py`, `agent/tests/test_whisper_stt.py`

**Interfaces:**
- Consumes: yok (sadece silme)
- Produces: yok — Task 5+ bu dosyaların yerine geçecek `live_session.py`'yi oluşturacak

- [ ] **Step 1: Dosyaları sil**

```bash
git rm agent/gemini/backend.py agent/gemini/client.py
git rm agent/dispatch.py
git rm agent/stt/__init__.py agent/stt/whisper_stt.py
git rm agent/tests/test_gemini_backend.py agent/tests/test_gemini_client.py agent/tests/test_dispatch.py agent/tests/test_whisper_stt.py
```

- [ ] **Step 2: `agent/venv`'den artık gereksiz `openai-whisper`/`torch` bağımlılığını kaldır (opsiyonel, disk yer açar)**

```bash
./agent/venv/Scripts/python.exe -m pip uninstall -y openai-whisper torch torchvision torchaudio
```

Bu adım başarısız olsa bile (ör. bağımlı paket hatası) devam edilebilir — `requirements.txt`'de zaten yok, önemli olan yeni kurulumların onu tekrar indirmemesi.

- [ ] **Step 3: Kalan test paketinin hâlâ toplanabildiğini doğrula (import hatası olmamalı)**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/ -v --collect-only`
Expected: Silinen dosyalara ait test yok, kalanlar (`test_config.py`, `test_open_app.py`, `test_registry.py`, `test_system_info.py`) hatasız toplanıyor.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(agent): tek seferlik generate_content + Whisper pipeline'ını kaldır"
```

---

### Task 3: Wake-word metin ayrıştırma (saf fonksiyon)

**Files:**
- Create: `agent/wake_word.py`
- Create: `agent/tests/test_wake_word.py`

**Interfaces:**
- Produces: `extract_command_after_wake_word(text: str) -> str | None` — `None` = "jarvis" yok; `""` = "jarvis" var ama arkasında komut yok (takip dinlemesi gerekir); başka bir string = wake-word'den sonraki komut metni.

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_wake_word.py` (bu adımda sadece bu fonksiyona dair testler):

```python
from agent.wake_word import extract_command_after_wake_word


def test_returns_none_when_wake_word_absent():
    assert extract_command_after_wake_word("bugün hava nasıl") is None


def test_returns_empty_string_when_wake_word_alone():
    assert extract_command_after_wake_word("jarvis") == ""
    assert extract_command_after_wake_word("Jarvis!") == ""


def test_returns_remainder_after_wake_word():
    assert extract_command_after_wake_word("jarvis saati söyle") == "saati söyle"


def test_is_case_and_turkish_char_insensitive():
    assert extract_command_after_wake_word("JARVİS not defterini aç") == "not defterini aç"


def test_ignores_wake_word_as_substring_of_another_word():
    assert extract_command_after_wake_word("jarvisimsi bir şey") is None
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_wake_word.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agent.wake_word'`)

- [ ] **Step 3: `agent/wake_word.py`'yi oluştur (bu adımda sadece ayrıştırma fonksiyonu)**

```python
import re
import unicodedata

_WAKE_PATTERN = re.compile(r"\bjarvis\b")


def _fold_turkish(text: str) -> str:
    text = text.lower().replace("ı", "i").replace("i̇", "i")
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def extract_command_after_wake_word(text: str) -> str | None:
    """None -> 'jarvis' metinde yok. '' -> 'jarvis' var ama arkasında komut
    yok, çağıran taraf takip dinlemesi yapmalı. Başka bir string -> wake-word
    sonrası komut metni (orijinal, foldlanmamış metinden alınır)."""
    folded = _fold_turkish(text)
    match = _WAKE_PATTERN.search(folded)
    if match is None:
        return None
    remainder = text[match.end():].strip(" ,.:;!?")
    return remainder
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_wake_word.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/wake_word.py agent/tests/test_wake_word.py
git commit -m "feat(agent): jarvis wake-word metin ayrıştırma"
```

---

### Task 4: WakeWordListener orkestrasyon (pause/resume, run_iteration)

**Files:**
- Modify: `agent/wake_word.py` (Task 3'ün üzerine ekleme)
- Modify: `agent/tests/test_wake_word.py` (yeni testler ekleme)

**Interfaces:**
- Consumes: `extract_command_after_wake_word` (Task 3)
- Produces: `WakeWordListener` sınıfı:
  - `__init__(self, on_command: Callable[[str], Awaitable[None]], on_wake_status: Callable[[bool], Awaitable[None]], recognizer=None, microphone_factory=None)`
  - `pause(self) -> None`, `resume(self) -> None`
  - `async def run_iteration(self) -> None` — testler bunu doğrudan çağırır
  - `async def run(self) -> None` — sonsuz döngü, `main.py` bunu çağırır

- [ ] **Step 1: Failing testleri ekle**

`agent/tests/test_wake_word.py`'nin sonuna ekle:

```python
import asyncio


class FakeRecognizer:
    def __init__(self, transcripts):
        self._transcripts = list(transcripts)

    def recognize_google(self, audio, language="tr-TR"):
        result = self._transcripts.pop(0)
        if result is None:
            raise LookupError("recognize_google should not be called without audio")
        return result

    def listen(self, source, timeout=None, phrase_time_limit=None):
        return object()


class FakeMicrophoneContext:
    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False


def make_listener(transcripts, commands, wake_statuses):
    async def on_command(text):
        commands.append(text)

    async def on_wake_status(active):
        wake_statuses.append(active)

    from agent.wake_word import WakeWordListener

    return WakeWordListener(
        on_command=on_command,
        on_wake_status=on_wake_status,
        recognizer=FakeRecognizer(transcripts),
        microphone_factory=lambda: FakeMicrophoneContext(),
    )


def test_run_iteration_dispatches_command_when_wake_word_and_command_together():
    commands, statuses = [], []
    listener = make_listener(["jarvis saati söyle"], commands, statuses)

    asyncio.run(listener.run_iteration())

    assert commands == ["saati söyle"]


def test_run_iteration_does_nothing_when_no_wake_word():
    commands, statuses = [], []
    listener = make_listener(["bugün hava nasıl"], commands, statuses)

    asyncio.run(listener.run_iteration())

    assert commands == []


def test_run_iteration_listens_again_when_wake_word_alone():
    commands, statuses = [], []
    listener = make_listener(["jarvis", "not defterini aç"], commands, statuses)

    asyncio.run(listener.run_iteration())

    assert commands == ["not defterini aç"]


def test_paused_listener_skips_recognition():
    commands, statuses = [], []
    listener = make_listener([], commands, statuses)
    listener.pause()

    asyncio.run(listener.run_iteration())

    assert commands == []


def test_run_emits_wake_status_true_then_false_around_iterations():
    commands, statuses = [], []
    listener = make_listener(["jarvis merhaba"], commands, statuses)

    call_count = {"n": 0}
    original = listener.run_iteration

    async def run_once_then_stop():
        call_count["n"] += 1
        await original()
        if call_count["n"] >= 1:
            raise StopAsyncIteration

    listener.run_iteration = run_once_then_stop

    async def scenario():
        try:
            await listener.run()
        except StopAsyncIteration:
            pass

    asyncio.run(scenario())

    assert statuses == [True, False]
    assert commands == ["merhaba"]
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_wake_word.py -v`
Expected: FAIL (`ImportError: cannot import name 'WakeWordListener'`)

- [ ] **Step 3: `WakeWordListener`'ı `agent/wake_word.py`'ye ekle**

Dosyanın sonuna ekle (üstteki `extract_command_after_wake_word`/`_fold_turkish` kalır):

```python
import asyncio
from typing import Awaitable, Callable

import speech_recognition as sr


class WakeWordListener:
    """Arka planda sürekli mikrofonu dinler, konuşmayı Google'ın ücretsiz
    web API'siyle metne çevirir, 'jarvis' geçip geçmediğine bakar. Push-to-talk
    ile aynı mikrofonu aynı anda kullanmamak için `pause`/`resume` ile
    dışarıdan durdurulabilir."""

    def __init__(
        self,
        on_command: Callable[[str], Awaitable[None]],
        on_wake_status: Callable[[bool], Awaitable[None]],
        recognizer=None,
        microphone_factory=None,
    ):
        self._on_command = on_command
        self._on_wake_status = on_wake_status
        self._recognizer = recognizer if recognizer is not None else sr.Recognizer()
        self._microphone_factory = microphone_factory if microphone_factory is not None else sr.Microphone
        self._paused = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    async def run(self) -> None:
        await self._on_wake_status(True)
        try:
            while True:
                await self.run_iteration()
        finally:
            await self._on_wake_status(False)

    async def run_iteration(self) -> None:
        if self._paused:
            await asyncio.sleep(0.2)
            return

        text = await asyncio.to_thread(self._listen_once)
        if text is None:
            return

        remainder = extract_command_after_wake_word(text)
        if remainder is None:
            return

        if remainder == "":
            follow_up = await asyncio.to_thread(self._listen_once, timeout=5, phrase_time_limit=6)
            if follow_up:
                await self._on_command(follow_up)
        else:
            await self._on_command(remainder)

    def _listen_once(self, timeout: float = 5, phrase_time_limit: float = 4) -> str | None:
        try:
            with self._microphone_factory() as source:
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            return self._recognizer.recognize_google(audio, language="tr-TR")
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            return None
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_wake_word.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Mikrofon açılamazsa devre dışı kalma için failing test ekle (spec'in Hata Yönetimi bölümü)**

`agent/tests/test_wake_word.py`'ye ekle:

```python
class FailingMicrophoneFactory:
    def __call__(self):
        raise OSError("mikrofon açılamadı")


def test_run_disables_itself_and_reports_wake_status_false_when_mic_unavailable():
    commands, statuses = [], []
    async def on_command(text):
        commands.append(text)
    async def on_wake_status(active):
        statuses.append(active)

    from agent.wake_word import WakeWordListener

    listener = WakeWordListener(
        on_command=on_command,
        on_wake_status=on_wake_status,
        recognizer=FakeRecognizer([]),
        microphone_factory=FailingMicrophoneFactory(),
    )

    asyncio.run(listener.run())

    assert statuses == [True, False]
    assert commands == []
```

- [ ] **Step 6: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_wake_word.py -v`
Expected: FAIL (`OSError` yakalanmadığı için test'in kendisi hata ile patlar, `run()` hiç dönmez)

- [ ] **Step 7: `WakeWordListener`'a mikrofon-kapalı durumunu ekle**

`__init__`'e `self._mic_unavailable = False` ekle. `run_iteration`'ı güncelle (mikrofon açma hatasını yakala):

```python
    async def run_iteration(self) -> None:
        if self._paused:
            await asyncio.sleep(0.2)
            return

        try:
            text = await asyncio.to_thread(self._listen_once)
        except OSError:
            self._mic_unavailable = True
            return

        if text is None:
            return

        remainder = extract_command_after_wake_word(text)
        if remainder is None:
            return

        if remainder == "":
            follow_up = await asyncio.to_thread(self._listen_once, timeout=5, phrase_time_limit=6)
            if follow_up:
                await self._on_command(follow_up)
        else:
            await self._on_command(remainder)
```

`run`'ı güncelle (mikrofon kapalıysa döngüden çık):

```python
    async def run(self) -> None:
        self._mic_unavailable = False
        await self._on_wake_status(True)
        try:
            while not self._mic_unavailable:
                await self.run_iteration()
        finally:
            await self._on_wake_status(False)
```

- [ ] **Step 8: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_wake_word.py -v`
Expected: PASS (11 passed)

- [ ] **Step 9: Commit**

```bash
git add agent/wake_word.py agent/tests/test_wake_word.py
git commit -m "feat(agent): WakeWordListener orkestrasyonu (pause/resume, run_iteration, mikrofon hatasında devre dışı kalma)"
```

---

### Task 5: LiveSession — bağlantı + yazılı komut + transcript

**Files:**
- Create: `agent/gemini/live_session.py`
- Create: `agent/tests/test_live_session.py`

**Interfaces:**
- Consumes: `agent/tools/registry.py`'nin `ToolSpec` (Task 5'te henüz tool-calling yok, sadece import/parametre için)
- Produces: `LiveSession` sınıfı:
  - `__init__(self, client, model: str, voice: str, tools: dict[str, ToolSpec], on_event: Callable[[dict], Awaitable[None]])`
  - `async def run(self) -> None`
  - `async def send_text(self, text: str) -> None`
  - Event sözlük şekilleri: `{"type": "transcript", "role": "user"|"agent", "text": str}`, `{"type": "turn_complete"}`

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_live_session.py`:

```python
import asyncio
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
    output_transcription=None,
):
    return SimpleNamespace(
        model_turn=model_turn,
        turn_complete=turn_complete,
        interrupted=interrupted,
        input_transcription=input_transcription,
        output_transcription=output_transcription,
    )


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


def test_run_emits_user_transcript_from_input_transcription():
    content = make_server_content(input_transcription=SimpleNamespace(text="saat kaç"))
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "transcript", "role": "user", "text": "saat kaç"} in events


def test_run_does_not_emit_turn_complete_when_false():
    content = make_server_content(turn_complete=False)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "turn_complete"} not in events


def test_send_text_sends_client_content_with_user_role():
    async def scenario():
        session = FakeSession(messages=[])
        client = FakeClient(session)
        async def on_event(event):
            pass

        live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
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
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agent.gemini.live_session'`)

- [ ] **Step 3: `agent/gemini/live_session.py`'yi oluştur (bu adımda tool-calling ve ses yok)**

```python
from google.genai import types

from agent.tools.registry import ToolSpec


class LiveSession:
    """Tek, kalıcı bir Gemini Live oturumunu sarar. Olayları `on_event` ile
    (düz dict) dışarı verir; bu sayede ws_server bu modülün WebSocket'ten
    hiç haberdar olmasına gerek kalmadan olayları frame'e çevirebilir."""

    def __init__(self, client, model: str, voice: str, tools: dict[str, ToolSpec], on_event):
        self._client = client
        self._model = model
        self._voice = voice
        self._tools = tools
        self._on_event = on_event
        self._session = None

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

    async def run(self) -> None:
        config = self._build_config()
        async with self._client.aio.live.connect(model=self._model, config=config) as session:
            self._session = session
            async for message in session.receive():
                await self._handle_message(message)

    async def send_text(self, text: str) -> None:
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part.from_text(text=text)]),
            turn_complete=True,
        )

    async def _handle_message(self, message) -> None:
        content = message.server_content
        if content is None:
            return

        if content.input_transcription is not None and content.input_transcription.text:
            await self._on_event({"type": "transcript", "role": "user", "text": content.input_transcription.text})

        if content.output_transcription is not None and content.output_transcription.text:
            await self._on_event({"type": "transcript", "role": "agent", "text": content.output_transcription.text})

        if content.turn_complete:
            await self._on_event({"type": "turn_complete"})
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/gemini/live_session.py agent/tests/test_live_session.py
git commit -m "feat(agent): LiveSession - bağlantı, yazılı komut, transcript"
```

---

### Task 6: LiveSession — ses akışı (mikrofon girişi + ses çıkışı)

**Files:**
- Modify: `agent/gemini/live_session.py`
- Modify: `agent/tests/test_live_session.py`

**Interfaces:**
- Produces (ek): `async def start_activity(self) -> None`, `async def send_audio_chunk(self, pcm_bytes: bytes) -> None`, `async def end_activity(self) -> None`; yeni event: `{"type": "audio_chunk", "data": bytes}`

- [ ] **Step 1: Failing testleri ekle**

`test_live_session.py`'ye ekle (dosyanın başındaki fake'ler aynı kalır):

```python
def test_send_audio_chunk_sends_pcm_blob_with_correct_mime_type():
    async def scenario():
        session = FakeSession(messages=[])
        client = FakeClient(session)
        async def on_event(event):
            pass

        live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
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


def test_run_emits_audio_chunk_event_from_model_turn_inline_data():
    inline_part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\xaa\xbb"))
    turn = SimpleNamespace(parts=[inline_part])
    content = make_server_content(model_turn=turn)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "audio_chunk", "data": b"\xaa\xbb"} in events


def test_run_ignores_model_turn_parts_without_inline_data():
    text_part = SimpleNamespace(inline_data=None)
    turn = SimpleNamespace(parts=[text_part])
    content = make_server_content(model_turn=turn)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert not any(e["type"] == "audio_chunk" for e in events)
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: FAIL (`AttributeError: 'LiveSession' object has no attribute 'start_activity'`)

- [ ] **Step 3: `live_session.py`'ye ses metodlarını ekle**

`send_text` metodunun altına ekle:

```python
    async def start_activity(self) -> None:
        await self._session.send_realtime_input(activity_start=types.ActivityStart())

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
        )

    async def end_activity(self) -> None:
        await self._session.send_realtime_input(activity_end=types.ActivityEnd())
```

`_handle_message`'ı, `model_turn` işleyecek şekilde güncelle (turn_complete kontrolünden önce ekle):

```python
        if content.model_turn is not None:
            for part in content.model_turn.parts or []:
                if part.inline_data is not None and part.inline_data.data:
                    await self._on_event({"type": "audio_chunk", "data": part.inline_data.data})
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/gemini/live_session.py agent/tests/test_live_session.py
git commit -m "feat(agent): LiveSession - mikrofon girişi (activity/audio) ve ses çıkışı"
```

---

### Task 7: LiveSession — tool-calling

**Files:**
- Modify: `agent/gemini/live_session.py`
- Modify: `agent/tests/test_live_session.py`

**Interfaces:**
- Consumes: `ToolSpec.handler(**kwargs) -> dict` (registry'den, değişmedi)
- Produces: model bir tool çağırdığında otomatik olarak handler çalıştırılıp `send_tool_response` ile sonuç geri gönderiliyor (dışarıya yeni bir public metod yok, `run()` içinde otomatik işleniyor)

- [ ] **Step 1: Failing testleri ekle**

```python
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
    live = LiveSession(client=client, model="m", voice="Kore", tools={"get_system_info": tool}, on_event=on_event)
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
    live = LiveSession(client=client, model="m", voice="Kore", tools={"open_app": tool}, on_event=on_event)
    asyncio.run(live.run())

    assert received_args == {"isim": "not defteri"}


def test_run_reports_error_for_unknown_tool_without_calling_any_handler():
    call = SimpleNamespace(id="call-3", name="does_not_exist", args={})
    tool_call = SimpleNamespace(function_calls=[call])
    session = FakeSession(messages=[make_message(tool_call=tool_call)])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    _, function_responses = session.sent[0]
    assert function_responses[0].response["status"] == "error"
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: FAIL (`message.tool_call` hiç işlenmediği için `session.sent` boş kalır, `IndexError`)

- [ ] **Step 3: `_handle_message`'ı tool_call işleyecek şekilde güncelle**

`_handle_message`'ın en başına ekle (content kontrolünden önce):

```python
    async def _handle_message(self, message) -> None:
        if message.tool_call is not None:
            await self._handle_tool_call(message.tool_call)
            return

        content = message.server_content
        ...
```

Dosyanın sonuna yeni metod ekle:

```python
    async def _handle_tool_call(self, tool_call) -> None:
        import asyncio

        responses = []
        for call in tool_call.function_calls:
            tool = self._tools.get(call.name)
            if tool is None:
                result = {"status": "error", "message": f"Bilinmeyen araç: {call.name}"}
            else:
                result = await asyncio.to_thread(tool.handler, **(call.args or {}))
            responses.append(types.FunctionResponse(id=call.id, name=call.name, response=result))
        await self._session.send_tool_response(function_responses=responses)
```

(Dosyanın en üstüne `import asyncio` eklemek daha temiz — yukarıdaki fonksiyon-içi import yerine dosya başına taşı.)

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/gemini/live_session.py agent/tests/test_live_session.py
git commit -m "feat(agent): LiveSession - tool-calling (registry handler'ları Live oturumuna bağlama)"
```

---

### Task 8: LiveSession — kesme (interrupted) sinyali

**Files:**
- Modify: `agent/gemini/live_session.py`
- Modify: `agent/tests/test_live_session.py`

**Interfaces:**
- Produces (ek event): `{"type": "interrupted"}`

- [ ] **Step 1: Failing testi ekle**

```python
def test_run_emits_interrupted_event():
    content = make_server_content(interrupted=True)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "interrupted"} in events


def test_run_does_not_emit_interrupted_when_false():
    content = make_server_content(interrupted=False)
    session = FakeSession(messages=[make_message(server_content=content)])
    client = FakeClient(session)
    events = []
    async def on_event(event):
        events.append(event)

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    assert {"type": "interrupted"} not in events
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: FAIL (`interrupted` event hiç üretilmiyor)

- [ ] **Step 3: `_handle_message`'a ekle**

`content is None` kontrolünden hemen sonra, `input_transcription` kontrolünden önce:

```python
        if content.interrupted:
            await self._on_event({"type": "interrupted"})
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/gemini/live_session.py agent/tests/test_live_session.py
git commit -m "feat(agent): LiveSession - interrupted sinyalini event olarak yay"
```

---

### Task 9: `ws_server.py` — JSON+binary köprü

**Files:**
- Modify: `agent/ws_server.py`
- Create: `agent/tests/test_ws_server.py`

**Interfaces:**
- Consumes: `LiveSession.send_text/start_activity/send_audio_chunk/end_activity` (Task 5-7), `WakeWordListener.pause/resume` (Task 4)
- Produces: `JarvisServer`:
  - `__init__(self, host: str, port: int)` — `self.live_session` ve `self.wake_word_listener` `None` başlar, `main.py` construction sonrası atar
  - `async def handle_live_event(self, event: dict) -> None` — `LiveSession`'ın `on_event` callback'i olarak geçilir
  - `async def handle_wake_command(self, text: str) -> None`, `async def handle_wake_status(self, active: bool) -> None` — `WakeWordListener`'ın callback'leri
  - `async def serve_forever(self) -> None`

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_ws_server.py`:

```python
import asyncio
import json

from agent.ws_server import JarvisServer


class FakeLiveSession:
    def __init__(self):
        self.calls = []

    async def send_text(self, text):
        self.calls.append(("send_text", text))

    async def start_activity(self):
        self.calls.append(("start_activity",))

    async def send_audio_chunk(self, pcm_bytes):
        self.calls.append(("send_audio_chunk", pcm_bytes))

    async def end_activity(self):
        self.calls.append(("end_activity",))


class FakeWakeWordListener:
    def __init__(self):
        self.paused = False
        self.resumed = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.resumed = True


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(data)


def make_server():
    server = JarvisServer(host="127.0.0.1", port=0)
    server.live_session = FakeLiveSession()
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


def test_binary_frame_with_tag_0x01_forwards_audio_chunk():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, b"\x01\xde\xad\xbe\xef"))

    assert ("send_audio_chunk", b"\xde\xad\xbe\xef") in server.live_session.calls


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


def test_new_turn_while_speaking_broadcasts_interrupt_first():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)
    asyncio.run(server.handle_live_event({"type": "audio_chunk", "data": b"\x01"}))
    ws.sent.clear()

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_start"})))

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert messages[0] == {"type": "interrupt"}
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_ws_server.py -v`
Expected: FAIL (mevcut `JarvisServer` hâlâ eski `gemini_client`/`transcribe_fn` imzasını bekliyor, `TypeError`)

- [ ] **Step 3: `agent/ws_server.py`'yi tamamen yeniden yaz**

Eski dosyadaki `from agent.dispatch import dispatch_text, dispatch_voice` importu ve `dispatch`'e yapılan tüm çağrılar kalkıyor (Task 2'de `dispatch.py` zaten silindi). Tam içerik:

```python
import asyncio
import json

import websockets

from agent.tools.system_info import get_system_info


class JarvisServer:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._clients: set = set()
        self._speaking = False
        self.live_session = None
        self.wake_word_listener = None

    async def _handler(self, websocket) -> None:
        self._clients.add(websocket)
        try:
            async for raw in websocket:
                await self._handle_client_message(websocket, raw)
        finally:
            self._clients.discard(websocket)

    async def _handle_client_message(self, websocket, raw) -> None:
        if isinstance(raw, (bytes, bytearray)):
            await self._handle_binary(raw)
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"type": "error", "message": "Geçersiz mesaj."}))
            return

        msg_type = msg.get("type")
        if msg_type == "command":
            # Yazılı komut: "listening" durumu atlanır (mikrofon yok), direkt "thinking".
            await self._maybe_interrupt()
            await self._broadcast_json({"type": "status", "state": "thinking"})
            await self.live_session.send_text(msg.get("text", ""))
        elif msg_type == "ptt_start":
            await self._maybe_interrupt()
            self.wake_word_listener.pause()
            await self._broadcast_json({"type": "status", "state": "listening"})
            await self.live_session.start_activity()
        elif msg_type == "ptt_end":
            await self.live_session.end_activity()
            await self._broadcast_json({"type": "status", "state": "thinking"})
            self.wake_word_listener.resume()
        else:
            await websocket.send(json.dumps({"type": "error", "message": f"Bilinmeyen mesaj tipi: {msg_type}"}))

    async def _handle_binary(self, raw: bytes) -> None:
        if not raw:
            return
        tag, payload = raw[0], bytes(raw[1:])
        if tag == 0x01:
            await self.live_session.send_audio_chunk(payload)

    async def _maybe_interrupt(self) -> None:
        """Yeni bir kullanıcı turu başlıyor (ptt basıldı, yazılı komut ya da
        wake-word). Jarvis hâlâ konuşuyorsa shell'e anında kesme sinyali
        gönderilir."""
        if self._speaking:
            await self._broadcast_json({"type": "interrupt"})
        self._speaking = False

    async def handle_wake_command(self, text: str) -> None:
        # Wake-word'ün kendi mikrofon yakalaması ("JARVIS DİNLİYOR" rozeti)
        # zaten ayrı bir kanalda gösteriliyor; burada gelen `text` komut
        # tamamen yakalanmış oluyor, o yüzden "listening" kısaca gösterilip
        # hemen "thinking"e geçiliyor.
        await self._maybe_interrupt()
        await self._broadcast_json({"type": "status", "state": "listening"})
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self.live_session.send_text(text)

    async def handle_wake_status(self, active: bool) -> None:
        await self._broadcast_json({"type": "wake_status", "active": active})

    async def handle_live_event(self, event: dict) -> None:
        etype = event["type"]
        if etype == "audio_chunk":
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
        elif etype == "error":
            await self._broadcast_json({"type": "error", "message": event["message"]})

    async def _broadcast_json(self, payload: dict) -> None:
        data = json.dumps(payload)
        for client in list(self._clients):
            try:
                await client.send(data)
            except websockets.exceptions.ConnectionClosed:
                self._clients.discard(client)

    async def _broadcast_binary(self, data: bytes) -> None:
        for client in list(self._clients):
            try:
                await client.send(data)
            except websockets.exceptions.ConnectionClosed:
                self._clients.discard(client)

    async def _broadcast_system_info(self) -> None:
        while True:
            info = await asyncio.to_thread(get_system_info)
            await self._broadcast_json({"type": "system_info", "data": info})
            await asyncio.sleep(3)

    async def serve_forever(self) -> None:
        async with websockets.serve(self._handler, self._host, self._port):
            await self._broadcast_system_info()
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_ws_server.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/ws_server.py agent/tests/test_ws_server.py
git commit -m "feat(agent): ws_server'ı Live/wake-word ile JSON+binary köprüsüne dönüştür"
```

---

### Task 10: `main.py` — bileşenleri birbirine bağla

**Files:**
- Modify: `agent/main.py`

**Interfaces:**
- Consumes: `JarvisServer`, `LiveSession`, `WakeWordListener` (Task 4, 5-8, 9), `load_config`, `build_tool_registry`
- Produces: `build_components() -> tuple[JarvisServer, LiveSession, WakeWordListener]`, `main_async()`, `main()`, `_attempt_live_session(live_session, on_error, backoff_seconds) -> None` (spec'in "Live bağlantısı kopar/kurulamazsa otomatik yeniden bağlanma" gereksinimi için)

- [ ] **Step 1: Yeniden-bağlanma denemesi için failing test yaz**

`agent/tests/test_main.py` (yeni dosya):

```python
import asyncio

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
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_main.py -v`
Expected: FAIL (`ImportError: cannot import name '_attempt_live_session'`)

- [ ] **Step 3: `agent/main.py`'yi tamamen yeniden yaz**

`build_components`/`main_async`/`main` için yeni bir davranış (test edilebilir saf mantık) yok — composition root olarak kalıyorlar, sadece `_attempt_live_session`/`run_live_session_with_backoff` yeni ve test edilen kısım. Tam içerik:

```python
import asyncio

from google import genai

from agent.config import load_config
from agent.gemini.live_session import LiveSession
from agent.tools.registry import build_tool_registry
from agent.wake_word import WakeWordListener
from agent.ws_server import JarvisServer


def build_components() -> tuple[JarvisServer, LiveSession, WakeWordListener]:
    config = load_config()
    tools = build_tool_registry()
    client = genai.Client(api_key=config.gemini_api_key)

    server = JarvisServer(host=config.ws_host, port=config.ws_port)

    live_session = LiveSession(
        client=client,
        model=config.gemini_model,
        voice=config.gemini_voice,
        tools=tools,
        on_event=server.handle_live_event,
    )

    wake_word_listener = WakeWordListener(
        on_command=server.handle_wake_command,
        on_wake_status=server.handle_wake_status,
    )

    server.live_session = live_session
    server.wake_word_listener = wake_word_listener

    return server, live_session, wake_word_listener


async def _attempt_live_session(live_session: LiveSession, on_error, backoff_seconds: float) -> None:
    """Tek bir bağlantı denemesi. `live_session.run()` hata fırlatırsa (bağlantı
    koptu/kurulamadı) `on_error` ile HUD'a bildirir ve backoff kadar bekler;
    normal döndüyse (örn. sunucu oturumu kapattı) sessizce döner — her iki
    durumda da çağıran taraf (bkz. `run_live_session_with_backoff`) yeniden
    dener."""
    try:
        await live_session.run()
    except Exception as error:
        await on_error(str(error))
        await asyncio.sleep(backoff_seconds)


async def run_live_session_with_backoff(live_session: LiveSession, on_error, backoff_seconds: float = 5) -> None:
    while True:
        await _attempt_live_session(live_session, on_error, backoff_seconds)


async def main_async() -> None:
    server, live_session, wake_word_listener = build_components()

    async def on_live_error(message: str) -> None:
        await server.handle_live_event({"type": "error", "message": message})

    await asyncio.gather(
        server.serve_forever(),
        run_live_session_with_backoff(live_session, on_live_error),
        wake_word_listener.run(),
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_main.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Modülün import edilebildiğini doğrula (gerçek ağ çağrısı yapmadan)**

Run: `./agent/venv/Scripts/python.exe -c "from agent.main import build_components; print('ok')"`
Expected: `ok` yazdırır, hata yok (bu adım gerçek Gemini bağlantısı kurmaz, sadece nesneler doğru şekilde birbirine bağlanabiliyor mu diye import kontrolü yapar).

- [ ] **Step 6: Commit**

```bash
git add agent/main.py agent/tests/test_main.py
git commit -m "feat(agent): main.py'yi LiveSession + WakeWordListener ile yeniden bağla, Live bağlantısı için backoff'lu yeniden deneme ekle"
```

---

### Task 11: `protocol.js` — yeni frame encode/decode

**Files:**
- Modify: `shell/renderer/protocol.js`
- Modify: `shell/renderer/protocol.test.js`

**Interfaces:**
- Produces: `buildTextCommand(text)` (değişmedi), `buildPttStart()`, `buildPttEnd()`, `encodeAudioChunk(int16Array) -> ArrayBuffer`, `decodeServerFrame(data) -> object` (hem binary hem JSON'ı ayırt eder), `parseServerMessage(raw)` (değişmedi, `decodeServerFrame` içeriden kullanır)
- `buildVoiceCommand` kaldırıldı.

- [ ] **Step 1: Failing testleri yaz**

`shell/renderer/protocol.test.js` tam içerik:

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const {
  buildTextCommand,
  buildPttStart,
  buildPttEnd,
  encodeAudioChunk,
  decodeServerFrame,
  parseServerMessage,
} = require('./protocol');

test('buildTextCommand encodes text as a command message', () => {
  const raw = buildTextCommand('not defterini aç');
  assert.deepEqual(JSON.parse(raw), { type: 'command', text: 'not defterini aç' });
});

test('buildPttStart encodes a ptt_start message', () => {
  assert.deepEqual(JSON.parse(buildPttStart()), { type: 'ptt_start' });
});

test('buildPttEnd encodes a ptt_end message', () => {
  assert.deepEqual(JSON.parse(buildPttEnd()), { type: 'ptt_end' });
});

test('encodeAudioChunk prefixes PCM16 data with tag 0x01', () => {
  const pcm = new Int16Array([1, -1, 256]);
  const frame = encodeAudioChunk(pcm);
  const bytes = new Uint8Array(frame);

  assert.equal(bytes[0], 0x01);
  assert.equal(bytes.length, 1 + pcm.byteLength);
  const payload = new Int16Array(bytes.slice(1).buffer);
  assert.deepEqual(Array.from(payload), [1, -1, 256]);
});

test('decodeServerFrame parses JSON text frames via parseServerMessage', () => {
  const msg = decodeServerFrame('{"type":"status","state":"idle"}');
  assert.deepEqual(msg, { type: 'status', state: 'idle' });
});

test('decodeServerFrame decodes tag 0x02 binary frames as audio_chunk', () => {
  const payload = new Uint8Array([9, 8, 7]);
  const frame = new Uint8Array(1 + payload.length);
  frame[0] = 0x02;
  frame.set(payload, 1);

  const msg = decodeServerFrame(frame.buffer);

  assert.equal(msg.type, 'audio_chunk');
  assert.deepEqual(Array.from(new Uint8Array(msg.data)), [9, 8, 7]);
});

test('decodeServerFrame throws on unknown binary tag', () => {
  const frame = new Uint8Array([0x99, 1, 2]);
  assert.throws(() => decodeServerFrame(frame.buffer));
});

test('parseServerMessage returns the parsed object for a valid message', () => {
  const msg = parseServerMessage('{"type":"response","text":"merhaba"}');
  assert.deepEqual(msg, { type: 'response', text: 'merhaba' });
});

test('parseServerMessage throws when "type" is missing', () => {
  assert.throws(() => parseServerMessage('{"text":"merhaba"}'));
});
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `node --test shell/renderer/protocol.test.js`
Expected: FAIL (`buildPttStart`/`buildPttEnd`/`encodeAudioChunk`/`decodeServerFrame` tanımsız — `require` sonucu `undefined`)

- [ ] **Step 3: `shell/renderer/protocol.js`'yi güncelle**

Tam içerik:

```js
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.jarvisProtocol = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  function buildTextCommand(text) {
    return JSON.stringify({ type: 'command', text });
  }

  function buildPttStart() {
    return JSON.stringify({ type: 'ptt_start' });
  }

  function buildPttEnd() {
    return JSON.stringify({ type: 'ptt_end' });
  }

  function encodeAudioChunk(int16Array) {
    const bytes = new Uint8Array(int16Array.buffer, int16Array.byteOffset, int16Array.byteLength);
    const frame = new Uint8Array(1 + bytes.length);
    frame[0] = 0x01;
    frame.set(bytes, 1);
    return frame.buffer;
  }

  function parseServerMessage(raw) {
    const msg = JSON.parse(raw);
    if (typeof msg.type !== 'string') {
      throw new Error('Sunucu mesajında "type" alanı yok.');
    }
    return msg;
  }

  function decodeServerFrame(data) {
    if (data instanceof ArrayBuffer) {
      const bytes = new Uint8Array(data);
      if (bytes[0] === 0x02) {
        return { type: 'audio_chunk', data: bytes.slice(1).buffer };
      }
      throw new Error('Bilinmeyen binary frame tipi: ' + bytes[0]);
    }
    return parseServerMessage(data);
  }

  return {
    buildTextCommand,
    buildPttStart,
    buildPttEnd,
    encodeAudioChunk,
    decodeServerFrame,
    parseServerMessage,
  };
});
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `node --test shell/renderer/protocol.test.js`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add shell/renderer/protocol.js shell/renderer/protocol.test.js
git commit -m "feat(shell): protocol.js - ptt/binary ses frame encode-decode"
```

---

### Task 12: `pcm-worklet.js` — mikrofon yakalama processor'ı

**Files:**
- Create: `shell/renderer/pcm-worklet.js`

**Interfaces:**
- Produces: `pcm-worklet-processor` adında kayıtlı bir `AudioWorkletProcessor`; ana thread'e `port.postMessage` ile `ArrayBuffer` (Int16 PCM) gönderir.
- Not: Gerçek bir `AudioContext`/`AudioWorklet` gerektirdiği için Node.js test ortamında otomatik test edilemez — bu görev sadece manuel doğrulamayla kapanır (Task 17'de).

- [ ] **Step 1: Dosyayı oluştur**

```js
class PCMWorkletProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];
      const pcm16 = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        const sample = Math.max(-1, Math.min(1, channelData[i]));
        pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-worklet-processor', PCMWorkletProcessor);
```

**Not:** Bu processor, `AudioContext`'in `{ sampleRate: 16000 }` ile oluşturulduğunu varsayar (Task 13'te böyle kurulacak) — kendi başına resampling yapmaz, tarayıcının native resampling'ine güvenir.

- [ ] **Step 2: Commit**

```bash
git add shell/renderer/pcm-worklet.js
git commit -m "feat(shell): mikrofon PCM16 yakalama için AudioWorkletProcessor"
```

---

### Task 13: `renderer.js` — push-to-talk mikrofon yakalama

**Files:**
- Modify: `shell/renderer/renderer.js`

**Interfaces:**
- Consumes: `window.jarvisProtocol.buildPttStart/buildPttEnd/encodeAudioChunk` (Task 11), `pcm-worklet.js` (Task 12, `audioContext.audioWorklet.addModule('pcm-worklet.js')` ile yüklenir)

- [ ] **Step 1: `renderer.js`'deki eski `MediaRecorder` tabanlı kaydı kaldır, yerine AudioWorklet tabanlı yakalamayı ekle**

`startRecording`/`stopRecording`/`blobToBase64` fonksiyonlarını ve `mediaRecorder`/`audioChunks` değişkenlerini komple sil. **`shouldStopRecording` guard'ı (mikrofon izni beklenirken keyup gelirse diye — bkz. mevcut kod tabanındaki `fix(shell): guard push-to-talk against keydown/keyup race before mic permission resolves` commit'i) aynen korunuyor**, sadece MediaRecorder yerine AudioWorklet'e uyarlanıyor:

```js
const PUSH_TO_TALK_KEY = ' ';
let recordingState = 'idle'; // 'idle' | 'starting' | 'recording'
let shouldStopRecording = false;
let captureContext = null;
let captureWorkletNode = null;
let captureStream = null;

async function startRecording() {
  if (recordingState !== 'idle') return; // Guard against re-entry (keydown repeat, multiple starts)
  recordingState = 'starting';
  shouldStopRecording = false;
  try {
    captureStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    captureContext = new AudioContext({ sampleRate: 16000 });
    await captureContext.audioWorklet.addModule('pcm-worklet.js');

    const source = captureContext.createMediaStreamSource(captureStream);
    captureWorkletNode = new AudioWorkletNode(captureContext, 'pcm-worklet-processor');
    captureWorkletNode.port.onmessage = (event) => {
      if (recordingState !== 'recording') return;
      socket.send(window.jarvisProtocol.encodeAudioChunk(new Int16Array(event.data)));
    };
    source.connect(captureWorkletNode);

    recordingState = 'recording';
    setAgentState('listening');
    socket.send(window.jarvisProtocol.buildPttStart());

    // If keyup fired while we were waiting for permission, stop immediately
    if (shouldStopRecording) {
      stopRecording();
    }
  } catch (err) {
    recordingState = 'idle';
    throw err;
  }
}

function stopRecording() {
  if (recordingState === 'starting') {
    // Mark to stop once recording actually starts
    shouldStopRecording = true;
    return;
  }

  if (recordingState !== 'recording') return;

  recordingState = 'idle'; // Prevent multiple concurrent stops

  socket.send(window.jarvisProtocol.buildPttEnd());

  captureWorkletNode.port.onmessage = null;
  captureWorkletNode.disconnect();
  captureWorkletNode = null;

  captureStream.getTracks().forEach((track) => track.stop());
  captureStream = null;

  captureContext.close();
  captureContext = null;
}
```

`window.addEventListener('keydown', ...)` / `keyup` blokları aynı kalır (zaten `startRecording`/`stopRecording`'i çağırıyorlar, imzaları değişmedi).

- [ ] **Step 2: Manuel doğrulama (bu görev için otomatik test yok — gerçek mikrofon/AudioContext gerektirir)**

`npm start` ile shell'i aç, push-to-talk tuşuna bas, DevTools Console'da hata olmadığını ve `socket.send` çağrılarının (Network/WS panelinden) binary frame gönderdiğini doğrula. Gerçek uçtan uca ses testi Task 17'de.

- [ ] **Step 3: Commit**

```bash
git add shell/renderer/renderer.js
git commit -m "feat(shell): push-to-talk mikrofon yakalamayı MediaRecorder'dan AudioWorklet'e taşı"
```

---

### Task 14: `renderer.js` — ses çalma (playback) + kesme

**Files:**
- Modify: `shell/renderer/renderer.js`

**Interfaces:**
- Consumes: `decodeServerFrame` (Task 11) sonucu `{type: 'audio_chunk', data: ArrayBuffer}` ve `{type: 'interrupt'}`

- [ ] **Step 1: Playback altyapısını ekle**

Dosyanın üst kısmına (socket tanımından sonra) ekle:

```js
const playbackContext = new AudioContext({ sampleRate: 24000 });
let nextPlaybackTime = 0;
let scheduledSources = [];

function playAudioChunk(arrayBuffer) {
  const pcm16 = new Int16Array(arrayBuffer);
  const float32 = new Float32Array(pcm16.length);
  for (let i = 0; i < pcm16.length; i++) {
    float32[i] = pcm16[i] / (pcm16[i] < 0 ? 0x8000 : 0x7fff);
  }

  const buffer = playbackContext.createBuffer(1, float32.length, 24000);
  buffer.copyToChannel(float32, 0);

  const source = playbackContext.createBufferSource();
  source.buffer = buffer;
  source.connect(playbackContext.destination);

  const startTime = Math.max(nextPlaybackTime, playbackContext.currentTime);
  source.start(startTime);
  nextPlaybackTime = startTime + buffer.duration;

  scheduledSources.push(source);
  source.onended = () => {
    scheduledSources = scheduledSources.filter((s) => s !== source);
  };
}

function stopPlaybackImmediately() {
  scheduledSources.forEach((source) => {
    try {
      source.stop();
    } catch (err) {
      // zaten bitmiş olabilir, yok say
    }
  });
  scheduledSources = [];
  nextPlaybackTime = 0;
}
```

- [ ] **Step 2: Mesaj işleyiciyi `decodeServerFrame` kullanacak ve yeni tipleri (transcript/interrupt/turn_complete/wake_status) ele alacak şekilde güncelle**

Mevcut `socket.addEventListener('message', ...)` bloğunu komple değiştir:

```js
socket.binaryType = 'arraybuffer';

socket.addEventListener('message', (event) => {
  const msg = window.jarvisProtocol.decodeServerFrame(event.data);

  if (msg.type === 'audio_chunk') {
    playAudioChunk(msg.data);
  } else if (msg.type === 'status') {
    setAgentState(msg.state);
  } else if (msg.type === 'transcript') {
    appendLog(msg.role === 'user' ? 'user' : 'jarvis', msg.text);
  } else if (msg.type === 'interrupt') {
    stopPlaybackImmediately();
  } else if (msg.type === 'turn_complete') {
    // durum zaten ayrı bir 'status' mesajıyla idle'a dönüyor, burada ek iş yok
  } else if (msg.type === 'wake_status') {
    wakeIndicator.classList.toggle('active', msg.active);
  } else if (msg.type === 'error') {
    appendLog('error', msg.message);
  } else if (msg.type === 'system_info') {
    updateSystemInfo(msg.data);
  }
});
```

- [ ] **Step 3: Manuel doğrulama**

`npm start` ile shell'i aç, DevTools Console'da `decodeServerFrame`/`playAudioChunk` çağrılarında hata olmadığını doğrula (gerçek ses çıkışı Task 17'de agent tarafı da hazır olunca test edilecek).

- [ ] **Step 4: Commit**

```bash
git add shell/renderer/renderer.js
git commit -m "feat(shell): Web Audio ile ses çalma + kesme (interrupt) desteği"
```

---

### Task 15: `renderer.js` + `index.html` + `styles.css` — HUD durumları ve wake rozeti

**Files:**
- Modify: `shell/renderer/index.html`
- Modify: `shell/renderer/styles.css`
- Modify: `shell/renderer/renderer.js`

**Interfaces:**
- Consumes: Task 14'te eklenen `wake_status`/`status` mesaj işleme

- [ ] **Step 1: `index.html`'e wake rozetini ekle**

`hud-top` header'ını güncelle:

```html
  <header class="hud-top">
    <span id="connection-status" class="status-pill">CONNECTING</span>
    <span id="wake-indicator" class="wake-indicator">JARVIS DİNLİYOR</span>
  </header>
```

- [ ] **Step 2: `styles.css`'e wake rozeti ve `speaking` durumu stillerini ekle**

Dosyanın sonuna ekle (mevcut `.visualizer[data-state="listening"]` vb. kurallarının yanına, aynı dosyadaki mevcut renk/spacing değişkenleriyle tutarlı şekilde):

```css
.wake-indicator {
  opacity: 0.35;
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  margin-left: 0.75rem;
  transition: opacity 0.2s ease;
}

.wake-indicator.active {
  opacity: 1;
}

.visualizer[data-state="speaking"] { box-shadow: 0 0 60px rgba(120, 130, 255, 0.5) inset; }
```

(Mevcut `[data-state="listening"]`/`[data-state="thinking"]` kuralları da statik `box-shadow` kullanıyor, `speaking` için de aynı desen — yeni bir animasyon eklenmiyor.)

- [ ] **Step 3: `renderer.js`'de `wakeIndicator` referansını ekle**

Dosyanın en üstündeki `document.getElementById` bloklarının yanına ekle:

```js
const wakeIndicator = document.getElementById('wake-indicator');
```

(Task 14'teki `wake_status` handler'ı zaten bu değişkeni kullanıyor.)

- [ ] **Step 4: Manuel doğrulama**

`npm start` ile shell'i aç, DevTools'ta `document.getElementById('wake-indicator')`'ın `null` dönmediğini doğrula.

- [ ] **Step 5: Commit**

```bash
git add shell/renderer/index.html shell/renderer/styles.css shell/renderer/renderer.js
git commit -m "feat(shell): speaking durumu + JARVIS DİNLİYOR rozeti"
```

---

### Task 16: Tüm otomatik test paketini uçtan uca çalıştır

**Files:** yok (sadece doğrulama)

- [ ] **Step 1: Python testlerinin tamamını çalıştır**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/ -v`
Expected: Tüm testler PASS (Task 1-9'daki yeni testler + değişmeyen `test_open_app.py`/`test_registry.py`/`test_system_info.py`)

- [ ] **Step 2: JS testlerinin tamamını çalıştır**

Run: `node --test shell/renderer/protocol.test.js`
Expected: Tüm testler PASS

- [ ] **Step 3: Herhangi bir test kırmızıysa düzelt, hepsi yeşil olana kadar tekrar çalıştır**

- [ ] **Step 4: Commit (sadece düzeltme gerektiyse)**

```bash
git add -A
git commit -m "fix: tam test paketi geçene kadar kalan uyumsuzlukları düzelt"
```

---

### Task 17: Uçtan uca manuel doğrulama (spec'in "sadece elle doğrulanacaklar" listesi)

**Files:** yok

- [ ] **Step 1: `agent/.env`'e gerçek `GEMINI_API_KEY` girildiğini doğrula**

- [ ] **Step 2: Agent'ı başlat, Live oturumunun hatasız kurulduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m agent.main`
Expected: Hata fırlatmadan çalışmaya devam ediyor (Ctrl+C ile durdurulana kadar).

- [ ] **Step 3: Shell'i başlat, push-to-talk ile gerçek bir komut söyle ("saat kaç", "not defterini aç")**

Run: `cd shell && npm start`
Expected: Jarvis Türkçe sesli cevap veriyor, HUD `listening → thinking → speaking → idle` sırasıyla geçiyor, konuşma panelinde hem kullanıcı hem Jarvis transcript'i görünüyor.

- [ ] **Step 4: "jarvis" diyerek wake-word'ü tetikle (push-to-talk'a basmadan)**

Expected: "JARVIS DİNLİYOR" rozeti sürekli aktif görünüyor; "jarvis" dendiğinde `listening` durumuna geçip komutu işliyor.

- [ ] **Step 5: Jarvis konuşurken tekrar "jarvis" de veya push-to-talk'a bas**

Expected: Çalmakta olan ses anında kesiliyor, yeni komut işleniyor (spec'teki kesme davranışı).

- [ ] **Step 6: Push-to-talk ile wake-word'ü art arda dene (biri diğerini bozmadan)**

Expected: Push-to-talk basılıyken wake-word döngüsü duraklıyor (mikrofon çakışması yok), bırakılınca devam ediyor.

- [ ] **Step 7: Herhangi bir sorun bulunursa not al, gerekiyorsa küçük bir düzeltme commit'i at**
