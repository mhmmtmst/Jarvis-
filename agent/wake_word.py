import asyncio
import audioop
import re
import unicodedata
from typing import Awaitable, Callable

import numpy as np
import speech_recognition as sr

_WAKE_PATTERN = re.compile(r"\basistan\b")
_TARGET_PEAK = 20000
_MAX_GAIN = 20.0

_STOP_PHRASES = {
    "dur", "yeter", "yeterli", "tesekkurler", "tesekkur ederim", "tesekkur",
    "tamam yeter", "bu kadar yeter", "kapat", "hoscakal", "hoscakalin",
    "hosca kal", "sag ol", "sagol", "sana bu kadar",
}
_SILENCE_LIMIT = 2  # ust uste bu kadar sessizlikten sonra suren sohbeti bitir

_OWW_SAMPLE_RATE = 16000
_OWW_CHUNK_SAMPLES = 1280  # openWakeWord modeli 80ms'lik parcalar bekliyor


class OpenWakeWordDetector:
    """openWakeWord tabanli, gercek zamanli ham mikrofon akisinda tek bir
    kelimeyi surekli dinleyen dedektor. Su an aktif kullanilmiyor ("jarvis"
    icin egitilmis hazir "hey_jarvis" modeli, kullanicinin yeni tetikleyicisi
    olan "asistan" icin gecerli degil) — STT tabanli tetikleme (asagida)
    "asistan" gibi gercek bir kelime icin yeterince guvenilir cikarsa hic
    devreye girmeyecek. Yetersiz kalirsa "asistan" icin ozel egitilecek bir
    modelle burasi yeniden aktif edilir, o yuzden sinif kasten sili̇nmedi."""

    def __init__(self, model=None, threshold: float = 0.22, keyword: str = "hey_jarvis", pyaudio_module=None):
        if model is None:
            from openwakeword.model import Model

            model = Model(wakeword_models=[keyword])
        self._model = model
        self._threshold = threshold
        self._keyword = keyword
        if pyaudio_module is None:
            import pyaudio as pyaudio_module
        self._pyaudio_module = pyaudio_module

    def wait_for_wake(self) -> bool:
        """Skor esigini gecene kadar bloklar, True doner. Mikrofon acilamazsa
        OSError yukari firlar (cagiran taraf mic_unavailable'a cevirir)."""
        pa = self._pyaudio_module.PyAudio()
        try:
            stream = pa.open(
                format=self._pyaudio_module.paInt16,
                channels=1,
                rate=_OWW_SAMPLE_RATE,
                input=True,
                frames_per_buffer=_OWW_CHUNK_SAMPLES,
            )
            try:
                if hasattr(self._model, "reset"):
                    self._model.reset()
                while True:
                    chunk = stream.read(_OWW_CHUNK_SAMPLES, exception_on_overflow=False)
                    audio = np.frombuffer(chunk, dtype=np.int16)
                    scores = self._model.predict(audio)
                    if scores.get(self._keyword, 0.0) >= self._threshold:
                        return True
            finally:
                stream.stop_stream()
                stream.close()
        finally:
            pa.terminate()


def _normalize_audio(audio: sr.AudioData) -> sr.AudioData:
    """Kullanıcının Windows mikrofon seviyesine güvenmek yerine yakalanan
    sesi dijital olarak hedef tepe seviyesine yükseltir (kısık mikrofonlarda
    Google STT'nin konuşmayı hiç çözemediği durum için)."""
    raw = audio.get_raw_data()
    peak = audioop.max(raw, audio.sample_width)
    if peak == 0:
        return audio
    gain = min(_MAX_GAIN, _TARGET_PEAK / peak)
    if gain <= 1.0:
        return audio
    boosted = audioop.mul(raw, audio.sample_width, gain)
    return sr.AudioData(boosted, audio.sample_rate, audio.sample_width)


def _fold_turkish(text: str) -> str:
    text = text.lower().replace("ı", "i").replace("i̇", "i")
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def extract_command_after_wake_word(text: str) -> str | None:
    """None -> 'asistan' metinde yok. '' -> 'asistan' var ama arkasında komut
    yok, çağıran taraf karşılama + takip dinlemesi yapmalı. Başka bir string
    -> wake-word sonrası komut metni (orijinal, foldlanmamış metinden alınır)."""
    folded = _fold_turkish(text)
    match = _WAKE_PATTERN.search(folded)
    if match is None:
        return None
    remainder = text[match.end():].strip(" ,.:;!?")
    return remainder


def _is_stop_phrase(text: str) -> bool:
    """Tam eşleşme yerine cümle içinde geçiyor mu diye bakar — kullanıcı
    genelde 'çok teşekkürler' / 'tamam sağ ol' gibi ek kelimelerle söylüyor."""
    folded = _fold_turkish(text)
    return any(re.search(rf"\b{re.escape(phrase)}\b", folded) for phrase in _STOP_PHRASES)


class WakeWordListener:
    """Arka planda sürekli mikrofonu dinler, konuşmayı Google'ın ücretsiz
    STT'siyle metne çevirir, 'asistan' geçip geçmediğine bakar (gerçek bir
    kelime olduğu için STT bunu yabancı bir isimden çok daha güvenilir tanır).
    Tetiklenince kısa bir karşılama yaptırır, ardından kullanıcı 'dur' /
    'teşekkürler' gibi bir durdurma ifadesi söyleyene ya da art arda
    sessizlik olana kadar 'asistan' tekrarlamadan doğal bir sohbet gibi
    devam eder. Push-to-talk ile aynı mikrofonu aynı anda kullanmamak için
    `pause`/`resume` ile dışarıdan durdurulabilir."""

    def __init__(
        self,
        on_command: Callable[[str], Awaitable[None]],
        on_wake_status: Callable[[bool], Awaitable[None]],
        on_wake_trigger: Callable[[], Awaitable[None]],
        on_conversation_end: Callable[[], Awaitable[None]],
        recognizer=None,
        microphone_factory=None,
    ):
        self._on_command = on_command
        self._on_wake_status = on_wake_status
        self._on_wake_trigger = on_wake_trigger
        self._on_conversation_end = on_conversation_end
        self._recognizer = recognizer if recognizer is not None else sr.Recognizer()
        self._microphone_factory = microphone_factory if microphone_factory is not None else sr.Microphone
        self._paused = False
        self._mic_unavailable = False
        self._turn_complete_event = asyncio.Event()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def notify_turn_complete(self) -> None:
        """Jarvis'in bir tura verdigi sesli yanit bitince (ws_server'dan)
        cagirilir; suren sohbet dongusu bir sonraki dinlemeye buradan devam eder."""
        self._turn_complete_event.set()

    async def _wait_for_turn_complete(self, timeout: float = 30) -> None:
        try:
            await asyncio.wait_for(self._turn_complete_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    async def run(self) -> None:
        self._mic_unavailable = False
        await self._on_wake_status(True)
        try:
            while not self._mic_unavailable:
                await self.run_iteration()
        finally:
            await self._on_wake_status(False)

    async def run_iteration(self) -> None:
        if self._paused:
            await asyncio.sleep(0.2)
            return

        try:
            text = await asyncio.to_thread(self._listen_once)
        except OSError:
            self._mic_unavailable = True
            return

        if text is None:
            return

        remainder = extract_command_after_wake_word(text)
        if remainder is None:
            return

        if remainder == "":
            self._turn_complete_event.clear()
            await self._on_wake_trigger()
            await self._wait_for_turn_complete()
            follow_up = await asyncio.to_thread(self._listen_once, timeout=8, phrase_time_limit=10)
        else:
            follow_up = remainder

        await self._converse(follow_up)

    async def _converse(self, first_command: str | None) -> None:
        """Tetiklendikten sonraki turu ve ardindan gelen dogal sohbeti
        yonetir. 'asistan' tekrar soylenmez; bir durdurma ifadesi soylenene
        ya da art arda sessizlik olusana kadar surer."""
        command = first_command
        silence_streak = 0
        while True:
            if not command:
                silence_streak += 1
                if silence_streak >= _SILENCE_LIMIT:
                    return
            else:
                silence_streak = 0
                if _is_stop_phrase(command):
                    # Kullanici duydugunu/durdugunu sessizce degil, kisa bir
                    # kapanis cumlesiyle (Gemini uzerinden) anlasin.
                    self._turn_complete_event.clear()
                    await self._on_conversation_end()
                    await self._wait_for_turn_complete()
                    return
                self._turn_complete_event.clear()
                await self._on_command(command)
                await self._wait_for_turn_complete()

            command = await asyncio.to_thread(self._listen_once, timeout=8, phrase_time_limit=10)

    def _listen_once(self, timeout: float = 5, phrase_time_limit: float = 4) -> str | None:
        with self._microphone_factory() as source:
            # Sabit varsayılan energy_threshold gerçek mikrofon/ortam gürültüsüne göre
            # çok yüksek kalabilir (konuşma hiç "başladı" sayılmaz); her denemede kısa
            # bir kalibrasyonla eşiği ortama göre ayarla.
            self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                return None
        audio = _normalize_audio(audio)
        try:
            return self._recognizer.recognize_google(audio, language="tr-TR")
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            return None
        except OSError:
            return None
