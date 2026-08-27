# Jarvis

Sesli, sürekli açık masaüstü asistanı. "**asistan**" diyerek uyandırıyorsun, Gemini Live ile
gerçek zamanlı konuşuyorsun; bilgisayarında uygulama açmak, ekranını okumak, komut çalıştırmak,
hava durumu sormak gibi işleri sesle yaptırabiliyorsun.

## İndir ve kur

1. [**En son sürümü indir**](https://github.com/mhmmtmst/Jarvis-/releases/latest) — `Jarvis-Setup.exe`.
2. Çift tıkla, kurulum sihirbazını takip et (masaüstü/başlat menüsü kısayolu oluşturur).
3. Uygulamayı ilk açtığında karşına bir **Gemini API anahtarı** ekranı çıkacak (kilitlenmiş
   bir SETTINGS sekmesi) — ücretsiz bir anahtar için
   [aistudio.google.com → Get API Key](https://aistudio.google.com/apikey).
4. Anahtarı yapıştırıp "KAYDET VE YENİDEN BAŞLAT"a bas. Asistan hazır.

Windows dışında resmi destek yok.

## Nasıl kullanılır

- Mikrofona **"asistan"** de, ardından ne istediğini söyle (örn. "asistan, hava durumu nasıl").
- HUD'daki orb dinlerken/konuşurken durumu gösterir.
- DEBUG panelinden (sağ üstteki simge) agent loglarını, ayarları ve yeniden başlatmayı yönetebilirsin.

## Neler yapabiliyor

- **Sesli sohbet** — Gemini Live ile düşük gecikmeli, doğal konuşma (Türkçe/İngilizce, konuştuğun dilde cevap verir)
- **Uygulama/dosya açma** — "şunu aç" dediğinde bilgisayarındaki uygulamayı veya dosyayı bulup açar
- **Tarayıcıda arama / URL açma**
- **YouTube / Spotify'da müzik/video arama** (sonuç sayfasını açar, ilk sonuca tıklamak sana kalır)
- **Ekranı okuma** — ekran görüntüsü alıp Gemini'ye ne olduğunu sorabilirsin
- **PowerShell komutu çalıştırma** — bilinen tehlikeli komut kalıpları (format, shutdown, disk silme vb.) engellenir
- **Sistem bilgisi** — CPU, RAM, disk, batarya yüzdeleri
- **Hava durumu** — konum belirtmezsen IP'den otomatik tespit eder
- **Kalıcı hafıza** — adını, tercihlerini, sana özel notları hatırlar; "şunu unut" dersen siler
- **Proje raporu** — takip ettiğin git projelerinin durumunu (branch, commit'lenmemiş değişiklik, son commit) özetler

Jarvis, Iron Man'deki Jarvis gibi kısa-öz ama sıcak ve tanıdık konuşur — resmi bir hizmetçi değil,
seni tanıyan bir yol arkadaşı gibi davranır.

## Geliştirme (kaynak koddan çalıştırma)

```bash
# Python agent
python -m venv agent/venv
./agent/venv/Scripts/python.exe -m pip install -r agent/requirements.txt
cp agent/.env.example agent/.env   # GEMINI_API_KEY'i doldur

# Electron kabuğu
cd shell && npm install && npm start
```

Kendi installer'ını derlemek için `agent/build-agent.sh` (agent.exe donduruyor) ve
`cd shell && npm run dist` (Windows installer üretiyor) sırasıyla çalıştırılır.
