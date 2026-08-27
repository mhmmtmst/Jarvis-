# Jarvis v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working v1 of Jarvis — a personal desktop agent you can command by typed text or push-to-talk voice, that can open applications and report system status, shown through a full-screen HUD.

**Architecture:** A Python 3.13 background service (`agent/`) owns the Gemini connection, tool execution, and local Whisper speech-to-text, and exposes a local WebSocket server. An Electron app (`shell/`) renders a full-screen HUD and talks to that WebSocket server as a client. The two processes are started independently and communicate only over `ws://127.0.0.1:8765`.

**Tech Stack:** Python 3.13, `google-genai` (Gemini function calling), `openai-whisper` (local STT), `websockets`, `psutil`, `python-dotenv`, `pytest`; Electron (Node's built-in `node:test` for pure-JS unit tests).

## Global Constraints

- `agent/` runs on Python 3.13 (updated from the original 3.12 target — 3.12 is not installed on this machine; 3.13 installs all dependencies, including `torch`, without error). Use `agent/venv/Scripts/python` for every command below.
- v1 has exactly two tools: `open_app(isim)` and `get_system_info()`. No other tool is added in this plan.
- No wake-word / continuous listening — activation is push-to-talk only (a key held while focused on the Jarvis window).
- No TTS — Jarvis replies as text in the HUD conversation panel only.
- No weather widget, no calendar/mail, no terminal-command tool, no camera access in v1.
- STT runs locally via Whisper — audio is never sent to a cloud STT service.
- The Gemini API key lives in `agent/.env` (via `python-dotenv`) and must never be committed; `.gitignore` must cover it.
- Communication between `agent/` and `shell/` is a local WebSocket at `127.0.0.1:8765` (configurable via env vars), JSON messages only.
- Working directory for all commands below is the project root: `C:\Users\mhmmt\OneDrive\Masaüstü\jarvis`.

---

## Task 1: Project scaffolding + agent config

**Files:**
- Create: `jarvis.txt` — leave as-is, untouched by this plan
- Create: `.gitignore`
- Create: `agent/__init__.py`
- Create: `agent/requirements.txt`
- Create: `agent/.env.example`
- Create: `agent/config.py`
- Create: `agent/tests/__init__.py`
- Create: `agent/tests/test_config.py`

**Interfaces:**
- Produces: `agent.config.JarvisConfig` (dataclass: `gemini_api_key: str`, `ws_host: str`, `ws_port: int`, `whisper_model: str`, `gemini_model: str`) and `agent.config.load_config(env: dict | None = None) -> JarvisConfig`, used by every later Python task.

- [ ] **Step 1: Create scaffolding files**

Create `.gitignore` at the project root:

```
# Python
agent/venv/
agent/__pycache__/
agent/**/__pycache__/
agent/.env
*.pyc

# Node / Electron
shell/node_modules/
shell/dist/

# OS
Thumbs.db
```

Create `agent/requirements.txt`:

```
google-genai>=1.0.0
openai-whisper>=20231117
websockets>=13.0
psutil>=6.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

Create `agent/.env.example`:

```
GEMINI_API_KEY=buraya-kendi-anahtarini-yaz
JARVIS_WS_HOST=127.0.0.1
JARVIS_WS_PORT=8765
JARVIS_WHISPER_MODEL=base
JARVIS_GEMINI_MODEL=gemini-3.5-flash
```

Create empty `agent/__init__.py` and empty `agent/tests/__init__.py`.

- [ ] **Step 2: Set up the Python virtual environment**

Run:
```bash
cd agent
py -3.13 -m venv venv
venv/Scripts/python -m pip install -r requirements.txt
cd ..
```
Expected: dependencies install without error (this also confirms Python 3.13 and pip are working).

**Already done:** Task 1's implementer already completed this step under Python
3.13.9 (3.12 is not installed on this machine; 3.13 was confirmed to install
all dependencies, including `torch`, without error — see the Global
Constraints update above). `agent/venv/` already exists; do not recreate it.

- [ ] **Step 3: Write the failing test for config loading**

Create `agent/tests/test_config.py`:

```python
from agent.config import load_config


def test_load_config_reads_provided_env_mapping():
    env = {
        "GEMINI_API_KEY": "test-key-123",
        "JARVIS_WS_HOST": "0.0.0.0",
        "JARVIS_WS_PORT": "9999",
        "JARVIS_WHISPER_MODEL": "small",
        "JARVIS_GEMINI_MODEL": "gemini-test-model",
    }

    config = load_config(env=env)

    assert config.gemini_api_key == "test-key-123"
    assert config.ws_host == "0.0.0.0"
    assert config.ws_port == 9999
    assert config.whisper_model == "small"
    assert config.gemini_model == "gemini-test-model"


def test_load_config_has_sane_defaults_when_env_is_empty():
    config = load_config(env={})

    assert config.gemini_api_key == ""
    assert config.ws_host == "127.0.0.1"
    assert config.ws_port == 8765
    assert config.whisper_model == "base"
    assert config.gemini_model == "gemini-3.5-flash"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_config.py -v` (from project root)
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.config'`

- [ ] **Step 5: Implement `agent/config.py`**

```python
from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass
class JarvisConfig:
    gemini_api_key: str
    ws_host: str
    ws_port: int
    whisper_model: str
    gemini_model: str


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
        whisper_model=env.get("JARVIS_WHISPER_MODEL", "base"),
        gemini_model=env.get("JARVIS_GEMINI_MODEL", "gemini-3.5-flash"),
    )
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add .gitignore agent/__init__.py agent/requirements.txt agent/.env.example agent/config.py agent/tests/__init__.py agent/tests/test_config.py
git commit -m "feat(agent): add project scaffolding and env-driven config"
```

---

## Task 2: `get_system_info` tool

**Files:**
- Create: `agent/tools/__init__.py`
- Create: `agent/tools/system_info.py`
- Create: `agent/tests/test_system_info.py`

**Interfaces:**
- Produces: `agent.tools.system_info.get_system_info() -> dict` with keys `cpu_percent: float`, `ram_percent: float`, `disk_percent: float`, `battery_percent: float | None`. Used by Task 4 (registry) and by `ws_server`'s periodic broadcast (Task 9).

- [ ] **Step 1: Write the failing test**

Create `agent/tools/__init__.py` (empty).

Create `agent/tests/test_system_info.py`:

```python
from unittest.mock import MagicMock, patch

from agent.tools.system_info import get_system_info


@patch("agent.tools.system_info.psutil")
def test_get_system_info_returns_expected_keys(mock_psutil):
    mock_psutil.cpu_percent.return_value = 12.3
    mock_psutil.virtual_memory.return_value = MagicMock(percent=45.6)
    mock_psutil.disk_usage.return_value = MagicMock(percent=70.1)
    mock_psutil.sensors_battery.return_value = MagicMock(percent=88)

    info = get_system_info()

    assert info == {
        "cpu_percent": 12.3,
        "ram_percent": 45.6,
        "disk_percent": 70.1,
        "battery_percent": 88,
    }


@patch("agent.tools.system_info.psutil")
def test_get_system_info_handles_missing_battery(mock_psutil):
    mock_psutil.cpu_percent.return_value = 5.0
    mock_psutil.virtual_memory.return_value = MagicMock(percent=20.0)
    mock_psutil.disk_usage.return_value = MagicMock(percent=30.0)
    mock_psutil.sensors_battery.return_value = None

    info = get_system_info()

    assert info["battery_percent"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_system_info.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.tools.system_info'`

- [ ] **Step 3: Implement `agent/tools/system_info.py`**

```python
import psutil


def get_system_info() -> dict:
    """Snapshot of CPU/RAM/disk/battery usage, used both as a Gemini tool
    and as the payload for the HUD's periodic system-status broadcast."""
    battery = psutil.sensors_battery()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("C:\\").percent,
        "battery_percent": battery.percent if battery else None,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_system_info.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add agent/tools/__init__.py agent/tools/system_info.py agent/tests/test_system_info.py
git commit -m "feat(agent): add get_system_info tool"
```

---

## Task 3: `open_app` tool

**Files:**
- Create: `agent/tools/open_app.py`
- Create: `agent/tests/test_open_app.py`

**Interfaces:**
- Produces: `agent.tools.open_app.open_app(isim: str, launcher=None) -> dict` returning `{"status": "ok"|"error", "message": str}`, and `agent.tools.open_app.resolve_app_name(isim: str) -> str`. Used by Task 4 (registry).

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_open_app.py`:

```python
import pytest

from agent.tools.open_app import open_app, resolve_app_name


def test_resolve_app_name_maps_known_turkish_alias():
    assert resolve_app_name("not defteri") == "notepad"


def test_resolve_app_name_is_case_and_space_insensitive():
    assert resolve_app_name("  Not Defteri  ") == "notepad"


def test_resolve_app_name_passes_through_unknown_names():
    assert resolve_app_name("spotify") == "spotify"


def test_open_app_calls_launcher_with_resolved_name_and_reports_success():
    calls = []

    def fake_launcher(name):
        calls.append(name)

    result = open_app("not defteri", launcher=fake_launcher)

    assert calls == ["notepad"]
    assert result == {"status": "ok", "message": "not defteri açıldı."}


def test_open_app_reports_error_when_launcher_fails():
    def failing_launcher(name):
        raise OSError("dosya bulunamadı")

    result = open_app("bilinmeyenuygulama", launcher=failing_launcher)

    assert result["status"] == "error"
    assert "bilinmeyenuygulama" in result["message"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_open_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.tools.open_app'`

- [ ] **Step 3: Implement `agent/tools/open_app.py`**

```python
import os

APP_ALIASES = {
    "not defteri": "notepad",
    "notepad": "notepad",
    "hesap makinesi": "calc",
    "calculator": "calc",
    "chrome": "chrome",
    "google chrome": "chrome",
    "explorer": "explorer",
    "dosya gezgini": "explorer",
}


def resolve_app_name(isim: str) -> str:
    key = isim.strip().lower()
    return APP_ALIASES.get(key, isim.strip())


def open_app(isim: str, launcher=None) -> dict:
    """Open an application or file by (Turkish-friendly) name. `launcher`
    defaults to os.startfile but is injectable for testing."""
    if launcher is None:
        launcher = os.startfile

    resolved = resolve_app_name(isim)
    try:
        launcher(resolved)
        return {"status": "ok", "message": f"{isim} açıldı."}
    except OSError as error:
        return {"status": "error", "message": f"{isim} açılamadı: {error}"}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_open_app.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add agent/tools/open_app.py agent/tests/test_open_app.py
git commit -m "feat(agent): add open_app tool with Turkish alias resolution"
```

---

## Task 4: Tool registry

**Files:**
- Create: `agent/tools/registry.py`
- Create: `agent/tests/test_registry.py`

**Interfaces:**
- Consumes: `open_app` from Task 3, `get_system_info` from Task 2.
- Produces: `agent.tools.registry.ToolSpec` (dataclass: `name: str`, `description: str`, `parameters: dict`, `handler: Callable[..., dict]`) and `agent.tools.registry.build_tool_registry() -> dict[str, ToolSpec]`. Used by Task 5 (`GeminiClient`) and Task 6 (`GoogleGenAIBackend`).

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_registry.py`:

```python
from agent.tools.registry import build_tool_registry


def test_registry_contains_both_v1_tools():
    registry = build_tool_registry()

    assert set(registry.keys()) == {"open_app", "get_system_info"}


def test_open_app_tool_spec_declares_required_isim_parameter():
    spec = build_tool_registry()["open_app"]

    assert spec.parameters["required"] == ["isim"]
    assert "isim" in spec.parameters["properties"]


def test_get_system_info_tool_spec_takes_no_parameters():
    spec = build_tool_registry()["get_system_info"]

    assert spec.parameters["properties"] == {}


def test_tool_handlers_are_callable_and_return_dicts():
    registry = build_tool_registry()

    result = registry["get_system_info"].handler()

    assert isinstance(result, dict)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.tools.registry'`

- [ ] **Step 3: Implement `agent/tools/registry.py`**

```python
from dataclasses import dataclass
from typing import Callable

from agent.tools.open_app import open_app
from agent.tools.system_info import get_system_info


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., dict]


def build_tool_registry() -> dict[str, ToolSpec]:
    return {
        "open_app": ToolSpec(
            name="open_app",
            description="Kullanıcının bilgisayarında bir uygulama veya dosya açar.",
            parameters={
                "type": "object",
                "properties": {
                    "isim": {
                        "type": "string",
                        "description": "Açılacak uygulamanın veya dosyanın adı",
                    }
                },
                "required": ["isim"],
            },
            handler=open_app,
        ),
        "get_system_info": ToolSpec(
            name="get_system_info",
            description="Bilgisayarın CPU, RAM, disk ve batarya kullanım yüzdelerini döner.",
            parameters={"type": "object", "properties": {}},
            handler=get_system_info,
        ),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_registry.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add agent/tools/registry.py agent/tests/test_registry.py
git commit -m "feat(agent): add tool registry for Gemini function declarations"
```

---

## Task 5: Gemini orchestration logic (`GeminiClient`)

This is the provider-agnostic tool-calling loop, unit-tested against a fake
backend so it never touches the network. v1 supports exactly one round of
function calls per command (send → maybe one batch of tool calls → final
answer), which is all `open_app` / `get_system_info` need.

**Files:**
- Create: `agent/gemini/__init__.py`
- Create: `agent/gemini/client.py`
- Create: `agent/tests/test_gemini_client.py`

**Interfaces:**
- Consumes: `agent.tools.registry.ToolSpec` from Task 4.
- Produces: `agent.gemini.client.FunctionCall` (dataclass: `name: str`, `args: dict`), `agent.gemini.client.InitialReply` (dataclass: `function_calls: list[FunctionCall]`, `text: str | None`, `raw: object`), `agent.gemini.client.GeminiBackend` (Protocol with `generate_initial(user_text: str) -> InitialReply` and `generate_followup(initial: InitialReply, tool_results: list[tuple[FunctionCall, dict]]) -> str`), and `agent.gemini.client.GeminiClient(backend, tools: dict[str, ToolSpec])` with `.send_command(user_text: str) -> str`. Used by Task 6 (real backend implements `GeminiBackend`) and Task 8 (`dispatch_text` calls `.send_command`).

- [ ] **Step 1: Write the failing tests**

Create `agent/gemini/__init__.py` (empty).

Create `agent/tests/test_gemini_client.py`:

```python
from agent.gemini.client import FunctionCall, GeminiClient, InitialReply
from agent.tools.registry import ToolSpec


class FakeBackend:
    def __init__(self, initial_reply, followup_text=None):
        self.initial_reply = initial_reply
        self.followup_text = followup_text
        self.followup_calls = []

    def generate_initial(self, user_text):
        return self.initial_reply

    def generate_followup(self, initial, tool_results):
        self.followup_calls.append((initial, tool_results))
        return self.followup_text


def make_tool(name="get_system_info", result=None):
    result = result if result is not None else {"status": "ok"}
    return ToolSpec(
        name=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
        handler=lambda **kwargs: result,
    )


def test_send_command_returns_text_directly_when_no_function_call():
    backend = FakeBackend(InitialReply(function_calls=[], text="merhaba", raw=None))
    client = GeminiClient(backend=backend, tools={})

    reply = client.send_command("selam")

    assert reply == "merhaba"
    assert backend.followup_calls == []


def test_send_command_executes_tool_and_returns_followup_text():
    tool = make_tool(result={"status": "ok", "message": "sistem iyi"})
    initial = InitialReply(
        function_calls=[FunctionCall(name="get_system_info", args={})],
        text=None,
        raw="raw-token",
    )
    backend = FakeBackend(initial, followup_text="Sistem durumu iyi görünüyor.")
    client = GeminiClient(backend=backend, tools={"get_system_info": tool})

    reply = client.send_command("sistem durumu nedir")

    assert reply == "Sistem durumu iyi görünüyor."
    assert len(backend.followup_calls) == 1
    passed_initial, passed_results = backend.followup_calls[0]
    assert passed_initial is initial
    assert passed_results == [
        (FunctionCall(name="get_system_info", args={}), {"status": "ok", "message": "sistem iyi"})
    ]


def test_send_command_reports_error_for_unknown_tool_without_calling_handler():
    initial = InitialReply(
        function_calls=[FunctionCall(name="does_not_exist", args={})],
        text=None,
        raw="raw-token",
    )
    backend = FakeBackend(initial, followup_text="Bir sorun oldu.")
    client = GeminiClient(backend=backend, tools={})

    client.send_command("bilinmeyen komut")

    _, passed_results = backend.followup_calls[0]
    (call, result) = passed_results[0]
    assert call.name == "does_not_exist"
    assert result["status"] == "error"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_gemini_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.gemini.client'`

- [ ] **Step 3: Implement `agent/gemini/client.py`**

```python
from dataclasses import dataclass
from typing import Protocol

from agent.tools.registry import ToolSpec


@dataclass(frozen=True)
class FunctionCall:
    name: str
    args: dict


@dataclass
class InitialReply:
    function_calls: list[FunctionCall]
    text: str | None
    raw: object  # backend-specific token needed to build the followup call


class GeminiBackend(Protocol):
    def generate_initial(self, user_text: str) -> InitialReply: ...

    def generate_followup(
        self,
        initial: InitialReply,
        tool_results: list[tuple[FunctionCall, dict]],
    ) -> str: ...


class GeminiClient:
    def __init__(self, backend: GeminiBackend, tools: dict[str, ToolSpec]):
        self._backend = backend
        self._tools = tools

    def send_command(self, user_text: str) -> str:
        initial = self._backend.generate_initial(user_text)
        if not initial.function_calls:
            return initial.text or ""

        results: list[tuple[FunctionCall, dict]] = []
        for call in initial.function_calls:
            tool = self._tools.get(call.name)
            if tool is None:
                results.append(
                    (call, {"status": "error", "message": f"Bilinmeyen araç: {call.name}"})
                )
                continue
            results.append((call, tool.handler(**call.args)))

        return self._backend.generate_followup(initial, results)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_gemini_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agent/gemini/__init__.py agent/gemini/client.py agent/tests/test_gemini_client.py
git commit -m "feat(agent): add provider-agnostic Gemini tool-calling orchestration"
```

---

## Task 6: Real Gemini backend (`GoogleGenAIBackend`)

Wraps the `google-genai` SDK behind the `GeminiBackend` protocol from Task
5. The SDK client is injectable so the parsing logic can be unit-tested
with a hand-built fake response, never hitting the network.

**Files:**
- Create: `agent/gemini/backend.py`
- Create: `agent/tests/test_gemini_backend.py`

**Interfaces:**
- Consumes: `FunctionCall`, `InitialReply` from Task 5; `ToolSpec` from Task 4.
- Produces: `agent.gemini.backend.GoogleGenAIBackend(api_key: str, model: str, tool_specs: list[ToolSpec], client=None)` implementing `GeminiBackend`. Used by Task 9 (`main.py`).

- [ ] **Step 1: Write the failing tests**

Create `agent/tests/test_gemini_backend.py`:

```python
from types import SimpleNamespace

from agent.gemini.backend import GoogleGenAIBackend
from agent.gemini.client import FunctionCall
from agent.tools.registry import ToolSpec


def make_tool_specs():
    return [
        ToolSpec(
            name="get_system_info",
            description="test",
            parameters={"type": "object", "properties": {}},
            handler=lambda: {},
        )
    ]


class FakeFunctionCallWrapper:
    """Mirrors the real SDK shape: top-level .name, nested .function_call.args."""

    def __init__(self, name, args):
        self.name = name
        self.function_call = SimpleNamespace(args=args)


class FakeResponse:
    def __init__(self, function_calls=None, text=None, content=None):
        self.function_calls = function_calls or []
        self.text = text
        self.candidates = [SimpleNamespace(content=content or SimpleNamespace())]


class FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


def test_generate_initial_returns_text_when_no_function_call():
    fake_client = FakeClient([FakeResponse(text="merhaba")])
    backend = GoogleGenAIBackend(
        api_key="unused", model="gemini-test", tool_specs=make_tool_specs(), client=fake_client
    )

    reply = backend.generate_initial("selam")

    assert reply.function_calls == []
    assert reply.text == "merhaba"


def test_generate_initial_extracts_function_calls():
    fake_call = FakeFunctionCallWrapper(name="get_system_info", args={"a": 1})
    fake_client = FakeClient([FakeResponse(function_calls=[fake_call], text=None)])
    backend = GoogleGenAIBackend(
        api_key="unused", model="gemini-test", tool_specs=make_tool_specs(), client=fake_client
    )

    reply = backend.generate_initial("sistem durumu nedir")

    assert reply.function_calls == [FunctionCall(name="get_system_info", args={"a": 1})]


def test_generate_followup_sends_tool_result_and_returns_final_text():
    initial_content = SimpleNamespace(marker="model-turn")
    fake_call = FakeFunctionCallWrapper(name="get_system_info", args={})
    first_response = FakeResponse(function_calls=[fake_call], text=None, content=initial_content)
    second_response = FakeResponse(text="Sistem durumu iyi.")
    fake_client = FakeClient([first_response, second_response])
    backend = GoogleGenAIBackend(
        api_key="unused", model="gemini-test", tool_specs=make_tool_specs(), client=fake_client
    )

    initial = backend.generate_initial("sistem durumu nedir")
    result_text = backend.generate_followup(
        initial, [(FunctionCall(name="get_system_info", args={}), {"status": "ok"})]
    )

    assert result_text == "Sistem durumu iyi."
    assert len(fake_client.models.calls) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_gemini_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.gemini.backend'`

- [ ] **Step 3: Implement `agent/gemini/backend.py`**

```python
from google import genai
from google.genai import types

from agent.gemini.client import FunctionCall, InitialReply
from agent.tools.registry import ToolSpec


class GoogleGenAIBackend:
    """GeminiBackend implementation backed by the real google-genai SDK.
    `client` is injectable so tests never hit the network."""

    def __init__(self, api_key: str, model: str, tool_specs: list[ToolSpec], client=None):
        self._client = client if client is not None else genai.Client(api_key=api_key)
        self._model = model
        self._tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=spec.name,
                    description=spec.description,
                    parameters_json_schema=spec.parameters,
                )
                for spec in tool_specs
            ]
        )

    def generate_initial(self, user_text: str) -> InitialReply:
        user_content = types.Content(
            role="user", parts=[types.Part.from_text(text=user_text)]
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=[user_content],
            config=types.GenerateContentConfig(tools=[self._tool]),
        )

        function_calls = [
            FunctionCall(name=call.name, args=dict(call.function_call.args or {}))
            for call in (response.function_calls or [])
        ]
        raw = {
            "user_content": user_content,
            "model_content": response.candidates[0].content,
        }
        return InitialReply(function_calls=function_calls, text=response.text, raw=raw)

    def generate_followup(
        self, initial: InitialReply, tool_results: list[tuple[FunctionCall, dict]]
    ) -> str:
        response_parts = [
            types.Part.from_function_response(name=call.name, response=result)
            for call, result in tool_results
        ]
        tool_content = types.Content(role="tool", parts=response_parts)

        response = self._client.models.generate_content(
            model=self._model,
            contents=[initial.raw["user_content"], initial.raw["model_content"], tool_content],
            config=types.GenerateContentConfig(tools=[self._tool]),
        )
        return response.text or ""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_gemini_backend.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agent/gemini/backend.py agent/tests/test_gemini_backend.py
git commit -m "feat(agent): add google-genai backed GeminiBackend adapter"
```

---

## Task 7: Local Whisper speech-to-text

**Files:**
- Create: `agent/stt/__init__.py`
- Create: `agent/stt/whisper_stt.py`
- Create: `agent/tests/test_whisper_stt.py`

**Interfaces:**
- Produces: `agent.stt.whisper_stt.transcribe(audio_path: str, model_name: str = "base", language: str = "tr") -> str`. Used by Task 9 (`main.py` binds `model_name` via `functools.partial` before passing to `dispatch_voice`).

- [ ] **Step 1: Write the failing tests**

Create `agent/stt/__init__.py` (empty).

Create `agent/tests/test_whisper_stt.py`:

```python
from unittest.mock import MagicMock, patch

from agent.stt.whisper_stt import transcribe


@patch("agent.stt.whisper_stt.whisper")
def test_transcribe_strips_and_returns_text(mock_whisper):
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "  merhaba jarvis  "}
    mock_whisper.load_model.return_value = fake_model

    result = transcribe("some/audio.webm", model_name="base", language="tr")

    assert result == "merhaba jarvis"
    fake_model.transcribe.assert_called_once_with("some/audio.webm", language="tr")


@patch("agent.stt.whisper_stt.whisper")
def test_transcribe_loads_model_once_per_model_name(mock_whisper):
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "test"}
    mock_whisper.load_model.return_value = fake_model

    transcribe("a.webm", model_name="cache-test-model")
    transcribe("b.webm", model_name="cache-test-model")

    mock_whisper.load_model.assert_called_once_with("cache-test-model")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_whisper_stt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.stt.whisper_stt'`

- [ ] **Step 3: Implement `agent/stt/whisper_stt.py`**

```python
import whisper

_model_cache: dict[str, object] = {}


def transcribe(audio_path: str, model_name: str = "base", language: str = "tr") -> str:
    model = _get_model(model_name)
    result = model.transcribe(audio_path, language=language)
    return result["text"].strip()


def _get_model(model_name: str):
    if model_name not in _model_cache:
        _model_cache[model_name] = whisper.load_model(model_name)
    return _model_cache[model_name]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_whisper_stt.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add agent/stt/__init__.py agent/stt/whisper_stt.py agent/tests/test_whisper_stt.py
git commit -m "feat(agent): add local Whisper speech-to-text wrapper"
```

---

## Task 8: Message dispatch (text + voice)

Pure functions that turn an incoming WebSocket message into an outgoing
JSON-able response dict, decoupled from any actual socket. This is what
Task 9's thin async server calls.

**Files:**
- Create: `agent/dispatch.py`
- Create: `agent/tests/test_dispatch.py`

**Interfaces:**
- Consumes: `GeminiClient.send_command` (Task 5), `transcribe` signature (Task 7).
- Produces: `agent.dispatch.dispatch_text(text: str, gemini_client) -> dict` and `agent.dispatch.dispatch_voice(audio_base64: str, transcribe_fn: Callable[[str], str], gemini_client) -> dict`. Used by Task 9 (`ws_server.py`).

- [ ] **Step 1: Write the failing tests**

Create `agent/tests/test_dispatch.py`:

```python
import base64
import os

from agent.dispatch import dispatch_text, dispatch_voice


class FakeGeminiClient:
    def __init__(self, reply=None, error=None):
        self._reply = reply
        self._error = error
        self.received = []

    def send_command(self, text):
        self.received.append(text)
        if self._error:
            raise self._error
        return self._reply


def test_dispatch_text_returns_response_message_on_success():
    client = FakeGeminiClient(reply="Not Defteri açıldı.")

    result = dispatch_text("not defterini aç", client)

    assert result == {"type": "response", "text": "Not Defteri açıldı."}
    assert client.received == ["not defterini aç"]


def test_dispatch_text_returns_error_message_when_client_raises():
    client = FakeGeminiClient(error=RuntimeError("Gemini API zaman aşımına uğradı"))

    result = dispatch_text("bir şey sor", client)

    assert result == {"type": "error", "message": "Gemini API zaman aşımına uğradı"}


def test_dispatch_voice_transcribes_then_dispatches_as_text():
    audio_base64 = base64.b64encode(b"fake-audio-bytes").decode("ascii")
    seen_paths = []

    def fake_transcribe(path):
        seen_paths.append(path)
        assert os.path.exists(path)
        return "cpu kullanımı nedir"

    client = FakeGeminiClient(reply="CPU kullanımı %12.")

    result = dispatch_voice(audio_base64, fake_transcribe, client)

    assert result == {"type": "response", "text": "CPU kullanımı %12."}
    assert client.received == ["cpu kullanımı nedir"]
    # temp file must be cleaned up after transcription
    assert not os.path.exists(seen_paths[0])


def test_dispatch_voice_returns_error_on_invalid_base64():
    result = dispatch_voice("not-valid-base64!!", lambda path: "x", FakeGeminiClient())

    assert result["type"] == "error"


def test_dispatch_voice_returns_error_when_transcription_is_empty():
    audio_base64 = base64.b64encode(b"fake-audio-bytes").decode("ascii")

    result = dispatch_voice(audio_base64, lambda path: "   ", FakeGeminiClient())

    assert result == {"type": "error", "message": "Seni duyamadım, tekrar dener misin?"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_dispatch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.dispatch'`

- [ ] **Step 3: Implement `agent/dispatch.py`**

```python
import base64
import binascii
import os
import tempfile
from typing import Callable


def dispatch_text(text: str, gemini_client) -> dict:
    try:
        reply = gemini_client.send_command(text)
        return {"type": "response", "text": reply}
    except Exception as error:  # Gemini/tool failures must not crash the server
        return {"type": "error", "message": str(error)}


def dispatch_voice(audio_base64: str, transcribe_fn: Callable[[str], str], gemini_client) -> dict:
    try:
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError):
        return {"type": "error", "message": "Ses verisi çözümlenemedi."}

    fd, path = tempfile.mkstemp(suffix=".webm")
    try:
        with os.fdopen(fd, "wb") as audio_file:
            audio_file.write(audio_bytes)
        text = transcribe_fn(path)
    except Exception as error:
        return {"type": "error", "message": f"Ses tanınamadı: {error}"}
    finally:
        if os.path.exists(path):
            os.remove(path)

    if not text.strip():
        return {"type": "error", "message": "Seni duyamadım, tekrar dener misin?"}

    return dispatch_text(text, gemini_client)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `agent/venv/Scripts/python -m pytest agent/tests/test_dispatch.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add agent/dispatch.py agent/tests/test_dispatch.py
git commit -m "feat(agent): add pure text/voice command dispatch"
```

---

## Task 9: WebSocket server + entry point

Thin async wrapper around Task 8's pure dispatch functions, plus the
composition root (`main.py`) that wires config, tools, Gemini, and Whisper
together. This task is verified manually (real sockets), not with pytest.

**Files:**
- Create: `agent/ws_server.py`
- Create: `agent/main.py`

**Interfaces:**
- Consumes: `dispatch_text`, `dispatch_voice` (Task 8); `get_system_info` (Task 2); `load_config` (Task 1); `build_tool_registry` (Task 4); `GeminiClient` (Task 5); `GoogleGenAIBackend` (Task 6); `transcribe` (Task 7).
- Produces: `agent.ws_server.JarvisServer(gemini_client, transcribe_fn, host, port)` with `.serve_forever() -> Awaitable[None]`, and a runnable `agent/main.py` (`python -m agent.main`).

- [ ] **Step 1: Implement `agent/ws_server.py`**

```python
import asyncio
import json

import websockets

from agent.dispatch import dispatch_text, dispatch_voice
from agent.tools.system_info import get_system_info


class JarvisServer:
    def __init__(self, gemini_client, transcribe_fn, host: str, port: int):
        self._gemini_client = gemini_client
        self._transcribe_fn = transcribe_fn
        self._host = host
        self._port = port
        self._clients: set = set()

    async def _handler(self, websocket) -> None:
        self._clients.add(websocket)
        try:
            async for raw in websocket:
                await self._handle_message(websocket, raw)
        finally:
            self._clients.discard(websocket)

    async def _handle_message(self, websocket, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"type": "error", "message": "Geçersiz mesaj."}))
            return

        await websocket.send(json.dumps({"type": "status", "state": "thinking"}))

        msg_type = msg.get("type")
        if msg_type == "command":
            result = dispatch_text(msg.get("text", ""), self._gemini_client)
        elif msg_type == "voice_command":
            result = dispatch_voice(
                msg.get("audio_base64", ""), self._transcribe_fn, self._gemini_client
            )
        else:
            result = {"type": "error", "message": f"Bilinmeyen mesaj tipi: {msg_type}"}

        await websocket.send(json.dumps(result))

    async def _broadcast_system_info(self) -> None:
        while True:
            payload = json.dumps({"type": "system_info", "data": get_system_info()})
            for client in list(self._clients):
                try:
                    await client.send(payload)
                except websockets.exceptions.ConnectionClosed:
                    self._clients.discard(client)
            await asyncio.sleep(3)

    async def serve_forever(self) -> None:
        async with websockets.serve(self._handler, self._host, self._port):
            await self._broadcast_system_info()
```

- [ ] **Step 2: Implement `agent/main.py`**

```python
import asyncio
from functools import partial

from agent.config import load_config
from agent.gemini.backend import GoogleGenAIBackend
from agent.gemini.client import GeminiClient
from agent.stt.whisper_stt import transcribe
from agent.tools.registry import build_tool_registry
from agent.ws_server import JarvisServer


def build_server() -> JarvisServer:
    config = load_config()
    tools = build_tool_registry()
    backend = GoogleGenAIBackend(
        api_key=config.gemini_api_key,
        model=config.gemini_model,
        tool_specs=list(tools.values()),
    )
    gemini_client = GeminiClient(backend=backend, tools=tools)
    transcribe_fn = partial(transcribe, model_name=config.whisper_model)

    return JarvisServer(
        gemini_client=gemini_client,
        transcribe_fn=transcribe_fn,
        host=config.ws_host,
        port=config.ws_port,
    )


def main() -> None:
    server = build_server()
    asyncio.run(server.serve_forever())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create your real `.env` and manually verify the server starts and responds**

```bash
cp agent/.env.example agent/.env
# edit agent/.env and paste a real Gemini API key from aistudio.google.com
agent/venv/Scripts/python -m agent.main
```
Expected: process starts and stays running with no traceback (leave it running for the next steps below — Ctrl+C to stop when done).

In a second terminal, verify the server accepts a connection and responds to a text command:

```bash
agent/venv/Scripts/python -c "
import asyncio, json, websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:8765') as ws:
        await ws.send(json.dumps({'type': 'command', 'text': 'merhaba'}))
        print(await ws.recv())  # status: thinking
        print(await ws.recv())  # response or error

asyncio.run(main())
"
```
Expected: two JSON lines printed — a `{"type": "status", "state": "thinking"}` line, then either a `{"type": "response", ...}` line (if the API key is valid) or a `{"type": "error", ...}` line (if not) — either way, the server must not crash or hang.

- [ ] **Step 4: Commit**

```bash
git add agent/ws_server.py agent/main.py
git commit -m "feat(agent): add WebSocket server and entry point"
```

---

## Task 10: Electron shell scaffolding

**Files:**
- Create: `shell/package.json`
- Create: `shell/main.js`
- Create: `shell/preload.js`
- Create: `shell/renderer/index.html` (placeholder, replaced fully in Task 12)

**Interfaces:**
- Produces: a runnable `npm start` in `shell/` that opens a full-screen window, plus `window.jarvisShell.quit()` exposed to the renderer (used by Task 13's shutdown button) and a microphone permission handler needed by Task 14.

- [ ] **Step 1: Create `shell/package.json`**

```json
{
  "name": "jarvis-shell",
  "version": "0.1.0",
  "private": true,
  "main": "main.js",
  "scripts": {
    "start": "electron ."
  },
  "devDependencies": {
    "electron": "^32.0.0"
  }
}
```

- [ ] **Step 2: Create `shell/main.js`**

```javascript
const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');

function createWindow() {
  const win = new BrowserWindow({
    fullscreen: true,
    autoHideMenuBar: true,
    backgroundColor: '#05080a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  return win;
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(permission === 'media');
  });

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.on('jarvis:quit', () => {
  app.quit();
});
```

- [ ] **Step 3: Create `shell/preload.js`**

```javascript
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvisShell', {
  quit: () => ipcRenderer.send('jarvis:quit'),
});
```

- [ ] **Step 4: Create a placeholder `shell/renderer/index.html`**

```html
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <title>Jarvis</title>
</head>
<body style="background:#05080a;color:#d9fff0;font-family:monospace;">
  <p>Jarvis shell scaffolding OK.</p>
</body>
</html>
```

- [ ] **Step 5: Manually verify the shell launches**

```bash
cd shell
npm install
npm start
```
Expected: a full-screen black window opens showing "Jarvis shell scaffolding OK." with no DevTools console errors. Close it (Alt+F4) when confirmed.

```bash
cd ..
```

- [ ] **Step 6: Commit**

```bash
git add shell/package.json shell/main.js shell/preload.js shell/renderer/index.html
git commit -m "feat(shell): add Electron shell scaffolding"
```

---

## Task 11: WebSocket protocol helpers (`protocol.js`)

Pure message-building/parsing functions, written once and used both in the
browser-side renderer and in a plain-Node test via a small UMD wrapper.

**Files:**
- Create: `shell/renderer/protocol.js`
- Create: `shell/renderer/protocol.test.js`

**Interfaces:**
- Produces (as CommonJS export for tests, and as `window.jarvisProtocol` in the renderer): `buildTextCommand(text) -> string`, `buildVoiceCommand(audioBase64) -> string`, `parseServerMessage(raw) -> object`. Used by Task 13 (`renderer.js`).

- [ ] **Step 1: Write the failing tests**

Create `shell/renderer/protocol.test.js`:

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildTextCommand, buildVoiceCommand, parseServerMessage } = require('./protocol');

test('buildTextCommand encodes text as a command message', () => {
  const raw = buildTextCommand('not defterini aç');
  assert.deepEqual(JSON.parse(raw), { type: 'command', text: 'not defterini aç' });
});

test('buildVoiceCommand encodes base64 audio as a voice_command message', () => {
  const raw = buildVoiceCommand('AAAA');
  assert.deepEqual(JSON.parse(raw), { type: 'voice_command', audio_base64: 'AAAA' });
});

test('parseServerMessage returns the parsed object for a valid message', () => {
  const msg = parseServerMessage('{"type":"response","text":"merhaba"}');
  assert.deepEqual(msg, { type: 'response', text: 'merhaba' });
});

test('parseServerMessage throws when "type" is missing', () => {
  assert.throws(() => parseServerMessage('{"text":"merhaba"}'));
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test shell/renderer/protocol.test.js`
Expected: FAIL — `Cannot find module './protocol'`

- [ ] **Step 3: Implement `shell/renderer/protocol.js`**

```javascript
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

  function buildVoiceCommand(audioBase64) {
    return JSON.stringify({ type: 'voice_command', audio_base64: audioBase64 });
  }

  function parseServerMessage(raw) {
    const msg = JSON.parse(raw);
    if (typeof msg.type !== 'string') {
      throw new Error('Sunucu mesajında "type" alanı yok.');
    }
    return msg;
  }

  return { buildTextCommand, buildVoiceCommand, parseServerMessage };
});
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test shell/renderer/protocol.test.js`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add shell/renderer/protocol.js shell/renderer/protocol.test.js
git commit -m "feat(shell): add WebSocket protocol helpers with unit tests"
```

---

## Task 12: HUD layout (HTML + CSS)

Full-screen HUD structure with real element ids for Task 13 to wire up.
Visual polish beyond this baseline (fonts, color grading, motion) is a
follow-up pass — when you get here, consider invoking the `impeccable` or
`ui-ux-pro-max` design skill on `shell/renderer/styles.css` before moving
on, since the spec calls for an original look, not just a functional one.

**Files:**
- Modify: `shell/renderer/index.html` (replace the Task 10 placeholder)
- Create: `shell/renderer/styles.css`

**Interfaces:**
- Produces: DOM element ids consumed by Task 13 — `connection-status`, `clock-time`, `clock-date`, `bar-cpu`, `bar-ram`, `bar-disk`, `bar-battery`, `agent-visualizer`, `agent-state`, `conversation-log`, `command-form`, `command-input`, `btn-pause`, `btn-shutdown`.

- [ ] **Step 1: Replace `shell/renderer/index.html`**

```html
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <title>Jarvis</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <header class="hud-top">
    <span id="connection-status" class="status-pill">CONNECTING</span>
  </header>

  <main class="hud-grid">
    <section class="hud-panel hud-left">
      <div class="widget widget-clock">
        <div id="clock-time" class="clock-time">--:--</div>
        <div id="clock-date" class="clock-date">-- ------ ----</div>
      </div>
      <div class="widget widget-system">
        <h2>SYSTEM STATUS</h2>
        <div class="bar-row">
          <span>CPU</span>
          <div class="bar"><div id="bar-cpu" class="bar-fill"></div></div>
        </div>
        <div class="bar-row">
          <span>RAM</span>
          <div class="bar"><div id="bar-ram" class="bar-fill"></div></div>
        </div>
        <div class="bar-row">
          <span>DISK</span>
          <div class="bar"><div id="bar-disk" class="bar-fill"></div></div>
        </div>
        <div class="bar-row">
          <span>BATTERY</span>
          <div class="bar"><div id="bar-battery" class="bar-fill"></div></div>
        </div>
      </div>
    </section>

    <section class="hud-panel hud-center">
      <div id="agent-visualizer" class="visualizer" data-state="idle"></div>
      <div class="wordmark">J.A.R.V.I.S</div>
      <div id="agent-state" class="agent-state">idle</div>
    </section>

    <section class="hud-panel hud-right">
      <h2>CONVERSATION</h2>
      <div id="conversation-log" class="conversation-log"></div>
      <form id="command-form" class="command-form">
        <input id="command-input" type="text" autocomplete="off" placeholder="Bir komut yaz..." />
        <button type="submit">SEND</button>
      </form>
    </section>
  </main>

  <footer class="hud-controls">
    <button id="btn-pause" type="button" class="control-btn">PAUSE</button>
    <button id="btn-shutdown" type="button" class="control-btn control-danger">SHUTDOWN</button>
  </footer>

  <script src="protocol.js"></script>
  <script src="renderer.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `shell/renderer/styles.css`**

```css
:root {
  --bg: #05080a;
  --panel-bg: rgba(10, 20, 18, 0.6);
  --accent: #35f2c0;
  --accent-dim: #1c6b56;
  --text: #d9fff0;
  --danger: #ff5b5b;
  --warn: #f2b035;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: 'Consolas', 'Cascadia Code', monospace;
  overflow: hidden;
}

.hud-top { display: flex; justify-content: flex-end; padding: 12px 24px; }

.status-pill {
  border: 1px solid var(--accent-dim);
  color: var(--accent);
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  letter-spacing: 2px;
}

.hud-grid {
  display: grid;
  grid-template-columns: 260px 1fr 320px;
  gap: 24px;
  padding: 0 24px;
  height: calc(100% - 120px);
}

.hud-panel {
  border: 1px solid var(--accent-dim);
  background: var(--panel-bg);
  border-radius: 8px;
  padding: 16px;
  overflow: hidden;
}

.hud-left { display: flex; flex-direction: column; gap: 24px; }

.clock-time { font-size: 40px; color: var(--accent); }
.clock-date { font-size: 12px; opacity: 0.7; letter-spacing: 1px; }

.widget-system h2, .hud-right h2 {
  font-size: 12px;
  letter-spacing: 2px;
  color: var(--accent);
  margin: 0 0 12px;
}

.bar-row { display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 8px; }
.bar { flex: 1; height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; width: 0%; background: var(--accent); transition: width 0.4s ease; }

.hud-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.visualizer {
  width: 220px;
  height: 220px;
  border-radius: 50%;
  border: 1px solid var(--accent-dim);
  box-shadow: 0 0 40px rgba(53, 242, 192, 0.15) inset;
  transition: box-shadow 0.3s ease;
}
.visualizer[data-state="listening"] { box-shadow: 0 0 60px rgba(53, 242, 192, 0.4) inset; }
.visualizer[data-state="thinking"] { box-shadow: 0 0 60px rgba(242, 176, 53, 0.4) inset; }

.wordmark { font-size: 20px; letter-spacing: 6px; color: var(--accent); }
.agent-state { font-size: 11px; letter-spacing: 2px; opacity: 0.7; text-transform: uppercase; }

.hud-right { display: flex; flex-direction: column; }
.conversation-log { flex: 1; overflow-y: auto; font-size: 13px; display: flex; flex-direction: column; gap: 8px; }
.conversation-log .entry-user { color: var(--text); }
.conversation-log .entry-jarvis { color: var(--accent); }
.conversation-log .entry-error { color: var(--danger); }

.command-form { display: flex; gap: 8px; margin-top: 12px; }
.command-form input {
  flex: 1;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--accent-dim);
  color: var(--text);
  padding: 8px;
  border-radius: 4px;
  font-family: inherit;
}
.command-form button, .control-btn {
  background: transparent;
  border: 1px solid var(--accent-dim);
  color: var(--accent);
  padding: 8px 14px;
  border-radius: 4px;
  font-family: inherit;
  letter-spacing: 1px;
  cursor: pointer;
}
.control-btn.control-danger { border-color: var(--danger); color: var(--danger); }

.hud-controls { display: flex; justify-content: center; gap: 16px; padding: 16px; }
```

- [ ] **Step 3: Manually verify the layout renders**

```bash
cd shell
npm start
```
Expected: full-screen HUD with three bordered panels (clock+system status on the left, center visualizer circle + "J.A.R.V.I.S" wordmark, conversation log + input on the right) and two buttons at the bottom. No `renderer.js` yet, so the page is otherwise static — that's expected at this point. Close the window when confirmed.

```bash
cd ..
```

- [ ] **Step 4: Commit**

```bash
git add shell/renderer/index.html shell/renderer/styles.css
git commit -m "feat(shell): add HUD layout and baseline styling"
```

---

## Task 13: Renderer wiring (WebSocket client + HUD state)

**Files:**
- Create: `shell/renderer/renderer.js`

**Interfaces:**
- Consumes: `window.jarvisProtocol` (Task 11), `window.jarvisShell` (Task 10), the DOM ids from Task 12, the WebSocket message shapes produced by `agent/ws_server.py` (Task 9): `{"type":"status","state":"thinking"}`, `{"type":"response","text":...}`, `{"type":"error","message":...}`, `{"type":"system_info","data":{...}}`.

- [ ] **Step 1: Create `shell/renderer/renderer.js`**

```javascript
const socket = new WebSocket('ws://127.0.0.1:8765');

const statusEl = document.getElementById('connection-status');
const clockTimeEl = document.getElementById('clock-time');
const clockDateEl = document.getElementById('clock-date');
const bars = {
  cpu: document.getElementById('bar-cpu'),
  ram: document.getElementById('bar-ram'),
  disk: document.getElementById('bar-disk'),
  battery: document.getElementById('bar-battery'),
};
const visualizer = document.getElementById('agent-visualizer');
const agentStateEl = document.getElementById('agent-state');
const logEl = document.getElementById('conversation-log');
const form = document.getElementById('command-form');
const input = document.getElementById('command-input');
const pauseBtn = document.getElementById('btn-pause');
const shutdownBtn = document.getElementById('btn-shutdown');

let paused = false;

function setAgentState(state) {
  visualizer.dataset.state = state;
  agentStateEl.textContent = state;
}

function appendLog(kind, text) {
  const line = document.createElement('div');
  line.className = `entry-${kind}`;
  line.textContent = text;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

function updateClock() {
  const now = new Date();
  clockTimeEl.textContent = now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  clockDateEl.textContent = now
    .toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric', weekday: 'long' })
    .toUpperCase();
}
setInterval(updateClock, 1000);
updateClock();

function updateSystemInfo(data) {
  bars.cpu.style.width = `${data.cpu_percent ?? 0}%`;
  bars.ram.style.width = `${data.ram_percent ?? 0}%`;
  bars.disk.style.width = `${data.disk_percent ?? 0}%`;
  bars.battery.style.width = `${data.battery_percent ?? 0}%`;
}

socket.addEventListener('open', () => {
  statusEl.textContent = 'ONLINE';
});
socket.addEventListener('close', () => {
  statusEl.textContent = 'CONNECTING';
});
socket.addEventListener('error', () => {
  statusEl.textContent = 'CONNECTING';
});

socket.addEventListener('message', (event) => {
  const msg = window.jarvisProtocol.parseServerMessage(event.data);
  if (msg.type === 'status' && msg.state === 'thinking') {
    setAgentState('thinking');
  } else if (msg.type === 'response') {
    setAgentState('idle');
    appendLog('jarvis', msg.text);
  } else if (msg.type === 'error') {
    setAgentState('idle');
    appendLog('error', msg.message);
  } else if (msg.type === 'system_info') {
    updateSystemInfo(msg.data);
  }
});

form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (paused) return;
  const text = input.value.trim();
  if (!text) return;
  appendLog('user', text);
  socket.send(window.jarvisProtocol.buildTextCommand(text));
  input.value = '';
});

pauseBtn.addEventListener('click', () => {
  paused = !paused;
  pauseBtn.textContent = paused ? 'RESUME' : 'PAUSE';
});

shutdownBtn.addEventListener('click', () => {
  window.jarvisShell.quit();
});
```

- [ ] **Step 2: Manually verify text commands work end to end**

```bash
agent/venv/Scripts/python -m agent.main
```
(in a second terminal)
```bash
cd shell && npm start
```
In the HUD, type `not defterini aç` into the command box and press Enter (or click SEND).
Expected: status pill shows `ONLINE`; the visualizer briefly shows `thinking`; Notepad opens on the desktop; the conversation panel shows your message followed by Jarvis's reply; the left system-status bars are moving on their own (from the periodic broadcast).

- [ ] **Step 3: Commit**

```bash
git add shell/renderer/renderer.js
git commit -m "feat(shell): wire renderer to WebSocket server and HUD state"
```

---

## Task 14: Push-to-talk voice input

**Files:**
- Modify: `shell/renderer/renderer.js`

**Interfaces:**
- Consumes: `navigator.mediaDevices.getUserMedia`/`MediaRecorder` (browser APIs, available in the Electron renderer), `window.jarvisProtocol.buildVoiceCommand` (Task 11), the microphone permission handler from Task 10.
- Produces: voice commands sent as `{"type":"voice_command","audio_base64":...}`, matching what `agent/dispatch.py`'s `dispatch_voice` (Task 8) expects.

- [ ] **Step 1: Append push-to-talk recording logic to `shell/renderer/renderer.js`**

```javascript
const PUSH_TO_TALK_KEY = ' ';
let mediaRecorder = null;
let audioChunks = [];

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  audioChunks = [];
  mediaRecorder.ondataavailable = (event) => audioChunks.push(event.data);
  mediaRecorder.start();
  setAgentState('listening');
}

function stopRecording() {
  if (!mediaRecorder) return;
  mediaRecorder.addEventListener(
    'stop',
    async () => {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      const base64 = await blobToBase64(blob);
      socket.send(window.jarvisProtocol.buildVoiceCommand(base64));
      mediaRecorder.stream.getTracks().forEach((track) => track.stop());
      mediaRecorder = null;
    },
    { once: true }
  );
  mediaRecorder.stop();
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result.split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

window.addEventListener('keydown', (event) => {
  if (
    event.key === PUSH_TO_TALK_KEY &&
    document.activeElement !== input &&
    !mediaRecorder &&
    !paused
  ) {
    event.preventDefault();
    startRecording();
  }
});

window.addEventListener('keyup', (event) => {
  if (event.key === PUSH_TO_TALK_KEY && mediaRecorder) {
    event.preventDefault();
    stopRecording();
  }
});
```

- [ ] **Step 2: Manually verify voice commands work end to end**

Whisper shells out to `ffmpeg` to decode the recorded audio. On this
machine `ffmpeg` is not on the default `PATH` — it's installed at
`C:\Users\mhmmt\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe`. Before
starting `agent.main` for this step, either add that folder to `PATH` for
the session or run:
```bash
set PATH=%PATH%;C:\Users\mhmmt\AppData\Local\Microsoft\WinGet\Links
agent\venv\Scripts\python -m agent.main
```

With `agent.main` (using the PATH above) and the shell both running (as in Task 13), click anywhere outside the text input to make sure it isn't focused, then hold Space, say "sistem durumu nedir", and release Space.
Expected: the visualizer switches to `listening` while Space is held, then to `thinking` right after release, then back to `idle` with Jarvis's spoken command transcribed and answered in the conversation panel. Confirm typing still works normally when the input box is focused (Space inside it should type a space, not start recording).

- [ ] **Step 3: Commit**

```bash
git add shell/renderer/renderer.js
git commit -m "feat(shell): add push-to-talk voice capture"
```

---

## Task 15: End-to-end verification against the spec's test plan

No new files — this task runs through the manual scenarios the spec calls
for and fixes anything that doesn't hold up.

- [ ] **Step 1: Verify the two example commands from both input paths**

With both `agent.main` and the shell running, try each of these as typed text, then again as a held-Space voice command:
- "Not Defteri'ni aç" → Notepad opens; HUD shows a success reply.
- "CPU kullanımı nedir" → HUD shows a reply mentioning a CPU percentage.

- [ ] **Step 2: Verify Gemini/API error handling is visible, not a crash**

Stop `agent.main`, edit `agent/.env` to set `GEMINI_API_KEY=geçersiz-anahtar`, restart `agent.main`, and send a text command from the HUD.
Expected: the HUD shows a `type: error` message in red in the conversation log; the agent process keeps running (check its terminal — no traceback/exit). Restore the real API key in `agent/.env` afterward and confirm a normal command works again.

- [ ] **Step 3: Verify unrecognized speech is handled**

Hold Space and release without saying anything (or in a silent room).
Expected: HUD shows "Seni duyamadım, tekrar dener misin?" instead of hanging or crashing.

- [ ] **Step 4: Verify SHUTDOWN closes the app cleanly**

Click the SHUTDOWN button in the HUD.
Expected: the Electron window and process both exit; `agent.main` keeps running untouched in its own terminal (it's a separate process).

- [ ] **Step 5: Final commit**

If any fixes were needed in the previous steps, stage and commit them individually with descriptive messages before considering v1 done. If no fixes were needed, there is nothing to commit for this task.
