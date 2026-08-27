import asyncio
import json

import agent.ws_server as ws_server_module
from agent.ws_server import JarvisServer


class FakeLiveSession:
    def __init__(self, raise_on: set | None = None):
        self.calls = []
        self._raise_on = raise_on or set()

    async def send_text(self, text):
        self.calls.append(("send_text", text))
        if "send_text" in self._raise_on:
            raise ConnectionError("bağlantı koptu")

    async def start_activity(self):
        self.calls.append(("start_activity",))
        if "start_activity" in self._raise_on:
            raise ConnectionError("bağlantı koptu")

    async def send_audio_chunk(self, pcm_bytes):
        self.calls.append(("send_audio_chunk", pcm_bytes))
        if "send_audio_chunk" in self._raise_on:
            raise ConnectionError("bağlantı koptu")

    async def end_activity(self):
        self.calls.append(("end_activity",))
        if "end_activity" in self._raise_on:
            raise ConnectionError("bağlantı koptu")


class FakeWakeWordListener:
    def __init__(self):
        self.paused = False
        self.resumed = False
        self.turn_complete_notified = False
        self.turn_complete_calls = 0

    def pause(self):
        self.paused = True

    def resume(self):
        self.resumed = True

    def notify_turn_complete(self):
        self.turn_complete_notified = True
        self.turn_complete_calls += 1


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(data)


async def _instant_sleep(seconds):
    """Testlerin gercek 0.2sn'lik parca gecikmelerini yasamadan calismasi
    icin varsayilan enjekte edilen uyku — gercek zamanlamayi kontrol eden
    testler kendi sahte uyku fonksiyonlarini acikca gecer."""
    return None


def make_server(raise_on: set | None = None, tts_synthesizer=None, tts_chunk_sleep=None):
    server = JarvisServer(
        host="127.0.0.1",
        port=0,
        tts_synthesizer=tts_synthesizer,
        tts_chunk_sleep=tts_chunk_sleep if tts_chunk_sleep is not None else _instant_sleep,
    )
    server.live_session = FakeLiveSession(raise_on=raise_on)
    server.wake_word_listener = FakeWakeWordListener()
    return server


def test_command_message_sends_text_and_skips_listening_status():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "command", "text": "merhaba"})))

    assert ("send_text", "merhaba") in server.live_session.calls
    statuses = [json.loads(m) for m in ws.sent if json.loads(m).get("type") == "status"]
    assert {"type": "status", "state": "thinking"} in statuses
    assert {"type": "status", "state": "listening"} not in statuses


def test_command_message_falls_back_to_idle_when_live_session_errors():
    server = make_server(raise_on={"send_text"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "command", "text": "merhaba"})))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "status", "state": "idle"} in messages
    assert any(m.get("type") == "error" for m in messages)


def test_ptt_start_pauses_wake_word_and_starts_activity():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_start"})))

    assert ("start_activity",) in server.live_session.calls
    assert server.wake_word_listener.paused is True


def test_ptt_end_ends_activity_resumes_wake_word_and_sends_thinking_status():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_end"})))

    assert ("end_activity",) in server.live_session.calls
    assert server.wake_word_listener.resumed is True
    statuses = [json.loads(m) for m in ws.sent if json.loads(m).get("type") == "status"]
    assert {"type": "status", "state": "thinking"} in statuses


def test_ptt_end_falls_back_to_idle_instead_of_getting_stuck_when_live_session_errors():
    server = make_server(raise_on={"end_activity"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_end"})))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "status", "state": "idle"} in messages
    assert {"type": "status", "state": "thinking"} not in messages
    assert any(m.get("type") == "error" for m in messages)
    assert server.wake_word_listener.resumed is True


def test_ptt_start_falls_back_to_idle_and_resumes_wake_word_when_live_session_errors():
    server = make_server(raise_on={"start_activity"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_start"})))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "status", "state": "idle"} in messages
    assert any(m.get("type") == "error" for m in messages)
    assert server.wake_word_listener.resumed is True


def test_binary_frame_with_tag_0x01_forwards_audio_chunk():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, b"\x01\xde\xad\xbe\xef"))

    assert ("send_audio_chunk", b"\xde\xad\xbe\xef") in server.live_session.calls


def test_binary_frame_does_not_crash_connection_when_live_session_errors():
    # PTT sirasinda saniyede onlarca ses parcasi akiyor; Live baglantisi tam
    # o anda yeniden baglaniyorsa burada patlamak TUM websocket baglantisini
    # (Electron<->agent) coktururdu — sessizce yutulmasi gerekiyor.
    server = make_server(raise_on={"send_audio_chunk"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, b"\x01\xde\xad\xbe\xef"))  # exception firlatmamali


def test_handle_wake_trigger_sends_system_nudge_for_greeting():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_wake_trigger())

    assert len(server.live_session.calls) == 1
    call_type, sent_text = server.live_session.calls[0]
    assert call_type == "send_text"
    assert sent_text.startswith("[SISTEM]")


def test_handle_conversation_end_sends_system_nudge_for_closing_remark():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_conversation_end())

    assert len(server.live_session.calls) == 1
    call_type, sent_text = server.live_session.calls[0]
    assert call_type == "send_text"
    assert sent_text.startswith("[SISTEM]")


def test_handle_live_event_session_ready_sends_startup_briefing_nudge():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "session_ready"}))

    assert len(server.live_session.calls) == 1
    call_type, sent_text = server.live_session.calls[0]
    assert call_type == "send_text"
    assert sent_text.startswith("[SISTEM]")


def test_handle_live_event_session_ready_only_briefs_once():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "session_ready"}))
    asyncio.run(server.handle_live_event({"type": "session_ready"}))

    assert len(server.live_session.calls) == 1


def test_handle_live_event_agent_text_complete_synthesizes_and_broadcasts_audio():
    async def fake_synth(text, voice):
        assert text == "merhaba"
        return b"\x01\x02\x03\x04"

    server = make_server(tts_synthesizer=fake_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "agent_text_complete", "text": "merhaba"}))

    binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
    assert binary_sent == [b"\x02\x01\x02\x03\x04"]
    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "status", "state": "speaking"} in messages
    assert {"type": "turn_complete"} in messages
    assert {"type": "status", "state": "idle"} in messages
    assert server.wake_word_listener.turn_complete_notified is True


def test_handle_live_event_agent_text_complete_sends_tts_failed_on_synthesis_error():
    async def failing_synth(text, voice):
        raise RuntimeError("edge-tts kırıldı")

    server = make_server(tts_synthesizer=failing_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "agent_text_complete", "text": "merhaba"}))

    binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
    assert binary_sent == []
    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "tts_failed", "text": "merhaba"} in messages


def test_handle_live_event_agent_text_complete_chunks_large_audio():
    async def fake_synth(text, voice):
        return b"\xab" * 25000

    server = make_server(tts_synthesizer=fake_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "agent_text_complete", "text": "uzun bir cevap"}))

    binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
    assert len(binary_sent) == 3
    assert sum(len(chunk) - 1 for chunk in binary_sent) == 25000
    assert all(chunk[0:1] == b"\x02" for chunk in binary_sent)


def test_agent_text_complete_result_discarded_after_interrupt():
    async def slow_synth(text, voice):
        await asyncio.sleep(0)
        return b"\x01\x02"

    server = make_server(tts_synthesizer=slow_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        task = asyncio.create_task(
            server.handle_live_event({"type": "agent_text_complete", "text": "merhaba"})
        )
        await asyncio.sleep(0)
        await server._maybe_interrupt()
        await task

    asyncio.run(scenario())

    binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
    assert binary_sent == []
    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert not any(m.get("type") == "status" and m.get("state") == "speaking" for m in messages)


def test_handle_live_event_transcript_broadcasts_transcript():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_live_event({"type": "transcript", "role": "agent", "text": "merhaba"}))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "transcript", "role": "agent", "text": "merhaba"} in messages


def test_handle_wake_command_starts_turn_and_sends_text():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_wake_command("saati söyle"))

    assert ("send_text", "saati söyle") in server.live_session.calls
    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "status", "state": "listening"} in messages
    assert {"type": "status", "state": "thinking"} in messages


def test_handle_wake_status_broadcasts_wake_status():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server.handle_wake_status(True))

    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "wake_status", "active": True} in messages


def test_location_message_stores_browser_location_and_refreshes_weather(monkeypatch):
    calls = []

    def fake_get_weather_summary(location="", default_location="", http_get=None):
        calls.append(default_location)
        return {"status": "ok", "city": "Safranbolu, Karabük", "temp_c": "27"}

    monkeypatch.setattr(ws_server_module, "get_weather_summary", fake_get_weather_summary)

    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "location", "lat": 41.2544, "lon": 32.6944})))

    assert server._browser_location == "41.2544,32.6944"
    assert calls[0] == "41.2544,32.6944"
    assert server._latest_weather == {"status": "ok", "city": "Safranbolu, Karabük", "temp_c": "27"}
    messages = [json.loads(m) for m in ws.sent]
    assert {"type": "weather_info", "data": server._latest_weather} in messages


def test_location_message_ignores_non_numeric_coordinates():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "location", "lat": "yok", "lon": None})))

    assert server._browser_location is None
    assert ws.sent == []


def test_new_turn_while_speaking_broadcasts_interrupt_first():
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)
    server._speaking = True

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_start"})))

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert messages[0] == {"type": "interrupt"}


# --- Bulgu 1: gonderim dongusu gercek sesin suresi kadar surmeli ------------


def test_chunk_send_loop_keeps_speaking_true_for_real_portion_of_playback():
    # 3 parcalik ses: ilk parca gonderildikten SONRA, son parca gonderilmeden
    # ONCE hala "_speaking=True" olmasi gerekiyor — yani dongu gercekten
    # parcalar arasinda duraklıyor, hepsini bir anda atmiyor.
    pcm = b"\xab" * (ws_server_module._TTS_CHUNK_BYTES * 3)

    async def fake_synth(text, voice):
        return pcm

    sleep_calls = []

    async def fake_chunk_sleep(seconds):
        sleep_calls.append(seconds)
        await asyncio.sleep(0)  # gercek gecikme yok, sadece bir zamanlama noktasi

    server = make_server(tts_synthesizer=fake_synth, tts_chunk_sleep=fake_chunk_sleep)
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        task = asyncio.create_task(
            server.handle_live_event({"type": "agent_text_complete", "text": "uzun bir cevap"})
        )
        await asyncio.sleep(0)  # ilk parca gonderilip ilk chunk_sleep'e girene kadar ilerlet

        binary_sent = [m for m in ws.sent if isinstance(m, (bytes, bytearray))]
        assert len(binary_sent) == 1  # sadece ilk parca gitmis olmali
        assert server._speaking is True  # ve konusma hala "devam ediyor" olmali

        await task

    asyncio.run(scenario())

    assert len(sleep_calls) == 3  # her parcadan sonra bir kez beklendi
    assert all(s == ws_server_module._TTS_CHUNK_SECONDS for s in sleep_calls)
    assert server._speaking is False  # tum parcalar gittikten sonra konusma bitti


def test_default_chunk_sleep_paces_by_real_pcm_duration():
    # Enjeksiyon yapilmazsa gercek asyncio.sleep kullanilir ve gercek sure
    # (24kHz, 16-bit mono -> 9600 bayt = 0.2 saniye) kadar bekler.
    assert ws_server_module._TTS_CHUNK_SECONDS == 9600 / (24000 * 2)

    server = JarvisServer(host="127.0.0.1", port=0)
    assert server._tts_chunk_sleep is asyncio.sleep


# --- Bulgu 2: her turun kesin olarak 'idle'a donmesi ------------------------


def test_tts_failure_still_settles_to_idle_and_notifies_wake_word():
    async def failing_synth(text, voice):
        raise RuntimeError("edge-tts kırıldı")

    server = make_server(tts_synthesizer=failing_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        await server._maybe_interrupt()
        await server.handle_live_event({"type": "agent_text_complete", "text": "merhaba"})

    asyncio.run(scenario())

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "tts_failed", "text": "merhaba"} in messages
    assert {"type": "turn_complete"} in messages
    assert {"type": "status", "state": "idle"} in messages
    assert server.wake_word_listener.turn_complete_calls == 1


def test_raw_turn_complete_after_successful_synthesis_does_not_double_fire():
    async def fake_synth(text, voice):
        return b"\x01\x02"

    server = make_server(tts_synthesizer=fake_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        await server._maybe_interrupt()
        await server.handle_live_event({"type": "agent_text_complete", "text": "merhaba"})
        # LiveSession agent_text_complete'ten hemen sonra HER ZAMAN kendi ham
        # turn_complete'ini de gonderir — bu ayni tur icin ikinci kez idle'a
        # dusmemeli (nesil sayaci senteze gectigi icin artik eslesmiyor).
        await server.handle_live_event({"type": "turn_complete"})

    asyncio.run(scenario())

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert messages.count({"type": "turn_complete"}) == 1
    assert messages.count({"type": "status", "state": "idle"}) == 1
    assert server.wake_word_listener.turn_complete_calls == 1


def test_raw_turn_complete_settles_idle_for_textless_turn():
    # Model bu turda hic metin uretmemis olabilir (sadece arac cagrisi
    # yaptiysa) — o zaman agent_text_complete hic gelmez, tek sinyal ham
    # turn_complete'tir; yine de idle'a donulmeli.
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        await server._maybe_interrupt()
        await server.handle_live_event({"type": "turn_complete"})

    asyncio.run(scenario())

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "turn_complete"} in messages
    assert {"type": "status", "state": "idle"} in messages
    assert server.wake_word_listener.turn_complete_calls == 1


def test_interrupted_textless_turn_settles_via_its_own_later_turn_complete():
    # Gemini bu turu (barge-in yuzunden) kesti VE hic metin uretmedi — bu
    # yuzden agent_text_complete hic gelmiyor. Tek sinyal, ayni turun kendi
    # ham turn_complete'i. "interrupted" olayi kendi nesil sayacini artirdigi
    # icin, eski koddaki hata bu turun ASLA settle edilmemesiydi (idle=0,
    # turn_complete=0, notify=0 — kullanici sonsuza kadar "thinking"de takili
    # kalirdi). Bu test bunun artik dogru settle edildigini dogruluyor.
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        await server._maybe_interrupt()  # tur basliyor (nesil=1, kuyruk=[1])
        await server.handle_live_event({"type": "interrupted"})  # Gemini kesti (nesil=2)
        await server.handle_live_event({"type": "turn_complete"})  # ayni turun ham olayi

    asyncio.run(scenario())

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert messages.count({"type": "turn_complete"}) == 1
    assert messages.count({"type": "status", "state": "idle"}) == 1
    assert server.wake_word_listener.turn_complete_calls == 1


def test_interrupted_turn_with_text_settles_once_not_twice_when_raw_turn_complete_follows():
    # Kesilen turun YINE DE metni varsa (Gemini kesmeden once kismi metin
    # uretmisti), senteze gecen normal yol onu zaten settle eder — kendi ham
    # turn_complete'i daha sonra geldiginde ikinci kez tetiklenmemeli.
    async def fake_synth(text, voice):
        return b"\x01\x02"

    server = make_server(tts_synthesizer=fake_synth)
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        await server._maybe_interrupt()  # tur basliyor (nesil=1)
        await server.handle_live_event({"type": "interrupted"})  # nesil=2
        await server.handle_live_event({"type": "agent_text_complete", "text": "kismi cevap"})  # nesil=3, settle(3)
        await server.handle_live_event({"type": "turn_complete"})  # ayni turun ham olayi, kuyruktan 1 gelir

    asyncio.run(scenario())

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert messages.count({"type": "turn_complete"}) == 1
    assert messages.count({"type": "status", "state": "idle"}) == 1
    assert server.wake_word_listener.turn_complete_calls == 1


def test_interrupted_turn_superseded_by_genuinely_newer_turn_still_does_not_settle():
    # "interrupted" isareti birakip metinsiz kalan bir tur, kendi ham
    # turn_complete'i ULASMADAN once GERCEKTEN farkli/daha yeni bir tur
    # basitirsa (yeni bir _maybe_interrupt cagrisi), artik gercekten
    # superseded'dir — force-settle YAPILMAMALI (yoksa yeni turun durumunun
    # UZERINE gecikmis bir 'idle' yayinlanir).
    server = make_server()
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        await server._maybe_interrupt()  # turn1 basliyor (nesil=1, kuyruk=[1])
        await server.handle_live_event({"type": "interrupted"})  # turn1 kesildi (nesil=2)
        await server._maybe_interrupt()  # turn2 GERCEKTEN yeni basliyor (nesil=3, kuyruk=[1,3])
        ws.sent.clear()
        # turn1'in gec gelen ham turn_complete'i simdi isleniyor.
        await server.handle_live_event({"type": "turn_complete"})

    asyncio.run(scenario())

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "status", "state": "idle"} not in messages
    assert {"type": "turn_complete"} not in messages
    assert server.wake_word_listener.turn_complete_calls == 0
    assert server._pending_turns == [3]  # turn2'nin girisi hala kuyrukta, tuketilmedi


def test_ptt_end_error_discards_pending_turn_so_fifo_does_not_permanently_corrupt():
    # Bulgu 2: ptt_start basariyla bir nesli kuyruga ekliyor (_open_ptt_generation
    # ile isaretleniyor); ptt_end'in end_activity() cagrisi patlarsa, o nesil
    # artik Gemini'den hicbir turn_complete almayacak. Eskiden ptt_end'in bunu
    # kuyruktan silecek bir yolu yoktu — bu girdi KALICI olarak orada kalip
    # SONRAKI her metinsiz turun ham turn_complete'ini yanlislikla tuketiyordu.
    server = make_server(raise_on={"end_activity"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_start"})))
    assert server._pending_turns == [1]  # ptt_start'in nesli kuyrukta

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_end"})))

    # end_activity() patladigi icin bu nesil icin asla bir turn_complete
    # gelmeyecek — kuyrukta yetim kalmamali.
    assert server._pending_turns == []
    assert server._open_ptt_generation is None

    # Kanit: sonraki, TAMAMEN ILGISIZ metinsiz bir tur artik dogru settle
    # ediliyor (eskiden bu, yetim girdiyi yanlislikla tuketip sessizce
    # basarisiz olurdu).
    ws.sent.clear()
    server.wake_word_listener.turn_complete_calls = 0

    async def next_turn():
        await server._maybe_interrupt()
        await server.handle_live_event({"type": "turn_complete"})

    asyncio.run(next_turn())

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "turn_complete"} in messages
    assert {"type": "status", "state": "idle"} in messages
    assert server.wake_word_listener.turn_complete_calls == 1


def test_ptt_end_without_prior_ptt_start_does_not_error_or_discard_anything():
    # ptt_start hic cagrilmamissa _open_ptt_generation None'dir — ptt_end'in
    # hata yolu bunu ayirt edip discard denemesin (None ile
    # _pending_turns.remove cagirmaya calismak yanlis bir girdi silebilirdi).
    server = make_server(raise_on={"end_activity"})
    ws = FakeWebSocket()
    server._clients.add(ws)

    # Baska (ilgisiz) bir tur zaten kuyrukta olsun.
    asyncio.run(server._maybe_interrupt())
    assert server._pending_turns == [1]

    asyncio.run(server._handle_client_message(ws, json.dumps({"type": "ptt_end"})))  # patlamamali

    assert server._pending_turns == [1]  # ilgisiz tur dokunulmadan kaldi
    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    assert {"type": "status", "state": "idle"} in messages


def test_stale_turn_complete_for_superseded_turn_does_not_settle_new_turn_prematurely():
    # Turn1 hala sentezleniyorken (paced dongu ortasinda) turn2 baslarsa,
    # turn1'in eski ham turn_complete'i (Gemini'den gec gelmis olsa bile)
    # turn2 icin erken bir "idle" yayinlamamali.
    pcm = b"\xab" * (ws_server_module._TTS_CHUNK_BYTES * 3)

    async def fake_synth(text, voice):
        return pcm

    async def fake_chunk_sleep(seconds):
        await asyncio.sleep(0)

    server = make_server(tts_synthesizer=fake_synth, tts_chunk_sleep=fake_chunk_sleep)
    ws = FakeWebSocket()
    server._clients.add(ws)

    async def scenario():
        await server._maybe_interrupt()  # turn1 basliyor (nesil=1, kuyruk=[1])
        task = asyncio.create_task(
            server.handle_live_event({"type": "agent_text_complete", "text": "turn1"})
        )
        await asyncio.sleep(0)  # turn1 ilk parcayi gonderip duraklasin (nesil=2)

        await server._maybe_interrupt()  # turn2 baslar (nesil=3, kuyruk=[1, 3]) -> turn1 kesilir
        await task  # turn1'in dongusu artik nesil uyusmazligindan dolayi sessizce cikar

        # turn1'in Gemini'den GEC gelen ham turn_complete'i simdi isleniyor.
        await server.handle_live_event({"type": "turn_complete"})

    asyncio.run(scenario())

    messages = [json.loads(m) for m in ws.sent if isinstance(m, str)]
    # turn1 icin ne "speaking" tamamlandi ne de "idle" yayinlanmis olmali —
    # sadece turn2'nin _maybe_interrupt'i yolladigi "interrupt" gorunmeli.
    assert {"type": "status", "state": "idle"} not in messages
    assert server.wake_word_listener.turn_complete_calls == 0
    assert server._pending_turns == [3]  # turn2'nin girisi hala kuyrukta, tuketilmedi
