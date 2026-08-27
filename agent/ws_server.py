import asyncio
import logging
import json

import websockets

from agent.tools.system_info import get_system_info
from agent.tools.tts import synthesize_speech
from agent.tools.weather import get_weather_summary

WEATHER_REFRESH_SECONDS = 900  # 15 dakika — ucretsiz wttr.in servisini yormamak icin
_TTS_CHUNK_BYTES = 9600  # 24kHz, 16-bit mono'da ~200ms
_PCM_SAMPLE_RATE_HZ = 24000
_PCM_BYTES_PER_SAMPLE = 2
# Client (renderer.js) her parcayi gercek zamanlamayla (Web Audio nextPlaybackTime)
# calarken sunucu tum parcalari milisaniyeler icinde gonderip _speaking'i hemen
# False yapiyordu — bu yuzden kullanici hala Jarvis'i dinlerken kesme (barge-in)
# neredeyse hic calismiyordu. Gonderim dongusu asagida bu sureyle eslenir.
_TTS_CHUNK_SECONDS = _TTS_CHUNK_BYTES / (_PCM_SAMPLE_RATE_HZ * _PCM_BYTES_PER_SAMPLE)

logger = logging.getLogger(__name__)


class JarvisServer:
    def __init__(
        self, host: str, port: int, weather_default_location: str = "",
        tts_voice: str = "tr-TR-AhmetNeural", tts_synthesizer=None, tts_chunk_sleep=None,
    ):
        self._host = host
        self._port = port
        self._weather_default_location = weather_default_location
        self._clients: set = set()
        self._speaking = False
        self.live_session = None
        self.wake_word_listener = None
        self._latest_weather = None
        self._browser_location: str | None = None
        self._briefed = False
        self._tts_voice = tts_voice
        self._tts_synthesizer = tts_synthesizer if tts_synthesizer is not None else synthesize_speech
        self._tts_chunk_sleep = tts_chunk_sleep if tts_chunk_sleep is not None else asyncio.sleep
        self._tts_generation = 0
        # Her _maybe_interrupt() cagrisi (= yeni bir tur) burada kendi nesil
        # numarasini FIFO sirayla biriktirir; Gemini'den gelen ham
        # "turn_complete" olayinin HANGI tura ait oldugunu (paylasilan tek bir
        # "mevcut tur" alani araya baska bir turun girmesiyle bozulabilecegi
        # icin) guvenilir bicimde bulmak icin kullanilir.
        self._pending_turns: list[int] = []
        self._settled_generation: int | None = None
        # "interrupted" ham olayi bu turun KENDI nesil sayacini artirir (yeni
        # sentezleri gecersiz kilmak icin) — ama bu, kendi metinsiz turn_complete'i
        # geldiginde onu "baska/daha yeni bir tur tarafindan gecersiz kilinmis"
        # sanip asla settle etmemesine yol acardi. Bu alan, artirmadan HEMEN once
        # o turun nesil numarasini saklar; ayni turun kendi turn_complete'i
        # geldiginde bununla eslesirse settle "force" ile (guncellik kontrolu
        # atlanarak) zorlanir. Gercekten DAHA SONRAKI/farkli bir _maybe_interrupt()
        # cagrisi (yeni bir kullanici turu) gelirse bu alan temizlenir — o zaman
        # bu tur artik gercekten "superseded" sayilir ve settle edilmemesi dogrudur.
        self._interrupted_pending_generation: int | None = None
        # ptt_start basariyla acilan push-to-talk turunun neslini burada tutar;
        # ptt_end mesaji AYRI bir sonraki WebSocket cagrisinda calistigi icin,
        # end_activity() patlarsa hangi kuyruk girdisini silecegini bu alan
        # olmadan bilemezdi (bkz. ptt_end handler'i).
        self._open_ptt_generation: int | None = None

    async def _handler(self, websocket) -> None:
        self._clients.add(websocket)
        if self._latest_weather is not None:
            # Hava durumu 15 dakikada bir yayinlaniyor; yeni baglanan bir
            # istemci (ornegin yeniden acilan shell penceresi) bu yayini
            # kacirmis olabilir, o yuzden son bilinen veriyi hemen gonder.
            await websocket.send(json.dumps({"type": "weather_info", "data": self._latest_weather}))
        try:
            async for raw in websocket:
                await self._handle_client_message(websocket, raw)
        finally:
            self._clients.discard(websocket)

    async def _handle_client_message(self, websocket, raw) -> None:
        if isinstance(raw, (bytes, bytearray)):
            await self._handle_binary(raw)
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"type": "error", "message": "Geçersiz mesaj."}))
            return

        msg_type = msg.get("type")
        if msg_type == "command":
            # Yazılı komut: "listening" durumu atlanır (mikrofon yok), direkt "thinking".
            generation = await self._maybe_interrupt()
            await self._broadcast_json({"type": "status", "state": "thinking"})
            await self._send_text_safely(msg.get("text", ""), generation)
        elif msg_type == "ptt_start":
            generation = await self._maybe_interrupt()
            self.wake_word_listener.pause()
            await self._broadcast_json({"type": "status", "state": "listening"})
            try:
                await self.live_session.start_activity()
                # Sadece basarili acilista kaydediyoruz: ptt_end (ayri, sonraki
                # bir WebSocket mesaji olarak) end_activity() patlarsa hangi
                # kuyruk girdisini silecegini bilsin diye.
                self._open_ptt_generation = generation
            except Exception as error:
                # Live baglantisi tam bu anda yeniden baglaniyor olabilir —
                # boyle birakirsak arayuz sonsuza kadar "listening"de kalir.
                # Bu tur Gemini'ye hic ulasmadigi icin ondan bir turn_complete
                # de gelmeyecek — kuyrukta asili kalip sonraki gercek turun
                # olayini yanlislikla tuketmesin diye burada atiyoruz.
                self._discard_pending_turn(generation)
                await self._broadcast_json({"type": "error", "message": f"Bağlantı kesildi, tekrar deneyin: {error}"})
                await self._broadcast_json({"type": "status", "state": "idle"})
                self.wake_word_listener.resume()
        elif msg_type == "ptt_end":
            # ptt_start'in actigi turun neslini hemen al ve temizle — boylece
            # bu ptt_end sadece bir kez kullanilir ve sonraki bir ptt_end
            # (ornegin ptt_start hic cagrilmadan) yanlislikla eski/baska bir
            # turu silmez.
            generation = self._open_ptt_generation
            self._open_ptt_generation = None
            try:
                await self.live_session.end_activity()
                await self._broadcast_json({"type": "status", "state": "thinking"})
            except Exception as error:
                # Aynen ptt_start'taki gibi: hata burada sessizce yutulursa
                # ne bir yanit gelir ne de durum guncellenir, arayuz takilir.
                # Ustelik bu tur artik Gemini'ye hic ulasmayacagi (end_activity
                # basarisiz oldugu) icin ondan bir turn_complete de gelmeyecek —
                # kuyrukta asili kalip SONRAKI turun olayini yanlislikla
                # tuketmesin diye (kalici FIFO bozulmasi) burada atiyoruz.
                if generation is not None:
                    self._discard_pending_turn(generation)
                await self._broadcast_json({"type": "error", "message": f"Bağlantı kesildi, tekrar deneyin: {error}"})
                await self._broadcast_json({"type": "status", "state": "idle"})
            self.wake_word_listener.resume()
        elif msg_type == "location":
            lat, lon = msg.get("lat"), msg.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                # Tarayicinin Wi-Fi tabanli konumu wttr.in'in IP tahmininden
                # cok daha hassas — kucuk ilceler IP'den hep en yakin buyuk
                # sehre dusuyordu. Gelir gelmez hava durumunu tazele.
                self._browser_location = f"{lat},{lon}"
                await self._refresh_weather()
        else:
            await websocket.send(json.dumps({"type": "error", "message": f"Bilinmeyen mesaj tipi: {msg_type}"}))

    async def _handle_binary(self, raw: bytes) -> None:
        if not raw:
            return
        tag, payload = raw[0], bytes(raw[1:])
        if tag == 0x01:
            try:
                await self.live_session.send_audio_chunk(payload)
            except Exception:
                # PTT sirasinda saniyede onlarca parca akiyor; Live baglantisi
                # tam o anda yeniden baglaniyorsa burada patlamak TUM
                # websocket baglantisini (Electron<->agent) coktururdu.
                # Kaybolan tek bir ses parcasi zaten normal/tolere edilebilir;
                # gercek hata ptt_end'de zaten kullaniciya bildiriliyor.
                pass

    async def _maybe_interrupt(self) -> int:
        """Yeni bir kullanıcı turu başlıyor (ptt basıldı, yazılı komut ya da
        wake-word). Jarvis hâlâ konuşuyorsa shell'e anında kesme sinyali
        gönderilir. Devam eden bir TTS sentezi varsa (nesil sayacı artırılarak)
        sonucu geldiğinde sessizce atılır.

        Bu yeni turun nesil numarasini dondurur ve `_pending_turns` kuyruguna
        ekler — Gemini'den bu tur icin gelecek ham "turn_complete" olayi bu
        numarayla eslestirilip `_settle_turn`'e verilir (bkz. handle_live_event)."""
        self._tts_generation += 1
        generation = self._tts_generation
        self._pending_turns.append(generation)
        # Gercekten yeni/farkli bir tur basliyor — eger onceki turdan kalma
        # "kendi kendine kesildi, henuz settle edilmedi" isareti varsa artik
        # gecersiz: o tur artik GERCEKTEN bu yeni tur tarafindan superseded
        # edildi, kendi turn_complete'i geldiginde normal guncellik kontrolune
        # tabi olup (dogru sekilde) settle edilmemeli.
        self._interrupted_pending_generation = None
        if self._speaking:
            await self._broadcast_json({"type": "interrupt"})
        self._speaking = False
        return generation

    def _discard_pending_turn(self, generation: int) -> None:
        """Bir tur, Gemini'ye hic ulasamadan (baglanti hatasi vb.) yarida
        kesildiginde cagrilir — o tur icin artik bir turn_complete gelmeyecegi
        icin kuyrukta asili kalip SONRAKI gercek turun olayini yanlislikla
        tuketmesin diye kaydini siler."""
        try:
            self._pending_turns.remove(generation)
        except ValueError:
            pass

    async def _settle_turn(self, generation: int, *, force: bool = False) -> None:
        """Bir tur icin durumu kesin olarak 'idle'a dondurur — basarili sentez,
        basarisiz sentez ya da metinsiz bir tur (sadece arac cagrisi) sonrasi
        cagrilabilir. Iki durumda hicbir sey yapmaz:
        1) `generation` artik guncel degilse (yeni bir kesme/tur onu gecersiz
           kildi) — o zaman durumu YENI tur sahipleniyor, eski tur icin idle
           yayinlanmamali. `force=True` bu kontrolu bilerek atlar: bu, bir
           turun KENDI "interrupted" olayinin bu ayni turun nesil sayacini
           artirmasi yuzunden kendi kendine "guncelligini yitirmis" gibi
           gorunmesini telafi etmek icin kullanilir (bkz. handle_live_event).
        2) Bu nesil icin zaten bir kez yerlestirilmisse (ayni tur icin hem
           sentez hem de ham turn_complete olayi tetiklemeye calisirsa cift
           yayin olmasin) — bu kontrol force ile de atlanmaz, cift yayini
           hicbir sekilde onlemez."""
        if generation == self._settled_generation:
            return
        if not force and generation != self._tts_generation:
            return
        self._settled_generation = generation
        await self._broadcast_json({"type": "turn_complete"})
        await self._broadcast_json({"type": "status", "state": "idle"})
        self.wake_word_listener.notify_turn_complete()

    async def _synthesize_and_broadcast(self, text: str) -> None:
        self._tts_generation += 1
        my_generation = self._tts_generation
        # Bu tur artik metniyle birlikte kendi (taze) neslinden settle
        # edilecek — "interrupted" olayindan kalma "henuz metinsiz settle
        # edilmedi" isareti varsa artik alakasiz, temizle. (Bu, o isaret
        # ayni turu mu yoksa BASKA bir turu mu isaret ediyor bilmeden hep
        # temizler; ama _maybe_interrupt zaten her yeni turda da temizledigi
        # icin bu noktada sadece "ayni turun kendi textiyle devam ettigi"
        # durum kalir — bkz. handle_live_event'teki interrupted/turn_complete
        # yorumlari.)
        self._interrupted_pending_generation = None
        try:
            pcm = await self._tts_synthesizer(text, self._tts_voice)
        except Exception as error:
            logger.warning("TTS sentezi başarısız: %s", error)
            if my_generation == self._tts_generation:
                await self._broadcast_json({"type": "tts_failed", "text": text})
            await self._settle_turn(my_generation)
            return

        if my_generation != self._tts_generation:
            return

        self._speaking = True
        await self._broadcast_json({"type": "status", "state": "speaking"})
        for i in range(0, len(pcm), _TTS_CHUNK_BYTES):
            if my_generation != self._tts_generation:
                return
            await self._broadcast_binary(b"\x02" + pcm[i : i + _TTS_CHUNK_BYTES])
            # Istemci her parcayi gercek zamanlamayla calar (Web Audio
            # nextPlaybackTime); sunucu burada da yaklasik ayni sureyi
            # bekleyerek _speaking'i sesin GERCEKTEN caldigi sure boyunca
            # True tutar — boylece bir kesme (_maybe_interrupt) araya
            # girdiginde yukaridaki nesil kontrolu onu gercekten yakalayabilir.
            await self._tts_chunk_sleep(_TTS_CHUNK_SECONDS)

        self._speaking = False
        await self._settle_turn(my_generation)

    async def _send_text_safely(self, text: str, generation: int) -> None:
        """live_session.send_text() Live baglantisi tam o anda yeniden
        baglaniyorsa hata firlatabilir; sessizce yutulursa ne yanit gelir ne
        de durum guncellenir, arayuz "thinking"de sonsuza kadar takilir."""
        try:
            await self.live_session.send_text(text)
        except Exception as error:
            # Bu tur Gemini'ye hic ulasmadi, ondan bir turn_complete gelmeyecek.
            self._discard_pending_turn(generation)
            await self._broadcast_json({"type": "error", "message": f"Bağlantı kesildi, tekrar deneyin: {error}"})
            await self._broadcast_json({"type": "status", "state": "idle"})

    async def handle_wake_command(self, text: str) -> None:
        # Wake-word'ün kendi mikrofon yakalaması ("JARVIS DİNLİYOR" rozeti)
        # zaten ayrı bir kanalda gösteriliyor; burada gelen `text` komut
        # tamamen yakalanmış oluyor, o yüzden "listening" kısaca gösterilip
        # hemen "thinking"e geçiliyor.
        generation = await self._maybe_interrupt()
        await self._broadcast_json({"type": "status", "state": "listening"})
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self._send_text_safely(text, generation)

    async def handle_wake_status(self, active: bool) -> None:
        await self._broadcast_json({"type": "wake_status", "active": active})

    async def handle_wake_trigger(self) -> None:
        # Kullanici "asistan" deyip arkasindan komut soylemedi — kisa bir
        # sesli karsilama yaptir, wake_word_listener bunun bitmesini
        # (turn_complete) bekleyip ardindan asil komutu dinlemeye baslayacak.
        generation = await self._maybe_interrupt()
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self._send_text_safely(
            "[SISTEM] Kullanıcı seni az önce çağırdı, henüz bir komut söylemedi. "
            "Kısaca doğal bir karşılama yap (örn. 'Nasıl yardımcı olabilirim?'), başka bir şey ekleme.",
            generation,
        )

    async def handle_conversation_end(self) -> None:
        # Kullanici "dur"/"teşekkürler" gibi bir durdurma ifadesi soyledi —
        # sessizce kesmek yerine kisa bir kapanis cumlesi soylet, boylece
        # kullanici sohbetin gercekten bittigini sesle anlar.
        generation = await self._maybe_interrupt()
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self._send_text_safely(
            "[SISTEM] Kullanıcı sohbeti bitirdi (örn. 'teşekkürler' dedi). "
            "Kısaca bir kapanış cümlesi söyle (örn. 'Başka bir şey olursa haber ederim.'), başka bir şey ekleme.",
            generation,
        )

    async def handle_startup_briefing(self) -> None:
        # Gemini Live baglantisi kurulunca (agent surecinin omru boyunca SADECE
        # bir kez) kisa bir "gunaydin brifingi" yaptir — get_weather ve
        # get_projects_report tool'lari zaten kayitli, model bunlari kendi
        # cagirip sonucu dogal bir karsilamaya cevirir.
        if self._briefed:
            return
        self._briefed = True
        # Diger tum tur-baslatan handler'lar gibi _maybe_interrupt() cagriliyor
        # (baslangicta kimse konusmuyor oldugu icin bir "interrupt" yayini
        # tetiklemez) — boylece bu turun nesli de _pending_turns kuyruguna
        # girer ve Gemini'nin ham turn_complete'i (or. brifing metinsiz kalirsa)
        # dogru sekilde idle'a donebilir.
        generation = await self._maybe_interrupt()
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self._send_text_safely(
            "[SISTEM] Jarvis az önce başlatıldı, kullanıcı henüz bir şey söylemedi. "
            "get_weather ve get_projects_report araçlarını çağırıp kısa, doğal bir "
            "günaydın brifingi ver: hava durumunu tek cümleyle özetle, projelerden "
            "sadece gerçekten dikkat gerektiren (commit'lenmemiş değişikliği olan) "
            "varsa bahset, hepsi temizse projelerden hiç bahsetme. Uzun tutma.",
            generation,
        )

    async def handle_live_event(self, event: dict) -> None:
        etype = event["type"]
        if etype == "session_ready":
            await self.handle_startup_briefing()
        elif etype == "agent_text_complete":
            await self._synthesize_and_broadcast(event["text"])
        elif etype == "transcript":
            await self._broadcast_json({"type": "transcript", "role": event["role"], "text": event["text"]})
        elif etype == "interrupted":
            # Bu, KENDI turunun (henuz turn_complete'i gelmemis) Gemini
            # tarafinda kesildigini bildiren ham bir olay. Nesli artirmadan
            # HEMEN once (hala guncelken) sakliyoruz: eger bu tur metinsiz
            # kalirsa (agent_text_complete hic gelmezse) asagidaki
            # turn_complete kolu bu nesli tanıyip settle'i "force" ile
            # zorlayacak — normalde nesil artirimi onu "guncelligini
            # yitirmis" gibi gosterip sonsuza kadar 'thinking'de birakirdi.
            # Eger bu tur METIN URETIRSE, _synthesize_and_broadcast bu isareti
            # kendisi temizleyip kendi (daha taze) nesliyle normal yoldan
            # settle eder — o zaman burada sakladigimiz deger asla kullanilmaz.
            self._interrupted_pending_generation = self._tts_generation
            self._tts_generation += 1
            await self._broadcast_json({"type": "interrupt"})
        elif etype == "turn_complete":
            # LiveSession her tur icin (metinli/metinsiz, basarili/basarisiz
            # sentez, hatta Gemini tarafinda kesilmis olsa dahi) tam olarak bir
            # kez bu ham olayi gonderir — bu yuzden burasi durumu 'idle'a
            # dondurmek icin GUVENILIR tek yer. Hangi turun bittigini
            # _pending_turns kuyrugundan (FIFO) buluyoruz; boylece paylasilan
            # tek bir "mevcut tur" alaninin araya baska bir turun girmesiyle
            # bozulmasindan etkilenmiyoruz. `_settle_turn` zaten guncelligini
            # yitirmis (kesilmis) ya da sentez tarafindan onceden
            # yerlestirilmis turlari kendisi eleyecek.
            generation = self._pending_turns.pop(0) if self._pending_turns else self._tts_generation
            # Bu TAM OLARAK bu turun kendi "interrupted" olayinin biraktigi
            # isaretse, force ile settle et (metinsiz kaldigi icin baska
            # hicbir yol onu settle edemez). Baska bir turu isaret ediyorsa
            # (ya da isaret yoksa) normal guncellik kontrolu gecerli olur.
            force = self._interrupted_pending_generation is not None and generation == self._interrupted_pending_generation
            if force:
                self._interrupted_pending_generation = None
            await self._settle_turn(generation, force=force)
        elif etype == "error":
            await self._broadcast_json({"type": "error", "message": event["message"]})

    async def _broadcast_json(self, payload: dict) -> None:
        data = json.dumps(payload)
        for client in list(self._clients):
            try:
                await client.send(data)
            except websockets.exceptions.ConnectionClosed:
                self._clients.discard(client)

    async def _broadcast_binary(self, data: bytes) -> None:
        for client in list(self._clients):
            try:
                await client.send(data)
            except websockets.exceptions.ConnectionClosed:
                self._clients.discard(client)

    async def _broadcast_system_info(self) -> None:
        while True:
            info = await asyncio.to_thread(get_system_info)
            await self._broadcast_json({"type": "system_info", "data": info})
            await asyncio.sleep(3)

    async def _refresh_weather(self) -> None:
        # Tarayicidan gelen hassas konum, .env'deki sabit yedekten oncelikli.
        location = self._browser_location or self._weather_default_location
        info = await asyncio.to_thread(get_weather_summary, default_location=location)
        self._latest_weather = info
        await self._broadcast_json({"type": "weather_info", "data": info})

    async def _broadcast_weather(self) -> None:
        while True:
            await self._refresh_weather()
            await asyncio.sleep(WEATHER_REFRESH_SECONDS)

    async def serve_forever(self) -> None:
        async with websockets.serve(self._handler, self._host, self._port):
            logger.info("WebSocket sunucusu %s:%s adresinde dinliyor", self._host, self._port)
            await asyncio.gather(
                self._broadcast_system_info(),
                self._broadcast_weather(),
            )
