from dataclasses import dataclass
import os

from dotenv import load_dotenv


_TTS_VOICE_IDS = {
    "Ahmet": "tr-TR-AhmetNeural",
    "Emel": "tr-TR-EmelNeural",
}
_DEFAULT_TTS_VOICE_ID = _TTS_VOICE_IDS["Ahmet"]


@dataclass
class JarvisConfig:
    gemini_api_key: str
    ws_host: str
    ws_port: int
    gemini_model: str
    weather_location: str
    report_projects: str
    mode: str
    search_root: str
    tts_voice: str


def load_config(env: dict | None = None) -> JarvisConfig:
    """Build a JarvisConfig. Pass `env` in tests to avoid touching real
    environment variables or the .env file."""
    if env is None:
        load_dotenv(os.environ.get("JARVIS_ENV_PATH") or None)
        env = os.environ

    return JarvisConfig(
        gemini_api_key=env.get("GEMINI_API_KEY", ""),
        ws_host=env.get("JARVIS_WS_HOST", "127.0.0.1"),
        ws_port=int(env.get("JARVIS_WS_PORT", "8765")),
        gemini_model=env.get("JARVIS_GEMINI_MODEL", "gemini-3.1-flash-live-preview"),
        weather_location=env.get("JARVIS_WEATHER_LOCATION", ""),
        report_projects=env.get("JARVIS_REPORT_PROJECTS", ""),
        mode=env.get("JARVIS_MODE", "rahat"),
        search_root=env.get("JARVIS_SEARCH_ROOT", ""),
        tts_voice=_TTS_VOICE_IDS.get(env.get("JARVIS_TTS_VOICE", "Ahmet"), _DEFAULT_TTS_VOICE_ID),
    )
