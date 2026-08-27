# Jarvis — Electron'un Python Agent'ı Yönetmesi Tasarımı

## Amaç

Şu an Jarvis iki ayrı, elle başlatılan süreçten oluşuyor: Python agent
(`agent/main.py`, WebSocket sunucusu + Gemini Live oturumu) ve Electron
kabuğu (`npm start`, `shell/`). Bu, hem "bilgisayar açılınca Jarvis kendi
açılsın" hedefini (bkz. backlog [[jarvis_next_features_backlog]] Round H'a
komşu bir istek) hem de gelecekteki bir Ayarlar panelinin "ayarı
değiştirince nasıl uygulanır" sorusunu engelliyor.

Bu tasarım, Electron'un Python agent'ı kendi **child process**'i olarak
başlatmasını, çökerse otomatik yeniden başlatmasını, kapanışta düzgünce
sonlandırmasını ve çıktısını HUD'da küçük bir DEBUG paneliyle görünür
kılmasını kapsıyor. Bir sonraki alt-proje (Ayarlar paneli) bu üzerine
kurulacak — bu tasarım kapsamında değil.

## Mimari

Değişiklik tamamen `shell/` (Electron) tarafında — Python agent kodu
(`agent/`) hiç değişmiyor, sadece dışarıdan nasıl başlatıldığı değişiyor.

- **Yeni modül `shell/agent-process.js`**: Python child process'in
  yaşam döngüsünü yöneten, Electron'un `app`/`BrowserWindow`
  nesnelerinden bağımsız, saf bir sınıf/modül (test edilebilirlik için).
  `main.js` sadece bunu örnekleyip olaylarını dinler.
- **Yol hesaplama**: `pythonPath = path.join(__dirname, '..', 'agent',
  'venv', 'Scripts', 'python.exe')`, `cwd = path.join(__dirname, '..')`
  (yani proje kökü — `agent.main`'in `from agent.config import ...` gibi
  mutlak paket import'larının çalışması için `-m agent.main` ile, cwd
  proje kökünde olacak şekilde çalıştırılmalı, `agent/main.py`'yi
  doğrudan dosya yolu ile DEĞİL).
- **Başlatma**: `child_process.spawn(pythonPath, ['-m', 'agent.main'],
  { cwd, windowsHide: true })`. `windowsHide: true` — otomatik başlangıçta
  ortada bir konsol penceresi belirmesin.
- **Log arabelleği**: son 200 satır, her biri `{ stream: 'stdout' | 'stderr',
  text }` şeklinde (stderr satırlarının DEBUG panelinde kırmızı
  gösterilebilmesi için kaynağı korunur), main process'te bir dizide
  tutulur (FIFO, 200'ü aşınca baştan siler).
- **IPC (main → renderer)**: `agent-log` (yeni bir satır geldikçe),
  `agent-status` (`starting`/`running`/`restarting`/`crashed` durum
  değişince). `preload.js`'e `onAgentLog(cb)`, `onAgentStatus(cb)`,
  `getAgentLogHistory()` (son 200 satırı senkron/promise ile döner, panel
  ilk açıldığında geçmişi doldurmak için), `restartAgent()` eklenir.

## Çökme ve yeniden başlatma

`agent-process.js` içindeki `AgentProcessManager` sınıfı:

```js
class AgentProcessManager extends EventEmitter {
  constructor({ pythonPath, cwd, spawnFn = spawn }) { ... }
  start() { ... }          // spawn eder, 'status' → 'starting' sonra ilk stdout'ta 'running' yayar
  stop() { ... }           // kasıtlı kapanış; child.kill('SIGTERM'), 2sn içinde kapanmazsa SIGKILL
  restart() { ... }        // stop() + start(), backoff sayacını sıfırlar
  _scheduleRestart() { ... } // backoff: 1s, 2s, 4s, 8s, 16s (üst sınır), 5 art arda hızlı
                              // çökmeden (her biri 10sn'den kısa sürerse) sonra 'crashed' yayıp durur
}
```

- `child.on('exit', (code, signal) => ...)`: eğer `stop()` kasıtlı
  çağrılmadıysa (bir `_intentionalStop` bayrağıyla ayırt edilir),
  `_scheduleRestart()` tetiklenir.
- Backoff süresi her ardışık hızlı çökmede iki katına çıkar, başarılı bir
  şekilde >10sn ayakta kalırsa sayaç sıfırlanır (geçici bir hata ile
  kalıcı bir yapılandırma hatasını ayırt etmek için).
- 5. ardışık hızlı çökmeden sonra `status: 'crashed'` yayılır ve daha
  fazla otomatik deneme yapılmaz; kullanıcı DEBUG panelindeki "yeniden
  başlat" butonuyla manuel tetikleyebilir (bu da sayaç/backoff'u sıfırlar).

Backoff hesaplaması (`nextBackoffMs(attempt)`) saf bir fonksiyon olarak
ayrılır — `Math.min(1000 * 2 ** attempt, 16000)` — böylece gerçek
`setTimeout`/`spawn` olmadan test edilebilir.

## `main.js` değişikliği

```js
const { AgentProcessManager } = require('./agent-process');

const agentManager = new AgentProcessManager({
  pythonPath: path.join(__dirname, '..', 'agent', 'venv', 'Scripts', 'python.exe'),
  cwd: path.join(__dirname, '..'),
});

app.whenReady().then(() => {
  // ...mevcut permission handler, createWindow()...
  agentManager.start();
  agentManager.on('log', (line) => mainWindow.webContents.send('agent-log', line));
  agentManager.on('status', (status) => mainWindow.webContents.send('agent-status', status));
});

app.on('before-quit', () => {
  agentManager.stop();
});

ipcMain.handle('jarvis:restart-agent', () => agentManager.restart());
ipcMain.handle('jarvis:agent-log-history', () => agentManager.getLogHistory());
```

(`mainWindow` mevcut `createWindow()`'un döndürdüğü pencere referansı
olacak şekilde `main.js`'te bir üst-seviye değişkene taşınmalı — şu an
sadece yerel bir değişken.)

## HUD — DEBUG paneli

Referans alınan (kod kopyalanmayan, sadece desen ilham kaynağı olan)
projedeki gibi, HUD üst köşesine küçük bir aç/kapa buton eklenir
(`index.html`'e yeni bir `#debug-toggle` elemanı, mevcut `hud-top`
header'ının içine). Tıklanınca `styles.css`'te yeni bir `.debug-panel`
(sabit konumlu, kaydırılabilir bir `<pre>`/log listesi) açılır/kapanır.
Panel açıldığında `getAgentLogHistory()` ile geçmiş doldurulur, sonra
`onAgentLog` ile canlı satırlar eklenir (stderr satırları kırmızı renkte,
mevcut `entry-error` sınıfının rengiyle tutarlı). Ayrı bir "Yeniden
Başlat" butonu `restartAgent()`'ı çağırır.

Bu panel, bir sonraki alt-projede (Ayarlar) aynı kabuğa ikinci bir sekme
(SETTINGS) eklenerek genişletilecek — bu tasarımda sadece DEBUG sekmesi
var, sekme mekanizması yok (tek panel, tek içerik).

## Test planı

`shell/renderer/agent-process.test.js` (mevcut `protocol.test.js` ile
aynı, bağımsız Node test çalıştırma deseninde):
- `nextBackoffMs(attempt)` saf fonksiyonu: artan değerler, üst sınırda
  sabitlenme.
- `AgentProcessManager`, enjekte edilmiş sahte bir `spawnFn` ile: `start()`
  çağrılınca doğru `pythonPath`/argümanlarla çağrıldığını doğrulama;
  sahte child'ın `exit` olayını tetikleyince `_scheduleRestart`'ın
  çağrıldığını (gerçek `setTimeout` yerine enjekte edilmiş bir zamanlayıcı
  ile) doğrulama; 5 ardışık hızlı çökmeden sonra `crashed` durumuna
  geçtiğini doğrulama; `stop()` çağrılınca `exit`'in yeniden başlatma
  TETİKLEMEDİĞİNİ doğrulama (kasıtlı kapanış ayrımı).
- Gerçek `child_process.spawn` ile uçtan uca doğrulama otomatik test
  kapsamı dışında — elle çalıştırılıp gözlemlenecek (plan'da ayrı bir
  manuel doğrulama adımı olarak belirtilecek).

## Kapsam dışı (bilinçli)

- Ayarlar paneli / SETTINGS sekmesi (sıradaki alt-proje).
- Windows başlangıcında Electron'un kendisinin açılması
  (`app.setLoginItemSettings`) — bu da Ayarlar panelindeki bir toggle
  olarak ele alınacak, bu tasarımda sadece Python'un Electron tarafından
  yönetilmesi var.
- Paketleme/installer (Round H) — yol hesaplaması paketlenmemiş
  (`npm start`) senaryo için doğru; paketlendiğinde (asar içinde farklı
  dizin yapısı) yeniden gözden geçirilecek, şimdiden o karmaşıklığı
  eklemiyoruz (YAGNI).
- Python tarafında herhangi bir değişiklik — `agent/main.py` zaten
  `python -m agent.main` ile çalışacak şekilde yazılmış, dokunulmuyor.
