from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass
class JarvisConfig:
    gemini_api_key: str
    ws_host: str
    ws_port: int
    gemini_model: str
    gemini_voice: str
    weather_location: str
    report_projects: str
    mode: str
    search_root: str


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
        gemini_voice=env.get("JARVIS_GEMINI_VOICE", "Kore"),
        weather_location=env.get("JARVIS_WEATHER_LOCATION", ""),
        report_projects=env.get("JARVIS_REPORT_PROJECTS", ""),
        mode=env.get("JARVIS_MODE", "rahat"),
        search_root=env.get("JARVIS_SEARCH_ROOT", ""),
    )
