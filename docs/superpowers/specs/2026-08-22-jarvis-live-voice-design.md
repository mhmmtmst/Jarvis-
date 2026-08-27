# Jarvis — Canlı Sesli Etkileşim (Live Voice) Tasarımı

## Amaç

v1'de Jarvis yalnızca yazıyla cevap veriyordu (sesli girdi push-to-talk +
Whisper ile metne çevriliyordu ama çıktı hep metindi). Bu, kullanıcının asıl
beklentisiyle uyuşmuyor: Jarvis'in gerçekten *konuşan* bir asistan olması.

Referans olarak incelenen [alpunlu12-commits/jarvis](https://github.com/alpunlu12-commits/jarvis)
projesi bu sorunu Gemini'nin **Live API**'siyle (gerçek zamanlı ses→ses)
çözüyor: mikrofon sürekli akışla Gemini'ye gönderiliyor, Gemini hem anlıyor
hem tool çağırıyor hem de kendi native sesiyle (Türkçe dahil) cevap veriyor.
Bu tasarım, Jarvis'in aynı yaklaşıma geçmesini kapsıyor.

Windows'ta yerel bir Türkçe SAPI sesi kurulu olmadığı doğrulandı (sadece
İngilizce "Microsoft Zira Desktop" var) — yerel bir TTS kütüphanesi Türkçe
metni yanlış aksanla okurdu. Gemini Live'ın native ses çıkışı bu sorunu
kökten çözüyor, ayrı bir TTS motoru gerektirmiyor.

## Mimari

Süreç modeli değişmiyor: `agent/` (Python) ve `shell/` (Electron) yerel bir
WebSocket üzerinden konuşmaya devam ediyor. Değişen, akan verinin türü:

- **Agent** açılışta tek bir kalıcı **Gemini Live oturumu** kurar
  (`response_modalities=["AUDIO"]`) ve uygulama çalıştığı sürece açık tutar.
  Shell yeniden bağlansa/yenilense bile oturum canlı kalır.
- **Shell**, push-to-talk basılıyken mikrofonu bir `AudioWorkletProcessor`
  ile 16kHz PCM16'ya çevirip **binary WebSocket frame** olarak agent'a
  akıtır; agent'tan gelen **binary ses frame'lerini** Web Audio API
  ring-buffer ile hoparlörden çalar. Yazılı komutlar ve durum/metin
  güncellemeleri hâlâ **JSON text frame** olarak gider/gelir — aynı
  WebSocket'te iki frame türü bir arada.
- Yazılı komut kutusu da Live oturumuna bağlanıyor: yazıyla sorulan bir şeye
  bile Jarvis artık sesli cevap verir — ayrı, sessiz bir metin yolu yok.
- **Kalkan bileşenler:** `agent/gemini/backend.py` ve `agent/gemini/client.py`
  (tek seferlik `generate_content` deseni), `agent/stt/whisper_stt.py` ve
  `openai-whisper`/`torch` bağımlılığı, shell'in `MediaRecorder`/webm-blob
  akışı. **Değişmeyenler:** `agent/tools/registry.py` ve tool handler'ların
  kendisi (`open_app.py`, `system_info.py`).

## Protokol (WebSocket mesaj şekli)

**Binary frame'ler (ham ses):**

| Yön | Tip byte | İçerik |
|---|---|---|
| shell→agent | `0x01` | push-to-talk basılıyken 16kHz PCM16 mikrofon parçaları |
| agent→shell | `0x02` | Gemini'nin ses cevabı parçaları (Web Audio ring-buffer ile çalınır) |

**JSON text frame'ler (kontrol/metin):**

| Yön | `type` | İçerik / amaç |
|---|---|---|
| shell→agent | `command` | Yazılı komut metni (Live oturumuna text turn olarak gider) |
| shell→agent | `ptt_start` / `ptt_end` | Push-to-talk basıldı/bırakıldı |
| agent→shell | `status` | HUD durumu: `listening`/`thinking`/`speaking`/`idle` |
| agent→shell | `transcript` | `role: user\|agent` + metin — konuşma paneline düşer |
| agent→shell | `interrupt` | Jarvis konuşurken yeni tetikleme oldu → shell çalmakta olduğu sesi anında keser |
| agent→shell | `turn_complete` | Bu tur bitti (`speaking` → `idle`) |
| agent→shell | `error` | Hata mesajı |

Eski `voice_command` (tam webm blob) tipi kalkıyor.

## Tool-calling (Live oturumu içinde)

`agent/tools/registry.py`'deki `ToolSpec` ve handler'lar (`open_app`,
`get_system_info`) aynen kalıyor. Bağlayıcı katman değişiyor:

- `gemini/client.py` + `gemini/backend.py` kalkıyor, yerine
  `agent/gemini/live_session.py` geliyor: Live bağlantısını `tools=[...]`
  ile açan, sürekli mesaj dinleyen async bir döngü.
- Model bir tool çağırmak istediğinde oturumdan bir `tool_call` olayı gelir
  → registry'den handler bulunur → mevcut desende olduğu gibi
  `asyncio.to_thread` ile (event loop'u bloklamadan) çalıştırılır → sonucu
  `FunctionResponse` olarak **aynı oturuma** geri gönderilir. Ayrı bir
  "followup" isteği yok.
- Gemini Live varsayılan olarak sunucu tarafında otomatik ses algılama
  yapar, ama mikrofon byte'ları zaten sadece push-to-talk basılıyken
  gönderiliyor — yani tuşa basılmadığı sürece gönderilecek ses yok,
  "sürekli dinleme yok" ilkesi bu yol için korunuyor (wake-word yolu hariç,
  aşağıya bakın).

## Wake-word ("jarvis") akışı

- Agent, Live oturumuyla birlikte **ikinci, bağımsız bir arka plan
  döngüsü** başlatır: doğrudan sistem mikrofonunu (`SpeechRecognition` +
  PyAudio ile) dinler, kısa parçalar hâlinde Google'ın ücretsiz konuşma
  tanıma API'sine gönderir, metinde "jarvis" geçip geçmediğine bakar. Bu,
  push-to-talk'un kullandığı Electron/Live ses hattından tamamen ayrı,
  üçüncü bir ses hattı.
  - **Gizlilik notu:** bu döngü çalıştığı sürece ortam sesi sürekli
    Google'a gidiyor; sadece "jarvis" tetiklenince Gemini Live'a bir şey
    gönderiliyor. Kullanıcı bu ödünleşimi bilerek, referans projedeki
    yaklaşımı (yerel/offline motor yerine) tercih etti.
- "jarvis" tespit edilince: kelimeden sonra bir şey varsa ("jarvis saati
  söyle") o kısım direkt komut olarak Live oturumuna gönderilir; sadece
  "jarvis" denduyse kısa bir takip dinlemesi yapılıp gelen cümle komut
  olarak gönderilir.
- Jarvis o an **konuşuyorsa**, "jarvis" tetiklenmesi aynı zamanda **kesme
  (interrupt)** sayılır — push-to-talk'a tekrar basmakla aynı davranış.
- Push-to-talk basılıyken wake-word döngüsü kendini duraklatır (aynı
  mikrofonun iki ayrı pipeline'dan aynı anda okunmaması için).
- **Bilinen risk:** `PyAudio`'nun Python 3.13 için hazır wheel'i
  olmayabilir (referans proje bu yüzden `pipwin` kullanıyor). Plan
  aşamasında doğrulanacak, gerekirse `sounddevice` gibi bir alternatife
  geçilecek.

## HUD durum makinesi

Merkezi görsel (`agent-visualizer`) 3 durumdan 4'e çıkıyor:

- `idle` → `listening`: push-to-talk basıldı **veya** "jarvis" algılandı
- `listening` → `thinking`: tuş bırakıldı / wake-word komutu yakalandı
- `thinking` → `speaking`: Gemini'den ilk ses parçası geldi
- `speaking` → `idle`: `turn_complete` geldi
- `speaking` → `listening` (idle'a uğramadan): kesme (yeni push-to-talk ya
  da "jarvis")
- Yazılı komut: `idle` → `thinking` (listening atlanır) → `speaking` →
  `idle`
- Herhangi bir durumda `error` gelirse → `idle`

**Yeni rozet:** üst durum etiketinin yanında, wake-word döngüsü arka planda
aktifken sabit görünen "JARVIS DİNLİYOR" göstergesi — gizlilik şeffaflığı
için, ana durumdan bağımsız.

## Hata yönetimi

- Gemini Live bağlantısı kopar/kurulamazsa → otomatik yeniden bağlanma
  (backoff), HUD'da görünür hata, süreç çökmez.
- Wake-word cloud STT hatası (internet kopması, API limiti, sessizlik/
  timeout) → sessizce yutulur, bir sonraki döngüde tekrar denenir, HUD'a
  basılmaz (spam olmasın diye).
- Mikrofon açılamıyor (PyAudio cihaz/izin hatası) → wake-word döngüsü
  devre dışı kalır, "JARVIS DİNLİYOR" rozeti kapalı gösterilir;
  push-to-talk (ayrı, Electron tarafındaki mikrofon erişimi) etkilenmez.
- Tool hatası → değişmiyor, handler zaten hata sözlüğü döndürüyor.
- Shell bağlı değilken bir yanıt üretilirse (ör. wake-word tetiklendi ama
  Electron kapalı) → agent komutu/tool'u yine işler, ses baytları
  gönderecek kimse yoksa sessizce düşer.
- API anahtarı eksik/geçersiz → Live bağlantısı kurulamaz, agent net bir
  hata loglar, `.env` düzeltilip yeniden başlatılana kadar bekler.

## Kapsam dışı

- Yerel/offline wake-word motoru (openWakeWord/Porcupine) — bilinçli
  olarak referans projenin bulut-STT yaklaşımı seçildi.
- Uzaktan/telefon üzerinden erişim (referans projenin `jarvis_web`
  tarayıcı istemcisi gibi) — mimari (binary frame + Electron) buna izin
  verir ama bu tasarımın hedefi değil.
- Oyun modu / çalışma modu makroları ("çalışma moduna geç" → birden fazla
  uygulama açma) — ayrı bir spec'te ele alınacak.
- Ekran/webcam görsel anlama, hava durumu, takvim/hatırlatıcı entegrasyonu
  — v1 spec'indeki backlog'da kalmaya devam ediyor.

## Test/doğrulama planı

**Otomatik testlerle kapsanacaklar:**

- Wake-word metin ayrıştırma (tespit, Türkçe karakter normalize, kelime
  sonrası komut ayrımı, takip-dinlemesi tetiklenmesi)
- Binary frame encode/decode (tip byte + PCM payload), hem Python
  (`ws_server`) hem JS (`protocol.js`) tarafında, mevcut `protocol.test.js`
  deseni genişletilerek
- `live_session.py`: fake Live bağlantısı enjekte edilerek — tool_call →
  doğru handler → `FunctionResponse`; ses parçası → doğru forward;
  `turn_complete` → doğru status
- `ws_server`: fake `live_session` ile — `ptt_start`/`ptt_end`, `command`,
  `interrupt` mesajlarının doğru tetiklediği davranışlar
- Tool handler'lar (`open_app`, `get_system_info`) — değişmiyor, mevcut
  testler kalıyor

**Sadece elle doğrulanacaklar:**

- Gerçek Gemini Live oturumuyla uçtan uca ses→ses akışı, Türkçe telaffuz
  kalitesi
- Gerçek "jarvis" wake-word'ün doğru tetiklenmesi/yanlış pozitif
  üretmemesi
- PyAudio'nun bu makinede/Python 3.13'te sorunsuz kurulup mikrofona
  erişebilmesi
- Kesme (interrupt) davranışının gerçek zamanlı hissi/gecikmesi
- Push-to-talk ile wake-word'ün aynı anda çakışmadan çalışması
