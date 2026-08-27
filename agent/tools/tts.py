import asyncio
import subprocess

import edge_tts

_SAMPLE_RATE_HZ = 24000
_DEFAULT_VOICE = "tr-TR-AhmetNeural"
# `handle_live_event` bu fonksiyonu Gemini'nin mesaj alma dongusundan senkron
# olarak bekliyor (await) — edge-tts'in agi kilitlenirse ya da ffmpeg
# takilirsa zaman asimi olmadan TUM Gemini Live dongusu sonsuza kadar
# durur. Her iki asama icin de mantikli bir ust sinir konuyor.
_FFMPEG_TIMEOUT_SECONDS = 30
_STREAM_TIMEOUT_SECONDS = 30


async def synthesize_speech(
    text: str,
    voice: str = _DEFAULT_VOICE,
    communicate_cls=None,
    ffmpeg_runner=None,
    stream_timeout: float = _STREAM_TIMEOUT_SECONDS,
) -> bytes:
    """Edge-TTS ile `text`'i sentezler, ffmpeg ile PCM16 24kHz mono bayta
    çevirip döner. Edge-TTS'in gerçek çıktısı audio-24khz-48kbitrate-mono-mp3
    (kaynak koddan doğrulandı); ffmpeg girdi formatını otomatik algıladığı
    için burada codec'i ayrıca belirtmeye gerek yok.
    `communicate_cls`/`ffmpeg_runner` testte enjekte edilir; `stream_timeout`
    testte gerçek 30 saniye beklemeden zaman aşımı yolunu tetiklemek için
    kısa bir değerle geçilebilir."""
    if communicate_cls is None:
        communicate_cls = edge_tts.Communicate
    if ffmpeg_runner is None:
        ffmpeg_runner = _run_ffmpeg

    communicate = communicate_cls(text, voice)
    raw_audio = bytearray()

    async def _consume_stream() -> None:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                raw_audio.extend(chunk["data"])

    # edge-tts gercekten reverse-engineer edilmis, resmi olmayan bir API —
    # sunucu tarafinda takilip hic yanit vermeyen bir baglanti bu bekleme
    # olmadan sonsuza kadar surerdi.
    await asyncio.wait_for(_consume_stream(), timeout=stream_timeout)

    return await asyncio.to_thread(ffmpeg_runner, bytes(raw_audio))


def _run_ffmpeg(raw_audio: bytes) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-ar", str(_SAMPLE_RATE_HZ), "-ac", "1", "pipe:1"],
        input=raw_audio,
        capture_output=True,
        check=True,
        timeout=_FFMPEG_TIMEOUT_SECONDS,
    )
    return result.stdout
