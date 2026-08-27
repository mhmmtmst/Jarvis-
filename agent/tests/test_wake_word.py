import asyncio

import pytest
import speech_recognition as sr

from agent.wake_word import (
    OpenWakeWordDetector,
    WakeWordListener,
    _is_stop_phrase,
    _normalize_audio,
    extract_command_after_wake_word,
)


def test_returns_none_when_wake_word_absent():
    assert extract_command_after_wake_word("bugün hava nasıl") is None


def test_returns_empty_string_when_wake_word_alone():
    assert extract_command_after_wake_word("asistan") == ""
    assert extract_command_after_wake_word("Asistan!") == ""


def test_returns_remainder_after_wake_word():
    assert extract_command_after_wake_word("asistan saati söyle") == "saati söyle"


def test_is_case_and_turkish_char_insensitive():
    assert extract_command_after_wake_word("ASİSTAN not defterini aç") == "not defterini aç"


def test_ignores_wake_word_as_substring_of_another_word():
    assert extract_command_after_wake_word("asistanimsi bir şey") is None


def test_is_stop_phrase_matches_known_phrases_case_and_turkish_insensitive():
    assert _is_stop_phrase("dur") is True
    assert _is_stop_phrase("Teşekkürler!") is True
    assert _is_stop_phrase("Sağ ol.") is True


def test_is_stop_phrase_rejects_ordinary_commands():
    assert _is_stop_phrase("saati söyle") is False


def test_is_stop_phrase_matches_phrase_with_extra_surrounding_words():
    assert _is_stop_phrase("Çok teşekkürler") is True
    assert _is_stop_phrase("Tamam sağ ol") is True
    assert _is_stop_phrase("İyi bir gün geçir, hoşça kal") is True


def test_is_stop_phrase_does_not_match_word_containing_stop_phrase_as_substring():
    assert _is_stop_phrase("durumu kontrol et") is False


def _tone_audio_data(peak: int, sample_width: int = 2, sample_rate: int = 44100, n: int = 200) -> sr.AudioData:
    import audioop

    frame = peak.to_bytes(sample_width, byteorder="little", signed=True)
    return sr.AudioData(frame * n, sample_rate, sample_width)


def test_normalize_audio_boosts_quiet_capture_toward_target_peak():
    import audioop

    quiet = _tone_audio_data(peak=1208)

    boosted = _normalize_audio(quiet)

    boosted_peak = audioop.max(boosted.get_raw_data(), boosted.sample_width)
    assert boosted_peak > 1208
    assert boosted.sample_rate == quiet.sample_rate
    assert boosted.sample_width == quiet.sample_width


def test_normalize_audio_leaves_already_loud_capture_unchanged():
    loud = _tone_audio_data(peak=25000)

    result = _normalize_audio(loud)

    assert result.get_raw_data() == loud.get_raw_data()


def test_normalize_audio_leaves_silence_unchanged():
    silence = sr.AudioData(b"\x00\x00" * 200, 44100, 2)

    result = _normalize_audio(silence)

    assert result.get_raw_data() == silence.get_raw_data()


def test_normalize_audio_caps_gain_for_near_silent_capture():
    import audioop

    near_silent = _tone_audio_data(peak=5)

    boosted = _normalize_audio(near_silent)

    boosted_peak = audioop.max(boosted.get_raw_data(), boosted.sample_width)
    assert boosted_peak == 5 * 20  # _MAX_GAIN uygulandı, hedef tepeye zıplamadı


# --- OpenWakeWordDetector (aktif kullanilmiyor, "asistan" icin ozel model egitilirse gerekecek) ---


class FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.stopped = False
        self.closed = False

    def read(self, n, exception_on_overflow=False):
        return self._chunks.pop(0)

    def stop_stream(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FakePyAudioInstance:
    def __init__(self, stream):
        self._stream = stream
        self.terminated = False

    def open(self, **kwargs):
        return self._stream

    def terminate(self):
        self.terminated = True


class FakePyAudioModule:
    paInt16 = 8

    def __init__(self, stream):
        self._stream = stream
        self.instance = None

    def PyAudio(self):
        self.instance = FakePyAudioInstance(self._stream)
        return self.instance


class FailingPyAudioInstance:
    def open(self, **kwargs):
        raise OSError("mikrofon açılamadı")

    def terminate(self):
        pass


class FailingPyAudioModule:
    paInt16 = 8

    def PyAudio(self):
        return FailingPyAudioInstance()


class FakeOWWModel:
    def __init__(self, scores_sequence, keyword="hey_jarvis"):
        self._scores_sequence = list(scores_sequence)
        self.keyword = keyword
        self.reset_called = False

    def reset(self):
        self.reset_called = True

    def predict(self, audio):
        score = self._scores_sequence.pop(0)
        return {self.keyword: score}


def _silent_chunk() -> bytes:
    return b"\x00\x00" * 1280


def test_open_wake_word_detector_returns_true_once_threshold_crossed():
    stream = FakeStream([_silent_chunk(), _silent_chunk(), _silent_chunk()])
    pa_module = FakePyAudioModule(stream)
    model = FakeOWWModel([0.1, 0.3, 0.9])

    detector = OpenWakeWordDetector(model=model, threshold=0.5, keyword="hey_jarvis", pyaudio_module=pa_module)

    assert detector.wait_for_wake() is True
    assert model.reset_called is True
    assert stream.stopped is True
    assert stream.closed is True
    assert pa_module.instance.terminated is True


def test_open_wake_word_detector_keeps_reading_below_threshold():
    stream = FakeStream([_silent_chunk(), _silent_chunk()])
    pa_module = FakePyAudioModule(stream)
    model = FakeOWWModel([0.2, 0.7])

    detector = OpenWakeWordDetector(model=model, threshold=0.5, pyaudio_module=pa_module)

    assert detector.wait_for_wake() is True


def test_open_wake_word_detector_propagates_oserror_when_mic_unavailable():
    detector = OpenWakeWordDetector(model=FakeOWWModel([]), pyaudio_module=FailingPyAudioModule())

    with pytest.raises(OSError):
        detector.wait_for_wake()


# --- WakeWordListener ---


class FakeRecognizer:
    """`transcripts` bitince listen() WaitTimeoutError firlatir — gercek
    sessizligi simule eder, boylece suren sohbet dongusu dogal olarak biter."""

    def __init__(self, transcripts):
        self._transcripts = list(transcripts)
        self.ambient_noise_calls = 0
        self.listen_calls = 0

    def recognize_google(self, audio, language="tr-TR"):
        result = self._transcripts.pop(0)
        if result is None:
            raise LookupError("recognize_google should not be called without audio")
        return result

    def listen(self, source, timeout=None, phrase_time_limit=None):
        self.listen_calls += 1
        if not self._transcripts:
            raise sr.WaitTimeoutError()
        return sr.AudioData(b"\x00\x00" * 100, 44100, 2)

    def adjust_for_ambient_noise(self, source, duration=0.5):
        self.ambient_noise_calls += 1


class FakeMicrophoneContext:
    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False


def make_listener(transcripts, commands, wake_statuses, wake_triggers=None, conversation_ends=None):
    box = {}

    async def on_command(text):
        commands.append(text)
        box["listener"].notify_turn_complete()

    async def on_wake_status(active):
        wake_statuses.append(active)

    async def on_wake_trigger():
        if wake_triggers is not None:
            wake_triggers.append(True)
        box["listener"].notify_turn_complete()

    async def on_conversation_end():
        if conversation_ends is not None:
            conversation_ends.append(True)
        box["listener"].notify_turn_complete()

    listener = WakeWordListener(
        on_command=on_command,
        on_wake_status=on_wake_status,
        on_wake_trigger=on_wake_trigger,
        on_conversation_end=on_conversation_end,
        recognizer=FakeRecognizer(transcripts),
        microphone_factory=lambda: FakeMicrophoneContext(),
    )
    box["listener"] = listener
    return listener


def test_run_iteration_dispatches_command_when_wake_word_and_command_together():
    commands, statuses = [], []
    listener = make_listener(["asistan saati söyle"], commands, statuses)

    asyncio.run(listener.run_iteration())

    assert commands == ["saati söyle"]


def test_run_iteration_does_nothing_when_no_wake_word():
    commands, statuses = [], []
    listener = make_listener(["bugün hava nasıl"], commands, statuses)

    asyncio.run(listener.run_iteration())

    assert commands == []


def test_run_iteration_greets_then_listens_again_when_wake_word_alone():
    commands, statuses, triggers = [], [], []
    listener = make_listener(["asistan", "not defterini aç"], commands, statuses, triggers)

    asyncio.run(listener.run_iteration())

    assert triggers == [True]
    assert commands == ["not defterini aç"]


def test_run_iteration_calibrates_ambient_noise():
    commands, statuses = [], []
    listener = make_listener(["asistan saati söyle"], commands, statuses)

    asyncio.run(listener.run_iteration())

    assert listener._recognizer.ambient_noise_calls >= 1


def test_run_iteration_continues_conversation_without_repeating_wake_word():
    commands, statuses = [], []
    listener = make_listener(
        ["asistan saati söyle", "hava nasıl", "teşekkürler"],
        commands,
        statuses,
    )

    asyncio.run(listener.run_iteration())

    assert commands == ["saati söyle", "hava nasıl"]


def test_run_iteration_stop_phrase_ends_conversation_without_dispatching_it():
    commands, statuses, ends = [], [], []
    listener = make_listener(["asistan saati söyle", "dur"], commands, statuses, conversation_ends=ends)

    asyncio.run(listener.run_iteration())

    assert commands == ["saati söyle"]


def test_run_iteration_stop_phrase_triggers_closing_remark():
    commands, statuses, ends = [], [], []
    listener = make_listener(["asistan", "teşekkürler"], commands, statuses, conversation_ends=ends)

    asyncio.run(listener.run_iteration())

    assert ends == [True]


def test_run_iteration_ends_conversation_after_repeated_silence():
    commands, statuses = [], []
    listener = make_listener(["asistan saati söyle"], commands, statuses)

    asyncio.run(listener.run_iteration())

    # transcripts tukendikten sonra listen() surekli WaitTimeoutError firlatir;
    # dongu (varsayilan _SILENCE_LIMIT=2) birkac denemeden sonra kendiliginden biter
    assert listener._recognizer.listen_calls >= 3


def test_paused_listener_skips_recognition():
    commands, statuses = [], []
    listener = make_listener([], commands, statuses)
    listener.pause()

    asyncio.run(listener.run_iteration())

    assert commands == []


def test_run_emits_wake_status_true_then_false_around_iterations():
    commands, statuses = [], []
    listener = make_listener(["asistan merhaba"], commands, statuses)

    call_count = {"n": 0}
    original = listener.run_iteration

    async def run_once_then_stop():
        call_count["n"] += 1
        await original()
        if call_count["n"] >= 1:
            raise StopAsyncIteration

    listener.run_iteration = run_once_then_stop

    async def scenario():
        try:
            await listener.run()
        except StopAsyncIteration:
            pass

    asyncio.run(scenario())

    assert statuses == [True, False]
    assert commands == ["merhaba"]


class FailingMicrophoneFactory:
    def __call__(self):
        raise OSError("mikrofon açılamadı")


def test_run_disables_itself_and_reports_wake_status_false_when_mic_unavailable():
    commands, statuses = [], []

    async def on_command(text):
        commands.append(text)

    async def on_wake_status(active):
        statuses.append(active)

    async def on_wake_trigger():
        pass

    async def on_conversation_end():
        pass

    listener = WakeWordListener(
        on_command=on_command,
        on_wake_status=on_wake_status,
        on_wake_trigger=on_wake_trigger,
        on_conversation_end=on_conversation_end,
        recognizer=FakeRecognizer([]),
        microphone_factory=FailingMicrophoneFactory(),
    )

    asyncio.run(listener.run())

    assert statuses == [True, False]
    assert commands == []
