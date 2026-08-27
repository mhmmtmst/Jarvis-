# Jarvis Ayarlar Paneli Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DEBUG paneline bir SETTINGS sekmesi eklemek — ses/model/hava durumu konumu/rapor projeleri `.env`'i elle düzenlemeden değiştirilebilsin, Windows başlangıcında otomatik açılma toggle'ı olsun.

**Architecture:** `.env` okuma/yazma için saf fonksiyonlar (`shell/settings.js`, test edilebilir) + ince fs sarmalayıcıları. `shell/main.js`'e 4 yeni `ipcMain.handle` (ayar oku/kaydet, başlangıçta-aç oku/ayarla). Kaydetme, mevcut test edilmiş `agentManager.restart()`'ı tetikler — gerçek zamanlı restart'sız uygulama YOK (spec'te gerekçelendirildi). UI: mevcut DEBUG panelinin kabuğu DEBUG/SETTINGS iki sekmeye bölünüyor.

**Tech Stack:** Node'un yerleşik `fs`/`node:test` modülleri, Electron'un native `app.setLoginItemSettings`/`app.getLoginItemSettings`'i.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-24-jarvis-settings-panel-design.md`.
- Yönetilen `.env` anahtarları SADECE şunlar: `JARVIS_GEMINI_VOICE`, `JARVIS_GEMINI_MODEL`, `JARVIS_WEATHER_LOCATION`, `JARVIS_REPORT_PROJECTS`.
- Windows başlangıcında açılma ayarı `.env`'e YAZILMAZ — tamamen Electron'un `app.setLoginItemSettings`'i üzerinden, OS seviyesinde, agent restart'ından bağımsız, değişince anında uygulanır.
- JS testleri kök dizinden: `node --test shell/settings.test.js`.
- `shell/agent-process.js`'e bu planda HİÇ dokunulmuyor — sadece mevcut, zaten test edilmiş `.restart()` metodu bir kara kutu olarak çağrılıyor.

---

### Task 1: `shell/settings.js` — `.env` okuma/yazma

**Files:**
- Create: `shell/settings.js`
- Create: `shell/settings.test.js`

**Interfaces:**
- Produces: `MANAGED_KEYS: string[]`, `parseEnvFile(text: string): Record<string,string>`, `updateEnvFile(text: string, updates: Record<string,string>): string`, `readSettings(envPath: string): Record<string,string>`, `writeSettings(envPath: string, updates: Record<string,string>): void`.

- [ ] **Step 1: Failing testleri yaz**

`shell/settings.test.js` tam içerik:

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const { parseEnvFile, updateEnvFile } = require('./settings');

test('parseEnvFile extracts KEY=value pairs, skipping blanks and comments', () => {
  const text = [
    '# yorum satırı',
    '',
    'GEMINI_API_KEY=abc123',
    'JARVIS_WS_PORT=8765',
  ].join('\n');

  assert.deepEqual(parseEnvFile(text), {
    GEMINI_API_KEY: 'abc123',
    JARVIS_WS_PORT: '8765',
  });
});

test('parseEnvFile handles a value that itself contains an equals sign', () => {
  const text = 'JARVIS_REPORT_PROJECTS=Odakla:C:/x=y,Jarvis:C:/z';
  assert.deepEqual(parseEnvFile(text), {
    JARVIS_REPORT_PROJECTS: 'Odakla:C:/x=y,Jarvis:C:/z',
  });
});

test('updateEnvFile replaces an existing key in place, preserving order and comments', () => {
  const text = [
    '# yorum',
    'GEMINI_API_KEY=abc123',
    'JARVIS_GEMINI_VOICE=Kore',
    'JARVIS_WS_PORT=8765',
  ].join('\n');

  const result = updateEnvFile(text, { JARVIS_GEMINI_VOICE: 'Charon' });

  assert.equal(result, [
    '# yorum',
    'GEMINI_API_KEY=abc123',
    'JARVIS_GEMINI_VOICE=Charon',
    'JARVIS_WS_PORT=8765',
  ].join('\n'));
});

test('updateEnvFile appends a key that does not exist yet in the file', () => {
  const text = 'GEMINI_API_KEY=abc123';

  const result = updateEnvFile(text, { JARVIS_GEMINI_VOICE: 'Charon' });

  assert.equal(result, 'GEMINI_API_KEY=abc123\nJARVIS_GEMINI_VOICE=Charon');
});

test('updateEnvFile handles multiple updates in one call, mixing replace and append', () => {
  const text = 'JARVIS_GEMINI_MODEL=old-model';

  const result = updateEnvFile(text, {
    JARVIS_GEMINI_MODEL: 'new-model',
    JARVIS_WEATHER_LOCATION: 'Safranbolu',
  });

  assert.equal(result, 'JARVIS_GEMINI_MODEL=new-model\nJARVIS_WEATHER_LOCATION=Safranbolu');
});

test('updateEnvFile on an empty starting file just appends all updates', () => {
  const result = updateEnvFile('', { JARVIS_GEMINI_VOICE: 'Charon' });
  assert.equal(result, 'JARVIS_GEMINI_VOICE=Charon');
});
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `node --test shell/settings.test.js`
Expected: FAIL (`Cannot find module './settings'`)

- [ ] **Step 3: `shell/settings.js`'yi oluştur**

Tam içerik:

```js
const fs = require('fs');

const MANAGED_KEYS = [
  'JARVIS_GEMINI_VOICE',
  'JARVIS_GEMINI_MODEL',
  'JARVIS_WEATHER_LOCATION',
  'JARVIS_REPORT_PROJECTS',
];

function parseEnvFile(text) {
  const values = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1);
    values[key] = value;
  }
  return values;
}

function updateEnvFile(text, updates) {
  const lines = text.length ? text.split(/\r?\n/) : [];
  const seen = new Set();
  const outLines = lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return line;
    const eq = trimmed.indexOf('=');
    if (eq === -1) return line;
    const key = trimmed.slice(0, eq).trim();
    if (Object.prototype.hasOwnProperty.call(updates, key)) {
      seen.add(key);
      return `${key}=${updates[key]}`;
    }
    return line;
  });
  for (const [key, value] of Object.entries(updates)) {
    if (!seen.has(key)) outLines.push(`${key}=${value}`);
  }
  return outLines.join('\n');
}

function readSettings(envPath) {
  let text = '';
  try {
    text = fs.readFileSync(envPath, 'utf-8');
  } catch (err) {
    text = '';
  }
  const values = parseEnvFile(text);
  const settings = {};
  for (const key of MANAGED_KEYS) {
    settings[key] = values[key] || '';
  }
  return settings;
}

function writeSettings(envPath, updates) {
  let text = '';
  try {
    text = fs.readFileSync(envPath, 'utf-8');
  } catch (err) {
    text = '';
  }
  const newText = updateEnvFile(text, updates);
  fs.writeFileSync(envPath, newText, 'utf-8');
}

module.exports = { MANAGED_KEYS, parseEnvFile, updateEnvFile, readSettings, writeSettings };
```

- [ ] **Step 4: Testi çalıştır, geçtiğini doğrula**

Run: `node --test shell/settings.test.js`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add shell/settings.js shell/settings.test.js
git commit -m "feat(shell): .env okuma/yazma için parseEnvFile/updateEnvFile ve readSettings/writeSettings"
```

---

### Task 2: `main.js`/`preload.js` — IPC bağlama

**Files:**
- Modify: `shell/main.js`
- Modify: `shell/preload.js`

**Interfaces:**
- Consumes: `shell/settings.js`'in `readSettings`/`writeSettings` (Task 1).
- Produces: `preload.js`'in `window.jarvisShell`'e eklediği `getSettings()`, `saveSettings(values)`, `getLaunchOnStartup()`, `setLaunchOnStartup(value)`.

- [ ] **Step 1: `shell/main.js`'i güncelle**

`const { AgentProcessManager } = require('./agent-process');` satırının hemen altına ekle:

```js
const { readSettings, writeSettings } = require('./settings');
```

`const agentManager = new AgentProcessManager({...});` bloğunun hemen altına ekle:

```js
const ENV_PATH = path.join(agentManager.cwd, 'agent', '.env');
```

Dosyanın en sonuna (mevcut `ipcMain.handle('jarvis:agent-log-history', ...)` satırının altına) ekle:

```js

ipcMain.handle('jarvis:get-settings', () => readSettings(ENV_PATH));

ipcMain.handle('jarvis:save-settings', (_event, updates) => {
  writeSettings(ENV_PATH, updates);
  agentManager.restart();
});

ipcMain.handle('jarvis:get-launch-on-startup', () => app.getLoginItemSettings().openAtLogin);

ipcMain.handle('jarvis:set-launch-on-startup', (_event, value) => {
  app.setLoginItemSettings({ openAtLogin: Boolean(value) });
});
```

- [ ] **Step 2: `shell/preload.js`'i güncelle**

`getAgentLogHistory: () => ipcRenderer.invoke('jarvis:agent-log-history'),` satırının altına ekle:

```js
  restartAgent: () => ipcRenderer.invoke('jarvis:restart-agent'),
  getSettings: () => ipcRenderer.invoke('jarvis:get-settings'),
  saveSettings: (values) => ipcRenderer.invoke('jarvis:save-settings', values),
  getLaunchOnStartup: () => ipcRenderer.invoke('jarvis:get-launch-on-startup'),
  setLaunchOnStartup: (value) => ipcRenderer.invoke('jarvis:set-launch-on-startup', value),
```

(Not: `restartAgent` satırı zaten mevcut — burada tekrar yazılması yanlışlıkla ikinci kez eklenmesin diye, sadece YENİ 4 satırı (`getSettings`'ten itibaren) mevcut `restartAgent` satırının hemen altına ekle, `restartAgent`'ı olduğu gibi bırak.)

- [ ] **Step 3: Elle doğrula**

Bu görevde otomatik test yok (mevcut `main.js`/`preload.js` deseniyle aynı — Electron yaşam döngüsü/IPC kodu bu projede hiç otomatik test edilmiyor). Elle doğrulama (gerçek `agent/.env` dosyası olan, gerçek `node_modules`/`venv` kurulu ana repoda yapılmalı, worktree'de mümkün değil):

1. `cd shell && npm start`.
2. `agent/.env` dosyasının içeriğini not al (yedek amaçlı).
3. Uygulama açılınca DEBUG panelini aç (henüz SETTINGS sekmesi yok, Task 3'te eklenecek) — sadece IPC handler'ların hata vermediğini görmek için, Electron DevTools konsolunda (varsa) `window.jarvisShell.getSettings()` çağırıp gerçek `.env` değerlerinin döndüğünü doğrula.

- [ ] **Step 4: Commit**

```bash
git add shell/main.js shell/preload.js
git commit -m "feat(shell): ayarlar için IPC handler'ları ve preload köprülerini ekle"
```

---

### Task 3: SETTINGS sekmesi UI

**Files:**
- Modify: `shell/renderer/index.html`
- Modify: `shell/renderer/styles.css`
- Modify: `shell/renderer/renderer.js`

**Interfaces:**
- Consumes: `window.jarvisShell.getSettings/saveSettings/getLaunchOnStartup/setLaunchOnStartup` (Task 2).

- [ ] **Step 1: `shell/renderer/index.html`'i güncelle**

Mevcut `#debug-panel` bloğunun TAMAMINI (mevcut `<div id="debug-panel" class="debug-panel hidden">` açılışından `</div>` kapanışına kadar) şununla DEĞİŞTİR:

```html
<div id="debug-panel" class="debug-panel hidden">
  <div class="debug-panel-header">
    <div class="debug-tabs">
      <button id="tab-debug" type="button" class="debug-tab active">DEBUG</button>
      <button id="tab-settings" type="button" class="debug-tab">SETTINGS</button>
    </div>
    <button id="debug-restart" type="button">YENİDEN BAŞLAT</button>
    <button id="debug-close" type="button">✕</button>
  </div>
  <div id="debug-body" class="debug-body">
    <div id="debug-log" class="debug-log"></div>
  </div>
  <div id="settings-body" class="settings-body hidden">
    <label class="settings-field">
      <span>SES</span>
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
    </label>
    <label class="settings-field">
      <span>MODEL</span>
      <input id="settings-model" type="text" autocomplete="off" />
    </label>
    <label class="settings-field">
      <span>HAVA DURUMU KONUMU</span>
      <input id="settings-weather-location" type="text" autocomplete="off" />
    </label>
    <label class="settings-field">
      <span>RAPOR PROJELERİ</span>
      <input id="settings-report-projects" type="text" autocomplete="off" />
    </label>
    <label class="settings-checkbox-row">
      <input id="settings-launch-on-startup" type="checkbox" />
      <span>Windows başlangıcında otomatik aç</span>
    </label>
    <button id="settings-save" type="button" class="settings-save-btn">KAYDET VE YENİDEN BAŞLAT</button>
  </div>
</div>
```

- [ ] **Step 2: `shell/renderer/styles.css`'e ekle**

Dosyanın sonuna ekle:

```css
.debug-body.hidden,
.settings-body.hidden {
  display: none;
}

.debug-panel-header .debug-tabs {
  display: flex;
  gap: 6px;
}

.debug-panel-header .debug-tab {
  background: transparent;
  border: 1px solid #0c2a28;
  color: var(--mid);
  font-size: 10px;
  padding: 3px 10px;
  cursor: pointer;
  letter-spacing: 0.05em;
}

.debug-panel-header .debug-tab.active {
  color: var(--pri);
  border-color: var(--pri);
}

.settings-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.settings-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--mid);
}

.settings-field input,
.settings-field select {
  background: #041111;
  border: 1px solid #0c2a28;
  color: var(--text);
  padding: 4px 6px;
  font-size: 12px;
}

.settings-checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--mid);
}

.settings-save-btn {
  background: transparent;
  border: 1px solid var(--pri);
  color: var(--pri);
  padding: 6px 10px;
  cursor: pointer;
  font-size: 11px;
  letter-spacing: 0.05em;
}
```

(Not: seçiciler `.debug-panel-header .debug-tab` şeklinde, sadece `.debug-tab` değil — çünkü dosyada zaten var olan `.debug-panel-header button { ... }` kuralı `.debug-tab`'dan daha yüksek özgüllüğe sahip (element+class > tek class) ve onu ezerdi.)

- [ ] **Step 3: `shell/renderer/renderer.js`'i güncelle**

DEBUG paneli bölümünün TAMAMINI (yorum satırından mevcut `window.jarvisShell.onAgentLog(...)` bloğunun sonuna kadar) şununla DEĞİŞTİR:

```js
// ── DEBUG paneli — Python agent çıktısı + Ayarlar ──────────────────────────
const debugToggle = document.getElementById('debug-toggle');
const debugPanel = document.getElementById('debug-panel');
const debugLog = document.getElementById('debug-log');
const debugRestart = document.getElementById('debug-restart');
const debugClose = document.getElementById('debug-close');
const tabDebug = document.getElementById('tab-debug');
const tabSettings = document.getElementById('tab-settings');
const debugBody = document.getElementById('debug-body');
const settingsBody = document.getElementById('settings-body');
const settingsVoice = document.getElementById('settings-voice');
const settingsModel = document.getElementById('settings-model');
const settingsWeatherLocation = document.getElementById('settings-weather-location');
const settingsReportProjects = document.getElementById('settings-report-projects');
const settingsLaunchOnStartup = document.getElementById('settings-launch-on-startup');
const settingsSave = document.getElementById('settings-save');
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

function setActiveTab(tab) {
  const isDebug = tab === 'debug';
  tabDebug.classList.toggle('active', isDebug);
  tabSettings.classList.toggle('active', !isDebug);
  debugBody.classList.toggle('hidden', !isDebug);
  settingsBody.classList.toggle('hidden', isDebug);
  debugRestart.classList.toggle('hidden', !isDebug);
  if (!isDebug) loadSettingsForm();
}

async function loadSettingsForm() {
  const [settings, launchOnStartup] = await Promise.all([
    window.jarvisShell.getSettings(),
    window.jarvisShell.getLaunchOnStartup(),
  ]);
  settingsVoice.value = settings.JARVIS_GEMINI_VOICE || '';
  settingsModel.value = settings.JARVIS_GEMINI_MODEL || '';
  settingsWeatherLocation.value = settings.JARVIS_WEATHER_LOCATION || '';
  settingsReportProjects.value = settings.JARVIS_REPORT_PROJECTS || '';
  settingsLaunchOnStartup.checked = Boolean(launchOnStartup);
}

async function openDebugPanel() {
  if (debugPanelOpening) return;
  debugPanelOpening = true;
  setActiveTab('debug');
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

tabDebug.addEventListener('click', () => setActiveTab('debug'));
tabSettings.addEventListener('click', () => setActiveTab('settings'));

settingsLaunchOnStartup.addEventListener('change', () => {
  window.jarvisShell.setLaunchOnStartup(settingsLaunchOnStartup.checked);
});

settingsSave.addEventListener('click', () => {
  window.jarvisShell.saveSettings({
    JARVIS_GEMINI_VOICE: settingsVoice.value,
    JARVIS_GEMINI_MODEL: settingsModel.value,
    JARVIS_WEATHER_LOCATION: settingsWeatherLocation.value,
    JARVIS_REPORT_PROJECTS: settingsReportProjects.value,
  });
});

window.jarvisShell.onAgentLog((entry) => {
  if (!debugPanel.classList.contains('hidden')) appendDebugLine(entry);
});
```

- [ ] **Step 4: Elle doğrula**

Bu görevde otomatik test yok (DOM kodu, mevcut renderer.js deseniyle aynı). Elle doğrulama (gerçek `agent/.env` olan ana repoda):

1. `agent/.env`'in içeriğini yedekle (kopyala).
2. `cd shell && npm start`.
3. DEBUG panelini aç — DEBUG sekmesi varsayılan olarak aktif olmalı, log akışı normal çalışmalı.
4. SETTINGS sekmesine geç — mevcut `.env` değerlerinin (ses, model, hava durumu konumu, rapor projeleri) forma doğru yüklendiğini doğrula.
5. Sesi değiştir, "KAYDET VE YENİDEN BAŞLAT"a bas — birkaç saniye içinde DEBUG sekmesine dönüp `[AGENT RESTARTING]`/`[AGENT RUNNING]` satırlarının göründüğünü, ve `agent/.env`'de `JARVIS_GEMINI_VOICE` satırının güncellendiğini doğrula.
6. "Windows başlangıcında otomatik aç" kutusunu işaretle — Windows Ayarlar > Uygulamalar > Başlangıç'ta Jarvis'in göründüğünü doğrula (veya `app.getLoginItemSettings()` ile tekrar oku).
7. `.env`'i yedekten geri yükle (test verisiyle kalıcı olarak değiştirmemek için).

- [ ] **Step 5: Commit**

```bash
git add shell/renderer/index.html shell/renderer/styles.css shell/renderer/renderer.js
git commit -m "feat(shell): DEBUG paneline SETTINGS sekmesi ekle"
```
