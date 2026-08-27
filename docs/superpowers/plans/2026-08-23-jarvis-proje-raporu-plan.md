# Jarvis "Rapor Ver" Proje Durumu Özeti Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jarvis'e, bilinen proje klasörlerinin (Odakla, ChronoPlay, doğum günü sitesi, Jarvis'in kendisi) git durumunu (branch, commit'lenmemiş değişiklik sayısı, son commit) sesli özetleyen bir `get_projects_report` tool'u eklemek.

**Architecture:** Mevcut `agent/tools/registry.py`'deki `ToolSpec` desenine eklenen yeni bir tool. Tool, yapılandırılmış veri döner (sesli cümleye çevirmeyi persona/Gemini yapar — `get_weather` ile aynı ayrım). `.env`'deki `JARVIS_REPORT_PROJECTS` (İsim:yol çiftleri) `agent/config.py` üzerinden okunur, `agent/tools/report.py`'deki `parse_report_projects` ile ayrıştırılır. Aynı git deposunun (toplevel) altındaki projeler tek bir grupta toplanır (Odakla/doğum-günü-sitesi/jarvis aynı home-dir reposu olduğu için), ChronoPlay ayrı bir grup olur; hiçbir projede remote yok, ahead/behind hiç hesaplanmaz.

**Tech Stack:** Python standart kütüphane (`subprocess`), mevcut proje deseni (`functools.partial` ile handler'a bağımlılık enjeksiyonu).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-23-jarvis-proje-raporu-design.md`.
- Hiçbir tool handler'ı ham exception fırlatmaz — `_handle_tool_call` (agent/gemini/live_session.py) handler'ları try/except ile sarmıyor, o yüzden her handler kendi hatalarını yakalayıp `{"status": "error", ...}` döner (mevcut `open_app.py` deseni).
- Yeni tool parametre şemalarında (Gemini'ye giden JSON schema) sadece modelin doldurması gereken alanlar olur; `runner`/`projects` gibi test/wiring amaçlı parametreler şemaya girmez (mevcut `open_app`'ın `launcher` parametresi gibi).
- Windows path'leri sürücü harfinden sonra kendi `:`'sini içerir (`C:/Users/...`) — `İsim:yol` ayrıştırması `split(":", 1)` ile SADECE ilk `:` üzerinden yapılmalı.
- Hiçbir yapılandırılmış projede remote yok — ahead/behind, push durumu gibi alanlar tasarıma girmiyor.
- Tüm testler kök dizinden çalıştırılır: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_X.py -v`.

---

### Task 1: `agent/tools/report.py` — proje listesi ayrıştırma + git durumu toplama

**Files:**
- Create: `agent/tools/report.py`
- Create: `agent/tests/test_report.py`

**Interfaces:**
- Produces: `parse_report_projects(raw: str) -> list[tuple[str, str]]`, `get_projects_report(projects: list[tuple[str, str]], runner=None) -> dict`.
- `runner`, verilirse `runner(args: list[str])` şeklinde çağrılır ve `.returncode`/`.stdout` alanları olan bir nesne döner (gerçekte `subprocess.run(args, capture_output=True, text=True, ...)`). Bu, `agent/tools/terminal.py`'deki parametresiz `runner()` closure deseninden FARKLI — burada tek bir `runner` ile birden çok farklı git komutu (`rev-parse`, `branch`, `status`, `log`) çağrıldığı için `runner` argüman listesi alıyor.

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_report.py` tam içerik:

```python
from types import SimpleNamespace

from agent.tools.report import get_projects_report, parse_report_projects


def _result(returncode=0, stdout=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout)


def test_parse_report_projects_splits_name_and_windows_path():
    raw = "Odakla:C:/Users/mhmmt/OneDrive/Masaüstü/Odakla,Jarvis:C:/Users/mhmmt/OneDrive/Masaüstü/jarvis"

    projects = parse_report_projects(raw)

    assert projects == [
        ("Odakla", "C:/Users/mhmmt/OneDrive/Masaüstü/Odakla"),
        ("Jarvis", "C:/Users/mhmmt/OneDrive/Masaüstü/jarvis"),
    ]


def test_parse_report_projects_ignores_empty_and_malformed_entries():
    raw = "Odakla:C:/Odakla, , NoColonHere ,ChronoPlay:C:/chronoplay"

    projects = parse_report_projects(raw)

    assert projects == [
        ("Odakla", "C:/Odakla"),
        ("ChronoPlay", "C:/chronoplay"),
    ]


def test_parse_report_projects_returns_empty_list_for_empty_string():
    assert parse_report_projects("") == []


def test_get_projects_report_returns_error_when_no_projects_configured():
    result = get_projects_report(projects=[])

    assert result == {
        "status": "error",
        "message": "Hiç proje yapılandırılmamış (JARVIS_REPORT_PROJECTS boş).",
    }


def test_get_projects_report_groups_projects_sharing_same_toplevel():
    responses = {
        ("git", "-C", "C:/home/Odakla", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/home/Jarvis", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/home", "branch", "--show-current"): _result(stdout="master\n"),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Odakla"): _result(stdout=""),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Odakla"): _result(
            stdout="fix: x|2 gün önce"
        ),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Jarvis"): _result(
            stdout=" M a.py\n?? b.py\n"
        ),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Jarvis"): _result(
            stdout="feat: y|1 saat önce"
        ),
    }

    def runner(args):
        return responses[tuple(args)]

    result = get_projects_report(
        projects=[("Odakla", "C:/home/Odakla"), ("Jarvis", "C:/home/Jarvis")],
        runner=runner,
    )

    assert result["status"] == "ok"
    assert len(result["repos"]) == 1
    repo = result["repos"][0]
    assert repo["toplevel"] == "C:/home"
    assert repo["branch"] == "master"
    assert repo["projects"] == [
        {
            "name": "Odakla",
            "changed_files": 0,
            "last_commit": {"message": "fix: x", "relative_date": "2 gün önce"},
        },
        {
            "name": "Jarvis",
            "changed_files": 2,
            "last_commit": {"message": "feat: y", "relative_date": "1 saat önce"},
        },
    ]
    assert result["errors"] == []


def test_get_projects_report_treats_separate_repo_as_its_own_group():
    responses = {
        ("git", "-C", "C:/home/Odakla", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/chronoplay", "rev-parse", "--show-toplevel"): _result(stdout="C:/chronoplay\n"),
        ("git", "-C", "C:/home", "branch", "--show-current"): _result(stdout="master\n"),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Odakla"): _result(stdout=""),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Odakla"): _result(
            stdout="fix: x|2 gün önce"
        ),
        ("git", "-C", "C:/chronoplay", "branch", "--show-current"): _result(stdout="main\n"),
        ("git", "-C", "C:/chronoplay", "status", "--porcelain", "--", "C:/chronoplay"): _result(
            stdout=" M f.cs\n"
        ),
        ("git", "-C", "C:/chronoplay", "log", "-1", "--format=%s|%ar", "--", "C:/chronoplay"): _result(
            stdout="wip|3 gün önce"
        ),
    }

    def runner(args):
        return responses[tuple(args)]

    result = get_projects_report(
        projects=[("Odakla", "C:/home/Odakla"), ("ChronoPlay", "C:/chronoplay")],
        runner=runner,
    )

    assert [repo["toplevel"] for repo in result["repos"]] == ["C:/home", "C:/chronoplay"]
    assert result["repos"][1]["branch"] == "main"
    assert result["repos"][1]["projects"][0]["changed_files"] == 1


def test_get_projects_report_isolates_error_for_one_bad_path():
    responses = {
        ("git", "-C", "C:/missing", "rev-parse", "--show-toplevel"): _result(returncode=128, stdout=""),
        ("git", "-C", "C:/home/Odakla", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/home", "branch", "--show-current"): _result(stdout="master\n"),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Odakla"): _result(stdout=""),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Odakla"): _result(stdout=""),
    }

    def runner(args):
        return responses[tuple(args)]

    result = get_projects_report(
        projects=[("Broken", "C:/missing"), ("Odakla", "C:/home/Odakla")],
        runner=runner,
    )

    assert result["errors"] == [{"name": "Broken", "message": "Git deposu bulunamadı."}]
    assert len(result["repos"]) == 1
    assert result["repos"][0]["projects"][0]["last_commit"] is None


def test_get_projects_report_isolates_unexpected_exception_per_project():
    def runner(args):
        if args[2] == "C:/boom":
            raise FileNotFoundError("git bulunamadı")
        return _result(stdout="C:/home\n")

    result = get_projects_report(
        projects=[("Boom", "C:/boom"), ("Odakla", "C:/home")],
        runner=runner,
    )

    assert result["errors"] == [{"name": "Boom", "message": "Rapor alınamadı: git bulunamadı"}]
    assert len(result["repos"]) == 1
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_report.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agent.tools.report'`)

- [ ] **Step 3: `agent/tools/report.py`'yi oluştur**

Tam içerik:

```python
import subprocess


def parse_report_projects(raw: str) -> list[tuple[str, str]]:
    """`.env`'deki JARVIS_REPORT_PROJECTS değerini (İsim:yol,İsim:yol,...)
    ayrıştırır. Windows path'leri sürücü harfinden sonra kendi `:`'sini
    içerdiği için her çift SADECE ilk `:` üzerinden bölünür."""
    projects = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name, path = entry.split(":", 1)
        name = name.strip()
        path = path.strip()
        if name and path:
            projects.append((name, path))
    return projects


def get_projects_report(projects: list[tuple[str, str]], runner=None) -> dict:
    """Bilinen proje klasörlerinin git durumunu (branch, değişen dosya
    sayısı, son commit) toplar. Aynı git deposunun (toplevel) altındaki
    projeler tek bir repo grubunda toplanır, böylece paylaşılan bir depoda
    (örn. Odakla/jarvis/doğum-günü-sitesi aynı home-dir reposu) branch
    bilgisi tekrar tekrar sorulmaz. Bir projenin git komutları başarısız
    olursa veya beklenmeyen bir hata fırlatırsa, o proje `errors` listesine
    eklenir; diğer projeler işlenmeye devam eder."""
    if runner is None:
        def runner(args):
            return subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
            )

    if not projects:
        return {"status": "error", "message": "Hiç proje yapılandırılmamış (JARVIS_REPORT_PROJECTS boş)."}

    repos: dict[str, dict] = {}
    order: list[str] = []
    errors: list[dict] = []

    for name, path in projects:
        try:
            toplevel_result = runner(["git", "-C", path, "rev-parse", "--show-toplevel"])
            if toplevel_result.returncode != 0:
                errors.append({"name": name, "message": "Git deposu bulunamadı."})
                continue

            toplevel = toplevel_result.stdout.strip()
            if toplevel not in repos:
                branch_result = runner(["git", "-C", toplevel, "branch", "--show-current"])
                branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "bilinmiyor"
                repos[toplevel] = {"toplevel": toplevel, "branch": branch, "projects": []}
                order.append(toplevel)

            status_result = runner(["git", "-C", toplevel, "status", "--porcelain", "--", path])
            changed_files = len(status_result.stdout.splitlines()) if status_result.returncode == 0 else 0

            log_result = runner(["git", "-C", toplevel, "log", "-1", "--format=%s|%ar", "--", path])
            last_commit = None
            if log_result.returncode == 0 and log_result.stdout.strip():
                message, _, relative_date = log_result.stdout.strip().partition("|")
                last_commit = {"message": message, "relative_date": relative_date}

            repos[toplevel]["projects"].append(
                {"name": name, "changed_files": changed_files, "last_commit": last_commit}
            )
        except Exception as error:
            errors.append({"name": name, "message": f"Rapor alınamadı: {error}"})

    return {
        "status": "ok",
        "repos": [repos[key] for key in order],
        "errors": errors,
    }
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_report.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/tools/report.py agent/tests/test_report.py
git commit -m "feat(agent): proje git durumu toplama - get_projects_report ve parse_report_projects"
```

---

### Task 2: `.env`/`config.py` — `JARVIS_REPORT_PROJECTS` okuma

**Files:**
- Modify: `agent/config.py`
- Modify: `agent/tests/test_config.py`
- Modify: `agent/.env.example`

**Interfaces:**
- Consumes: yok (bağımsız config alanı).
- Produces: `JarvisConfig.report_projects: str` (ham `.env` değeri, henüz ayrıştırılmamış — ayrıştırma Task 3'te `agent/main.py`'de `parse_report_projects` ile yapılır).

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_config.py`'yi güncelle — her iki mevcut testin `env` sözlüğüne ve assertion'larına ekleme yap:

```python
from agent.config import load_config


def test_load_config_reads_provided_env_mapping():
    env = {
        "GEMINI_API_KEY": "test-key-123",
        "JARVIS_WS_HOST": "0.0.0.0",
        "JARVIS_WS_PORT": "9999",
        "JARVIS_GEMINI_MODEL": "gemini-test-model",
        "JARVIS_GEMINI_VOICE": "Puck",
        "JARVIS_WEATHER_LOCATION": "Safranbolu, Karabük",
        "JARVIS_REPORT_PROJECTS": "Odakla:C:/Odakla,Jarvis:C:/jarvis",
    }

    config = load_config(env=env)

    assert config.gemini_api_key == "test-key-123"
    assert config.ws_host == "0.0.0.0"
    assert config.ws_port == 9999
    assert config.gemini_model == "gemini-test-model"
    assert config.gemini_voice == "Puck"
    assert config.weather_location == "Safranbolu, Karabük"
    assert config.report_projects == "Odakla:C:/Odakla,Jarvis:C:/jarvis"


def test_load_config_has_sane_defaults_when_env_is_empty():
    config = load_config(env={})

    assert config.gemini_api_key == ""
    assert config.ws_host == "127.0.0.1"
    assert config.ws_port == 8765
    assert config.gemini_model == "gemini-3.1-flash-live-preview"
    assert config.gemini_voice == "Kore"
    assert config.weather_location == ""
    assert config.report_projects == ""
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_config.py -v`
Expected: FAIL (`AttributeError: 'JarvisConfig' object has no attribute 'report_projects'`)

- [ ] **Step 3: `agent/config.py`'yi güncelle**

`JarvisConfig` dataclass'ına yeni alan ekle (`weather_location`'ın hemen altına):

```python
@dataclass
class JarvisConfig:
    gemini_api_key: str
    ws_host: str
    ws_port: int
    gemini_model: str
    gemini_voice: str
    weather_location: str
    report_projects: str
```

`load_config`'in döndürdüğü `JarvisConfig(...)` çağrısına ekle:

```python
        weather_location=env.get("JARVIS_WEATHER_LOCATION", ""),
        report_projects=env.get("JARVIS_REPORT_PROJECTS", ""),
    )
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: `.env.example`'a örnek satır ekle**

`agent/.env.example`'ın sonuna ekle:

```
JARVIS_REPORT_PROJECTS=Odakla:C:/Users/mhmmt/OneDrive/Masaüstü/Odakla,ChronoPlay:C:/Users/mhmmt/OneDrive/Masaüstü/chronoplay,Jarvis:C:/Users/mhmmt/OneDrive/Masaüstü/jarvis
```

- [ ] **Step 6: Commit**

```bash
git add agent/config.py agent/tests/test_config.py agent/.env.example
git commit -m "feat(agent): JARVIS_REPORT_PROJECTS config alanını ekle"
```

---

### Task 3: Registry + `main.py` bağlama

**Files:**
- Modify: `agent/tools/registry.py`
- Modify: `agent/main.py`
- Modify: `agent/tests/test_registry.py`

**Interfaces:**
- Consumes: `agent.tools.report.get_projects_report`, `agent.tools.report.parse_report_projects` (Task 1), `JarvisConfig.report_projects` (Task 2).
- Produces: `build_tool_registry(client, weather_default_location="", report_projects=None)` — yeni `report_projects: list[tuple[str, str]] | None = None` parametresi.

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_registry.py`'de `test_registry_contains_all_tools`'u güncelle (yeni tool'u sete ekle):

```python
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
        "delete_memory",
        "get_weather",
        "get_projects_report",
    }
```

Dosyanın sonuna ekle:

```python
def test_get_projects_report_tool_spec_takes_no_parameters():
    spec = build_tool_registry(make_fake_client())["get_projects_report"]

    assert spec.parameters["properties"] == {}
    assert spec.parameters["required"] == []


def test_get_projects_report_handler_is_bound_to_the_given_projects():
    registry = build_tool_registry(make_fake_client(), report_projects=[])

    result = registry["get_projects_report"].handler()

    assert result == {
        "status": "error",
        "message": "Hiç proje yapılandırılmamış (JARVIS_REPORT_PROJECTS boş).",
    }
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_registry.py -v`
Expected: FAIL (`KeyError: 'get_projects_report'` veya set eşitsizliği)

- [ ] **Step 3: `agent/tools/registry.py`'yi güncelle**

İmport'lara ekle:

```python
from agent.tools.report import get_projects_report
```

`build_tool_registry`'nin imzasını değiştir:

```python
def build_tool_registry(
    client,
    weather_default_location: str = "",
    report_projects: list[tuple[str, str]] | None = None,
) -> dict[str, ToolSpec]:
```

Döndürülen dict'e, `"get_weather"` girdisinden hemen sonra ekle:

```python
        "get_projects_report": ToolSpec(
            name="get_projects_report",
            description=(
                "Bilinen proje klasörlerinin (Odakla, ChronoPlay, doğum günü sitesi, Jarvis) "
                "git durumunu döner: branch, commit'lenmemiş değişiklik sayısı, son commit. "
                "Kullanıcı 'rapor ver', 'projelerde durum ne', 'neyi yarım bıraktım' derse "
                "kullan. Cevaplarken önemli olanı öne çıkar: temiz/güncel projelerden tek "
                "cümleyle bahset, commit'lenmemiş değişikliği olan projeleri detaylandır."
            ),
            parameters={"type": "object", "properties": {}},
            handler=partial(get_projects_report, projects=report_projects or []),
        ),
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_registry.py -v`
Expected: PASS (16 passed)

- [ ] **Step 5: `agent/main.py`'yi güncelle**

İmport'lara ekle:

```python
from agent.tools.report import parse_report_projects
```

`build_components()` içinde `tools = build_tool_registry(...)` satırını değiştir:

```python
    report_projects = parse_report_projects(config.report_projects)
    tools = build_tool_registry(
        client,
        weather_default_location=config.weather_location,
        report_projects=report_projects,
    )
```

- [ ] **Step 6: Tüm test paketini çalıştır, hiçbir şeyin bozulmadığını doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/ -v`
Expected: tüm testler PASS

- [ ] **Step 7: Commit**

```bash
git add agent/tools/registry.py agent/main.py agent/tests/test_registry.py
git commit -m "feat(agent): get_projects_report'u registry'ye ve main.py wiring'e bağla"
```

---

### Task 4: Persona — "rapor ver" örneği

**Files:**
- Modify: `agent/persona.py`
- Create: `agent/tests/test_persona.py`

**Interfaces:**
- Consumes: yok (statik string güncellemesi).

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_persona.py` tam içerik:

```python
from agent.persona import JARVIS_PERSONA


def test_persona_lists_get_projects_report_tool():
    assert "get_projects_report" in JARVIS_PERSONA


def test_persona_has_rapor_ver_example():
    assert "rapor ver" in JARVIS_PERSONA.lower()
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_persona.py -v`
Expected: FAIL (`assert 'get_projects_report' in JARVIS_PERSONA`)

- [ ] **Step 3: `agent/persona.py`'yi güncelle**

`ARAÇLAR:` bölümündeki son satırın (`- remember / recall / delete_memory: Kalıcı hafıza`) altına ekle:

```python
- get_projects_report: Bilinen proje klasörlerinin git durumu (branch, değişiklik, son commit)
```

`ÖRNEK KONUŞMALAR:` bölümüne, `- "Ne hatırlıyorsun" → recall()` satırından önce ekle:

```python
- "Rapor ver" → get_projects_report()
- "Projelerde durum ne" → get_projects_report()
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_persona.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Tüm test paketini son kez çalıştır**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/ -v`
Expected: tüm testler PASS

- [ ] **Step 6: Commit**

```bash
git add agent/persona.py agent/tests/test_persona.py
git commit -m "feat(agent): persona'ya rapor ver ornegini ekle"
```
