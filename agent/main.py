import asyncio
import logging
import sys

from google import genai

from agent.config import load_config
from agent.gemini.live_session import LiveSession
from agent.tools.registry import build_tool_registry
from agent.tools.report import parse_report_projects
from agent.wake_word import WakeWordListener
from agent.ws_server import JarvisServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)


def build_components() -> tuple[JarvisServer, LiveSession, WakeWordListener]:
    config = load_config()
    client = genai.Client(api_key=config.gemini_api_key)
    report_projects = parse_report_projects(config.report_projects)
    tools = build_tool_registry(
        client,
        weather_default_location=config.weather_location,
        report_projects=report_projects,
        search_default_root=config.search_root,
    )

    server = JarvisServer(
        host=config.ws_host,
        port=config.ws_port,
        weather_default_location=config.weather_location,
    )

    live_session = LiveSession(
        client=client,
        model=config.gemini_model,
        voice=config.gemini_voice,
        tools=tools,
        on_event=server.handle_live_event,
        mode=config.mode,
    )

    wake_word_listener = WakeWordListener(
        on_command=server.handle_wake_command,
        on_wake_status=server.handle_wake_status,
        on_wake_trigger=server.handle_wake_trigger,
        on_conversation_end=server.handle_conversation_end,
    )

    server.live_session = live_session
    server.wake_word_listener = wake_word_listener

    return server, live_session, wake_word_listener


async def _attempt_live_session(live_session: LiveSession, on_error, backoff_seconds: float) -> None:
    """Tek bir bağlantı denemesi. `live_session.run()` hata fırlatırsa (bağlantı
    koptu/kurulamadı) `on_error` ile HUD'a bildirir ve backoff kadar bekler;
    normal döndüyse (örn. sunucu oturumu kapattı) sessizce döner — her iki
    durumda da çağıran taraf (bkz. `run_live_session_with_backoff`) yeniden
    dener."""
    try:
        await live_session.run()
    except Exception as error:
        logger.warning("Gemini Live bağlantısı koptu: %s", error)
        await on_error(str(error))
        await asyncio.sleep(backoff_seconds)


async def run_live_session_with_backoff(live_session: LiveSession, on_error, backoff_seconds: float = 5) -> None:
    while True:
        await _attempt_live_session(live_session, on_error, backoff_seconds)


async def main_async() -> None:
    server, live_session, wake_word_listener = build_components()
    logger.info("Jarvis agent başlatılıyor...")

    async def on_live_error(message: str) -> None:
        await server.handle_live_event({"type": "error", "message": message})

    await asyncio.gather(
        server.serve_forever(),
        run_live_session_with_backoff(live_session, on_live_error),
        wake_word_listener.run(),
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
