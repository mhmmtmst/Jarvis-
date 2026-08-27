# Jarvis — Edge-TTS ile Doğal Türkçe Ses Tasarımı

## Amaç

Kullanıcı, Gemini Live'ın built-in seslerinin (Charon/Puck/Kore/Fenrir/Leda/
Orus/Zephyr/Aoede) Türkçede robotik/yapay geldiğini belirtti. Amaç: sesi,
Microsoft Edge'in "Sesli Oku" özelliğinin kullandığı gerçek Azure nöral
seslerini ücretsiz sunan `edge-tts` paketiyle, gerçekten doğal bir Türkçe
sese (Ahmet — erkek) çevirmek.

Araştırılan alternatifler ve neden reddedildikleri kullanıcıyla birlikte
karara bağlandı:
- **ElevenLabs vb. ücretli servisler**: kullanıcı ücretsiz istedi, elendi.
- **Piper (yerel/offline nöral TTS)**: tamamen ücretsiz ve resmi-API riski
  yok, ama Türkçe sesleri de topluluk-eğitimli ve robotik — kullanıcının
  asıl şikayetini (doğallık) çözmüyor, elendi.
- **Edge-TTS**: gerçek Azure nöral ses kalitesi, tamamen ücretsiz, API
  anahtarı gerekmiyor. Riski: resmi olmayan (reverse-engineered) bir API,
  Microsoft istediği an kırabilir. Bu risk, aşağıdaki fallback mekanizmasıyla
  "asistan tamamen sessiz kalır" seviyesinden "o an biraz daha robotik bir
  sese düşer" seviyesine indiriliyor — kullanıcı bu trade-off'u kabul etti.

## Mimari

Değişiklik üç katmanda: `agent/gemini/live_session.py` (Gemini artık ses
değil sadece metin üretiyor), yeni `agent/tools/tts.py` (Edge-TTS sentezi +
PCM dönüşümü), `agent/ws_server.py` (sentezi tetikleme + fallback sinyali +
kesme iptali). Client tarafında (`shell/renderer/`) mevcut `audio_chunk`
binary protokolü DEĞİŞMİYOR — Edge-TTS'in ürettiği ses, Gemini'nin ürettiği
sesle birebir aynı formatta (PCM16, 24kHz, mono) client'a akıtılıyor.

### Gemini Live tarafı — `agent/gemini/live_session.py`

`LiveConnectConfig`'te `response_modalities=["AUDIO"]` → `["TEXT"]`.
`speech_config`/`voice_config` ve `output_audio_transcription` kaldırılıyor
(artık anlamsız — ses üretilmiyor). Model'in cevabı artık
`content.model_turn.parts[].text` üzerinden düz metin olarak geliyor (şu an
`output_transcription.text` üzerinden gelen "agent" transkriptiyle aynı rolü
üstleniyor); `_handle_message`, bu metni topluyor ve `turn_complete`'te
tam metni tek bir `{"type": "agent_text_complete", "text": ...}` olayıyla
dışarı veriyor (mevcut `{"type": "transcript", "role": "agent", ...}` olayı,
kullanıcının transcript panelde metni anında görmesi için parça parça
gelen text'lerde AYNEN yayınlanmaya devam ediyor — sadece ses artık ayrı
bir adımda, tam metin hazır olunca üretiliyor).

Kullanıcının mikrofon girişi (STT/anlama) DEĞİŞMİYOR — `send_audio_chunk`/
`start_activity`/`end_activity` aynen kalıyor, sadece Gemini'nin *çıktı*
modu değişiyor.

### Sentez — yeni `agent/tools/tts.py`

```python
async def synthesize_speech(text: str, voice: str = "tr-TR-AhmetNeural") -> bytes:
    """edge-tts ile sentezler, PCM16 24kHz mono bytes döner (ffmpeg ile
    dönüştürülür). edge-tts'in gerçek ham çıktı formatı implementasyon
    sırasında doğrulanacak (varsayımla ilerlenmeyecek, bkz. plan Step 1)."""
```

`ffmpeg` bu makinede zaten kurulu (bkz. `video_editing_tools_setup` hafızası)
— yeni bir sistem bağımlılığı eklemiyoruz, sadece `agent/requirements.txt`'e
`edge-tts` ekleniyor.

### Tetikleme + fallback + kesme — `agent/ws_server.py`

`handle_live_event`'e yeni bir dal: `agent_text_complete` geldiğinde
`synthesize_speech`'i çağırır, başarılı olursa PCM'i mevcut `audio_chunk`
binary yayınıyla (aynı `\x02` prefix'i) client'a gönderir.

**Nesil sayacı ile kesme:** her yeni turn/interrupt'ta bir sayaç artırılır;
`synthesize_speech` sonucu geldiğinde sayaç hâlâ aynıysa gönderilir, farklıysa
(araya yeni bir turn/kesme girmiş demektir) sessizce atılır.

**Fallback:** `synthesize_speech` exception fırlatırsa (ağ hatası, edge-tts
kırılması vb.), Python tarafında YENİDEN ses üretmeye uğraşılmıyor (karmaşıklık
+ gecikme). Bunun yerine client'a `{"type": "tts_failed"}` gönderiliyor —
transcript metni zaten ayrıca yayınlanmış oluyor. Renderer bunu yakalayıp
tarayıcının (Electron/Chromium'un) yerleşik `window.speechSynthesis` API'sini
son çare olarak devreye sokuyor (Windows'un kurulu Türkçe sesiyle, internet
gerektirmeden, sıfır ekstra Python bağımlılığıyla) — asistan hiçbir zaman
tamamen sessiz kalmıyor.

### SETTINGS değişikliği

`shell/renderer/index.html`'deki "SES" dropdown'ı (Charon/Puck/...) →
Ahmet/Emel seçenekleriyle değiştiriliyor (varsayılan Ahmet). `.env`'de
`JARVIS_GEMINI_VOICE` → `JARVIS_TTS_VOICE=Ahmet|Emel` (agent/config.py,
settings.js MANAGED_KEYS, registry/persona referansları buna göre güncellenir).

## Test Stratejisi

- `agent/tools/tts.py`: `synthesize_speech`'in edge-tts/ffmpeg çağrılarını
  enjekte edilebilir yapıp (mevcut `run_command`'ın `runner` deseni gibi)
  sahte verilerle test edilir; gerçek ağ çağrısı test'lerde yapılmaz.
- `live_session.py`: TEXT modunda `agent_text_complete` olayının doğru
  tetiklendiği, mevcut `FakeSession`/`FakeClient` test altyapısıyla test edilir.
- `ws_server.py`: sentez başarı/hata/kesme-sırasında-gelen-sonuç senaryoları
  `FakeLiveSession` deseniyle test edilir (yeni bir sahte `tts_synthesizer`
  enjekte edilerek).
- Gerçek Edge-TTS sentezi ve ffmpeg dönüşümü, implementasyon sırasında canlı
  doğrulanacak (plan'ın ilk adımı — gerçek çıktı formatını netleştirmek için).
- `response_modalities=["TEXT"]` iken Gemini Live SDK'nın metni gerçekte
  hangi alandan verdiği (`content.model_turn.parts[].text` mi, yoksa başka
  bir alan mı) da aynı şekilde koddan/gerçek bir çağrıdan doğrulanacak,
  varsayımla kilitlenmeyecek (bkz. `feedback_verify_webfetch_api_claims_against_source` hafızası).

## Kapsam Dışı

- Cümle-bazlı parça parça (streaming) sentez — tam metin bekleyip tek seferde
  sentezlemek daha basit; gecikme gerçekte rahatsız ederse ileride eklenebilir.
- Ses hızı/perde ayarı — Edge-TTS bunu destekliyor ama şimdilik varsayılan
  hız/perde kullanılıyor.
