# Jarvis — Ayarlar Paneli Tasarımı

## Amaç

Round J'nin (bkz. `jarvis_next_features_backlog` hafızası, idea 26) 2. ve son
alt-projesi: mevcut DEBUG paneline ikinci bir SETTINGS sekmesi ekleyerek
kullanıcının ses/model/hava durumu konumu/rapor projeleri'ni ve Windows
başlangıcında otomatik açılmayı, `.env` dosyasını elle düzenlemeden
değiştirebilmesini sağlamak. 1. alt-proje (Electron'un Python agent'ı
child process olarak yönetmesi, `AgentProcessManager.restart()`) bu
tasarımın ön koşuluydu ve zaten merge edildi.

Referans alınan (kod kopyalanmayan, sadece desen ilham kaynağı olan)
projedeki gibi gerçek zamanlı, restart'sız "hot apply" YOK — kapsamlı
bir brainstorming sonucu bilinçli olarak reddedildi: Jarvis'in Electron+
Python iki-süreçli mimarisinde bunu yapmak, zaten kez kez bug çıkarmış
`agent-process.js`'e ve `LiveSession`'a yeni bir "çalışırken yeniden
yapılandır" yolu eklemeyi gerektirirdi. Bunun yerine: `.env`'e yaz, sonra
zaten var olan, test edilmiş `agentManager.restart()`'ı çağır (~1-2sn).

## Mimari

Değişiklik üç katmanda: `shell/main.js` (yeni bir `settings.js` modülü +
IPC handler'ları), `shell/preload.js` (köprü fonksiyonları), ve
`shell/renderer/` (DEBUG panelinin SETTINGS sekmesi).

### `.env` okuma/yazma — `shell/settings.js`

Saf, dosya I/O'dan ayrı iki fonksiyon (test edilebilirlik için):

```js
function parseEnvFile(text) { ... }   // -> { KEY: "value", ... }
function updateEnvFile(text, updates) { ... }  // -> yeni dosya metni
```

`parseEnvFile`: satır satır `KEY=value` ayrıştırır, boş satırları ve `#`
yorumlarını atlar. `updateEnvFile`: verilen `updates` dict'indeki
anahtarları YERİNDE günceller (satır sırası/yorumlar korunur), dict'te
olup dosyada olmayan anahtarları sona ekler.

Yönetilen 4 anahtar: `JARVIS_GEMINI_VOICE`, `JARVIS_GEMINI_MODEL`,
`JARVIS_WEATHER_LOCATION`, `JARVIS_REPORT_PROJECTS`.

İnce fs sarmalayıcıları (test edilmez, sadece elle doğrulanır):

```js
function readSettings(envPath) { ... }   // fs.readFileSync + parseEnvFile, sadece 4 anahtarı döner
function writeSettings(envPath, updates) { ... }  // fs.readFileSync + updateEnvFile + fs.writeFileSync
```

`.env` yolu: `path.join(agentManager.cwd, 'agent', '.env')` — mevcut
`pythonPath`/`cwd` hesaplamasıyla aynı `__dirname`'e göreli desen.

### IPC — `shell/main.js`

Üç yeni `ipcMain.handle`:
- `jarvis:get-settings` → `readSettings(envPath)`
- `jarvis:save-settings` → `writeSettings(envPath, updates)`, sonra
  `agentManager.restart()`
- `jarvis:get-launch-on-startup` → `app.getLoginItemSettings().openAtLogin`
- `jarvis:set-launch-on-startup` → `app.setLoginItemSettings({ openAtLogin: value })`

(`app.setLoginItemSettings` Electron'un yerleşik, native bir özelliği —
ek kütüphane gerekmiyor. Not: uygulama henüz paketlenmediği için
[Round H] bu ayar şu an geliştirme sırasında çalışan Electron ikili
dosyasının yolunu kaydediyor — paketlendiğinde otomatik olarak doğru
kurulu `.exe` yoluna geçecek, ekstra iş gerekmiyor ama şimdilik bilinen
bir sınırlama.)

`preload.js`'e eklenen köprüler: `getSettings()`, `saveSettings(values)`,
`getLaunchOnStartup()`, `setLaunchOnStartup(value)` — hepsi
`ipcRenderer.invoke` üzerinden (mevcut `getAgentLogHistory`/`restartAgent`
deseniyle aynı).

### UI — DEBUG panelinin SETTINGS sekmesi

Mevcut `#debug-panel`'in header'ı iki sekmeli hale geliyor: **DEBUG** /
**SETTINGS**. `#debug-toggle` butonu davranışını değiştirmiyor (paneli
aç/kapa), sadece panel içeriği artık iki gövdeden biri (`#debug-body`
mevcut log akışını, `#settings-body` yeni formu içeriyor) arasında
sekme durumuna göre gösterilip gizleniyor. Mevcut "YENİDEN BAŞLAT" butonu
SADECE DEBUG sekmesinde görünür kalıyor (SETTINGS'in kendi kaydet
butonu var, ikisi karışmasın).

SETTINGS sekmesi alanları:
- **Ses** — `<select>`, sabit 8 seçenek (Charon, Puck, Aoede, Kore,
  Fenrir, Leda, Orus, Zephyr — bu oturumda daha önce doğrulanmış geçerli
  Gemini Live sesleri).
- **Model** — `<input type="text">` (dropdown değil — model isimleri sık
  deprecate oluyor, bu oturumda 2 kez başımıza geldi, serbest metin daha
  esnek).
- **Hava durumu konumu** — `<input type="text">`.
- **Rapor projeleri** — `<input type="text">`, ham `İsim:yol,İsim:yol`
  formatında (ayrı ekle/çıkar satırları yok, kapsam küçük tutuluyor).
- **Windows başlangıcında aç** — `<input type="checkbox">`. Değişince
  ANINDA uygulanır (`setLaunchOnStartup` çağrılır, agent restart'ıyla
  hiç ilgisi yok — OS seviyesinde bağımsız bir ayar).
- **"KAYDET VE YENİDEN BAŞLAT"** butonu — SADECE 4 `.env` alanını
  `saveSettings()` ile yazar (bu da `agentManager.restart()`'ı tetikler).
  Birden fazla alan değiştirilip TEK seferde kaydedilebilir — her alan
  kendi başına anlık kaydetmiyor.

Panel açılıp SETTINGS sekmesine geçildiğinde `getSettings()` +
`getLaunchOnStartup()` ile mevcut değerler forma yüklenir (her sekme
değişiminde taze çekilir). `.env`'de henüz olmayan bir anahtar için
(örn. `JARVIS_GEMINI_VOICE` — bu oturumda gerçek `.env`'de eksik olduğu
zaten keşfedilmişti) `readSettings` boş string döner; UI bu durumda
ses dropdown'ını boş/ilk seçenekte bırakır, metin alanlarını boş
gösterir — kullanıcı ilk kaydedişinde eksik anahtar dosyaya eklenir.

## Test planı

- `shell/settings.js`'in `parseEnvFile`/`updateEnvFile` saf fonksiyonları
  `node:test` ile tam kapsamlı test edilir (yeni anahtar ekleme, mevcut
  anahtarı yerinde güncelleme, yorum/boş satırları koruma, Windows
  path'lerindeki `:` ile çakışmama — `agent/tools/report.py`'deki
  `parse_report_projects`'in aynı gotcha'sı burada da geçerli ama bu kez
  `KEY=value` ayracı `=` olduğu için `:` çakışması YOK, sadece not
  düşülüyor).
- `readSettings`/`writeSettings` (gerçek fs I/O) ve `main.js`/`preload.js`
  IPC wiring'i ve renderer UI kodu — mevcut kod tabanı deseniyle aynı
  (bu tür dosya I/O ve DOM kodu bu projede hiç otomatik test edilmiyor,
  elle doğrulama adımlarıyla planda ayrıca belirtilecek).

## Kapsam dışı (bilinçli)

- Gerçek zamanlı restart'sız uygulama (yukarıda gerekçelendirildi).
- Gemini API anahtarını panelden düzenleme (kullanıcı reddetti).
- Rapor projeleri için ayrı ekle/çıkar satırları UI'ı (tek metin alanı
  yeterli).
- SFX/ses seviyesi kontrolleri (referans projede var ama Jarvis'te
  karşılığı yok, istenmedi).
