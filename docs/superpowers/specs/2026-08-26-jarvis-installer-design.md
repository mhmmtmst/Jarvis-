# Jarvis Gerçek Installer Tasarımı

**Goal:** Jarvis'i (`shell/` Electron kabuğu + `agent/` Python arka planı) başka bilgisayarlara çift-tıkla kurulabilen tek bir Windows installer (`.exe`) olarak paketlemek ve GitHub Release üzerinden dağıtmak. Kullanıcıların Python/Node kurmasına veya paketleri elle `pip install` etmesine gerek kalmayacak.

## Kapsam

- **Kapsamda:** PyInstaller ile Python agent'ın tek bir `agent.exe`'ye dönüştürülmesi, electron-builder + NSIS ile `shell/`'in kurulum paketine çevrilmesi, `agent.exe`'nin bu pakete `extraResources` olarak gömülmesi, production'da `.env`/config'in `userData` dizinine taşınması, ilk kurulumda `GEMINI_API_KEY` girişini zorunlu kılan bloklayıcı bir SETTINGS ekranı, GitHub'da yeni bir public repo açılıp derlenen `.exe`'nin bir Release'e yüklenmesi.
- **Kapsam dışı (v1):** Otomatik güncelleme (`electron-updater`), Odakla'daki gibi ayrı markalı `installer-shell` katmanı, kod imzalama sertifikası, Mac/Linux desteği.

## Referans alınan yaklaşımlar

- **alpunlu12-commits/jarvis** (incelendi, İSTENMİYOR): Build sistemi yok — düz Python kaynak kodu zip'i + elle kurulum talimatı (`KURULUM.txt`: Python 3.12 kur, VS Code kur, `pip install ...`, `py -3.12 main.py`). Tek faydalı fikir: API anahtarını `config/api_keys.json` gibi ayrı bir dosyada tutup, anahtar yoksa ana pencereyi bloklayan bir "İLK KURULUM GEREKLİ" modalı göstermesi (`app_config.py`, `ui.py: wait_for_api_key`).
- **Kullanıcının kendi `odakla-desktop` projesi** (referans alınan yaklaşım): `electron-builder` + NSIS + GitHub Releases + `electron-updater`. Saf Electron+web olduğu için Python paketleme problemi yok; bizim projede bu ekstra olarak var.

## Mimari

### 1. Python agent paketleme
- `agent/` → PyInstaller ile `agent.exe`'ye dönüştürülür.
- `--onedir` modu tercih edilir (`--onefile` değil): `openwakeword`'ün ONNX model dosyaları ve `PyAudio`'nun native bağımlılıkları nedeniyle onefile modunda çalışma zamanı çıkarma (extraction) sorunlarına daha yatkın; onedir modunda tüm bağımlılıklar bir klasörde durur, `--add-data` ile model dosyaları pakete eklenir.
- Plan aşamasında ilk task bu paketlemeyi izole şekilde doğrulayacak (agent.exe tek başına çalıştırılıp WS sunucusunun ayağa kalktığı test edilecek) — native bağımlılıklar PyInstaller ile sürtünme çıkarabilir, bu riski en başta görmek için.

### 2. Electron kabuğu paketleme
- `shell/package.json`'a `electron-builder` devDependency + `build` bloğu eklenir (Odakla'daki `build` bloğu referans alınır: `appId`, `productName: "Jarvis"`, `win.target: nsis`, `nsis.oneClick: false`, masaüstü+start menu kısayolu).
- `extraResources` ile derlenmiş `agent.exe` (ve varsa yanındaki `_internal`/model klasörü) installer'ın içine gömülür.
- `publish: { provider: "github", owner: "mhmmtmst", repo: "jarvis" }`.

### 3. `shell/main.js` — dev/production ayrımı
- `agentManager` oluşturulurken `pythonPath`/spawn hedefi `app.isPackaged`'a göre seçilir:
  - Dev: mevcut davranış — `venv/Scripts/python.exe -m agent.main`, cwd = proje kökü.
  - Packaged: gömülü `agent.exe`, doğrudan çalıştırılır (Python interpreter yok).
- `shell/agent-process.js`'e (spawn/restart/backoff mantığı) DOKUNULMUYOR — sadece kendisine geçilen `pythonPath` ve argümanlar değişiyor, kara kutu olarak kalıyor.

### 4. `.env` / config konumu (production)
- Dev modda değişiklik yok: `agent/.env` (proje köküne göre).
- Packaged modda: `app.getPath('userData')` altında (`%APPDATA%\Jarvis\.env`). Kurulum dizini (`Program Files`) admin izni olmadan yazılamayacağı için buraya taşınıyor.
- İlk açılışta bu dosya yoksa, pakete gömülü `.env.example`'dan boş bir şablon oluşturuluyor.
- Electron, hesapladığı bu `ENV_PATH`'i `JARVIS_ENV_PATH` ortam değişkeni olarak agent'a (`agent.exe` veya dev'de `python -m agent.main`) geçiyor.
- `agent/config.py`'deki `load_dotenv()` çağrısı, `JARVIS_ENV_PATH` ortam değişkeni set edilmişse onu, edilmemişse (dev/test) mevcut varsayılan aramayı kullanacak şekilde güncelleniyor.

### 5. İlk kurulum / API anahtarı akışı
- `GEMINI_API_KEY`, `shell/settings.js`'in `MANAGED_KEYS` listesine eklenir (mevcut 4 alana +1).
- SETTINGS sekmesinde bu alan `type="password"` bir input olarak eklenir.
- Uygulama açılışında (`renderer.js` başlangıcında) `.env`'de `GEMINI_API_KEY` boşsa: DEBUG paneli otomatik SETTINGS sekmesinde açılır ve kapatma/DEBUG'a geçiş engellenir (alpunlu'nun bloklayıcı modal deseninin uyarlanmış hali) — kaydedilene kadar ana HUD ile normal etkileşim (komut girişi, push-to-talk) kilitlenir. Anahtar kaydedilip agent restart olduktan sonra kilit kalkar.

### 6. Dağıtım
- GitHub'da yeni public repo: `mhmmtmst/jarvis`.
- `npm run dist -- --publish always` (electron-builder) derlenen `.exe`'yi doğrudan bir GitHub Release'e yükler.
- Paylaşılacak link: GitHub Release sayfasındaki `.exe` asset linki.

## Güvenlik / gizlilik notu

- `agent/.env.example`'daki `JARVIS_REPORT_PROJECTS` şu an kullanıcının gerçek yerel klasör yollarını (`C:/Users/mhmmt/...`) içeriyor. Repo public olacağı için bu, genelleştirilmiş bir placeholder ile (`Proje1:C:/path/to/proje1,Proje2:C:/path/to/proje2` gibi) değiştirilecek.
- `agent/.env` zaten `.gitignore`'da, gerçek anahtar hiçbir zaman commit edilmeyecek — bu değişmiyor.

## Test / doğrulama planı

- PyInstaller çıktısı (`agent.exe`) tek başına çalıştırılıp WS sunucusunun (8765 portu) ayağa kalktığı, ses/wake-word modüllerinin hata vermeden yüklendiği doğrulanır.
- `shell/settings.test.js`'e `GEMINI_API_KEY`'in `MANAGED_KEYS`'e eklenmesiyle ilgili yeni testler eklenir (mevcut testler halihazırda updateEnvFile/parseEnvFile'ı genel amaçlı test ediyor, yeni key özel bir kod dalı gerektirmiyor).
- Tam installer akışı elle doğrulanır: `.exe` çalıştırılır → kurulum sihirbazı → uygulama ilk açılışta SETTINGS'e kilitlenmiş halde açılır → API anahtarı girilir → HUD açılır → ses komutu test edilir.
- Bu elle doğrulama gerçek bir Windows makinesinde (mümkünse başka bir bilgisayarda veya en azından temiz bir kullanıcı profilinde) yapılmalı — geliştirme makinesinde zaten kurulu olan `venv`/`node_modules` yanıltıcı olabilir.

## Riskler

- PyInstaller + `openwakeword`/`PyAudio` native bağımlılıkları paketlemede sürtünme çıkarabilir (en büyük risk, ilk task bunu izole test eder).
- Kod imzalama sertifikası yok — Windows SmartScreen ilk çalıştırmada uyarı gösterebilir (Odakla'da da aynı durum, `verifyUpdateCodeSignature` atlanarak yaşanıyor; installer için de kullanıcıya "Daha fazla bilgi > Yine de çalıştır" gerekebileceği belirtilecek).
