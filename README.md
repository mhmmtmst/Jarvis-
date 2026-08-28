# Jarvis

[![Son sürüm](https://img.shields.io/github/v/release/mhmmtmst/Jarvis-?label=s%C3%BCr%C3%BCm&color=6b6bf5)](https://github.com/mhmmtmst/Jarvis-/releases/latest)
[![İndirme sayısı](https://img.shields.io/github/downloads/mhmmtmst/Jarvis-/total?label=indirme&color=6b6bf5)](https://github.com/mhmmtmst/Jarvis-/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows-6b6bf5)](#i̇ndir-ve-kur)
[![Dil](https://img.shields.io/badge/dil-Türkçe-6b6bf5)](#nasıl-kullanılır)

Sesli, sürekli açık masaüstü asistanı. **"asistan"** diyerek uyandırıyorsun, Gemini Live ile
gerçek zamanlı konuşuyorsun; bilgisayarında uygulama açmak, ekranını okumak, komut çalıştırmak,
dosya aramak, hava durumu sormak gibi işleri sesle yaptırabiliyorsun.

## 📦 İndir ve kur

1. [**En son sürümü indir**](https://github.com/mhmmtmst/Jarvis-/releases/latest) — `Jarvis-Setup.exe`.
2. Çift tıkla, kurulum sihirbazını takip et (masaüstü/başlat menüsü kısayolu oluşturur).
3. Uygulamayı ilk açtığında karşına bir **Gemini API anahtarı** ekranı çıkacak (kilitlenmiş
   bir SETTINGS sekmesi) — ücretsiz bir anahtar için
   [aistudio.google.com → Get API Key](https://aistudio.google.com/apikey).
4. Anahtarı yapıştırıp "KAYDET VE YENİDEN BAŞLAT"a bas. Asistan hazır.
5. Yeni sürümler çıktığında uygulama kendi kendine indirir, bir sonraki açılışta kurar —
   elle güncelleme gerekmez.

Windows dışında resmi destek yok.

## 🎙️ Nasıl kullanılır

- Mikrofona **"asistan"** de, ardından ne istediğini söyle (örn. "asistan, hava durumu nasıl").
- **Boşluk tuşuna basılı tutarak** da konuşabilirsin (push-to-talk) — wake-word beklemeden.
- Ekrandaki orb dinlerken/düşünürken/konuşurken rengiyle ve nefes hızıyla durumu gösterir.
- Yazmayı tercih edersen sağdaki kutuya komutunu yazıp gönderebilirsin.
- DEBUG panelinden (sağ üstteki simge) agent loglarını, ayarları ve yeniden başlatmayı yönetebilirsin.

## ✨ Neler yapabiliyor

| | |
|---|---|
| 🗣️ **Doğal sesli sohbet** | Gemini Live ile düşük gecikmeli konuşma (Türkçe/İngilizce, konuştuğun dilde cevap verir), cevapları gerçek bir Azure nöral sesle (Edge-TTS, Ahmet/Emel) sesli okur — sorun çıkarsa tarayıcının kendi sesine sessizce düşer, asistan hiç sessiz kalmaz |
| ☀️ **Günaydın brifingi** | Uygulama açılınca kendiliğinden hava durumunu ve (varsa) dikkat gerektiren proje değişikliklerini tek seferlik kısa bir özetle anlatır |
| 🚀 **Uygulama/dosya açma** | "şunu aç" dediğinde bilgisayarındaki uygulamayı veya dosyayı bulup açar |
| 🔍 **Dosya arama** | Bir klasör altında dosya adında veya içeriğinde geçen kelimeyi arar (node_modules/venv/.git gibi gürültülü klasörleri atlar) |
| 🌐 **Tarayıcıda arama / URL açma** | |
| 🎵 **YouTube / Spotify'da müzik/video arama** | (sonuç sayfasını açar, ilk sonuca tıklamak sana kalır) |
| 🖼️ **Ekranı okuma** | Ekran görüntüsü alıp Gemini'ye ne olduğunu sorabilirsin |
| ⚠️ **Komut çalıştırma, riskli olanlar sözlü onaylı** | PowerShell komutu çalıştırır; dosya silme, süreç/servis durdurma gibi riskli bir komutta önce ne yapacağını söyler, sözlü onayını ister |
| 📊 **Sistem bilgisi** | CPU, RAM, disk, batarya yüzdeleri |
| 🌦️ **Hava durumu** | Konum belirtmezsen IP'den otomatik tespit eder |
| 🧠 **Kalıcı hafıza** | Adını, tercihlerini, sana özel notları hatırlar; "şunu unut" dersen siler |
| 📁 **Proje raporu** | Takip ettiğin git projelerinin durumunu (branch, commit'lenmemiş değişiklik, son commit) özetler |
| 🧘 **Rahat / Çalışma modu** | Çalışma modunda sohbete girmez, şakalaşmaz — sorulanı doğrudan ve kısa yanıtlar |

Jarvis, Iron Man'deki Jarvis gibi kısa-öz ama sıcak ve tanıdık konuşur — resmi bir hizmetçi değil,
seni tanıyan bir yol arkadaşı gibi davranır.

## ⚙️ Ayarlar

SETTINGS sekmesinden (DEBUG panelinin yanında) şunları değiştirebilirsin:

- **Gemini API anahtarı**, **model** adı
- **Ses**: Ahmet (erkek) / Emel (kadın)
- **Hava durumu konumu** (boş bırakılırsa IP'den tahmin edilir)
- **Rapor projeleri**: `İsim:Yol` formatında, virgülle ayrılmış proje listesi
- **Mod**: Rahat / Çalışma
- **Windows başlangıcında otomatik açma**

Dosya arama için varsayılan kök klasör `JARVIS_SEARCH_ROOT` ile `.env` dosyasından ayarlanır
(SETTINGS'te yok, boşsa kullanıcı klasöründen arar).

## 🛠️ Geliştirme (kaynak koddan çalıştırma)

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
