# Jarvis Gerçek Installer Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Task 8 İSTİSNA'dır** — GitHub'da gerçek, public bir repo oluşturup kod push'luyor ve bir Release yayınlıyor; bu görevi otomatik bir subagent'a dispatch ETME, kullanıcıyla birlikte, her adımda onay alarak yürüt.

**Goal:** Jarvis'i (`shell/` Electron kabuğu + `agent/` Python arka planı) başka bilgisayarlara çift-tıkla kurulabilen tek bir Windows installer (`.exe`) olarak paketlemek ve bunu bir GitHub Release'e yüklemek.

**Architecture:** Python agent `agent_entry.py` üzerinden PyInstaller ile `agent.exe`'ye donduruluyor; Electron kabuğu `electron-builder` + NSIS ile paketleniyor ve donmuş `agent.exe`'yi `extraResources` ile içine gömüyor. `shell/main.js`, `app.isPackaged`'a göre dev'de venv Python'ı `-m agent.main` ile, paketli modda gömülü `agent.exe`'yi doğrudan spawn ediyor. `.env`, dev'de `agent/.env`'de kalıyor; paketli modda `app.getPath('userData')` altına taşınıyor ve `JARVIS_ENV_PATH` ortam değişkeniyle agent'a geçiliyor. `GEMINI_API_KEY`, SETTINGS sekmesinin yönettiği alanlara ekleniyor; boşsa uygulama açılışında SETTINGS sekmesine kilitleniyor.

**Tech Stack:** PyInstaller (Python dondurma), electron-builder + NSIS (Windows installer), GitHub Releases (dağıtım).

## Global Constraints

- Yönetilen `.env` anahtarları: mevcut 4 anahtara (`JARVIS_GEMINI_VOICE`, `JARVIS_GEMINI_MODEL`, `JARVIS_WEATHER_LOCATION`, `JARVIS_REPORT_PROJECTS`) `GEMINI_API_KEY` ekleniyor (toplam 5).
- JS testleri kök dizinden: `node --test shell/<dosya>.test.js`.
- Python testleri kök dizinden: `./agent/venv/Scripts/python.exe -m pytest agent/tests/<dosya>.py -v`.
- `shell/agent-process.js`'e bu planda TEK bir ek yapılıyor: constructor'a opsiyonel `args`/`env` parametreleri (varsayılanları mevcut hardcoded davranışı birebir koruyor, spawn/restart/backoff mantığının geri kalanı değişmiyor).
- Auto-update (`electron-updater`), Odakla'daki ayrı markalı `installer-shell` katmanı ve kod imzalama sertifikası bu planın KAPSAMI DIŞINDA.
- GitHub hedefi: yeni public repo `mhmmtmst/jarvis`.

---

### Task 1: `agent/config.py` — `JARVIS_ENV_PATH` ortam değişkenini onurlandırma

**Files:**
- Modify: `agent/config.py`
- Test: `agent/tests/test_config.py`

**Interfaces:**
- Produces: `load_config()` (imzası aynı) artık `env=None` çağrıldığında, `JARVIS_ENV_PATH` ortam değişkeni set edilmişse `.env`'i o yoldan okuyor.

- [ ] **Step 1: Failing test ekle**

`agent/tests/test_config.py`'nin sonuna ekle:

```python
def test_load_config_reads_env_file_from_jarvis_env_path(tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "GEMINI_API_KEY=from-custom-path\nJARVIS_GEMINI_VOICE=Zephyr\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_GEMINI_VOICE", raising=False)
    monkeypatch.setenv("JARVIS_ENV_PATH", str(env_file))

    config = load_config()

    assert config.gemini_api_key == "from-custom-path"
    assert config.gemini_voice == "Zephyr"
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_config.py -v`
Expected: `test_load_config_reads_env_file_from_jarvis_env_path` FAIL (gerçek `.env`'den veya boş değerden okuyup `from-custom-path`/`Zephyr` bulamıyor)

- [ ] **Step 3: `agent/config.py`'yi güncelle**

`load_config` fonksiyonundaki şu satırı:

```python
    if env is None:
        load_dotenv()
        env = os.environ
```

şununla değiştir:

```python
    if env is None:
        load_dotenv(os.environ.get("JARVIS_ENV_PATH") or None)
        env = os.environ
```

- [ ] **Step 4: Testi çalıştır, tüm dosyanın geçtiğini doğrula**

Run: `./agent/venv/Scripts/python.exe -m pytest agent/tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/config.py agent/tests/test_config.py
git commit -m "feat(agent): JARVIS_ENV_PATH ortam değişkeni set edilmişse .env'i o yoldan oku"
```

---

### Task 2: `shell/agent-process.js` — özelleştirilebilir spawn `args`/`env`

**Files:**
- Modify: `shell/agent-process.js`
- Test: `shell/agent-process.test.js`

**Interfaces:**
- Produces: `AgentProcessManager` constructor'ı artık opsiyonel `args` (varsayılan `['-m', 'agent.main']`) ve `env` (varsayılan `{}`) parametreleri kabul ediyor; `env` spawn'a geçilen ortam değişkenlerinin üzerine merge ediliyor.

- [ ] **Step 1: Failing testleri ekle**

`shell/agent-process.test.js`'e, mevcut `test('start() spawns python with -m agent.main from the given cwd, hidden window', ...)` testinin hemen altına ekle:

```js
test('start() uses custom args when provided, instead of the default -m agent.main', () => {
  const calls = [];
  const fakeChild = makeFakeChild();
  const spawnFn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    return fakeChild;
  };
  const manager = new AgentProcessManager({
    pythonPath: 'C:/agent.exe', cwd: 'C:/jarvis', args: [], spawnFn,
  });

  manager.start();

  assert.deepEqual(calls[0].args, []);
});

test('start() merges the custom env option on top of the PYTHONUNBUFFERED/PYTHONIOENCODING defaults', () => {
  const calls = [];
  const fakeChild = makeFakeChild();
  const spawnFn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    return fakeChild;
  };
  const manager = new AgentProcessManager({
    pythonPath: 'C:/py.exe', cwd: 'C:/jarvis', spawnFn,
    env: { JARVIS_ENV_PATH: 'C:/Users/x/AppData/Roaming/Jarvis/.env' },
  });

  manager.start();

  assert.equal(calls[0].opts.env.JARVIS_ENV_PATH, 'C:/Users/x/AppData/Roaming/Jarvis/.env');
  assert.equal(calls[0].opts.env.PYTHONUNBUFFERED, '1');
  assert.equal(calls[0].opts.env.PYTHONIOENCODING, 'utf-8');
});
```

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını doğrula**

Run: `node --test shell/agent-process.test.js`
Expected: Yeni 2 test FAIL (`args`/`env` seçenekleri henüz yok — ilk test `['-m', 'agent.main']` alır, ikinci test `JARVIS_ENV_PATH` `undefined` bulur)

- [ ] **Step 3: `shell/agent-process.js`'i güncelle**

Constructor satırını:

```js
  constructor({ pythonPath, cwd, spawnFn = spawn, setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout, nowFn = Date.now }) {
    super();
    this.pythonPath = pythonPath;
    this.cwd = cwd;
    this.spawnFn = spawnFn;
```

şununla değiştir:

```js
  constructor({ pythonPath, cwd, args = ['-m', 'agent.main'], env = {}, spawnFn = spawn, setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout, nowFn = Date.now }) {
    super();
    this.pythonPath = pythonPath;
    this.cwd = cwd;
    this.args = args;
    this.env = env;
    this.spawnFn = spawnFn;
```

`start()` içindeki spawn çağrısını:

```js
    const child = this.spawnFn(this.pythonPath, ['-m', 'agent.main'], {
      cwd: this.cwd,
      windowsHide: true,
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
    });
```

şununla değiştir:

```js
    const child = this.spawnFn(this.pythonPath, this.args, {
      cwd: this.cwd,
      windowsHide: true,
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', ...this.env },
    });
```

- [ ] **Step 4: Tüm dosyanın testlerini çalıştır, geçtiğini doğrula**

Run: `node --test shell/agent-process.test.js`
Expected: PASS, tüm testler (eskiler dahil) yeşil

- [ ] **Step 5: Commit**

```bash
git add shell/agent-process.js shell/agent-process.test.js
git commit -m "feat(shell): AgentProcessManager'a özelleştirilebilir spawn args/env ekle"
```

---

### Task 3: `shell/settings.js` — `GEMINI_API_KEY` + `resolveEnvPath`

**Files:**
- Modify: `shell/settings.js`
- Test: `shell/settings.test.js`

**Interfaces:**
- Produces: `MANAGED_KEYS` artık `'GEMINI_API_KEY'` içeriyor; yeni `resolveEnvPath({ isPackaged, userDataPath, projectRoot }): string` — `isPackaged` false ise `path.join(projectRoot, 'agent', '.env')`, true ise `path.join(userDataPath, '.env')` döndürüyor.

- [ ] **Step 1: Failing testleri ekle**

`shell/settings.test.js`'in sonuna ekle:

```js
const { resolveEnvPath, MANAGED_KEYS } = require('./settings');

test('MANAGED_KEYS includes GEMINI_API_KEY', () => {
  assert.ok(MANAGED_KEYS.includes('GEMINI_API_KEY'));
});

test('readSettings picks up GEMINI_API_KEY from the .env text via parseEnvFile/updateEnvFile round trip', () => {
  const text = 'GEMINI_API_KEY=secret-abc\nJARVIS_GEMINI_VOICE=Kore';
  assert.deepEqual(parseEnvFile(text), {
    GEMINI_API_KEY: 'secret-abc',
    JARVIS_GEMINI_VOICE: 'Kore',
  });
});

test('resolveEnvPath returns the dev path (projectRoot/agent/.env) when not packaged', () => {
  const result = resolveEnvPath({
    isPackaged: false,
    userDataPath: 'C:/Users/x/AppData/Roaming/Jarvis',
    projectRoot: 'C:/jarvis',
  });
  assert.equal(result, require('path').join('C:/jarvis', 'agent', '.env'));
});

test('resolveEnvPath returns the userData path (userDataPath/.env) when packaged', () => {
  const result = resolveEnvPath({
    isPackaged: true,
    userDataPath: 'C:/Users/x/AppData/Roaming/Jarvis',
    projectRoot: 'C:/jarvis',
  });
  assert.equal(result, require('path').join('C:/Users/x/AppData/Roaming/Jarvis', '.env'));
});
```

(Not: dosyanın en üstündeki `const { parseEnvFile, updateEnvFile } = require('./settings');` satırı zaten mevcut — yukarıdaki yeni `require` satırı ayrı, `resolveEnvPath`/`MANAGED_KEYS`'i içe aktarmak için.)

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını doğrula**

Run: `node --test shell/settings.test.js`
Expected: `MANAGED_KEYS includes GEMINI_API_KEY` ve iki `resolveEnvPath` testi FAIL (`resolveEnvPath is not a function` / `MANAGED_KEYS` içinde `GEMINI_API_KEY` yok)

- [ ] **Step 3: `shell/settings.js`'i güncelle**

`MANAGED_KEYS` tanımını:

```js
const MANAGED_KEYS = [
  'JARVIS_GEMINI_VOICE',
  'JARVIS_GEMINI_MODEL',
  'JARVIS_WEATHER_LOCATION',
  'JARVIS_REPORT_PROJECTS',
];
```

şununla değiştir:

```js
const MANAGED_KEYS = [
  'GEMINI_API_KEY',
  'JARVIS_GEMINI_VOICE',
  'JARVIS_GEMINI_MODEL',
  'JARVIS_WEATHER_LOCATION',
  'JARVIS_REPORT_PROJECTS',
];
```

Dosyanın en üstüne, `const fs = require('fs');` satırının altına ekle:

```js
const path = require('path');
```

`module.exports` satırının hemen üstüne ekle:

```js
function resolveEnvPath({ isPackaged, userDataPath, projectRoot }) {
  return isPackaged
    ? path.join(userDataPath, '.env')
    : path.join(projectRoot, 'agent', '.env');
}
```

`module.exports` satırını:

```js
module.exports = { MANAGED_KEYS, parseEnvFile, updateEnvFile, readSettings, writeSettings };
```

şununla değiştir:

```js
module.exports = { MANAGED_KEYS, parseEnvFile, updateEnvFile, readSettings, writeSettings, resolveEnvPath };
```

- [ ] **Step 4: Tüm dosyanın testlerini çalıştır, geçtiğini doğrula**

Run: `node --test shell/settings.test.js`
Expected: PASS, tüm testler (eskiler dahil) yeşil

- [ ] **Step 5: Commit**

```bash
git add shell/settings.js shell/settings.test.js
git commit -m "feat(shell): GEMINI_API_KEY'i MANAGED_KEYS'e ekle, dev/prod .env yolu için resolveEnvPath ekle"
```

---

### Task 4: `shell/main.js` — dev/prod spawn ve `.env` yolu ayrımı

**Files:**
- Modify: `shell/main.js`

**Interfaces:**
- Consumes: `resolveEnvPath` (Task 3), `AgentProcessManager`'ın `args`/`env` seçenekleri (Task 2).

**Bu görevde otomatik test yok** (mevcut `main.js` deseniyle aynı — Electron yaşam döngüsü/spawn kod bu projede hiç otomatik test edilmiyor, sadece `agent-process.js`'in kendisi test ediliyor). Elle doğrulama adımı aşağıda.

- [ ] **Step 1: `shell/main.js`'i güncelle**

Dosyanın en üstündeki import bloğunu:

```js
const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const { AgentProcessManager } = require('./agent-process');
const { readSettings, writeSettings } = require('./settings');

let mainWindow = null;

const agentManager = new AgentProcessManager({
  pythonPath: path.join(__dirname, '..', 'agent', 'venv', 'Scripts', 'python.exe'),
  cwd: path.join(__dirname, '..'),
});

const ENV_PATH = path.join(agentManager.cwd, 'agent', '.env');
```

şununla değiştir:

```js
const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const fs = require('fs');
const { AgentProcessManager } = require('./agent-process');
const { readSettings, writeSettings, resolveEnvPath } = require('./settings');

let mainWindow = null;

const PROJECT_ROOT = path.join(__dirname, '..');

const ENV_PATH = resolveEnvPath({
  isPackaged: app.isPackaged,
  userDataPath: app.getPath('userData'),
  projectRoot: PROJECT_ROOT,
});

if (app.isPackaged && !fs.existsSync(ENV_PATH)) {
  fs.mkdirSync(path.dirname(ENV_PATH), { recursive: true });
  fs.copyFileSync(path.join(process.resourcesPath, 'agent', '.env.example'), ENV_PATH);
}

const agentManager = new AgentProcessManager({
  pythonPath: app.isPackaged
    ? path.join(process.resourcesPath, 'agent', 'agent.exe')
    : path.join(PROJECT_ROOT, 'agent', 'venv', 'Scripts', 'python.exe'),
  args: app.isPackaged ? [] : ['-m', 'agent.main'],
  cwd: app.isPackaged ? path.join(process.resourcesPath, 'agent') : PROJECT_ROOT,
  env: { JARVIS_ENV_PATH: ENV_PATH },
});
```

- [ ] **Step 2: Syntax kontrolü**

Run: `node -c shell/main.js`
Expected: hata yok (çıktı boş)

- [ ] **Step 3: Elle doğrula (dev modda regresyon yok)**

1. `agent/.env`'in içeriğini not al (yedek amaçlı).
2. `cd shell && npm start`.
3. Uygulama açılınca DEBUG panelini aç, agent'ın normal başladığını (`[AGENT RUNNING]`) doğrula — bu, `app.isPackaged === false` dalının eskisiyle birebir aynı `pythonPath`/`cwd`/`args` ürettiğini kanıtlar.
4. SETTINGS sekmesine geçip "KAYDET VE YENİDEN BAŞLAT"a bas, agent'ın yeniden başladığını doğrula.

- [ ] **Step 4: Commit**

```bash
git add shell/main.js
git commit -m "feat(shell): main.js'de paketli/dev modda agent spawn ve .env yolu ayrımı"
```

---

### Task 5: SETTINGS sekmesi — `GEMINI_API_KEY` alanı + ilk kurulum kilidi

**Files:**
- Modify: `shell/renderer/index.html`
- Modify: `shell/renderer/styles.css`
- Modify: `shell/renderer/renderer.js`

**Interfaces:**
- Consumes: `window.jarvisShell.getSettings()`/`saveSettings()` (`GEMINI_API_KEY` artık bu objenin bir alanı, Task 3 sayesinde otomatik).

**Bu görevde otomatik test yok** (DOM kodu, mevcut renderer.js deseniyle aynı). Elle doğrulama adımı aşağıda.

- [ ] **Step 1: `shell/renderer/index.html`'i güncelle**

`<div id="settings-body" class="settings-body hidden">` açılışının hemen altına, `SES` alanından ÖNCE ekle:

```html
      <label class="settings-field">
        <span>GEMINI API ANAHTARI</span>
        <input id="settings-gemini-key" type="password" autocomplete="off" />
      </label>
```

`</div>` kapanışından (settings-body'nin kapanışından) hemen ÖNCE, `KAYDET VE YENİDEN BAŞLAT` butonundan ÖNCE ekle:

```html
      <div id="settings-firstrun-note" class="settings-firstrun-note hidden">
        İlk kurulum: Gemini API anahtarınızı girip kaydedin. Ücretsiz anahtar için aistudio.google.com → Get API Key.
      </div>
```

- [ ] **Step 2: `shell/renderer/styles.css`'e ekle**

Dosyanın sonuna ekle:

```css
.settings-firstrun-note {
  font-size: 11px;
  color: var(--gold);
  line-height: 1.5;
}

.settings-firstrun-note.hidden {
  display: none;
}

.debug-tabs .debug-tab.hidden {
  display: none;
}
```

- [ ] **Step 3: `shell/renderer/renderer.js`'i güncelle**

`const settingsSave = document.getElementById('settings-save');` satırının altına ekle:

```js
const settingsGeminiKey = document.getElementById('settings-gemini-key');
const settingsFirstrunNote = document.getElementById('settings-firstrun-note');
let firstRunLocked = false;
```

`loadSettingsForm` fonksiyonunu:

```js
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
```

şununla değiştir:

```js
async function loadSettingsForm() {
  const [settings, launchOnStartup] = await Promise.all([
    window.jarvisShell.getSettings(),
    window.jarvisShell.getLaunchOnStartup(),
  ]);
  settingsGeminiKey.value = settings.GEMINI_API_KEY || '';
  settingsVoice.value = settings.JARVIS_GEMINI_VOICE || '';
  settingsModel.value = settings.JARVIS_GEMINI_MODEL || '';
  settingsWeatherLocation.value = settings.JARVIS_WEATHER_LOCATION || '';
  settingsReportProjects.value = settings.JARVIS_REPORT_PROJECTS || '';
  settingsLaunchOnStartup.checked = Boolean(launchOnStartup);
}

async function checkFirstRunLock() {
  const settings = await window.jarvisShell.getSettings();
  if (settings.GEMINI_API_KEY) return;
  firstRunLocked = true;
  settingsFirstrunNote.classList.remove('hidden');
  tabDebug.classList.add('hidden');
  debugClose.classList.add('hidden');
  debugRestart.classList.add('hidden');
  setActiveTab('settings');
  debugPanel.classList.remove('hidden');
}

function exitFirstRunLock() {
  firstRunLocked = false;
  settingsFirstrunNote.classList.add('hidden');
  tabDebug.classList.remove('hidden');
  debugClose.classList.remove('hidden');
}
```

`debugClose.addEventListener('click', ...)` bloğunu:

```js
debugClose.addEventListener('click', () => {
  debugPanel.classList.add('hidden');
});
```

şununla değiştir:

```js
debugClose.addEventListener('click', () => {
  if (firstRunLocked) return;
  debugPanel.classList.add('hidden');
});
```

`tabDebug.addEventListener('click', () => setActiveTab('debug'));` satırını:

```js
tabDebug.addEventListener('click', () => setActiveTab('debug'));
```

şununla değiştir:

```js
tabDebug.addEventListener('click', () => {
  if (firstRunLocked) return;
  setActiveTab('debug');
});
```

`settingsSave.addEventListener('click', ...)` bloğunu:

```js
settingsSave.addEventListener('click', () => {
  window.jarvisShell.saveSettings({
    JARVIS_GEMINI_VOICE: settingsVoice.value,
    JARVIS_GEMINI_MODEL: settingsModel.value,
    JARVIS_WEATHER_LOCATION: settingsWeatherLocation.value,
    JARVIS_REPORT_PROJECTS: settingsReportProjects.value,
  });
});
```

şununla değiştir:

```js
settingsSave.addEventListener('click', () => {
  window.jarvisShell.saveSettings({
    GEMINI_API_KEY: settingsGeminiKey.value,
    JARVIS_GEMINI_VOICE: settingsVoice.value,
    JARVIS_GEMINI_MODEL: settingsModel.value,
    JARVIS_WEATHER_LOCATION: settingsWeatherLocation.value,
    JARVIS_REPORT_PROJECTS: settingsReportProjects.value,
  });
  if (firstRunLocked && settingsGeminiKey.value.trim()) {
    exitFirstRunLock();
  }
});
```

Dosyanın en sonuna (`window.jarvisShell.onAgentLog(...)` bloğunun altına) ekle:

```js

checkFirstRunLock();
```

`debugToggle.addEventListener('click', ...)` bloğunu:

```js
debugToggle.addEventListener('click', () => {
  if (debugPanel.classList.contains('hidden')) {
    openDebugPanel();
  } else {
    debugPanel.classList.add('hidden');
  }
});
```

şununla değiştir:

```js
debugToggle.addEventListener('click', () => {
  if (firstRunLocked) return;
  if (debugPanel.classList.contains('hidden')) {
    openDebugPanel();
  } else {
    debugPanel.classList.add('hidden');
  }
});
```

- [ ] **Step 4: Syntax kontrolü**

Run: `node -c shell/renderer/renderer.js`
Expected: hata yok (çıktı boş)

- [ ] **Step 5: Elle doğrula**

1. `agent/.env`'i yedekle (kopyala), sonra içindeki `GEMINI_API_KEY=...` satırını sil veya değerini boşalt.
2. `cd shell && npm start`.
3. Uygulama açılır açılmaz DEBUG panelinin otomatik SETTINGS sekmesinde ve kapatılamaz şekilde açıldığını doğrula (✕ ve DEBUG sekmesi görünmüyor/tıklanamıyor, sarı bir "İlk kurulum" notu görünüyor).
4. Gemini API anahtarını gir, "KAYDET VE YENİDEN BAŞLAT"a bas — panelin kilidinin açıldığını (✕ ve DEBUG sekmesi geri geldi), agent'ın yeniden başladığını doğrula.
5. Uygulamayı kapatıp tekrar aç — bu sefer kilidin OLMADIĞINI (anahtar zaten `.env`'de olduğu için) doğrula.
6. `.env`'i yedekten geri yükle.

- [ ] **Step 6: Commit**

```bash
git add shell/renderer/index.html shell/renderer/styles.css shell/renderer/renderer.js
git commit -m "feat(shell): SETTINGS'e GEMINI_API_KEY alanı ve ilk kurulum kilidi ekle"
```

---

### Task 6: Python agent'ı PyInstaller ile `agent.exe`'ye dondurma

**Files:**
- Create: `agent_entry.py` (repo kökü)
- Modify: `.gitignore`

**Interfaces:**
- Produces: `agent-dist/agent/agent.exe` (+ yanındaki destek dosyaları) — Task 7'nin `extraResources`'ının kaynağı.

**Bu görevde otomatik test yok** (build/paketleme adımı). Elle doğrulama adımı aşağıda; bu görevin ana riski native bağımlılıklardır (spec'te belirtildi), doğrulama adımları bunu erken yakalamak için var.

- [ ] **Step 1: `agent_entry.py`'yi oluştur**

Repo kökünde (`agent/` klasörüyle aynı seviyede), tam içerik:

```python
from agent.main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: PyInstaller'ı venv'e kur**

Run: `./agent/venv/Scripts/python.exe -m pip install pyinstaller`
Expected: kurulum başarıyla biter (`Successfully installed pyinstaller-...`)

- [ ] **Step 3: `.gitignore`'a ekle**

`.gitignore`'ın `# Python` bölümüne ekle:

```
agent-dist/
build/pyinstaller/
*.spec
```

- [ ] **Step 4: PyInstaller build'i çalıştır**

Repo kökünden run:

```bash
./agent/venv/Scripts/pyinstaller.exe --name agent --onedir --distpath agent-dist --workpath build/pyinstaller --specpath build --paths . --collect-all speech_recognition --noconfirm agent_entry.py
```

Expected: `agent-dist/agent/agent.exe` dosyası oluşur, build sırasında `ModuleNotFoundError`/`ImportError` gibi bir hata çıkmaz.

**Not (plan yazıldıktan sonra doğrulandı):** `openwakeword`, `requirements.txt`'de listeli ama gerçek `agent/venv`'de KURULU DEĞİL — `agent/wake_word.py`'deki `OpenWakeWordDetector` sınıfı şu an aktif kullanılmayan, kasıtlı olarak silinmemiş ölü kod (yorumda açıkça belirtiliyor: "Şu an aktif kullanılmıyor"), import da o sınıfın `__init__`'i içinde, hiç çağrılmıyor. Bu yüzden `--collect-all openwakeword` KOMUTA EKLENMİYOR (kurulu olmayan bir paket için PyInstaller hata verir) — sadece `speech_recognition` (gerçekten kurulu ve kullanılıyor) collect-all ediliyor.

- [ ] **Step 5: Donmuş exe'yi çalıştırıp doğrula**

Run (repo kökünden, gerçek `.env`'i işaret ederek):

```bash
JARVIS_ENV_PATH="$(pwd)/agent/.env" ./agent-dist/agent/agent.exe
```

Expected: konsolda `Jarvis agent başlatılıyor...` log satırı görünür, süreç çökmeden birkaç saniye ayakta kalır. Ayrı bir terminalde `netstat -ano | findstr 8765` ile 8765 portunun `LISTENING` durumda olduğunu doğrula. `Ctrl+C` ile durdur.

Eğer `ModuleNotFoundError: No module named 'X'` gibi bir hata ile çökerse: Step 4'teki komuta `--collect-all X` ekleyip Step 4-5'i tekrar et (örn. `--collect-all pyaudio`, `--collect-all google.genai`).

- [ ] **Step 6: Commit**

```bash
git add agent_entry.py .gitignore
git commit -m "build(agent): PyInstaller ile agent.exe donduran build girdi noktasını ekle"
```

---

### Task 7: `shell/` — electron-builder ile NSIS installer'a paketleme

**Files:**
- Modify: `shell/package.json`

**Interfaces:**
- Consumes: `agent-dist/agent/` (Task 6 çıktısı), `agent/.env.example`.
- Produces: `shell/release/Jarvis-Setup.exe` (`npm run dist` çıktısı).

**Bu görevde otomatik test yok** (build/paketleme adımı). Elle doğrulama adımı aşağıda.

- [ ] **Step 1: `electron-builder`'ı kur**

Run: `cd shell && npm install --save-dev electron-builder`
Expected: kurulum başarıyla biter, `shell/package.json`'daki `devDependencies`'e `electron-builder` eklenir.

- [ ] **Step 2: `.gitignore`'a build çıktısını ekle**

`.gitignore`'ın `# Node / Electron` bölümüne ekle:

```
shell/release/
```

- [ ] **Step 3: `shell/package.json`'ı güncelle**

Mevcut içeriği:

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

şununla değiştir (electron-builder'ın Step 1'de eklediği sürüm numarasını koru):

```json
{
  "name": "jarvis-shell",
  "version": "0.1.0",
  "private": true,
  "main": "main.js",
  "scripts": {
    "start": "electron .",
    "dist": "electron-builder"
  },
  "devDependencies": {
    "electron": "^32.0.0",
    "electron-builder": "^24.13.3"
  },
  "build": {
    "appId": "app.jarvis.desktop",
    "productName": "Jarvis",
    "artifactName": "Jarvis-Setup.${ext}",
    "directories": {
      "output": "release"
    },
    "files": [
      "main.js",
      "preload.js",
      "agent-process.js",
      "settings.js",
      "renderer/**/*"
    ],
    "extraResources": [
      {
        "from": "../agent-dist/agent",
        "to": "agent"
      },
      {
        "from": "../agent/.env.example",
        "to": "agent/.env.example"
      }
    ],
    "publish": {
      "provider": "github",
      "owner": "mhmmtmst",
      "repo": "jarvis",
      "releaseType": "release"
    },
    "win": {
      "target": "nsis",
      "icon": "build/icon.ico"
    },
    "nsis": {
      "oneClick": false,
      "allowToChangeInstallationDirectory": true,
      "createDesktopShortcut": true,
      "createStartMenuShortcut": true,
      "shortcutName": "Jarvis",
      "artifactName": "Jarvis-Setup.${ext}"
    }
  }
}
```

(Not: `electron-builder`'ın Step 1'de kurduğu gerçek sürüm numarası `^24.13.3`'ten farklıysa, `npm install` tarafından yazılan değeri koru, elle değiştirme.)

- [ ] **Step 4: İkon dosyasını yerleştir**

Kullanıcının hazırladığı `.ico` dosyasını `shell/build/icon.ico` olarak yerleştir (bu dosya olmadan Step 5 `win.icon` alanı çözülemediği için hata verir — icon henüz hazır değilse bu adımı ve Step 5'i kullanıcıdan icon gelene kadar erteleyip diğer taskları bitirebilirsin, ama `npm run dist` bu dosya olmadan çalışmaz).

- [ ] **Step 5: Build'i çalıştır ve doğrula**

Run: `cd shell && npm run dist`
Expected: `shell/release/Jarvis-Setup.exe` oluşur, build loglarında hata yok.

- [ ] **Step 6: Installer'ı elle doğrula**

1. `shell/release/Jarvis-Setup.exe`'yi çalıştır (geliştirme makinesinde, gerçek kurulum yapacağını unutma — istersen bir VM'de veya `allowToChangeInstallationDirectory` sayesinde ayrı bir klasöre kur).
2. Kurulum sihirbazının açıldığını, masaüstü/start menu kısayolu oluşturduğunu doğrula.
3. Kurulan uygulamayı aç — Task 5'teki ilk-kurulum kilidinin (GEMINI_API_KEY boşsa) göründüğünü doğrula (kurulum sonrası `%APPDATA%\Jarvis\.env` henüz boş bir `.env.example` kopyası olduğu için).
4. Anahtarı girip kaydet, HUD'un açıldığını, agent'ın (`agent.exe`) çalıştığını (Görev Yöneticisi'nde `agent.exe` sürecini gör) doğrula.
5. Test kurulumunu Windows Ayarlar > Uygulamalar'dan kaldır (uninstall).

- [ ] **Step 7: Commit**

```bash
git add shell/package.json shell/package-lock.json
git commit -m "build(shell): electron-builder + NSIS installer paketleme yapılandırması ekle"
```

---

### Task 8: `.env.example` sanitizasyonu + GitHub repo + Release yayınlama

> ⚠️ Bu görev SDD ile otomatik dispatch EDİLMEZ. Gerçek, public bir GitHub reposu oluşturup kod push'luyor ve bir Release yayınlıyor — kullanıcıyla birlikte, her adımda onay alarak yürüt.

**Files:**
- Modify: `agent/.env.example`

- [ ] **Step 1: `agent/.env.example`'ı sanitize et**

Mevcut içeriği:

```
GEMINI_API_KEY=buraya-kendi-anahtarini-yaz
JARVIS_WS_HOST=127.0.0.1
JARVIS_WS_PORT=8765
JARVIS_GEMINI_MODEL=gemini-3.1-flash-live-preview
JARVIS_GEMINI_VOICE=Kore
JARVIS_WEATHER_LOCATION=Safranbolu, Karabük
JARVIS_REPORT_PROJECTS=Odakla:C:/Users/mhmmt/OneDrive/Masaüstü/Odakla,ChronoPlay:C:/Users/mhmmt/OneDrive/Masaüstü/chronoplay,Jarvis:C:/Users/mhmmt/OneDrive/Masaüstü/jarvis,DogumGunuSitesi:C:/Users/mhmmt/OneDrive/Masaüstü/projeler/doğum günü
```

şununla değiştir:

```
GEMINI_API_KEY=buraya-kendi-anahtarini-yaz
JARVIS_WS_HOST=127.0.0.1
JARVIS_WS_PORT=8765
JARVIS_GEMINI_MODEL=gemini-3.1-flash-live-preview
JARVIS_GEMINI_VOICE=Kore
JARVIS_WEATHER_LOCATION=Safranbolu, Karabük
JARVIS_REPORT_PROJECTS=Proje1:C:/path/to/proje1,Proje2:C:/path/to/proje2
```

Commit:

```bash
git add agent/.env.example
git commit -m "chore(agent): .env.example'daki gerçek yerel yolları genel placeholder ile değiştir (public repo hazırlığı)"
```

- [ ] **Step 2: GitHub'da yeni public repo oluştur**

Kullanıcı, github.com/new adresinden `mhmmtmst` hesabında `jarvis` adında YENİ, PUBLIC bir repo oluşturur (README/gitignore/license EKLEMEDEN — mevcut yerel repo push edilecek).

- [ ] **Step 3: Yerel repoyu push'la**

Kullanıcının onayıyla:

```bash
git remote add origin https://github.com/mhmmtmst/jarvis.git
git push -u origin master
```

- [ ] **Step 4: GitHub Personal Access Token oluştur**

Kullanıcı, github.com/settings/tokens adresinden `repo` yetkisine sahip bir Personal Access Token oluşturur (electron-builder'ın Release'e dosya yükleyebilmesi için gerekli). Bu token'ı kimseyle paylaşmaz, sadece kendi terminaline `GH_TOKEN` ortam değişkeni olarak girer:

```bash
export GH_TOKEN=kendi_tokenin
```

- [ ] **Step 5: Publish'li build'i çalıştır**

Kullanıcının onayıyla, `GH_TOKEN` set edilmiş terminalde:

```bash
cd shell && npm run dist -- --publish always
```

Expected: `shell/release/Jarvis-Setup.exe` derlenir VE `github.com/mhmmtmst/jarvis/releases` altında yeni bir Release (v0.1.0) oluşur, `.exe` asset olarak yüklenir.

- [ ] **Step 6: Release'i doğrula**

Kullanıcı, `github.com/mhmmtmst/jarvis/releases` sayfasını tarayıcıda açıp Release'in ve `.exe` asset linkinin göründüğünü doğrular. Bu link artık paylaşılabilir "İndir" linkidir.
