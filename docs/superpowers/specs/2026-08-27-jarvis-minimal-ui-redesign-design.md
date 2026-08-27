# Jarvis — Minimal UI Redesign Tasarımı

## Amaç

Kullanıcı, mevcut arayüzün (`shell/renderer/`) "yapay zekadan çıkmış gibi
göründüğünü" belirtti. İnceleme sonucu bunun tek bir yerel sorun değil,
tutarlı bir klişe olduğu netleşti: camgöbeği/siyah neon palet, parantez
köşeli ("bracket-cornered") paneller, tamamı BÜYÜK HARF İngilizce etiketler
(TIME/WEATHER/SYSTEM STATUS/CONVERSATION), monospace font, halka+parçacık
sistemli dönen bir "orb", tam ekran nokta ızgarası + radar tarama çizgisi —
hepsi birlikte klasik "Iron Man J.A.R.V.I.S HUD" pastişi oluşturuyor.
Tarayıcıda üç farklı yön (Minimal Modern / Sıcak & Kişisel / Menekşe-Odakla
uyumlu) mockup olarak karşılaştırıldı, kullanıcı **Minimal Modern**'i seçti.

Amaç bu klişeden çıkıp sakin, arka planda az bakılan bir masaüstü aracına
yakışan, koyu-nötr + tek aksan renkli, sade bir görsel kimliğe geçmek.

## Kapsam

**Sadece görsel kimlik.** Mevcut 3 sütunlu HUD yerleşimi (sol widget
kolonu / orta orb+kontroller / sağ konuşma paneli), widget sayısı/içeriği,
pencere boyutu, WebSocket protokolü, state machine ve tüm fonksiyonel
davranış **değişmiyor**. Değişen: renk paleti, tipografi, panel/buton
şekli, orb'un çizim mantığı, arka plan efekti, panel başlıklarının ve
durum metinlerinin dili/harf biçimi.

## Renk Paleti ve Tipografi

`shell/renderer/styles.css`'teki `:root` değişkenleri değişiyor:

| Token | Eski | Yeni | Kullanım |
|---|---|---|---|
| `--bg` | `#020c0c` | `#121214` | Sayfa zemini |
| `--panel-bg` | `#030f0f` | `#1a1a1d` | Panel yüzeyi |
| `--panel-border` (yeni) | — | `#26262a` | Panel/buton kenarlığı |
| `--pri` (aksan) | `#00d4c0` | `#6b6bf5` | Tek sakin aksan (aktif durum, bar dolgusu, odak) |
| `--text` | `#7dfff6` | `#e4e4e7` | Birincil metin |
| `--text-dim` (yeni) | — | `#9a9aa2` | İkincil metin/etiket |
| `--text-faint` (yeni) | — | `#6a6a72` | Placeholder/soluk metin |
| `--green` (idle/listening) | `#00ff88` | `#6b6bf5` | Boşta/dinliyor — ana aksanla birleşiyor |
| `--gold` (thinking) | `#ffcc00` | `#d9b46a` | Düşünüyor |
| `--blue` (speaking) | `#4488ff` | `#7ec8e3` | Konuşuyor (aksandan ayrışsın diye açık gök mavisi) |
| `--red` (error) | `#ff3344` | `#e2685f` | Hata |
| `--muted` (paused) | `#cc2255` | `#55555c` | Duraklatıldı — nötr soluk gri |

Bu haliyle idle/listening durumu ayrı bir renk yerine doğrudan ana aksanı
kullanıyor (orb'un "hazır" hali = markanın kendi rengi); thinking/speaking/
error/paused ayrışması korunuyor ama pastelleştirilmiş.

`--mid`, `--dim`, `--dimmer`, `--org`, `--org2` token'ları bu
redesign'da kullanılmayan yerlerden (bar warn/crit renkleri, eski panel
kenarlığı) temizlenecek; hâlâ kullanılan yerler yeni token'lara taşınacak.

Font: `@import` ile gelen Rajdhani kaldırılıyor, yerine sistem sans-serif
yığını (`-apple-system, 'Segoe UI', system-ui, sans-serif`) kullanılıyor.
`.display-font` sınıfı ve `font-weight: 700` + büyük `letter-spacing`
kullanan yerler normale çekiliyor (bkz. Bileşenler).

## Bileşenler

- **Panel köşeleri** (`.hud-panel::before/::after` bracket L-şekli):
  kaldırılıyor. Yerine `.hud-panel` üzerinde `border: 1px solid
  var(--panel-border); border-radius: 10px;`.
- **Butonlar** (`.control-btn`, `.command-form button`, `.settings-save-btn`):
  gradyan arka plan + `box-shadow` bevel/glow kaldırılıyor. Yerine düz
  `background: var(--panel-bg); border: 1px solid var(--panel-border);
  border-radius: 8px;`, hover'da sadece `background` hafif açılıyor
  (`color-mix` glow yok).
- **Orb** (`shell/renderer/orb.js`): mevcut halka-sistemi + 160 parçacıklı
  yörünge alanı + 84 parçacıklı kabuk + dönen segment yaylar tamamen
  kaldırılıyor. Yerine tek bir `radial-gradient` daire (CSS veya basit
  canvas çizimi), state'e göre renk değişimi (`ORB_COLORS` haritası aynı
  mantıkla korunuyor, sadece paletteki renkler pastelleştiriliyor) ve
  mevcut `scale`/`haloA` hedefli yumuşak geçiş mantığı (idle'da yavaş
  "nefes", speaking'de daha hızlı/büyük nefes) **davranış olarak aynen
  korunuyor** — sadece çizilen şekil sadeleşiyor. `OrbRenderer` sınıfının
  public arayüzü (`setState`, `setUserSpeaking`, `setPaused`) değişmiyor,
  `renderer.js`'te orb'u çağıran hiçbir yer güncellenmeyecek.
- **Arka plan** (`shell/renderer/bg.js`): nokta ızgarası + radar tarama
  çizgisi + 24 sürüklenen parçacık tamamen kaldırılıyor. `bg.js` dosyası
  ve onu yükleyen `<script src="bg.js">` satırı `index.html`'den
  tamamen siliniyor (ölü kod bırakılmıyor); `#bg-canvas` elementi de
  kaldırılıyor, sayfa zemini doğrudan `body`'nin `var(--bg)` rengiyle
  sağlanıyor.
- **Konuşma paneli** (`.conversation-log`): balon değil, düz liste.
  Her mesaj: küçük soluk "sen"/"jarvis" etiketi + altında metin + ince
  `border-bottom` ayırıcı (bkz. mockup). `.entry-user`/`.entry-jarvis`/
  `.entry-error` sınıflarının anlamı korunuyor, sadece görsel biçimleri
  değişiyor.
- **Panel başlıkları ve durum metinleri** — Türkçeleştirme + normal harf:
  - `TIME` → `Saat`, `WEATHER` → `Hava durumu`, `SYSTEM STATUS` → `Sistem`,
    `CONVERSATION` → `Konuşma`
  - `CONNECTING` → `bağlanıyor`, bağlı durumdaki `.status-pill.online`
    metni → `bağlandı`, `.status-pill.error` → `bağlantı hatası`
  - `PAUSE` → `duraklat`, `SHUTDOWN` → `kapat`, `LIVE` → `canlı`
  - `#agent-state` içeriği (`idle`/`listening`/`thinking`/`speaking`/
    `error`) → `boşta`/`dinliyor`/`düşünüyor`/`konuşuyor`/`hata`
  - `DEBUG`/`SETTINGS` sekme başlıkları ve içindeki alan etiketleri
    (`GEMINI API ANAHTARI` vb.) kapsam dışı — bu panel geliştirici/ileri
    kullanıcıya yönelik, asistanın "kişilik" yüzeyi değil
  - Bu metin değişiklikleri `index.html` (statik etiketler) ve
    `renderer.js`'teki (dinamik olarak yazılan state/status metinleri)
    ilgili satırlarda yapılacak — bu string'leri üreten JS mantığı
    (hangi state'te hangi metnin gösterileceği) değişmiyor, sadece
    string'lerin kendisi değişiyor.
- **Debug/Settings paneli** (`.debug-panel`, `.settings-*`): şu an ayrı,
  sabit koyu-yeşil (`#041111`/`#0c2a28`) bir palet kullanıyor — yeni ortak
  token'lara (`--panel-bg`, `--panel-border`, `--text-dim`) geçiriliyor,
  böylece ana ekranla tutarlı görünüyor. Fonksiyon değişmiyor.
- **Wave bars** (`.wave-bars`, ses aktivite göstergesi): `--mid`/`--pri`
  yerine `--text-faint`/`--pri` (yeni aksan) kullanacak, glow kaldırılacak.

## Kapsam Dışı

- Grid yapısının kendisi (sütun sayısı/genişlikleri), widget seti,
  pencere boyutu — kullanıcı bu redesign'ı "sadece görsel kimlik" olarak
  sınırladı, yapısal değişiklik istemedi.
- Işık (light) tema — uygulama bir overlay/masaüstü aracı, koyu tema tek
  hedef.
- Otomatik görsel/pixel-diff testi — YAGNI, manuel gözle doğrulama yeterli.
- `orb.js`/`bg.js` dışındaki JS mimarisi (WebSocket protokolü, state
  machine, ayarlar mantığı) — bu dosyalar hiç değişmiyor.

## Test Stratejisi

Bu tamamen görsel bir değişiklik; davranışsal test yazılacak yeni bir
mantık yok. Mevcut testler (`shell/protocol.test.js`,
`shell/settings.test.js`) fonksiyonel davranışı (mesaj encode/decode,
ayar okuma/yazma) zaten kapsıyor ve bu redesign onları kırmamalı —
plan'ın her görev sonunda `node --test` ile doğrulanacak.

Ek olarak: Electron uygulaması gerçekten açılıp (`npm start`, geçerli bir
`GEMINI_API_KEY` ile veya en azından UI'ın state'lerini elle tetikleyerek)
her durum (boşta/dinliyor/düşünüyor/konuşuyor/hata/duraklatıldı) gözle
kontrol edilecek: doğru renk, orb'un doğru "nefes" hızı, panel
metinlerinin doğru Türkçe karşılıkları.

## Görsel Referans

Kullanıcıyla üzerinde anlaşılan mockup, brainstorming oturumunun görsel
eşlikçi dosyalarında kayıtlı:
`.superpowers/brainstorm/3347-1787859324/content/final-design.html`
(bu dosya `.superpowers/` git-ignore'lu olduğu için repoya girmiyor —
implementasyon sırasında referans için yerel olarak açılabilir).
