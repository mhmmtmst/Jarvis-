# Jarvis Agent Loglama + Durum Geçmişi Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Python agent'a anlamlı log satırları eklemek, ve `AgentProcessManager`'ın durum geçişlerini (starting/running/restarting/crashed) log geçmişiyle aynı kronolojik tampona yazmasını sağlayarak DEBUG panelinin soğuk başlangıçta bile ilk durumları göstermesini sağlamak.

**Architecture:** `shell/agent-process.js`'te tek bir `_recordHistory(entry)` metodu hem stdout/stderr satırlarını (`_pushLog` üzerinden) hem durum geçişlerini (yeni `_emitStatus` sarmalayıcı üzerinden) aynı `logHistory` dizisine, gerçek oluş sırasıyla yazar. Renderer'daki ayrı `debugStatusLog` tamponu tamamen kaldırılır (artık gereksiz). Python tarafında `agent/main.py`'de bir kez `logging.basicConfig` çağrılır, dört anlamlı noktaya (agent başlangıcı, WS sunucusu dinlemeye başladı, Live oturumu kuruldu, Live bağlantısı koptu) log satırı eklenir.

**Tech Stack:** Python stdlib `logging`, pytest'in `caplog` fixture'ı (yeni bağımlılık yok). Node'un yerleşik `node:test` (mevcut desen).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-24-jarvis-agent-logging-and-status-history-design.md`.
- Python testleri kök dizinden: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_X.py -v`.
- JS testleri kök dizinden: `node --test shell/agent-process.test.js`.
- Yüksek frekanslı olaylar (tool çağrıları, ses paketleri, transkriptler) loglanmıyor — sadece seyrek, tanısal değeri olan 4 nokta.
- `main.js`/`preload.js`'e bu planda hiç dokunulmuyor.

---

### Task 1: Python agent'a log satırları ekleme

**Files:**
- Modify: `agent/main.py`
- Modify: `agent/ws_server.py`
- Modify: `agent/gemini/live_session.py`
- Modify: `agent/tests/test_main.py`
- Create: `agent/tests/test_ws_server_logging.py`
- Modify: `agent/tests/test_live_session.py`

**Interfaces:**
- Consumes: yok (bağımsız, mevcut modüllere ekleme).
- Produces: her üç modülde `logging.getLogger(__name__)` üzerinden loglanan satırlar; harici bir arayüz değişikliği yok.

- [ ] **Step 1: Failing testleri yaz**

`agent/tests/test_main.py`'nin en üstündeki `import asyncio` satırının altına `import logging` ekle. Sonra dosyanın sonuna ekle:

```python
def test_attempt_live_session_logs_a_warning_on_failure(caplog):
    class FailingLiveSession:
        async def run(self):
            raise RuntimeError("bağlantı koptu")

    async def on_error(message):
        pass

    with caplog.at_level(logging.WARNING):
        asyncio.run(_attempt_live_session(FailingLiveSession(), on_error, backoff_seconds=0))

    assert any("bağlantı koptu" in record.message for record in caplog.records)
```

Yeni dosya `agent/tests/test_ws_server_logging.py` tam içerik. Not: `_broadcast_system_info`/`_broadcast_weather` gerçek `psutil`/ağ çağrıları yapan sonsuz döngülerdir (bkz. `agent/ws_server.py:189-205`) — gerçek `serve_forever()`'ı hiç değiştirmeden test edersek test yavaş/flaky olur ve gerçek ağ isteği atar. Bu yüzden ikisi de no-op ile monkeypatch'lenir; `serve_forever()` böylece gerçekten tamamlanır (sonsuz döngüye girmez), test hızlı ve deterministik kalır:

```python
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
```

`agent/tests/test_live_session.py`'nin en üstündeki `import asyncio` satırının altına `import logging` ekle. Sonra dosyanın sonuna ekle (dosyanın başındaki mevcut `FakeSession`/`FakeClient`/`make_message` yardımcılarını kullanır — bunlar zaten dosyada tanımlı, tekrar yazma):

```python
def test_run_logs_when_live_session_connects(caplog):
    session = FakeSession(messages=[])
    client = FakeClient(session)
    async def on_event(event):
        pass

    live = LiveSession(client=client, model="gemini-test-model", voice="Kore", tools={}, on_event=on_event)

    with caplog.at_level(logging.INFO):
        asyncio.run(live.run())

    assert any("gemini-test-model" in record.message for record in caplog.records)
```

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_main.py agent/tests/test_ws_server_logging.py agent/tests/test_live_session.py -v`
Expected: yeni 3 test FAIL (henüz hiçbir log satırı yok, `caplog.records` boş).

- [ ] **Step 3: `agent/main.py`'yi güncelle**

Dosyanın en üstündeki `import asyncio` satırını şununla değiştir (iki yeni stdlib import'u ekleniyor):

```python
import asyncio
import logging
import sys
```

Mevcut `from agent.ws_server import JarvisServer` satırının hemen altına, `def build_components()` tanımından önce, boş bir satırla ayrılmış şekilde ekle:

```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)
```

`main_async()`'ın en başına ekle:

```python
async def main_async() -> None:
    server, live_session, wake_word_listener = build_components()
    logger.info("Jarvis agent başlatılıyor...")
```

`_attempt_live_session`'ın `except` bloğuna, mevcut `await on_error(str(error))` satırının hemen üstüne ekle:

```python
    try:
        await live_session.run()
    except Exception as error:
        logger.warning("Gemini Live bağlantısı koptu: %s", error)
        await on_error(str(error))
        await asyncio.sleep(backoff_seconds)
```

- [ ] **Step 4: `agent/ws_server.py`'yi güncelle**

Dosyanın en üstündeki `import asyncio` satırını şununla değiştir:

```python
import asyncio
import logging
```

`WEATHER_REFRESH_SECONDS = 900  # ...` satırının hemen altına ekle:

```python
logger = logging.getLogger(__name__)
```

`serve_forever`'ı güncelle:

```python
    async def serve_forever(self) -> None:
        async with websockets.serve(self._handler, self._host, self._port):
            logger.info("WebSocket sunucusu %s:%s adresinde dinliyor", self._host, self._port)
            await asyncio.gather(
                self._broadcast_system_info(),
                self._broadcast_weather(),
            )
```

- [ ] **Step 5: `agent/gemini/live_session.py`'yi güncelle**

Dosyanın en üstündeki `import asyncio` satırını şununla değiştir:

```python
import asyncio
import logging
```

`from agent.tools.registry import ToolSpec` satırının hemen altına, `class LiveSession:` tanımından önce, ekle:

```python
logger = logging.getLogger(__name__)
```

`run`'ı güncelle:

```python
    async def run(self) -> None:
        config = self._build_config()
        async with self._client.aio.live.connect(model=self._model, config=config) as session:
            logger.info("Gemini Live oturumu kuruldu (model=%s)", self._model)
            self._session = session
            async for message in session.receive():
                await self._handle_message(message)
```

- [ ] **Step 6: Testleri çalıştır, geçtiklerini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_main.py agent/tests/test_ws_server_logging.py agent/tests/test_live_session.py -v`
Expected: PASS

- [ ] **Step 7: Tüm Python test paketini çalıştır**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/ -v`
Expected: tüm testler PASS (yeni loglama eski testleri bozmamalı — `logging.basicConfig` idempotent değildir ama testler ayrı process'lerde/aynı process içinde tekrar çağrılsa bile hata fırlatmaz, sadece ilk çağrı etkili olur)

- [ ] **Step 8: Commit**

```bash
git add agent/main.py agent/ws_server.py agent/gemini/live_session.py agent/tests/test_main.py agent/tests/test_ws_server_logging.py agent/tests/test_live_session.py
git commit -m "feat(agent): agent başlangıcı, WS dinleme ve Live bağlantı olaylarını logla"
```

---

### Task 2: `shell/agent-process.js` — durum geçişlerini log geçmişine yazma

**Files:**
- Modify: `shell/agent-process.js`
- Modify: `shell/agent-process.test.js`

**Interfaces:**
- Consumes: yok (Task 1'den bağımsız).
- Produces: `getLogHistory()` artık `{stream: 'status', text: '[AGENT ...]'}` girdilerini de gerçek kronolojik sırayla içerir. `'status'` event'i (dış API, `main.js` tarafından kullanılıyor) davranışsal olarak DEĞİŞMİYOR — hâlâ aynı string değerlerle yayınlanıyor.

- [ ] **Step 1: Failing testleri yaz**

`shell/agent-process.test.js`'de, mevcut `'log lines are buffered with stream origin, split on newlines, empty lines dropped'` testini BUL ve tamamen şu haliyle DEĞİŞTİR (artık `start()` da bir log girdisi ürettiği için beklenen dizi güncelleniyor):

```js
test('log lines are buffered with stream origin, split on newlines, empty lines dropped', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });
  const logs = [];
  manager.on('log', (entry) => logs.push(entry));

  manager.start();
  fakeChild.stdout.emit('data', Buffer.from('satir1\nsatir2\n'));
  fakeChild.stderr.emit('data', Buffer.from('hata!\n'));

  assert.deepEqual(logs, [
    { stream: 'status', text: '[AGENT STARTING]' },
    { stream: 'stdout', text: 'satir1' },
    { stream: 'stdout', text: 'satir2' },
    { stream: 'stderr', text: 'hata!' },
  ]);
  assert.deepEqual(manager.getLogHistory(), logs);
});
```

Dosyanın sonuna ekle:

```js
test('status transitions are recorded into the same chronological history as log lines', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });

  manager.start();
  fakeChild.stdout.emit('data', Buffer.from('merhaba\n'));
  fakeChild.emit('spawn');

  assert.deepEqual(manager.getLogHistory(), [
    { stream: 'status', text: '[AGENT STARTING]' },
    { stream: 'stdout', text: 'merhaba' },
    { stream: 'status', text: '[AGENT RUNNING]' },
  ]);
});

test('the external status event still fires unchanged for main.js IPC forwarding', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });
  const statuses = [];
  manager.on('status', (s) => statuses.push(s));

  manager.start();
  fakeChild.emit('spawn');

  assert.deepEqual(statuses, ['starting', 'running']);
});
```

- [ ] **Step 2: Testleri çalıştır, yeni 2 testin FAIL, güncellenen testin de FAIL olduğunu doğrula**

Run: `node --test shell/agent-process.test.js`
Expected: 3 test FAIL (güncellenen "log lines are buffered..." testi henüz eski davranışı bekliyormuş gibi kod değişmediği için status girdisi olmadan FAIL verir; yeni 2 test de FAIL).

- [ ] **Step 3: `shell/agent-process.js`'yi güncelle**

`start()` içindeki `this.emit('status', 'starting');` satırını şuna değiştir:

```js
    this._emitStatus('starting');
```

`start()` içindeki `child.on('spawn', () => this.emit('status', 'running'));` satırını şuna değiştir:

```js
    child.on('spawn', () => this._emitStatus('running'));
```

`_handleExit`'teki `this.emit('status', 'crashed');` satırını şuna değiştir:

```js
      this._emitStatus('crashed');
```

`_handleExit`'teki `this.emit('status', 'restarting');` satırını şuna değiştir:

```js
    this._emitStatus('restarting');
```

`_pushLog` metodunu şu şekilde sadeleştir (artık `_recordHistory`'yi kullanıyor):

```js
  _pushLog(stream, chunk) {
    const text = chunk.toString('utf-8');
    for (const line of text.split(/\r?\n/)) {
      if (!line) continue;
      this._recordHistory({ stream, text: line });
    }
  }
```

`_pushLog`'un hemen üstüne (veya altına, sınıf içinde herhangi bir yere) iki yeni metot ekle:

```js
  _emitStatus(status) {
    this._recordHistory({ stream: 'status', text: `[AGENT ${status.toUpperCase()}]` });
    this.emit('status', status);
  }

  _recordHistory(entry) {
    this.logHistory.push(entry);
    if (this.logHistory.length > LOG_HISTORY_LIMIT) this.logHistory.shift();
    this.emit('log', entry);
  }
```

- [ ] **Step 4: Testleri çalıştır, geçtiğini doğrula**

Run: `node --test shell/agent-process.test.js`
Expected: PASS (18 passed — mevcut 16 testten 1 tanesi güncellendi (sayıyı değiştirmez) + bu görevin 2 yeni testi = 18)

- [ ] **Step 5: Commit**

```bash
git add shell/agent-process.js shell/agent-process.test.js
git commit -m "feat(shell): durum geçişlerini log geçmişiyle aynı kronolojik tampona yaz"
```

---

### Task 3: DEBUG paneli — artık gereksiz olan renderer-taraflı durum tamponunu kaldırma

**Files:**
- Modify: `shell/renderer/renderer.js`
- Modify: `shell/renderer/styles.css`

**Interfaces:**
- Consumes: `shell/agent-process.js`'in artık durum satırlarını da `getAgentLogHistory()`/`onAgentLog` üzerinden yaydığı gerçeği (Task 2, bu görevden önce yapılmış olmalı).

- [ ] **Step 1: `shell/renderer/renderer.js`'i güncelle**

DEBUG paneli bölümünün mevcut hali (yorum satırından `window.jarvisShell.onAgentStatus(...)` bloğunun sonuna kadar) şu şekilde DEĞİŞTİRİLİYOR — `debugStatusLog` dizisi, `recordStatusLine` fonksiyonu, `openDebugPanel`'deki `debugStatusLog.forEach(appendDebugLine);` satırı, ve tüm `window.jarvisShell.onAgentStatus(...)` bloğu KALDIRILIYOR:

```js
// ── DEBUG paneli — Python agent çıktısı ────────────────────────────────────
const debugToggle = document.getElementById('debug-toggle');
const debugPanel = document.getElementById('debug-panel');
const debugLog = document.getElementById('debug-log');
const debugRestart = document.getElementById('debug-restart');
const debugClose = document.getElementById('debug-close');
let debugPanelOpening = false;

function appendDebugLine(entry) {
  const line = document.createElement('div');
  line.className = `debug-log-line ${entry.stream}`;
  line.textContent = entry.text;
  debugLog.appendChild(line);
  while (debugLog.children.length > 500) {
    debugLog.removeChild(debugLog.firstChild);
  }
  debugLog.scrollTop = debugLog.scrollHeight;
}

async function openDebugPanel() {
  if (debugPanelOpening) return;
  debugPanelOpening = true;
  debugPanel.classList.remove('hidden');
  debugLog.innerHTML = '';
  const history = await window.jarvisShell.getAgentLogHistory();
  debugPanelOpening = false;
  if (debugPanel.classList.contains('hidden')) return;
  history.forEach(appendDebugLine);
}

debugToggle.addEventListener('click', () => {
  if (debugPanel.classList.contains('hidden')) {
    openDebugPanel();
  } else {
    debugPanel.classList.add('hidden');
  }
});

debugClose.addEventListener('click', () => {
  debugPanel.classList.add('hidden');
});

debugRestart.addEventListener('click', () => {
  window.jarvisShell.restartAgent();
});

window.jarvisShell.onAgentLog((entry) => {
  if (!debugPanel.classList.contains('hidden')) appendDebugLine(entry);
});
```

(Not: `window.jarvisShell.onAgentStatus` köprüsü `preload.js`'de hâlâ duruyor, sadece renderer artık onu debug log'a eklemek için kullanmıyor — bu planın kapsamında `preload.js`/`main.js`'e dokunulmuyor.)

- [ ] **Step 2: `shell/renderer/styles.css`'e ekle**

`.debug-log-line.stderr { color: var(--red); }` kuralının hemen altına ekle:

```css
.debug-log-line.status {
  color: var(--gold);
}
```

- [ ] **Step 3: Elle doğrula**

Bu görevde otomatik test yok (DOM kodu, mevcut renderer.js deseniyle aynı). Elle doğrulama:

1. `cd shell && npm start`.
2. DEBUG panelini aç — geçmişte artık `[AGENT STARTING]`/`[AGENT RUNNING]` satırlarının (altın/gold renkte) göründüğünü doğrula (önceden bu satırlar sadece panel açıkken canlı görünüyordu, şimdi geçmişte de olmalı).
3. "YENİDEN BAŞLAT"a bas, panelin `[AGENT RESTARTING]`/`[AGENT RUNNING]` satırlarını doğru renkte gösterdiğini doğrula.
4. Python tarafında (artık Task 1 sayesinde) `WebSocket sunucusu ... dinliyor` gibi normal stdout satırlarının da göründüğünü doğrula.

- [ ] **Step 4: Commit**

```bash
git add shell/renderer/renderer.js shell/renderer/styles.css
git commit -m "refactor(shell): DEBUG panelinden artık gereksiz renderer-taraflı durum tamponunu kaldır"
```
