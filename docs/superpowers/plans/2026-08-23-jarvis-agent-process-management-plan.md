# Electron'un Python Agent'ı Yönetmesi Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Electron kabuğu, Python agent'ı (`agent/main.py`) kendi child process'i olarak başlatsın, beklenmedik çökmede backoff'lu otomatik yeniden başlatsın, kapanışta düzgünce sonlandırsın, ve çıktısını HUD'da yeni bir DEBUG panelinde göstersin.

**Architecture:** Yeni, saf/test edilebilir bir `AgentProcessManager` sınıfı (`shell/agent-process.js`, Node'un `EventEmitter`'ından türetilmiş) süreç yaşam döngüsünü yönetir; `shell/main.js` bunu örnekleyip `app.whenReady()`'de başlatır, `before-quit`'te durdurur, ve `log`/`status` olaylarını IPC ile renderer'a iletir. `shell/preload.js`'e yeni köprü fonksiyonları eklenir. HUD'a (`shell/renderer/`) yeni bir aç/kapa DEBUG paneli eklenir.

**Tech Stack:** Node.js `child_process`/`events` (Electron'un ana süreci), Node'un yerleşik `node:test` modülü (mevcut `protocol.test.js` deseniyle aynı), düz CommonJS (`shell/agent-process.js` sadece Electron ana sürecinde çalışır, `protocol.js`'in aksine tarayıcıda da çalışması gerekmediği için UMD sarmalayıcı yok).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-23-jarvis-agent-process-management-design.md`.
- Python agent'ın doğru çalışması için `-m agent.main` ile, `cwd` proje kökünde (`shell/`'in bir üst dizini) olacak şekilde başlatılmalı — `agent/main.py`'yi doğrudan dosya yolu ile ÇALIŞTIRMA (mutlak paket import'ları `python -m` gerektiriyor).
- JS testleri kök dizinden şu şekilde çalıştırılır: `node --test shell/agent-process.test.js`. Mevcut `node --test shell/renderer/protocol.test.js` deseniyle aynı (Jest yok, `node:test` + `node:assert/strict`).
- `shell/main.js`/`shell/preload.js` gibi Electron yaşam döngüsü koduna dair değişiklikler bu projede otomatik test edilmiyor (mevcut kod tabanında da `main.js`'in kendisi hiç test edilmiyor) — bunun yerine her görevin sonunda somut bir elle-doğrulama adımı var.
- Yeni işlem yönetimi backoff sabitleri: `MAX_BACKOFF_MS = 16000`, `MAX_RESTART_ATTEMPTS = 5`, `STABLE_UPTIME_MS = 10000`.

---

### Task 1: `shell/agent-process.js` — `AgentProcessManager` + `nextBackoffMs`

**Files:**
- Create: `shell/agent-process.js`
- Create: `shell/agent-process.test.js`

**Interfaces:**
- Produces: `nextBackoffMs(attempt: number): number`, `class AgentProcessManager extends EventEmitter` with `constructor({ pythonPath, cwd, spawnFn, setTimeoutFn, clearTimeoutFn })`, `.start()`, `.stop()`, `.restart()`, `.getLogHistory(): Array<{stream, text}>`. Olaylar: `'log'` (payload `{ stream: 'stdout'|'stderr', text: string }`), `'status'` (payload `'starting' | 'running' | 'restarting' | 'crashed'`).

- [ ] **Step 1: Failing testleri yaz**

`shell/agent-process.test.js` tam içerik:

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { AgentProcessManager, nextBackoffMs } = require('./agent-process');

function makeFakeChild() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.killCalls = [];
  child.kill = (signal) => child.killCalls.push(signal);
  return child;
}

function makeFakeTimers() {
  const scheduled = [];
  const setTimeoutFn = (fn, delay) => {
    const handle = { fn, delay };
    scheduled.push(handle);
    return handle;
  };
  const clearTimeoutFn = (handle) => {
    const idx = scheduled.indexOf(handle);
    if (idx !== -1) scheduled.splice(idx, 1);
  };
  return {
    setTimeoutFn,
    clearTimeoutFn,
    scheduled,
    fireNext: () => scheduled.shift().fn(),
  };
}

test('nextBackoffMs doubles each attempt and caps at 16000', () => {
  assert.equal(nextBackoffMs(0), 1000);
  assert.equal(nextBackoffMs(1), 2000);
  assert.equal(nextBackoffMs(2), 4000);
  assert.equal(nextBackoffMs(3), 8000);
  assert.equal(nextBackoffMs(4), 16000);
  assert.equal(nextBackoffMs(5), 16000);
});

test('start() spawns python with -m agent.main from the given cwd, hidden window', () => {
  const calls = [];
  const fakeChild = makeFakeChild();
  const spawnFn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    return fakeChild;
  };
  const manager = new AgentProcessManager({ pythonPath: 'C:/py.exe', cwd: 'C:/jarvis', spawnFn });

  manager.start();

  assert.deepEqual(calls, [
    { cmd: 'C:/py.exe', args: ['-m', 'agent.main'], opts: { cwd: 'C:/jarvis', windowsHide: true } },
  ]);
});

test('start() emits status starting then running on spawn', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });
  const statuses = [];
  manager.on('status', (s) => statuses.push(s));

  manager.start();
  assert.deepEqual(statuses, ['starting']);
  fakeChild.emit('spawn');
  assert.deepEqual(statuses, ['starting', 'running']);
});

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
    { stream: 'stdout', text: 'satir1' },
    { stream: 'stdout', text: 'satir2' },
    { stream: 'stderr', text: 'hata!' },
  ]);
  assert.deepEqual(manager.getLogHistory(), logs);
});

test('log history is capped at 200 entries (FIFO)', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });

  manager.start();
  for (let i = 0; i < 205; i++) {
    fakeChild.stdout.emit('data', Buffer.from(`line-${i}\n`));
  }

  const history = manager.getLogHistory();
  assert.equal(history.length, 200);
  assert.equal(history[0].text, 'line-5');
  assert.equal(history[199].text, 'line-204');
});

test('unexpected exit schedules a restart with the first backoff delay', () => {
  let spawnCount = 0;
  const spawnFn = () => {
    spawnCount += 1;
    return makeFakeChild();
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start();
  assert.equal(spawnCount, 1);
  manager.child.emit('exit', 1, null);

  assert.equal(timers.scheduled.length, 1);
  assert.equal(timers.scheduled[0].delay, 1000);

  timers.fireNext();
  assert.equal(spawnCount, 2);
});

test('gives up after 5 consecutive fast crashes and emits crashed status, no 6th spawn', () => {
  let spawnCount = 0;
  const spawnFn = () => {
    spawnCount += 1;
    return makeFakeChild();
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });
  const statuses = [];
  manager.on('status', (s) => statuses.push(s));

  manager.start(); // spawn #1
  for (let i = 0; i < 4; i++) {
    manager.child.emit('exit', 1, null);
    timers.fireNext(); // spawns #2..#5
  }
  assert.equal(spawnCount, 5);

  manager.child.emit('exit', 1, null); // 5th crash — give up
  assert.equal(timers.scheduled.length, 0);
  assert.equal(spawnCount, 5);
  assert.ok(statuses.includes('crashed'));
});

test('stop() kills the child and does not schedule a restart on its exit', () => {
  const fakeChild = makeFakeChild();
  const spawnFn = () => fakeChild;
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start();
  manager.stop();
  assert.deepEqual(fakeChild.killCalls, ['SIGTERM']);

  fakeChild.emit('exit', 0, 'SIGTERM');
  assert.equal(timers.scheduled.length, 0);
});

test('restart() from a crashed (no child) state respawns immediately without waiting for a timer', () => {
  let spawnCount = 0;
  const spawnFn = () => {
    spawnCount += 1;
    return makeFakeChild();
  };
  const timers = makeFakeTimers();
  const manager = new AgentProcessManager({
    pythonPath: 'p', cwd: 'c', spawnFn,
    setTimeoutFn: timers.setTimeoutFn, clearTimeoutFn: timers.clearTimeoutFn,
  });

  manager.start(); // #1
  for (let i = 0; i < 4; i++) {
    manager.child.emit('exit', 1, null);
    timers.fireNext();
  }
  manager.child.emit('exit', 1, null); // gives up, spawnCount == 5, no child
  assert.equal(manager.child, null);

  manager.restart();
  assert.equal(spawnCount, 6);
});

test('restart() while a child is running waits for its real exit before respawning (no race)', () => {
  let spawnCount = 0;
  const children = [];
  const spawnFn = () => {
    spawnCount += 1;
    const child = makeFakeChild();
    children.push(child);
    return child;
  };
  const manager = new AgentProcessManager({ pythonPath: 'p', cwd: 'c', spawnFn });

  manager.start();
  assert.equal(spawnCount, 1);

  manager.restart();
  assert.equal(spawnCount, 1, 'must not spawn a new child before the old one has actually exited');
  assert.deepEqual(children[0].killCalls, ['SIGTERM']);

  children[0].emit('exit', 0, 'SIGTERM');
  assert.equal(spawnCount, 2);
});
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `node --test shell/agent-process.test.js`
Expected: FAIL (`Cannot find module './agent-process'`)

- [ ] **Step 3: `shell/agent-process.js`'yi oluştur**

Tam içerik:

```js
const { EventEmitter } = require('node:events');
const { spawn } = require('node:child_process');

const MAX_BACKOFF_MS = 16000;
const MAX_RESTART_ATTEMPTS = 5;
const STABLE_UPTIME_MS = 10000;
const LOG_HISTORY_LIMIT = 200;

function nextBackoffMs(attempt) {
  return Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS);
}

class AgentProcessManager extends EventEmitter {
  constructor({ pythonPath, cwd, spawnFn = spawn, setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout }) {
    super();
    this.pythonPath = pythonPath;
    this.cwd = cwd;
    this.spawnFn = spawnFn;
    this.setTimeoutFn = setTimeoutFn;
    this.clearTimeoutFn = clearTimeoutFn;

    this.child = null;
    this.logHistory = [];
    this.consecutiveFastCrashes = 0;
    this.startedAt = null;
    this._intentionalStop = false;
    this._restartTimer = null;
  }

  start() {
    this._intentionalStop = false;
    this.emit('status', 'starting');

    this.child = this.spawnFn(this.pythonPath, ['-m', 'agent.main'], {
      cwd: this.cwd,
      windowsHide: true,
    });
    this.startedAt = Date.now();

    this.child.stdout.on('data', (chunk) => this._pushLog('stdout', chunk));
    this.child.stderr.on('data', (chunk) => this._pushLog('stderr', chunk));
    this.child.on('spawn', () => this.emit('status', 'running'));
    this.child.on('exit', () => this._handleExit());
  }

  stop() {
    this._intentionalStop = true;
    if (this._restartTimer) {
      this.clearTimeoutFn(this._restartTimer);
      this._restartTimer = null;
    }
    if (this.child) {
      this.child.kill('SIGTERM');
    }
  }

  restart() {
    this.consecutiveFastCrashes = 0;
    if (this._restartTimer) {
      this.clearTimeoutFn(this._restartTimer);
      this._restartTimer = null;
    }

    if (this.child) {
      this._intentionalStop = true;
      this.child.once('exit', () => {
        this.start();
      });
      this.child.kill('SIGTERM');
    } else {
      this.start();
    }
  }

  getLogHistory() {
    return this.logHistory.slice();
  }

  _handleExit() {
    this.child = null;
    if (this._intentionalStop) return;

    const uptime = Date.now() - this.startedAt;
    if (uptime >= STABLE_UPTIME_MS) {
      this.consecutiveFastCrashes = 0;
    } else {
      this.consecutiveFastCrashes += 1;
    }

    if (this.consecutiveFastCrashes >= MAX_RESTART_ATTEMPTS) {
      this.emit('status', 'crashed');
      return;
    }

    const delay = nextBackoffMs(this.consecutiveFastCrashes - 1);
    this.emit('status', 'restarting');
    this._restartTimer = this.setTimeoutFn(() => this.start(), delay);
  }

  _pushLog(stream, chunk) {
    const text = chunk.toString('utf-8');
    for (const line of text.split(/\r?\n/)) {
      if (!line) continue;
      const entry = { stream, text: line };
      this.logHistory.push(entry);
      if (this.logHistory.length > LOG_HISTORY_LIMIT) this.logHistory.shift();
      this.emit('log', entry);
    }
  }
}

module.exports = { AgentProcessManager, nextBackoffMs };
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `node --test shell/agent-process.test.js`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add shell/agent-process.js shell/agent-process.test.js
git commit -m "feat(shell): add AgentProcessManager for spawning/restarting the Python agent"
```

---

### Task 2: `main.js`/`preload.js` — Python agent'ı gerçekten başlatma + IPC

**Files:**
- Modify: `shell/main.js`
- Modify: `shell/preload.js`

**Interfaces:**
- Consumes: `AgentProcessManager` (Task 1).
- Produces: `preload.js`'in `window.jarvisShell`'e eklediği `onAgentLog(callback)`, `onAgentStatus(callback)`, `getAgentLogHistory(): Promise<Array<{stream, text}>>`, `restartAgent(): Promise<void>`.

- [ ] **Step 1: `shell/main.js`'i güncelle**

Tam içerik (mevcut dosyanın tamamının yerine geçer):

```js
const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const { AgentProcessManager } = require('./agent-process');

let mainWindow = null;

const agentManager = new AgentProcessManager({
  pythonPath: path.join(__dirname, '..', 'agent', 'venv', 'Scripts', 'python.exe'),
  cwd: path.join(__dirname, '..'),
});

function createWindow() {
  mainWindow = new BrowserWindow({
    fullscreen: true,
    autoHideMenuBar: true,
    backgroundColor: '#05080a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  return mainWindow;
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(permission === 'media' || permission === 'geolocation');
  });

  createWindow();

  agentManager.on('log', (entry) => {
    if (mainWindow) mainWindow.webContents.send('agent-log', entry);
  });
  agentManager.on('status', (status) => {
    if (mainWindow) mainWindow.webContents.send('agent-status', status);
  });
  agentManager.start();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  agentManager.stop();
});

ipcMain.on('jarvis:quit', () => {
  app.quit();
});

ipcMain.handle('jarvis:restart-agent', () => {
  agentManager.restart();
});

ipcMain.handle('jarvis:agent-log-history', () => agentManager.getLogHistory());
```

- [ ] **Step 2: `shell/preload.js`'i güncelle**

Tam içerik (mevcut dosyanın tamamının yerine geçer):

```js
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvisShell', {
  quit: () => ipcRenderer.send('jarvis:quit'),
  onAgentLog: (callback) => {
    ipcRenderer.on('agent-log', (_event, entry) => callback(entry));
  },
  onAgentStatus: (callback) => {
    ipcRenderer.on('agent-status', (_event, status) => callback(status));
  },
  getAgentLogHistory: () => ipcRenderer.invoke('jarvis:agent-log-history'),
  restartAgent: () => ipcRenderer.invoke('jarvis:restart-agent'),
});
```

- [ ] **Step 3: Elle doğrula**

Bu görevde otomatik test yok (mevcut `main.js` de hiç test edilmiyor — aynı kod tabanı deseni). Elle doğrulama:

1. `agent/.env`'in `GEMINI_API_KEY` gibi gerekli alanlarının dolu olduğundan emin ol (bu görevden önce Python agent'ı `./agent/venv/Scripts/python.exe -m agent.main` ile ELLE başlatıp çalıştığını zaten biliyoruz).
2. Çalışan varsa mevcut elle-başlatılmış Python agent'ı kapat (aynı WS portunda çakışma olmasın: 8765).
3. `cd shell && npm start` çalıştır.
4. Görev Yöneticisi'nde (Task Manager) yeni bir `python.exe` sürecinin Electron ile birlikte başladığını doğrula.
5. HUD'un normal şekilde bağlandığını doğrula (üstteki durum "ONLINE" olmalı — bu, Python agent'ın Electron tarafından başarıyla başlatılıp WS sunucusunun ayakta olduğunun kanıtı).
6. Electron penceresini kapat (veya SHUTDOWN butonuna bas), birkaç saniye bekle, Görev Yöneticisi'nde `python.exe`'nin de kapandığını doğrula (yetim süreç kalmamalı).

- [ ] **Step 4: Commit**

```bash
git add shell/main.js shell/preload.js
git commit -m "feat(shell): main.js Python agent'ı child process olarak başlatıp yönetsin"
```

---

### Task 3: HUD — DEBUG paneli

**Files:**
- Modify: `shell/renderer/index.html`
- Modify: `shell/renderer/styles.css`
- Modify: `shell/renderer/renderer.js`

**Interfaces:**
- Consumes: `window.jarvisShell.onAgentLog`, `onAgentStatus`, `getAgentLogHistory`, `restartAgent` (Task 2).

- [ ] **Step 1: `shell/renderer/index.html`'i güncelle**

`<header class="hud-top">` içine, mevcut `#wake-indicator` span'ından hemen sonra ekle:

```html
    <button id="debug-toggle" type="button" class="debug-toggle">DEBUG</button>
```

`</main>` kapanışından hemen sonra, `<script src="protocol.js">` satırından önce ekle:

```html
  <div id="debug-panel" class="debug-panel hidden">
    <div class="debug-panel-header">
      <span>AGENT DEBUG</span>
      <button id="debug-restart" type="button">YENİDEN BAŞLAT</button>
      <button id="debug-close" type="button">✕</button>
    </div>
    <div id="debug-log" class="debug-log"></div>
  </div>
```

- [ ] **Step 2: `shell/renderer/styles.css`'e ekle**

Dosyanın sonuna ekle:

```css
.debug-toggle {
  margin-left: 12px;
  background: transparent;
  border: 1px solid var(--c-mid, #4f7b78);
  color: var(--c-mid, #4f7b78);
  font-size: 11px;
  padding: 3px 8px;
  cursor: pointer;
  letter-spacing: 0.05em;
}

.debug-panel {
  position: fixed;
  top: 48px;
  right: 16px;
  width: 420px;
  height: 320px;
  background: #041111;
  border: 1px solid #0c2a28;
  z-index: 50;
  display: flex;
  flex-direction: column;
}

.debug-panel.hidden {
  display: none;
}

.debug-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid #0c2a28;
  font-size: 11px;
  letter-spacing: 0.05em;
}

.debug-panel-header button {
  background: transparent;
  border: 1px solid #0c2a28;
  color: inherit;
  cursor: pointer;
  font-size: 10px;
  padding: 2px 6px;
  margin-left: 6px;
}

.debug-log {
  flex: 1;
  overflow-y: auto;
  padding: 8px 10px;
  font-family: monospace;
  font-size: 11px;
  white-space: pre-wrap;
}

.debug-log-line.stderr {
  color: #ff6b6b;
}
```

- [ ] **Step 3: `shell/renderer/renderer.js`'in sonuna ekle**

```js
// ── DEBUG paneli — Python agent çıktısı ────────────────────────────────────
const debugToggle = document.getElementById('debug-toggle');
const debugPanel = document.getElementById('debug-panel');
const debugLog = document.getElementById('debug-log');
const debugRestart = document.getElementById('debug-restart');
const debugClose = document.getElementById('debug-close');

function appendDebugLine(entry) {
  const line = document.createElement('div');
  line.className = `debug-log-line ${entry.stream}`;
  line.textContent = entry.text;
  debugLog.appendChild(line);
  debugLog.scrollTop = debugLog.scrollHeight;
}

async function openDebugPanel() {
  debugPanel.classList.remove('hidden');
  debugLog.innerHTML = '';
  const history = await window.jarvisShell.getAgentLogHistory();
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

window.jarvisShell.onAgentStatus((status) => {
  appendDebugLine({ stream: 'stdout', text: `[AGENT ${status.toUpperCase()}]` });
});
```

- [ ] **Step 4: Elle doğrula**

Bu görevde otomatik test yok (DOM manipülasyonu — mevcut `updateWeather`/`updateSystemInfo` gibi renderer fonksiyonları da hiç test edilmiyor, aynı desen). Elle doğrulama:

1. `cd shell && npm start`.
2. Sağ üstte yeni "DEBUG" butonunu gör, tıkla — panel açılmalı ve Python agent'ın başlangıç loglarını (geçmiş) göstermeli.
3. Konuşma/komut gönder, Python tarafında yeni bir log satırı oluşacak bir olay tetikle (örn. bir hata) — panelde canlı olarak yeni satır belirmeli.
4. "YENİDEN BAŞLAT"a bas — birkaç saniye içinde `[AGENT STARTING]`/`[AGENT RUNNING]` satırlarının panelde göründüğünü ve HUD'un yeniden "ONLINE" olduğunu doğrula.
5. Paneli ✕ ile kapat, tekrar aç — geçmişin hâlâ göründüğünü doğrula.

- [ ] **Step 5: Commit**

```bash
git add shell/renderer/index.html shell/renderer/styles.css shell/renderer/renderer.js
git commit -m "feat(shell): HUD'a Python agent çıktısını gösteren DEBUG paneli ekle"
```
