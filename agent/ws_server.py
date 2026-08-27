import asyncio
import logging
import json

import websockets

from agent.tools.system_info import get_system_info
from agent.tools.weather import get_weather_summary

WEATHER_REFRESH_SECONDS = 900  # 15 dakika — ucretsiz wttr.in servisini yormamak icin

logger = logging.getLogger(__name__)


class JarvisServer:
    def __init__(self, host: str, port: int, weather_default_location: str = ""):
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
            await self._maybe_interrupt()
            await self._broadcast_json({"type": "status", "state": "thinking"})
            await self._send_text_safely(msg.get("text", ""))
        elif msg_type == "ptt_start":
            await self._maybe_interrupt()
            self.wake_word_listener.pause()
            await self._broadcast_json({"type": "status", "state": "listening"})
            try:
                await self.live_session.start_activity()
            except Exception as error:
                # Live baglantisi tam bu anda yeniden baglaniyor olabilir —
                # boyle birakirsak arayuz sonsuza kadar "listening"de kalir.
                await self._broadcast_json({"type": "error", "message": f"Bağlantı kesildi, tekrar deneyin: {error}"})
                await self._broadcast_json({"type": "status", "state": "idle"})
                self.wake_word_listener.resume()
        elif msg_type == "ptt_end":
            try:
                await self.live_session.end_activity()
                await self._broadcast_json({"type": "status", "state": "thinking"})
            except Exception as error:
                # Aynen ptt_start'taki gibi: hata burada sessizce yutulursa
                # ne bir yanit gelir ne de durum guncellenir, arayuz takilir.
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

    async def _maybe_interrupt(self) -> None:
        """Yeni bir kullanıcı turu başlıyor (ptt basıldı, yazılı komut ya da
        wake-word). Jarvis hâlâ konuşuyorsa shell'e anında kesme sinyali
        gönderilir."""
        if self._speaking:
            await self._broadcast_json({"type": "interrupt"})
        self._speaking = False

    async def _send_text_safely(self, text: str) -> None:
        """live_session.send_text() Live baglantisi tam o anda yeniden
        baglaniyorsa hata firlatabilir; sessizce yutulursa ne yanit gelir ne
        de durum guncellenir, arayuz "thinking"de sonsuza kadar takilir."""
        try:
            await self.live_session.send_text(text)
        except Exception as error:
            await self._broadcast_json({"type": "error", "message": f"Bağlantı kesildi, tekrar deneyin: {error}"})
            await self._broadcast_json({"type": "status", "state": "idle"})

    async def handle_wake_command(self, text: str) -> None:
        # Wake-word'ün kendi mikrofon yakalaması ("JARVIS DİNLİYOR" rozeti)
        # zaten ayrı bir kanalda gösteriliyor; burada gelen `text` komut
        # tamamen yakalanmış oluyor, o yüzden "listening" kısaca gösterilip
        # hemen "thinking"e geçiliyor.
        await self._maybe_interrupt()
        await self._broadcast_json({"type": "status", "state": "listening"})
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self._send_text_safely(text)

    async def handle_wake_status(self, active: bool) -> None:
        await self._broadcast_json({"type": "wake_status", "active": active})

    async def handle_wake_trigger(self) -> None:
        # Kullanici "asistan" deyip arkasindan komut soylemedi — kisa bir
        # sesli karsilama yaptir, wake_word_listener bunun bitmesini
        # (turn_complete) bekleyip ardindan asil komutu dinlemeye baslayacak.
        await self._maybe_interrupt()
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self._send_text_safely(
            "[SISTEM] Kullanıcı seni az önce çağırdı, henüz bir komut söylemedi. "
            "Kısaca doğal bir karşılama yap (örn. 'Nasıl yardımcı olabilirim?'), başka bir şey ekleme."
        )

    async def handle_conversation_end(self) -> None:
        # Kullanici "dur"/"teşekkürler" gibi bir durdurma ifadesi soyledi —
        # sessizce kesmek yerine kisa bir kapanis cumlesi soylet, boylece
        # kullanici sohbetin gercekten bittigini sesle anlar.
        await self._maybe_interrupt()
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self._send_text_safely(
            "[SISTEM] Kullanıcı sohbeti bitirdi (örn. 'teşekkürler' dedi). "
            "Kısaca bir kapanış cümlesi söyle (örn. 'Başka bir şey olursa haber ederim.'), başka bir şey ekleme."
        )

    async def handle_startup_briefing(self) -> None:
        # Gemini Live baglantisi kurulunca (agent surecinin omru boyunca SADECE
        # bir kez) kisa bir "gunaydin brifingi" yaptir — get_weather ve
        # get_projects_report tool'lari zaten kayitli, model bunlari kendi
        # cagirip sonucu dogal bir karsilamaya cevirir.
        if self._briefed:
            return
        self._briefed = True
        await self._broadcast_json({"type": "status", "state": "thinking"})
        await self._send_text_safely(
            "[SISTEM] Jarvis az önce başlatıldı, kullanıcı henüz bir şey söylemedi. "
            "get_weather ve get_projects_report araçlarını çağırıp kısa, doğal bir "
            "günaydın brifingi ver: hava durumunu tek cümleyle özetle, projelerden "
            "sadece gerçekten dikkat gerektiren (commit'lenmemiş değişikliği olan) "
            "varsa bahset, hepsi temizse projelerden hiç bahsetme. Uzun tutma."
        )

    async def handle_live_event(self, event: dict) -> None:
        etype = event["type"]
        if etype == "session_ready":
            await self.handle_startup_briefing()
        elif etype == "audio_chunk":
            if not self._speaking:
                self._speaking = True
                await self._broadcast_json({"type": "status", "state": "speaking"})
            await self._broadcast_binary(b"\x02" + event["data"])
        elif etype == "transcript":
            await self._broadcast_json({"type": "transcript", "role": event["role"], "text": event["text"]})
        elif etype == "interrupted":
            await self._broadcast_json({"type": "interrupt"})
        elif etype == "turn_complete":
            self._speaking = False
            await self._broadcast_json({"type": "turn_complete"})
            await self._broadcast_json({"type": "status", "state": "idle"})
            self.wake_word_listener.notify_turn_complete()
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
