# Jarvis v1 — Tasarım

## Amaç

Sesli/yazılı komut verilen, gerçek eylemler yapabilen (uygulama açma, sistem
bilgisi) kişisel bir masaüstü ajanı. İlham kaynağı: kullanıcının izlediği bir
demo videosu ("Jarvis, rapor ver" → sesli özet → görev devri) ve
alpunlu12-commits/jarvis GitHub reposunun kurulum videosu (Iron Man tarzı HUD
arayüz). İkisi de yalnızca referans; kod hiçbirinden kopyalanmıyor, sıfırdan
yazılıyor.

## Mimari

İki süreç, yerel bir WebSocket üzerinden konuşur:

- **`agent/`** — Python 3.13 arka plan servisi. Gemini API bağlantısı,
  function-calling ile tool seçimi/çalıştırma, yerel Whisper ile ses→metin
  çevirisi.
- **`shell/`** — Electron uygulaması. Tam ekran HUD arayüzü, agent'a
  WebSocket ile bağlanır, komut gönderir ve cevap/durum günceller.

Python'un tercih edilme sebebi: ses (SpeechRecognition/PyAudio, yerel
Whisper) ve sistem otomasyonu (psutil, mss) kütüphaneleri Node/Electron
tarafından çok daha olgun. Electron ise arayüz için kullanılıyor çünkü
kullanıcının (Odakla projesinden) bu konuda derin tecrübesi var.

## Etkileşim akışı

1. Kullanıcı ya HUD'daki konuşma kutusuna yazar, ya da kısayol tuşunu basılı
   tutup konuşur (push-to-talk; wake-word/sürekli dinleme yok).
2. Sesliyse: kayıt bırakılınca yerel Whisper modeliyle metne çevrilir.
3. Metin `agent`'a WebSocket üzerinden gönderilir.
4. `agent`, Gemini'ye function-calling ile sorar: hangi tool çağrılmalı
   (varsa) ve hangi argümanlarla.
5. Seçilen tool çalıştırılır, sonucu Gemini'ye geri verilir, Gemini son
   cevabı üretir.
6. Cevap metin olarak `shell`'e gönderilir, HUD'daki konuşma panelinde
   gösterilir. v1'de sesli cevap (TTS) yok.

## v1 tool'ları

- `open_app(isim)` — bir uygulama veya dosya açar (Windows).
- `get_system_info()` — CPU/RAM/disk/batarya durumunu döner.

Kasıtlı olarak az tutuldu; genişletme v2+'da yapılacak (aşağıya bakın).

## UI (HUD)

Tam ekran, referans videodaki "Iron Man HUD" estetiğinden ilham alan ama
birebir kopyalanmayan özgün bir görsel kimlik (uygulama aşamasında tasarım
skill'leriyle detaylandırılacak):

- **Sol panel:** canlı saat + sistem durumu widget'ı (CPU/RAM/disk/batarya
  çubukları — `get_system_info()` sonucundan periyodik beslenir)
- **Orta:** ajanın durumunu gösteren animasyonlu bir görsel (idle / dinliyor
  / düşünüyor)
- **Sağ panel:** konuşma geçmişi + yazılı komut kutusu
- **Alt kontrol çubuğu:** LIVE / PAUSE / SHUTDOWN
- **Üst durum etiketi:** CONNECTING / ONLINE / THINKING

Hava durumu widget'ı v1'de yok (ayrı bir API key/entegrasyon gerektiriyor,
v2'ye bırakıldı).

## Hata yönetimi

- Gemini API hatası veya rate-limit → kullanıcıya HUD üzerinde görünür hata
  mesajı, agent çökmez.
- Mikrofon/Whisper hatası (ör. sessizlik, tanınamayan ses) → "seni
  duyamadım" tarzı geri bildirim, yeniden denemeye izin verir.
- Bilinmeyen/tool gerektirmeyen komut → Gemini kendi doğal dil cevabıyla
  yanıtlar (tool çağrılmaz).
- Gemini API anahtarı `.env` dosyasında tutulur, git'e girmez
  (`.gitignore`'a eklenir).

## Kapsam dışı — v1'de yok

Güvenlik veya karmaşıklık nedeniyle bilinçli olarak ertelendi:

- Wake-word ile sürekli dinleme (şimdilik push-to-talk yeterli)
- Sesli cevap (TTS)
- Terminal komutu çalıştırma (ayrı bir güvenlik tasarımı gerektirir)
- Kamera erişimi

## Backlog — v2 ve sonrası (fikir notu, tasarımı yapılmadı)

- **Odakla entegrasyonu:** odak seansı başlayınca otomatik sessiz mod;
  haftalık/günlük brifingte Odakla verilerini (seri, XP) de kullanma
- **Oyun/toplantı farkındalığı:** çalışan process'i (ör. Valorant/CS2) veya
  takvim etkinliğini algılayıp otomatik "rahatsız etme" moduna geçme
- **Geliştirici/yayın otomasyonu:** git repo durumunu sorgulama, tekrar eden
  release adımlarını yarı-otonom tetikleme
- **Ekran görsel anlama:** `mss` ile ekran görüntüsü alıp Gemini vision'a
  sorma ("ekranımda ne var", "bu hata ne anlama geliyor")
- **Küçük pratikler:** indirilenler klasörü otomatik düzenleme, özel makro
  komutları ("çalışma moduna geç" → birden fazla uygulama açma), gün
  boyu biriken bildirimleri istek üzerine özetleme
- **Hava durumu widget'ı**
- **Takvim/hatırlatıcı, mail okuma/özetleme**

## Test/doğrulama planı

- Tool fonksiyonları (`open_app`, `get_system_info`) için birim testleri
  (path çözümleme, sistem bilgisi formatı)
- Manuel uçtan uca doğrulama: birkaç örnek komutla (“Not Defteri’ni aç”,
  “CPU kullanımı nedir”) hem yazılı hem push-to-talk sesli yoldan deneme
- Whisper/Gemini API hatalarının kullanıcıya düzgün yansıdığının manuel
  kontrolü
