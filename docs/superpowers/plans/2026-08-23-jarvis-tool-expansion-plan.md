# Jarvis Yeni Tool'lar (Persona, Tarayıcı, Terminal, Medya, Ekran, Bellek) Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jarvis'e persona (kimlik), tarayıcı/arama, terminal komutu, medya arama, ekran okuma ve bellek (hatırlama) yeteneklerini eklemek — mevcut `agent/tools/registry.py`'deki `ToolSpec` deseniyle.

**Architecture:** Persona bir tool değil, `LiveSession._build_config()`'e eklenen bir `system_instruction` string'i. Diğer 5 yetenek (`open_browser`, `play_media`, `run_command`, `read_screen`, `remember`/`recall`) mevcut `ToolSpec(name, description, parameters, handler)` desenine eklenen yeni tool'lar — her biri kendi dosyasında, injectable bağımlılıklarla (gerçek tarayıcı/subprocess/ekran/dosya I/O testte sahtesiyle değiştirilir), `{"status": "ok"/"error"/"blocked", ...}` dönen handler'lar. `build_tool_registry()` artık bir `genai.Client` parametresi alıyor (sadece `read_screen` kullanıyor, ekran görüntüsünü ayrı bir senkron `generate_content` çağrısıyla tarif ettirmek için).

**Tech Stack:** Python 3.13, mevcut `google-genai` client (Live oturumundan bağımsız `client.models.generate_content` çağrısı), `Pillow` (yeni bağımlılık, `PIL.ImageGrab.grab()`), Python standart kütüphane (`webbrowser`, `subprocess`, `re`, `json`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-23-jarvis-tool-expansion-design.md`.
- `read_screen` için model adı: `gemini-3.6-flash` — bu tasarım sürecinde gerçek `GEMINI_API_KEY` ile hem düz metin hem görüntü+metin girdisiyle canlı doğrulandı (`gemini-2.5-flash` artık kullanılamıyor, 404 dönüyor).
- Hiçbir tool handler'ı ham exception fırlatmaz — `_handle_tool_call` (agent/gemini/live_session.py) handler'ları try/except ile sarmıyor, o yüzden her handler kendi hatalarını yakalayıp `{"status": "error", ...}` döner (mevcut `open_app.py` deseni).
- Yeni tool parametre şemalarında (Gemini'ye giden JSON schema) sadece modelin doldurması gereken alanlar olur; `opener`/`runner`/`grabber`/`client`/`path` gibi test/wiring amaçlı parametreler şemaya girmez (mevcut `open_app`'ın `launcher` parametresi gibi).
- Tüm testler kök dizinden çalıştırılır: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_X.py -v`.
- Kişisel veri dosyası `agent/memory.json` asla git'e girmez.

---

### Task 1: Persona — `system_instruction`

**Files:**
- Create: `agent/persona.py`
- Modify: `agent/gemini/live_session.py`
- Modify: `agent/tests/test_live_session.py`

**Interfaces:**
- Produces: `agent.persona.JARVIS_PERSONA: str`. `LiveSession._build_config()`'in döndürdüğü `types.LiveConnectConfig`'e `system_instruction=JARVIS_PERSONA` eklenir.

- [ ] **Step 1: Failing testi yaz**

`agent/tests/test_live_session.py`'nin sonuna ekle:

```python
def test_run_connects_with_jarvis_persona_as_system_instruction():
    from agent.persona import JARVIS_PERSONA

    session = FakeSession(messages=[])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(client=client, model="m", voice="Kore", tools={}, on_event=on_event)
    asyncio.run(live.run())

    config = client.aio.live.connect_calls[0]["config"]
    assert config.system_instruction == JARVIS_PERSONA
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agent.persona'`)

- [ ] **Step 3: `agent/persona.py`'yi oluştur**

Tam içerik:

```python
JARVIS_PERSONA = """Sen Jarvis'sin — kullanıcının kişisel masaüstü asistanısın. Iron Man'deki
Jarvis gibi resmi, saygılı ama kısa ve öz konuşursun; gereksiz laf kalabalığı yapmazsın.
Kullanıcı hangi dilde konuşursa (Türkçe/İngilizce) sen de o dilde cevap verirsin.
Elindeki araçları (uygulama açma, tarayıcı, terminal, medya, ekran okuma, bellek, sistem
bilgisi) gerektiğinde doğrudan kullanırsın, önce izin istemene gerek yok."""
```

- [ ] **Step 4: `agent/gemini/live_session.py`'yi güncelle**

Dosyanın başına import ekle:

```python
from agent.persona import JARVIS_PERSONA
```

`_build_config`'in döndürdüğü `types.LiveConnectConfig(...)` çağrısına `system_instruction=JARVIS_PERSONA,` satırını ekle (örn. `response_modalities=["AUDIO"],` satırının hemen altına):

```python
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=JARVIS_PERSONA,
            speech_config=types.SpeechConfig(
```

- [ ] **Step 5: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_live_session.py -v`
Expected: PASS (14 passed)

- [ ] **Step 6: Commit**

```bash
git add agent/persona.py agent/gemini/live_session.py agent/tests/test_live_session.py
git commit -m "feat(agent): Jarvis persona'sını Live oturumuna system_instruction olarak ekle"
```

---

### Task 2: `browser.py` — arama/URL açma + medya arama

**Files:**
- Create: `agent/tools/browser.py`
- Create: `agent/tests/test_browser.py`

**Interfaces:**
- Produces: `resolve_target_url(query_or_url: str) -> str`, `open_browser(query_or_url: str, opener=None) -> dict`, `play_media(query: str, platform: str = "youtube", opener=None) -> dict`

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_browser.py` tam içerik:

```python
import urllib.parse

from agent.tools.browser import open_browser, play_media, resolve_target_url


def test_resolve_target_url_passes_through_full_url():
    assert resolve_target_url("https://example.com") == "https://example.com"


def test_resolve_target_url_adds_scheme_to_bare_domain():
    assert resolve_target_url("python.org") == "https://python.org"


def test_resolve_target_url_adds_scheme_to_domain_with_path():
    assert resolve_target_url("github.com/anthropics") == "https://github.com/anthropics"


def test_resolve_target_url_treats_phrase_as_search_query():
    query = "İstanbul hava durumu"
    expected = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    assert resolve_target_url(query) == expected


def test_resolve_target_url_treats_single_word_without_dot_as_search():
    query = "python nedir"
    expected = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    assert resolve_target_url(query) == expected


def test_resolve_target_url_treats_non_http_scheme_as_search_query():
    query = "ftp://example.com"
    expected = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    assert resolve_target_url(query) == expected


def test_open_browser_calls_opener_with_resolved_url_and_returns_ok():
    calls = []
    def opener(url):
        calls.append(url)
        return True

    result = open_browser("python.org", opener=opener)

    assert calls == ["https://python.org"]
    assert result["status"] == "ok"


def test_open_browser_returns_error_when_opener_fails():
    result = open_browser("python.org", opener=lambda url: False)

    assert result["status"] == "error"


def test_play_media_defaults_to_youtube_search():
    calls = []
    def opener(url):
        calls.append(url)
        return True

    result = play_media("bohemian rhapsody", opener=opener)

    assert calls == ["https://www.youtube.com/results?search_query=bohemian%20rhapsody"]
    assert result["status"] == "ok"


def test_play_media_uses_spotify_when_requested():
    calls = []
    def opener(url):
        calls.append(url)
        return True

    play_media("bohemian rhapsody", platform="spotify", opener=opener)

    assert calls == ["https://open.spotify.com/search/bohemian%20rhapsody"]


def test_play_media_returns_error_when_opener_fails():
    result = play_media("test", opener=lambda url: False)

    assert result["status"] == "error"
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_browser.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agent.tools.browser'`)

- [ ] **Step 3: `agent/tools/browser.py`'yi oluştur**

Tam içerik:

```python
import re
import urllib.parse
import webbrowser

_DOMAIN_LIKE = re.compile(r"^[\w-]+(\.[\w-]+)+(/\S*)?$")


def resolve_target_url(query_or_url: str) -> str:
    """http(s):// ile başlayan ya da 'domain.tld' gibi görünen (boşluksuz)
    girdiyi olduğu gibi (şema eksikse https:// eklenerek) döner; aksi halde
    Google arama URL'i olarak döner."""
    text = query_or_url.strip()
    if text.startswith(("http://", "https://")):
        return text
    if " " not in text and _DOMAIN_LIKE.match(text):
        return f"https://{text}"
    return f"https://www.google.com/search?q={urllib.parse.quote(text)}"


def open_browser(query_or_url: str, opener=None) -> dict:
    if opener is None:
        opener = webbrowser.open
    url = resolve_target_url(query_or_url)
    if opener(url):
        return {"status": "ok", "message": f"Tarayıcıda açıldı: {url}"}
    return {"status": "error", "message": f"Tarayıcı açılamadı: {url}"}


def play_media(query: str, platform: str = "youtube", opener=None) -> dict:
    if opener is None:
        opener = webbrowser.open
    if platform == "spotify":
        url = f"https://open.spotify.com/search/{urllib.parse.quote(query)}"
    else:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    if opener(url):
        return {"status": "ok", "message": f"Tarayıcıda açıldı: {url}"}
    return {"status": "error", "message": f"Tarayıcı açılamadı: {url}"}
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_browser.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/tools/browser.py agent/tests/test_browser.py
git commit -m "feat(agent): open_browser/play_media - arama/URL açma + medya arama tool'ları"
```

---

### Task 3: `terminal.py` — güvenli terminal komutu

**Files:**
- Create: `agent/tools/terminal.py`
- Create: `agent/tests/test_terminal.py`

**Interfaces:**
- Produces: `is_dangerous(command: str) -> bool`, `run_command(command: str, cwd: str | None = None, runner=None) -> dict`

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_terminal.py` tam içerik:

```python
import subprocess
from types import SimpleNamespace

from agent.tools.terminal import is_dangerous, run_command


def test_is_dangerous_detects_format_command():
    assert is_dangerous("format C:") is True


def test_is_dangerous_detects_diskpart():
    assert is_dangerous("diskpart") is True


def test_is_dangerous_detects_shutdown():
    assert is_dangerous("shutdown /s /t 0") is True


def test_is_dangerous_detects_rm_rf_root():
    assert is_dangerous("rm -rf /") is True


def test_is_dangerous_detects_root_delete_variants():
    assert is_dangerous("del /s /q C:\\") is True
    assert is_dangerous("rd /s /q D:\\") is True
    assert is_dangerous("Remove-Item -Recurse -Force C:\\") is True


def test_is_dangerous_allows_safe_commands():
    assert is_dangerous("git status") is False
    assert is_dangerous("npm test") is False
    assert is_dangerous("dir") is False
    assert is_dangerous("python -m pytest") is False


def test_run_command_blocks_dangerous_without_calling_runner():
    calls = []
    def runner():
        calls.append(1)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    result = run_command("format C:", runner=runner)

    assert result["status"] == "blocked"
    assert calls == []


def test_run_command_returns_ok_on_success():
    def runner():
        return SimpleNamespace(stdout="merhaba\n", stderr="", returncode=0)

    result = run_command("echo merhaba", runner=runner)

    assert result["status"] == "ok"
    assert "merhaba" in result["output"]
    assert result["returncode"] == 0


def test_run_command_returns_error_on_nonzero_exit():
    def runner():
        return SimpleNamespace(stdout="", stderr="komut bulunamadı", returncode=1)

    result = run_command("not-a-real-command", runner=runner)

    assert result["status"] == "error"
    assert result["returncode"] == 1


def test_run_command_truncates_long_output():
    def runner():
        return SimpleNamespace(stdout="x" * 5000, stderr="", returncode=0)

    result = run_command("dir", runner=runner)

    assert len(result["output"]) == 4000


def test_run_command_handles_timeout():
    def runner():
        raise subprocess.TimeoutExpired(cmd="sleep 100", timeout=30)

    result = run_command("sleep 100", runner=runner)

    assert result["status"] == "error"
    assert "zaman aşımı" in result["message"]


def test_run_command_handles_invalid_cwd():
    def runner():
        raise FileNotFoundError("klasör yok")

    result = run_command("dir", cwd="C:\\olmayan\\klasor", runner=runner)

    assert result["status"] == "error"
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_terminal.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agent.tools.terminal'`)

- [ ] **Step 3: `agent/tools/terminal.py`'yi oluştur**

Tam içerik:

```python
import re
import subprocess

_DANGEROUS_PATTERNS = [
    r"\bformat\s+[a-z]:",
    r"\bdiskpart\b",
    r"\bshutdown\b",
    r"\bstop-computer\b",
    r"\brestart-computer\b",
    r"\brm\s+-rf\s+/",
    r"\b(del|erase)\s+/s\s+/q\s+[a-z]:\\?\s*$",
    r"\brd\s+/s\s+/q\s+[a-z]:\\?\s*$",
    r"remove-item\s+.*-recurse.*-force.*[a-z]:\\?\s*$",
    r"\bvssadmin\s+delete\b",
    r"\breg\s+delete\b",
    r"\bnet\s+user\b.*\bdelete\b",
]


def is_dangerous(command: str) -> bool:
    lowered = command.lower()
    return any(re.search(pattern, lowered) for pattern in _DANGEROUS_PATTERNS)


def run_command(command: str, cwd: str | None = None, runner=None) -> dict:
    """PowerShell üzerinden komut çalıştırır. `runner` testte enjekte
    edilir; gerçekte parametresiz bir closure olarak subprocess.run'ı
    komut/cwd'yi kapsayarak çağırır."""
    if is_dangerous(command):
        return {"status": "blocked", "message": "Bu komut güvenlik nedeniyle engellendi."}

    if runner is None:
        def runner():
            return subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )

    try:
        result = runner()
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Komut zaman aşımına uğradı (30sn)."}
    except OSError as error:
        return {"status": "error", "message": f"Komut çalıştırılamadı: {error}"}

    output = (result.stdout + result.stderr)[:4000]
    status = "ok" if result.returncode == 0 else "error"
    return {"status": status, "output": output, "returncode": result.returncode}
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_terminal.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/tools/terminal.py agent/tests/test_terminal.py
git commit -m "feat(agent): run_command - blocklist'li terminal komutu tool'u"
```

---

### Task 4: `screen.py` — ekran okuma

**Files:**
- Modify: `agent/requirements.txt`
- Create: `agent/tools/screen.py`
- Create: `agent/tests/test_screen.py`

**Interfaces:**
- Produces: `read_screen(soru: str = "Ekranda ne var, kısaca özetle.", grabber=None, client=None) -> dict`

- [ ] **Step 1: `requirements.txt`'e Pillow ekle ve venv'e kur**

`agent/requirements.txt`'e ekle (dosyanın sonuna):

```
Pillow>=10.0.0
```

Run: `./agent/venv/Scripts/python.exe -m pip install Pillow`

- [ ] **Step 2: Failing testleri yaz**

`agent/tests/test_screen.py` tam içerik:

```python
from types import SimpleNamespace

from agent.tools.screen import read_screen


class FakeImage:
    def save(self, buf, format):
        buf.write(b"fake-png-bytes")


def test_read_screen_calls_generate_content_with_image_and_question():
    calls = []

    class FakeModels:
        def generate_content(self, *, model, contents):
            calls.append({"model": model, "contents": contents})
            return SimpleNamespace(text="Kırmızı bir daire görüyorum.")

    fake_client = SimpleNamespace(models=FakeModels())

    result = read_screen(soru="Ne görüyorsun?", grabber=lambda: FakeImage(), client=fake_client)

    assert result == {"status": "ok", "description": "Kırmızı bir daire görüyorum."}
    assert calls[0]["model"] == "gemini-3.6-flash"
    assert calls[0]["contents"][1] == "Ne görüyorsun?"


def test_read_screen_uses_default_question_when_not_given():
    class FakeModels:
        def generate_content(self, *, model, contents):
            return SimpleNamespace(text="özet")

    fake_client = SimpleNamespace(models=FakeModels())

    result = read_screen(grabber=lambda: FakeImage(), client=fake_client)

    assert result["status"] == "ok"
    assert result["description"] == "özet"


def test_read_screen_returns_error_when_capture_fails():
    def failing_grabber():
        raise OSError("ekran erişilemedi")

    result = read_screen(grabber=failing_grabber, client=SimpleNamespace())

    assert result["status"] == "error"


def test_read_screen_returns_error_when_generate_content_fails():
    class FailingModels:
        def generate_content(self, *, model, contents):
            raise RuntimeError("API hatası")

    fake_client = SimpleNamespace(models=FailingModels())

    result = read_screen(grabber=lambda: FakeImage(), client=fake_client)

    assert result["status"] == "error"
```

- [ ] **Step 3: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_screen.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agent.tools.screen'`)

- [ ] **Step 4: `agent/tools/screen.py`'yi oluştur**

Tam içerik:

```python
import io

from google.genai import types

_DEFAULT_QUESTION = "Ekranda ne var, kısaca özetle."
_MODEL = "gemini-3.6-flash"


def read_screen(soru: str = _DEFAULT_QUESTION, grabber=None, client=None) -> dict:
    """Ekran görüntüsü alıp ayrı, senkron bir generate_content çağrısıyla
    (Live oturumundan bağımsız) Gemini'ye tarif ettirir. `grabber` testte
    enjekte edilir; gerçekte PIL.ImageGrab.grab kullanılır."""
    if grabber is None:
        from PIL import ImageGrab
        grabber = ImageGrab.grab

    try:
        image = grabber()
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        response = client.models.generate_content(
            model=_MODEL,
            contents=[types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"), soru],
        )
        return {"status": "ok", "description": response.text}
    except Exception as error:
        return {"status": "error", "message": f"Ekran okunamadı: {error}"}
```

- [ ] **Step 5: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_screen.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add agent/requirements.txt agent/tools/screen.py agent/tests/test_screen.py
git commit -m "feat(agent): read_screen - ekran görüntüsünü Gemini'ye tarif ettirme tool'u"
```

---

### Task 5: `memory.py` — bellek (`remember`/`recall`)

**Files:**
- Create: `agent/memory.py`
- Create: `agent/tests/test_memory.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `remember(bilgi: str, path: str = _DEFAULT_PATH) -> dict`, `recall(path: str = _DEFAULT_PATH) -> dict`

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_memory.py` tam içerik:

```python
import json

from agent.memory import recall, remember


def test_recall_returns_empty_list_when_file_does_not_exist(tmp_path):
    path = str(tmp_path / "memory.json")

    result = recall(path=path)

    assert result == {"status": "ok", "items": [], "message": "Henüz hatırladığım bir şey yok."}


def test_remember_creates_file_and_appends_entry(tmp_path):
    path = str(tmp_path / "memory.json")

    result = remember("kullanıcının kedisinin adı Pamuk", path=path)

    assert result == {"status": "ok", "message": "Hatırlayacağım."}
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    assert entries[0]["text"] == "kullanıcının kedisinin adı Pamuk"
    assert "timestamp" in entries[0]


def test_remember_appends_to_existing_entries(tmp_path):
    path = str(tmp_path / "memory.json")
    remember("ilk bilgi", path=path)
    remember("ikinci bilgi", path=path)

    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    assert [e["text"] for e in entries] == ["ilk bilgi", "ikinci bilgi"]


def test_recall_returns_all_remembered_texts(tmp_path):
    path = str(tmp_path / "memory.json")
    remember("ilk bilgi", path=path)
    remember("ikinci bilgi", path=path)

    result = recall(path=path)

    assert result == {"status": "ok", "items": ["ilk bilgi", "ikinci bilgi"]}
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_memory.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agent.memory'`)

- [ ] **Step 3: `agent/memory.py`'yi oluştur**

Tam içerik:

```python
import json
import os
from datetime import datetime

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "memory.json")


def _load(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, entries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def remember(bilgi: str, path: str = _DEFAULT_PATH) -> dict:
    entries = _load(path)
    entries.append({"text": bilgi, "timestamp": datetime.now().isoformat()})
    _save(path, entries)
    return {"status": "ok", "message": "Hatırlayacağım."}


def recall(path: str = _DEFAULT_PATH) -> dict:
    entries = _load(path)
    if not entries:
        return {"status": "ok", "items": [], "message": "Henüz hatırladığım bir şey yok."}
    return {"status": "ok", "items": [entry["text"] for entry in entries]}
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_memory.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: `.gitignore`'a ekle**

`.gitignore`'daki `# Python` bölümüne (`agent/.env` satırının yanına) ekle:

```
agent/memory.json
```

- [ ] **Step 6: Commit**

```bash
git add agent/memory.py agent/tests/test_memory.py .gitignore
git commit -m "feat(agent): remember/recall - düz liste JSON bellek tool'u"
```

---

### Task 6: `registry.py` + `main.py` — tüm yeni tool'ları bağla

**Files:**
- Modify: `agent/tools/registry.py`
- Modify: `agent/tests/test_registry.py`
- Modify: `agent/main.py`

**Interfaces:**
- Consumes: `open_browser`, `play_media` (Task 2), `run_command` (Task 3), `read_screen` (Task 4), `remember`, `recall` (Task 5)
- Produces: `build_tool_registry(client) -> dict[str, ToolSpec]` (imza değişti — artık bir `client` parametresi alıyor), 8 tool içerir: `open_app`, `get_system_info`, `open_browser`, `run_command`, `play_media`, `read_screen`, `remember`, `recall`.

- [ ] **Step 1: `test_registry.py`'yi güncelle (yeni imza + yeni tool'lar)**

`agent/tests/test_registry.py` tam içerik:

```python
from types import SimpleNamespace

from agent.tools.registry import build_tool_registry


def make_fake_client():
    return SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text="")))


def test_registry_contains_all_tools():
    registry = build_tool_registry(make_fake_client())

    assert set(registry.keys()) == {
        "open_app",
        "get_system_info",
        "open_browser",
        "run_command",
        "play_media",
        "read_screen",
        "remember",
        "recall",
    }


def test_open_app_tool_spec_declares_required_isim_parameter():
    spec = build_tool_registry(make_fake_client())["open_app"]

    assert spec.parameters["required"] == ["isim"]
    assert "isim" in spec.parameters["properties"]


def test_get_system_info_tool_spec_takes_no_parameters():
    spec = build_tool_registry(make_fake_client())["get_system_info"]

    assert spec.parameters["properties"] == {}


def test_tool_handlers_are_callable_and_return_dicts():
    registry = build_tool_registry(make_fake_client())

    result = registry["get_system_info"].handler()

    assert isinstance(result, dict)


def test_open_browser_tool_spec_declares_required_query_or_url_parameter():
    spec = build_tool_registry(make_fake_client())["open_browser"]

    assert spec.parameters["required"] == ["query_or_url"]


def test_run_command_tool_spec_declares_required_command_and_optional_cwd():
    spec = build_tool_registry(make_fake_client())["run_command"]

    assert spec.parameters["required"] == ["command"]
    assert "cwd" in spec.parameters["properties"]


def test_play_media_tool_spec_declares_required_query_parameter():
    spec = build_tool_registry(make_fake_client())["play_media"]

    assert spec.parameters["required"] == ["query"]


def test_read_screen_tool_spec_has_no_required_parameters():
    spec = build_tool_registry(make_fake_client())["read_screen"]

    assert spec.parameters["required"] == []


def test_remember_tool_spec_declares_required_bilgi_parameter():
    spec = build_tool_registry(make_fake_client())["remember"]

    assert spec.parameters["required"] == ["bilgi"]


def test_recall_tool_spec_takes_no_parameters():
    spec = build_tool_registry(make_fake_client())["recall"]

    assert spec.parameters["properties"] == {}


def test_read_screen_handler_is_bound_to_the_given_client():
    fake_client = make_fake_client()
    registry = build_tool_registry(fake_client)

    result = registry["read_screen"].handler(grabber=lambda: SimpleNamespace(save=lambda buf, format: None))

    assert result["status"] == "ok"
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_registry.py -v`
Expected: FAIL (`TypeError: build_tool_registry() takes 0 positional arguments but 1 was given`)

- [ ] **Step 3: `agent/tools/registry.py`'yi tamamen yeniden yaz**

Tam içerik:

```python
from dataclasses import dataclass
from functools import partial
from typing import Callable

from agent.memory import recall, remember
from agent.tools.browser import open_browser, play_media
from agent.tools.open_app import open_app
from agent.tools.screen import read_screen
from agent.tools.system_info import get_system_info
from agent.tools.terminal import run_command


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., dict]


def build_tool_registry(client) -> dict[str, ToolSpec]:
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
        "open_browser": ToolSpec(
            name="open_browser",
            description="Tarayıcıda bir arama yapar veya doğrudan bir URL açar. Kullanıcı bir şey aramak isterse veya bir siteyi/URL'i açmak isterse bu tool'u kullan.",
            parameters={
                "type": "object",
                "properties": {
                    "query_or_url": {
                        "type": "string",
                        "description": "Aranacak kelime/cümle veya açılacak URL",
                    }
                },
                "required": ["query_or_url"],
            },
            handler=open_browser,
        ),
        "run_command": ToolSpec(
            name="run_command",
            description="Kullanıcının bilgisayarında bir PowerShell komutu çalıştırır ve çıktısını döner. Tehlikeli komutlar (format, shutdown, disk silme vb.) otomatik engellenir.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Çalıştırılacak PowerShell komutu",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Komutun çalışacağı klasör (opsiyonel, verilmezse mevcut klasör kullanılır)",
                    },
                },
                "required": ["command"],
            },
            handler=run_command,
        ),
        "play_media": ToolSpec(
            name="play_media",
            description="YouTube veya Spotify'da bir şarkı/video arar ve arama sonuç sayfasını tarayıcıda açar (otomatik çalmaz, kullanıcı ilk sonuca tıklamalı).",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Aranacak şarkı/video/sanatçı",
                    },
                    "platform": {
                        "type": "string",
                        "description": "youtube veya spotify",
                        "enum": ["youtube", "spotify"],
                    },
                },
                "required": ["query"],
            },
            handler=play_media,
        ),
        "read_screen": ToolSpec(
            name="read_screen",
            description="Kullanıcının ekranının bir görüntüsünü alır ve Gemini'ye tarif ettirir. Kullanıcı ekranda ne olduğunu sorarsa veya ekrandaki bir şeyi analiz etmeni isterse kullan.",
            parameters={
                "type": "object",
                "properties": {
                    "soru": {
                        "type": "string",
                        "description": "Ekran hakkında sorulacak soru (opsiyonel)",
                    }
                },
                "required": [],
            },
            handler=partial(read_screen, client=client),
        ),
        "remember": ToolSpec(
            name="remember",
            description="Kullanıcının söylediği bir bilgiyi kalıcı olarak hatırlar. Kullanıcı 'bunu hatırla' derse kullan.",
            parameters={
                "type": "object",
                "properties": {
                    "bilgi": {
                        "type": "string",
                        "description": "Hatırlanacak bilgi",
                    }
                },
                "required": ["bilgi"],
            },
            handler=remember,
        ),
        "recall": ToolSpec(
            name="recall",
            description="Daha önce hatırlanan tüm bilgileri döner. Kullanıcı 'ne hatırlıyorsun' derse veya geçmişte söylediği bir şeye referans verirse kullan.",
            parameters={"type": "object", "properties": {}},
            handler=recall,
        ),
    }
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_registry.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: `agent/main.py`'yi güncelle**

`build_components()` içinde `client` oluşturmayı `tools = build_tool_registry()` çağrısından önceye taşı ve çağrıya `client`'ı geçir:

```python
def build_components() -> tuple[JarvisServer, LiveSession, WakeWordListener]:
    config = load_config()
    client = genai.Client(api_key=config.gemini_api_key)
    tools = build_tool_registry(client)

    server = JarvisServer(host=config.ws_host, port=config.ws_port)
```

(Bu satırın altındaki `live_session = LiveSession(client=client, ...)` bloğu aynen kalır — `client` zaten yukarı taşındığı için değişmiyor.)

- [ ] **Step 6: `main.py`'nin hâlâ sorunsuz import edildiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -c "from agent.main import build_components; print('ok')"`
Expected: `ok` yazdırır, hata yok.

- [ ] **Step 7: Commit**

```bash
git add agent/tools/registry.py agent/tests/test_registry.py agent/main.py
git commit -m "feat(agent): registry'ye 6 yeni tool'u bağla, build_tool_registry client parametresi alsın"
```

---

### Task 7: Tüm otomatik test paketini uçtan uca çalıştır

**Files:** yok (sadece doğrulama)

- [ ] **Step 1: Python testlerinin tamamını çalıştır**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/ -v`
Expected: Tüm testler PASS (Task 1-6'daki yeni testler + `test_open_app.py`/`test_system_info.py`/`test_wake_word.py`/`test_live_session.py`/`test_ws_server.py`/`test_main.py`)

- [ ] **Step 2: JS testlerinin tamamını çalıştır (bu görevde değişmedi ama regresyon kontrolü)**

Run: `node --test shell/renderer/protocol.test.js`
Expected: Tüm testler PASS

- [ ] **Step 3: Herhangi bir test kırmızıysa düzelt, hepsi yeşil olana kadar tekrar çalıştır**

- [ ] **Step 4: Commit (sadece düzeltme gerektiyse)**

```bash
git add -A
git commit -m "fix: tam test paketi geçene kadar kalan uyumsuzlukları düzelt"
```

---

### Task 8: Uçtan uca manuel doğrulama

**Files:** yok

- [ ] **Step 1: Agent'ı başlat, hatasız çalıştığını doğrula**

Run: `./agent/venv/Scripts/python.exe -m agent.main`
Expected: Hata fırlatmadan çalışmaya devam ediyor.

- [ ] **Step 2: Shell'i başlat, persona'yı sesle doğrula**

Run: `cd shell && npm start`
Push-to-talk ile bir şey sor ("Nasılsın?"). Expected: Jarvis kısa, resmi/saygılı bir tonda cevap veriyor (persona hissediliyor), Türkçe konuşursan Türkçe, İngilizce konuşursan İngilizce cevap veriyor.

- [ ] **Step 3: `open_browser`'ı sesle test et**

"Jarvis, python.org'u aç" ve "Jarvis, bugün hava nasıl diye ara" gibi komutlar ver.
Expected: İlkinde doğrudan python.org açılıyor, ikincisinde Google arama sonucu açılıyor.

- [ ] **Step 4: `run_command`'ı sesle test et**

"Jarvis, git status'u çalıştır" gibi bir komut ver (bir git reposundayken).
Expected: Komut çıktısı Jarvis tarafından özetlenip sesli okunuyor. Ardından "Jarvis, diski formatla" gibi tehlikeli bir komut dene.
Expected: Engellendiğini söylüyor, hiçbir şey çalıştırmıyor.

- [ ] **Step 5: `play_media`'yı sesle test et**

"Jarvis, YouTube'da lofi müzik ara" de.
Expected: YouTube arama sonuç sayfası tarayıcıda açılıyor.

- [ ] **Step 6: `read_screen`'i sesle test et**

Ekranda bir şey aç (örn. bir kod editörü), "Jarvis, ekranda ne var?" de.
Expected: Jarvis ekranın gerçek içeriğini doğru tarif ediyor.

- [ ] **Step 7: `remember`/`recall`'ı sesle test et**

"Jarvis, şunu hatırla: kedimin adı Pamuk" de, ardından (aynı veya yeni bir oturumda) "Jarvis, ne hatırlıyorsun?" de.
Expected: İkinci soruda "kedimin adı Pamuk" bilgisi geri geliyor.

- [ ] **Step 8: Herhangi bir sorun bulunursa not al, gerekiyorsa küçük bir düzeltme commit'i at**
