const socket = new WebSocket('ws://127.0.0.1:8765');

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
  // Tarayıcının kendi speechSynthesis fallback sesi de (varsa) hemen kesilmeli
  // — Edge-TTS parçaları için kesme artık gerçek çalma süresince çalıştığı
  // için (bkz. ws_server._synthesize_and_broadcast paced gönderim) bu yol da
  // artık gerçekten tetiklenebiliyor.
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}

const statusEl = document.getElementById('connection-status');
const liveBadge = document.getElementById('live-badge');
const wakeIndicator = document.getElementById('wake-indicator');
const clockTimeEl = document.getElementById('clock-time');
const clockDateEl = document.getElementById('clock-date');
const bars = {
  cpu: document.getElementById('bar-cpu'),
  ram: document.getElementById('bar-ram'),
  disk: document.getElementById('bar-disk'),
  battery: document.getElementById('bar-battery'),
};
const pcts = {
  cpu: document.getElementById('pct-cpu'),
  ram: document.getElementById('pct-ram'),
  disk: document.getElementById('pct-disk'),
  battery: document.getElementById('pct-battery'),
};
const hudCenter = document.getElementById('hud-center');
const agentStateEl = document.getElementById('agent-state');
const logEl = document.getElementById('conversation-log');
const form = document.getElementById('command-form');
const input = document.getElementById('command-input');
const pauseBtn = document.getElementById('btn-pause');
const shutdownBtn = document.getElementById('btn-shutdown');

const orbRenderer = new window.OrbRenderer(document.getElementById('orb-canvas'));

let paused = false;

// ── Dalga çubuklari (equalizer) — konusurken canli, aksi halde duz ────────
const waveBarsEl = document.getElementById('wave-bars');
const WAVE_BAR_COUNT = 18;
for (let i = 0; i < WAVE_BAR_COUNT; i++) {
  const bar = document.createElement('span');
  waveBarsEl.appendChild(bar);
}
const waveBars = Array.from(waveBarsEl.children);

function animateWaveBars() {
  const active = hudCenter.dataset.state === 'speaking' || hudCenter.dataset.state === 'listening';
  waveBarsEl.classList.toggle('active', active);
  waveBars.forEach((bar) => {
    const h = active ? (hudCenter.dataset.state === 'speaking' ? 4 + Math.random() * 26 : 2 + Math.random() * 10) : 3;
    bar.style.height = `${h}px`;
  });
}
setInterval(animateWaveBars, 110);

function setAgentState(state) {
  hudCenter.dataset.state = state;
  agentStateEl.textContent = window.jarvisStateLabels.describeAgentState(state);
  orbRenderer.setState(state);
}

function appendLog(kind, text) {
  const line = document.createElement('div');
  line.className = `log-line entry-${kind}`;

  const speaker = document.createElement('div');
  speaker.className = 'log-speaker';
  speaker.textContent = kind === 'user' ? 'sen' : kind === 'error' ? 'hata' : 'jarvis';

  const body = document.createElement('div');
  body.className = 'log-text';
  body.textContent = text;

  line.appendChild(speaker);
  line.appendChild(body);
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

function updateClock() {
  const now = new Date();
  clockTimeEl.textContent = now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  clockDateEl.textContent = now
    .toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric', weekday: 'long' });
}
setInterval(updateClock, 1000);
updateClock();

function setBarLevel(key, value) {
  const row = bars[key].closest('.bar-row');
  row.classList.remove('warn', 'crit');
  if (key === 'battery') {
    if (value < 20) row.classList.add('crit');
  } else if (value > 80) {
    row.classList.add('crit');
  } else if (value > 55) {
    row.classList.add('warn');
  }
}

const weatherBody = document.getElementById('weather-body');

function updateWeather(data) {
  if (!data || data.status !== 'ok') {
    weatherBody.innerHTML = '';
    weatherBody.className = 'weather-placeholder';
    weatherBody.textContent = 'Hava durumu bilgisi alınamadı';
    return;
  }
  weatherBody.className = '';
  weatherBody.innerHTML = `
    <div class="weather-temp">${Math.round(data.temp_c)}°C</div>
    <div class="weather-city">${data.city}</div>
    <div class="weather-condition">${data.condition}</div>
    <div class="weather-detail">Hissedilen ${Math.round(data.feels_like_c)}°C · Nem %${data.humidity}</div>
  `;
}

function updateSystemInfo(data) {
  bars.cpu.style.width = `${data.cpu_percent ?? 0}%`;
  bars.ram.style.width = `${data.ram_percent ?? 0}%`;
  bars.disk.style.width = `${data.disk_percent ?? 0}%`;
  bars.battery.style.width = `${data.battery_percent ?? 0}%`;

  pcts.cpu.textContent = `${Math.round(data.cpu_percent ?? 0)}%`;
  pcts.ram.textContent = `${Math.round(data.ram_percent ?? 0)}%`;
  pcts.disk.textContent = `${Math.round(data.disk_percent ?? 0)}%`;
  pcts.battery.textContent = data.battery_percent == null ? '--%' : `${Math.round(data.battery_percent)}%`;

  setBarLevel('cpu', data.cpu_percent ?? 0);
  setBarLevel('ram', data.ram_percent ?? 0);
  setBarLevel('disk', data.disk_percent ?? 0);
  setBarLevel('battery', data.battery_percent ?? 100);
}

// Wi-Fi tabanli tarayici konumu IP-tabanli tahminden cok daha hassas —
// wttr.in'in IP'den bulduğu şehir yanlış çıkabiliyor (küçük ilçeler için
// hep en yakın büyük şehre düşüyor). İzin verilmezse/başarısız olursa
// backend .env'deki JARVIS_WEATHER_LOCATION'a veya IP tahminine düşer.
function sendBrowserLocation() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(window.jarvisProtocol.buildLocation(pos.coords.latitude, pos.coords.longitude));
      }
    },
    () => {
      // konum alinamadi (izin reddedildi, Wi-Fi donanimi yok, servis kapali
      // vb.) — backend zaten .env/IP tahminine dusuyor, sessizce vazgec
    },
    { timeout: 10000, maximumAge: 3600000 },
  );
}

socket.addEventListener('open', () => {
  statusEl.textContent = 'bağlandı';
  statusEl.classList.add('online');
  statusEl.classList.remove('error');
  liveBadge.classList.remove('offline');
  sendBrowserLocation();
});
socket.addEventListener('close', () => {
  statusEl.textContent = 'bağlanıyor';
  statusEl.classList.remove('online');
  liveBadge.classList.add('offline');
});
socket.addEventListener('error', () => {
  statusEl.textContent = 'bağlantı hatası';
  statusEl.classList.remove('online');
  statusEl.classList.add('error');
  liveBadge.classList.add('offline');
});

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
  } else if (msg.type === 'weather_info') {
    updateWeather(msg.data);
  } else if (msg.type === 'tts_failed') {
    speakWithBrowserFallback(msg.text);
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
  pauseBtn.textContent = paused ? 'devam et' : 'duraklat';
  orbRenderer.setPaused(paused);
});

shutdownBtn.addEventListener('click', () => {
  window.jarvisShell.quit();
});

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

window.addEventListener('keydown', (event) => {
  if (
    event.key === PUSH_TO_TALK_KEY &&
    document.activeElement !== input &&
    recordingState === 'idle' &&
    !paused
  ) {
    event.preventDefault();
    startRecording();
  }
});

window.addEventListener('keyup', (event) => {
  if (event.key === PUSH_TO_TALK_KEY && recordingState !== 'idle') {
    event.preventDefault();
    stopRecording();
  }
});

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
const settingsMode = document.getElementById('settings-mode');
const settingsLaunchOnStartup = document.getElementById('settings-launch-on-startup');
const settingsSave = document.getElementById('settings-save');
const settingsGeminiKey = document.getElementById('settings-gemini-key');
const settingsFirstrunNote = document.getElementById('settings-firstrun-note');
const settingsVersionLabel = document.getElementById('settings-version-label');
const settingsUpdateStatus = document.getElementById('settings-update-status');
let firstRunLocked = false;
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
  settingsGeminiKey.value = settings.GEMINI_API_KEY || '';
  // Elle düzenlenmiş bir .env, tam Azure ses kimliğini (örn.
  // "tr-TR-AhmetNeural") ya da geçersiz bir değer bırakmış olabilir — bu
  // durumda dropdown sessizce boş görünmesin, bilinen bir varsayılana düşsün.
  const validVoices = ['Ahmet', 'Emel'];
  settingsVoice.value = validVoices.includes(settings.JARVIS_TTS_VOICE) ? settings.JARVIS_TTS_VOICE : 'Ahmet';
  settingsModel.value = settings.JARVIS_GEMINI_MODEL || '';
  settingsWeatherLocation.value = settings.JARVIS_WEATHER_LOCATION || '';
  settingsReportProjects.value = settings.JARVIS_REPORT_PROJECTS || '';
  settingsMode.value = settings.JARVIS_MODE || 'rahat';
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
  if (firstRunLocked) return;
  if (debugPanel.classList.contains('hidden')) {
    openDebugPanel();
  } else {
    debugPanel.classList.add('hidden');
  }
});

debugClose.addEventListener('click', () => {
  if (firstRunLocked) return;
  debugPanel.classList.add('hidden');
});

debugRestart.addEventListener('click', () => {
  window.jarvisShell.restartAgent();
});

tabDebug.addEventListener('click', () => {
  if (firstRunLocked) return;
  setActiveTab('debug');
});
tabSettings.addEventListener('click', () => setActiveTab('settings'));

settingsLaunchOnStartup.addEventListener('change', () => {
  window.jarvisShell.setLaunchOnStartup(settingsLaunchOnStartup.checked);
});

settingsSave.addEventListener('click', () => {
  window.jarvisShell.saveSettings({
    GEMINI_API_KEY: settingsGeminiKey.value,
    JARVIS_TTS_VOICE: settingsVoice.value,
    JARVIS_GEMINI_MODEL: settingsModel.value,
    JARVIS_WEATHER_LOCATION: settingsWeatherLocation.value,
    JARVIS_REPORT_PROJECTS: settingsReportProjects.value,
    JARVIS_MODE: settingsMode.value,
  });
  if (firstRunLocked && settingsGeminiKey.value.trim()) {
    exitFirstRunLock();
  }
});

window.jarvisShell.onAgentLog((entry) => {
  if (!debugPanel.classList.contains('hidden')) appendDebugLine(entry);
});

function speakWithBrowserFallback(text) {
  if (!('speechSynthesis' in window) || !text) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'tr-TR';
  window.speechSynthesis.speak(utterance);
}

const UPDATE_STATUS_TEXT = {
  checking: 'güncelleme kontrol ediliyor...',
  available: (s) => `yeni sürüm indiriliyor: v${s.version}`,
  downloading: (s) => `indiriliyor: %${s.percent}`,
  ready: (s) => `v${s.version} hazır — yeniden başlatınca kurulacak`,
  'up-to-date': '',
  error: 'güncelleme kontrolü başarısız',
};

window.jarvisShell.onUpdateStatus((status) => {
  const text = UPDATE_STATUS_TEXT[status.state];
  settingsUpdateStatus.textContent = typeof text === 'function' ? text(status) : text || '';
});

window.jarvisShell.getAppVersion().then((version) => {
  settingsVersionLabel.textContent = `v${version}`;
});

checkFirstRunLock();
