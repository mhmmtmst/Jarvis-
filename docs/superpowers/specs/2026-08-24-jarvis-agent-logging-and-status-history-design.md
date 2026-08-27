# Jarvis — Agent Loglama + DEBUG Panelinde Durum Geçmişi Tasarımı

## Amaç

"Electron'un Python agent'ı yönetmesi" özelliğinin final review'ında iki bulgu bilerek ertelenmişti (bkz. `jarvis_agent_process_management_shipped_2026-08-24` hafızası):

1. **Python agent hiçbir şey loglamıyor** — `agent/**/*.py`'de tek bir `print`/`logging` çağrısı yok. DEBUG paneli normal kullanımda tamamen boş kalıyor, sadece bir çökme olursa ham traceback görünüyor.
2. **İlk `starting`/`running` durum satırları soğuk başlangıçta kayboluyor** — bu satırlar renderer'ın IPC dinleyicileri kurulmadan önce (pencere yüklenirken) yayınlanıyor ve hiçbir yerde saklanmıyor.

Bu tasarım ikisini birlikte, tek ve tutarlı bir mekanizmayla çözüyor: **durum geçişlerini de log geçmişiyle aynı, tek kronolojik tampona yazmak** (main process'te), ayrıca Python tarafına birkaç anlamlı log satırı eklemek.

## Mimari — durum geçmişini log geçmişiyle birleştirme

Şu an `shell/agent-process.js`'te iki ayrı mekanizma var: `logHistory` (main process'te, sadece stdout/stderr, 200 satır) ve renderer'daki `debugStatusLog` (sadece durum geçişleri, 50 satır, panel kapalıyken main process'in bilmediği bir yerde tutuluyor). Bu ayrım hem "ilk durumlar kayboluyor" sorununun kök nedeni hem de kronolojik sırayı bozuyor (panel açılışında önce tüm loglar, sonra tüm durumlar art arda basılıyor, gerçek sırayla karışık değil).

**Çözüm:** Durum geçişlerini de `logHistory`'ye, gerçek oluş sırasına göre, `stream: "status"` etiketiyle yazan tek bir `_recordHistory(entry)` metodu. Hem `_pushLog` (stdout/stderr satırları) hem yeni bir `_emitStatus(status)` sarmalayıcı bunu kullanır. `_emitStatus`, mevcut `this.emit('status', status)` çağrılarının hepsinin yerine geçer: hem geçmişe yazar hem de (geriye dönük uyumluluk için) hâlâ `'status'` event'ini yayınlar — `main.js`/`preload.js`'in mevcut `'agent-status'` IPC köprüsü hiç değişmeden çalışmaya devam eder.

`_recordHistory` ayrıca `this.emit('log', entry)` de yayınladığı için, durum satırları artık **otomatik olarak** mevcut `'agent-log'` IPC yoluyla da renderer'a ulaşır — `main.js`'te hiçbir değişiklik gerekmiyor. `getLogHistory()` artık hem log hem durum satırlarını doğru kronolojik sırayla, tek bir 200'lük tamponda döner.

**Sonuç:** Renderer'daki `debugStatusLog`/`recordStatusLine` mekanizması (2026-08-23 gece eklenmişti) tamamen gereksiz hale geliyor ve kaldırılıyor — aynı işi artık main process'teki tek tampon, daha erken (uygulama açılışının ilk anından itibaren) ve daha doğru sırayla yapıyor. `onAgentStatus` IPC köprüsü (`preload.js`) dokunulmadan kalıyor ama debug panelinin artık onu kullanmasına gerek yok (ileride başka bir amaçla — örn. ayrı bir bağlantı göstergesi — kullanılabilir, bu tasarımın kapsamı dışında).

## Python tarafı — anlamlı log satırları

`agent/main.py`'de bir kez `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)` çağrılır (PYTHONUNBUFFERED zaten süreç yönetimi tarafında ayarlı, ek bir şey gerekmiyor). Dört anlamlı nokta loglanır — sık tekrarlayan (her ses paketi, her tool çağrısı gibi) değil, DEBUG panelinde gerçekten "ne oluyor" sorusuna cevap veren, seyrek olaylar:

1. `agent/main.py`, `main_async()` başında: agent başlıyor (model adı config'ten).
2. `agent/main.py`, `_attempt_live_session`'ın `except` bloğunda (hâlâ mevcut `on_error` çağrısının yanında): Gemini Live bağlantısı koptuğunda uyarı — bu, kullanıcının "aşırı bağlantı kesiliyor" şikayetini gelecekte panelden takip edebilmesini sağlar.
3. `agent/ws_server.py`, `serve_forever()`'da `websockets.serve(...)` bloğuna girer girmez: WS sunucusu dinlemeye başladı.
4. `agent/gemini/live_session.py`, `run()`'da `client.aio.live.connect(...)` başarıyla bağlandıktan hemen sonra: Live oturumu kuruldu.

## Kapsam dışı (bilinçli)

- Tool çağrıları, ses paketleri, transkript gibi yüksek frekanslı olaylar loglanmıyor (panel spam'e boğulmasın).
- `debugStatusLog`'un kaldırılması dışında renderer'ın genel DEBUG paneli tasarımı değişmiyor.
- `main.js`/`preload.js`'e dokunulmuyor.
