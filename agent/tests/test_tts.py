import asyncio
import subprocess

import pytest

from agent.tools.tts import synthesize_speech


class FakeCommunicate:
    def __init__(self, text, voice):
        self.text = text
        self.voice = voice

    async def stream(self):
        yield {"type": "audio", "data": b"raw-mp3-bytes-1"}
        yield {"type": "WordBoundary", "offset": 0, "duration": 100, "text": "x"}
        yield {"type": "audio", "data": b"raw-mp3-bytes-2"}


def test_synthesize_speech_passes_text_and_voice_to_communicate():
    captured = {}

    class CapturingCommunicate(FakeCommunicate):
        def __init__(self, text, voice):
            captured["text"] = text
            captured["voice"] = voice
            super().__init__(text, voice)

    result = asyncio.run(
        synthesize_speech(
            "merhaba",
            voice="tr-TR-AhmetNeural",
            communicate_cls=CapturingCommunicate,
            ffmpeg_runner=lambda raw: b"\x00\x01" * 4,
        )
    )

    assert captured == {"text": "merhaba", "voice": "tr-TR-AhmetNeural"}
    assert result == b"\x00\x01" * 4


def test_synthesize_speech_concatenates_only_audio_chunks_before_ffmpeg():
    seen_raw = {}

    def fake_ffmpeg(raw_audio):
        seen_raw["value"] = raw_audio
        return b"pcm-output"

    result = asyncio.run(
        synthesize_speech("merhaba", communicate_cls=FakeCommunicate, ffmpeg_runner=fake_ffmpeg)
    )

    assert seen_raw["value"] == b"raw-mp3-bytes-1raw-mp3-bytes-2"
    assert result == b"pcm-output"


def test_synthesize_speech_uses_default_voice_when_not_given():
    captured = {}

    class CapturingCommunicate(FakeCommunicate):
        def __init__(self, text, voice):
            captured["voice"] = voice
            super().__init__(text, voice)

    asyncio.run(
        synthesize_speech(
            "merhaba", communicate_cls=CapturingCommunicate, ffmpeg_runner=lambda raw: b""
        )
    )

    assert captured["voice"] == "tr-TR-AhmetNeural"


def test_synthesize_speech_propagates_ffmpeg_timeout_instead_of_hanging():
    # ffmpeg gercekten takilirsa subprocess.run(timeout=...) bir
    # TimeoutExpired firlatir — bunun sessizce yutulmadan yukari (cagiran
    # _synthesize_and_broadcast'in "except Exception" blogunun yakalayabilecegi
    # sekilde) yayildigini dogruluyoruz. Gercek 30 saniye beklemek yerine
    # ffmpeg_runner'i direkt TimeoutExpired firlatacak sekilde enjekte ediyoruz.
    def hanging_ffmpeg(raw_audio):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)

    with pytest.raises(subprocess.TimeoutExpired):
        asyncio.run(
            synthesize_speech("merhaba", communicate_cls=FakeCommunicate, ffmpeg_runner=hanging_ffmpeg)
        )


def test_synthesize_speech_stream_timeout_raises_instead_of_hanging_forever():
    # edge-tts'in agi hic yanit vermeden takilirsa (`communicate.stream()`
    # hic bitmezse) bu, tum Gemini Live alma dongusunu sonsuza kadar
    # kilitlerdi. Gercek 30 saniye beklemeden bu yolu tetiklemek icin cok
    # kisa bir stream_timeout ve gercekten hic bitmeyen sahte bir stream
    # kullaniyoruz.
    class HangingCommunicate:
        def __init__(self, text, voice):
            pass

        async def stream(self):
            await asyncio.sleep(3600)
            yield {"type": "audio", "data": b"never"}  # pragma: no cover

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(
            synthesize_speech(
                "merhaba",
                communicate_cls=HangingCommunicate,
                ffmpeg_runner=lambda raw: b"",
                stream_timeout=0.01,
            )
        )


def test_synthesize_speech_real_edge_tts_and_ffmpeg_produce_even_length_pcm():
    """Gerçek edge-tts + ffmpeg entegrasyonunun bozulmadığını kontrol eden
    tek canlı test (ağ + ffmpeg gerektirir) — test_terminal.py'nin gerçek
    subprocess testiyle aynı desen."""
    result = asyncio.run(synthesize_speech("merhaba dünya"))

    assert len(result) > 0
    assert len(result) % 2 == 0  # PCM16 = örnek başına 2 bayt
