# Jarvis — Yeni Tool'lar (Persona, Tarayıcı, Terminal, Medya, Ekran, Bellek) Tasarımı

## Amaç

Live Voice tasarımıyla Jarvis artık gerçek zamanlı sesli konuşabiliyor ama
elinde sadece 2 tool var: `open_app` ve `get_system_info`. Referans olarak
incelenen [alpunlu12-commits/jarvis](https://github.com/alpunlu12-commits/jarvis)
projesinin `ÖZELLİKLER.txt` dosyası çok daha geniş bir yetenek listesi
gösteriyor (takvim, müzik, WhatsApp, tarayıcı, terminal, bellek, ekran
okuma...). Bu tasarım, o listeden **bu makinede/Windows'ta düşük efor ve
sıfıra yakın dış bağımlılıkla** (API key/OAuth kurulumu gerektirmeyecek
şekilde) yapılabilecek altı parçayı kapsıyor:

1. **Persona** — Jarvis'e bir kimlik/ton kazandırmak (yeni bir tool değil,
   Live oturumuna sistem talimatı)
2. **`open_browser`** — arama yapma / URL açma
3. **`run_command`** — güvenli (blocklist'li) terminal komutu çalıştırma
4. **`play_media`** — YouTube/Spotify'da arama sayfası açma
5. **`read_screen`** — ekran görüntüsü alıp Gemini'ye tarif ettirme
6. **`remember` / `recall`** — basit kalıcı bellek

Takvim/Hatırlatıcı, WhatsApp, YouTube istatistik ve Odakla entegrasyonu
bilinçli olarak kapsam dışı bırakıldı (OAuth/Firebase erişimi gerektiriyor,
ayrı bir tasarım gerektirir). Kod referans projeden kopyalanmıyor, sadece
özellik listesi ilham kaynağı.

## Mimari

Değişiklik `agent/` (Python) tarafıyla sınırlı — `shell/` (Electron) hiç
etkilenmiyor, çünkü tüm bu yetenekler mevcut tool-calling yolundan
(`LiveSession` → registry → handler → `FunctionResponse`) geçiyor, protokole
yeni bir frame tipi eklenmiyor.

- **Persona**, bir tool değil: `agent/persona.py`'de sabit bir `JARVIS_PERSONA`
  string'i, `LiveSession._build_config()`'e `system_instruction=` olarak
  geçiliyor (kurulu SDK'da `LiveConnectConfig.system_instruction` düz `str`
  kabul ediyor, doğrulandı).
- **5 yeni tool**, mevcut `agent/tools/registry.py`'deki `ToolSpec` desenine
  ekleniyor: her biri kendi dosyasında (`browser.py`, `terminal.py`,
  `screen.py`), memory ise `agent/memory.py`'de üst seviyede (diğer
  tool'lardan farklı olarak `agent/tools/` altında değil, çünkü dosya I/O'su
  var ve tool-registry'ye bağımlı değil).
- **`build_tool_registry()` imzası değişiyor**: `read_screen` tek başına bir
  `genai.Client`'a ihtiyaç duyduğu için (ekran görüntüsünü tarif ettirmek
  amacıyla ayrı, senkron bir `generate_content` çağrısı yapıyor) fonksiyon
  artık `build_tool_registry(client)` şeklinde bir client parametresi alıyor.
  `agent/main.py`'deki `build_components()` zaten bir client oluşturuyor,
  aynısı hem `LiveSession`'a hem registry'ye geçiriliyor.
- **Yeni bağımlılık:** `Pillow` (`PIL.ImageGrab.grab()` ile ekran görüntüsü).
- **Değişmeyenler:** WebSocket protokolü, `ws_server.py`, `wake_word.py`,
  `live_session.py`'nin ses/tool-call akışı (sadece `_build_config()`'e bir
  satır ekleniyor).

## Persona

`agent/persona.py`:

```python
JARVIS_PERSONA = """Sen Jarvis'sin — kullanıcının kişisel masaüstü asistanısın. Iron Man'deki
Jarvis gibi resmi, saygılı ama kısa ve öz konuşursun; gereksiz laf kalabalığı yapmazsın.
Kullanıcı hangi dilde konuşursa (Türkçe/İngilizce) sen de o dilde cevap verirsin.
Elindeki araçları (uygulama açma, tarayıcı, terminal, medya, ekran okuma, bellek, sistem
bilgisi) gerektiğinde doğrudan kullanırsın, önce izin istemene gerek yok."""
```

`LiveSession._build_config()`'e tek satır: `system_instruction=JARVIS_PERSONA`.

## `open_browser` — arama / URL açma

`agent/tools/browser.py`:

```python
def resolve_target_url(query_or_url: str) -> str:
    # http(s):// ile başlıyorsa veya "domain.tld" gibi görünüyorsa (boşluksuz)
    # olduğu gibi (şema eksikse https:// eklenerek) döner; değilse Google
    # arama URL'i olarak döner.

def open_browser(query_or_url: str, opener=None) -> dict:
    # opener varsayılan webbrowser.open; testte sahte opener enjekte edilir.
    # {"status": "ok"/"error", "message": ...}
```

Parametre: `query_or_url: string`. Tool açıklaması modele hem arama hem URL
açma için kullanılacağını belirtir.

## `run_command` — terminal komutu

`agent/tools/terminal.py`:

```python
_DANGEROUS_PATTERNS = [
    r"\bformat\s+[a-z]:", r"\bdiskpart\b", r"\bshutdown\b",
    r"\bstop-computer\b", r"\brestart-computer\b", r"\brm\s+-rf\s+/",
    r"\b(del|erase)\s+/s\s+/q\s+[a-z]:\\?\s*$",
    r"\brd\s+/s\s+/q\s+[a-z]:\\?\s*$",
    r"remove-item\s+.*-recurse.*-force.*[a-z]:\\?\s*$",
    r"\bvssadmin\s+delete\b", r"\breg\s+delete\b", r"\bnet\s+user\b.*\bdelete\b",
]

def is_dangerous(command: str) -> bool: ...

def run_command(command: str, cwd: str | None = None, runner=None) -> dict:
    # is_dangerous ise {"status": "blocked", ...}
    # runner varsayılan: powershell.exe -NoProfile -Command <command>,
    #   capture_output=True, text=True, timeout=30
    # TimeoutExpired -> {"status": "error", "message": "...zaman aşımı..."}
    # çıktı (stdout+stderr) 4000 karaktere kırpılır
    # {"status": "ok"/"error", "output": ..., "returncode": ...}
```

Parametreler: `command: string` (zorunlu), `cwd: string` (opsiyonel — farklı
proje klasörlerinde komut çalıştırmak için, örn. "jarvis projesinde git
status"). Blocklist bir güvenlik duvarı değil, kazara/yanlış-anlaşılan sesli
komutun geri dönüşü olmayan hasar vermesini önlemek için (tek kullanıcılı,
güvenilir girdi varsayımıyla).

## `play_media` — müzik/medya arama

`agent/tools/browser.py` içinde, `open_browser` ile aynı dosyada (aynı
`opener` deseni):

```python
def play_media(query: str, platform: str = "youtube", opener=None) -> dict:
    # platform == "spotify" -> https://open.spotify.com/search/<query>
    # aksi halde -> https://www.youtube.com/results?search_query=<query>
```

Otomatik çalma yok (API key/OAuth gerektirir, kapsam dışı) — arama sonuç
sayfası açılır, kullanıcı ilk sonuca tıklar. Parametreler: `query: string`,
`platform: string` (opsiyonel, `"youtube"`/`"spotify"`).

## `read_screen` — ekran okuma

`agent/tools/screen.py`:

```python
def read_screen(soru: str = "Ekranda ne var, kısaca özetle.", grabber=None, client=None) -> dict:
    # grabber varsayılan: PIL.ImageGrab.grab
    # görüntü PNG'ye çevrilir, client.models.generate_content(
    #     model="gemini-3.6-flash",
    #     contents=[types.Part.from_bytes(data=png_bytes, mime_type="image/png"), soru],
    # ) senkron çağrılır (registry çağıranı asyncio.to_thread ile sarmalıyor,
    # LiveSession'daki tool-call handling zaten böyle çalışıyor)
    # {"status": "ok", "description": response.text}
```

Live API'nin tool-call mekanizması sadece metin/JSON dönebiliyor (görüntü
döndüremiyor), o yüzden ekran görüntüsü doğrudan canlı ses oturumuna
gönderilemiyor — ayrı, senkron bir `generate_content` çağrısıyla (aynı
`genai.Client`, farklı bir model isteği) tarif alınıp metin olarak Live
oturumuna dönülüyor. Parametre: `soru: string` (opsiyonel, model neyi merak
ettiğini belirtebilir, örn. "bu hata mesajı ne diyor").

`model="gemini-3.6-flash"` sabit bir model id — Live modelinden (`gemini-live-2.5-flash-preview`)
farklı, çünkü `generate_content` Live-özel modeli kabul etmiyor. Bu tasarım
sürecinde gerçek `GEMINI_API_KEY` ile canlı doğrulandı: ilk denenen
`gemini-2.5-flash` artık kullanılamıyor (`404 NOT_FOUND`, API
`gemini-3.6-flash`'a geçmeyi öneriyor); `gemini-3.6-flash` hem düz metin
hem görüntü+metin (`Part.from_bytes` ile PNG) girdisiyle gerçek bir çağrıda
test edildi ve doğru çalıştı.

## Bellek — `remember` / `recall`

`agent/memory.py` (tool klasörü dışında, çünkü registry'siz bağımsız
kullanılabilir bir dosya I/O modülü):

```python
_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "memory.json")

def remember(bilgi: str, path: str = _DEFAULT_PATH) -> dict:
    # entries.append({"text": bilgi, "timestamp": datetime.now().isoformat()})
    # {"status": "ok", "message": "Hatırlayacağım."}

def recall(path: str = _DEFAULT_PATH) -> dict:
    # boşsa {"status": "ok", "items": [], "message": "Henüz hatırladığım bir şey yok."}
    # doluysa {"status": "ok", "items": [<text>, ...]}
```

Düz liste — semantik arama yok, `recall()` tüm listeyi döner, Gemini
kendi bağlamı içinden ilgiliyi seçer. `agent/memory.json` `.gitignore`'a
eklenecek (kişisel veri). **Bilinen sınırlık:** kayıt sayısı sınırsız büyür,
"unut" tool'u yok — YAGNI, ileride gerekirse eklenir.

## Wiring değişiklikleri

- `agent/tools/registry.py`: `build_tool_registry()` → `build_tool_registry(client)`,
  6 yeni tool eklenir (`open_browser`, `run_command`, `play_media`,
  `read_screen`, `remember`, `recall`).
- `agent/main.py`: `build_components()`'teki `genai.Client`, hem
  `LiveSession`'a hem `build_tool_registry(client)`'a geçirilir.
- `agent/gemini/live_session.py`: `_build_config()`'e `system_instruction=JARVIS_PERSONA`.
- `agent/requirements.txt`: `Pillow>=10.0.0` eklenir.
- `.gitignore`: `agent/memory.json` eklenir.

## Hata yönetimi

- `open_browser`/`play_media`: `opener` (gerçekte `webbrowser.open`)
  `False` dönerse `{"status": "error", ...}`.
- `run_command`: blocklist eşleşirse `{"status": "blocked", ...}` (hata değil,
  ayrı bir durum — model bunu kullanıcıya "bu komutu çalıştıramam" diye
  aktarabilsin diye); timeout'ta `{"status": "error", ...}`; komut
  başarısız dönerse (`returncode != 0`) `{"status": "error", "output": ...}`;
  `cwd` var olmayan bir klasörse (`subprocess.run` `FileNotFoundError`/`OSError`
  fırlatır) bu da yakalanıp `{"status": "error", "message": ...}` döner —
  hiçbir handler ham exception fırlatmaz kuralı (`open_app`'ın zaten
  uyduğu kural) burada da korunuyor, çünkü `_handle_tool_call` çağıranı
  handler'ları try/except ile sarmıyor.
- `read_screen`: `ImageGrab.grab()` veya `generate_content` hata fırlatırsa
  (ör. API kotası, ekran erişimi yok) — handler bu istisnayı yakalayıp
  `{"status": "error", "message": str(error)}` döner (diğer tool'larla
  tutarlı: hiçbir handler ham exception fırlatmaz).
- `remember`/`recall`: dosya bozuksa (`json.JSONDecodeError`) — `_load` boş
  liste döner, üzerine yazılır (kurtarılamaz bozuk dosya durumunda veri
  kaybı kabul edilebilir, kişisel/düşük riskli veri).

## Kapsam dışı

- Takvim/Hatırlatıcı (Windows'ta Mac'teki Apple Takvim karşılığı yok, Google
  Calendar OAuth gerektirir).
- WhatsApp mesajlaşma (WhatsApp Web otomasyonu kırılgan, ayrı bir tasarım
  gerektirir).
- YouTube istatistik (API key kurulumu, düşük değer).
- Gerçek otomatik müzik çalma (YouTube Data API + Spotify OAuth).
- Odakla entegrasyonu (Firebase erişimi/state yönetimi — ayrı bir tasarım).
- Bellekte "unut" tool'u, semantik arama, boyut sınırı.
- Claude Code'u sesle tetikleme (kullanıcı bilinçli olarak sadece komut
  çalıştırma seviyesinde kalmayı seçti).

## Test/doğrulama planı

**Otomatik testlerle kapsanacaklar (hepsi TDD, sahte/injectable bağımlılıklarla):**

- `resolve_target_url`: URL/domain/arama sorgusu ayrımı (çeşitli girdi
  örnekleri)
- `open_browser`/`play_media`: sahte `opener` ile çağrıldığını ve doğru URL'i
  ürettiğini doğrulama
- `is_dangerous`: her blocklist deseni için pozitif örnek + güvenli
  komutlar için negatif örnek
- `run_command`: sahte `runner` ile başarılı/başarısız/timeout senaryoları,
  blocklist eşleşince `runner`'ın hiç çağrılmadığının doğrulanması
- `read_screen`: sahte `grabber` + sahte `client` (sabit `response.text`)
  ile, gerçek ekran/API çağrısı olmadan
- `remember`/`recall`: geçici test dosya yoluyla (`tmp_path` benzeri),
  gerçek `agent/memory.json`'a dokunmadan
- `LiveSession._build_config()`: `system_instruction` alanının doğru
  geçtiğinin doğrulanması (mevcut `test_run_connects_with_configured_model_and_voice`
  testine bir assertion eklenir)
- `build_tool_registry(client)`: 8 tool'un (2 eski + 6 yeni) hepsinin
  registry'de doğru isimle bulunduğunun doğrulanması

**Sadece elle doğrulanacaklar:**

- Gerçek tarayıcı açma/arama davranışı (varsayılan tarayıcı, gerçek pencere)
- Gerçek terminal komutlarının PowerShell'de beklendiği gibi çalışması
- Gerçek ekran görüntüsü + Gemini'nin tarifinin doğruluğu/hızı
- Persona'nın gerçek konuşma tonuna etkisi (Live oturumunda sesli test)
- Bellek tool'unun gerçek bir konuşmada doğal şekilde tetiklenmesi
  ("bunu hatırla" gibi ifadelerin model tarafından doğru tool çağrısına
  dönüşmesi)
