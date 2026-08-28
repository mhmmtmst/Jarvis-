import asyncio
import logging

from google.genai import types

from agent.memory import format_memory_for_prompt, load_memory
from agent.persona import build_persona
from agent.tools.registry import ToolSpec

logger = logging.getLogger(__name__)


class LiveSession:
    """Tek, kalıcı bir Gemini Live oturumunu sarar. Olayları `on_event` ile
    (düz dict) dışarı verir; bu sayede ws_server bu modülün WebSocket'ten
    hiç haberdar olmasına gerek kalmadan olayları frame'e çevirebilir."""

    def __init__(
        self, client, model: str, tools: dict[str, ToolSpec], on_event,
        memory_loader=None, mode: str = "rahat",
    ):
        self._client = client
        self._model = model
        self._tools = tools
        self._on_event = on_event
        self._memory_loader = memory_loader if memory_loader is not None else load_memory
        self._mode = mode
        self._session = None
        self._pending_agent_text = ""

    def _build_system_instruction(self) -> str:
        # Live API'de system_instruction sadece baglanti kurulurken bir kere
        # gonderilir (oturum icinde canli guncellenemez); o yuzden hafiza
        # burada, her yeniden baglantida taze okunur.
        persona = build_persona(self._mode)
        memory_block = format_memory_for_prompt(self._memory_loader())
        if not memory_block:
            return persona
        return f"{persona}\n\n{memory_block}"

    def _build_config(self) -> types.LiveConnectConfig:
        tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=spec.name,
                    description=spec.description,
                    parameters_json_schema=spec.parameters,
                )
                for spec in self._tools.values()
            ]
        )
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self._build_system_instruction(),
            tools=[tool],
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

    async def run(self) -> None:
        config = self._build_config()
        async with self._client.aio.live.connect(model=self._model, config=config) as session:
            logger.info("Gemini Live oturumu kuruldu (model=%s)", self._model)
            self._session = session
            await self._on_event({"type": "session_ready"})
            async for message in session.receive():
                await self._handle_message(message)

    async def send_text(self, text: str) -> None:
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part.from_text(text=text)]),
            turn_complete=True,
        )

    async def start_activity(self) -> None:
        await self._session.send_realtime_input(activity_start=types.ActivityStart())

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
        )

    async def end_activity(self) -> None:
        await self._session.send_realtime_input(activity_end=types.ActivityEnd())

    async def _handle_message(self, message) -> None:
        if message.tool_call is not None:
            await self._handle_tool_call(message.tool_call)
            return

        content = message.server_content
        if content is None:
            return

        if content.interrupted:
            await self._on_event({"type": "interrupted"})

        if content.input_transcription is not None and content.input_transcription.text:
            await self._on_event({"type": "transcript", "role": "user", "text": content.input_transcription.text})

        if content.output_transcription is not None and content.output_transcription.text:
            text = content.output_transcription.text
            self._pending_agent_text += text
            await self._on_event({"type": "transcript", "role": "agent", "text": text})

        if content.turn_complete:
            if self._pending_agent_text:
                await self._on_event({"type": "agent_text_complete", "text": self._pending_agent_text})
            self._pending_agent_text = ""
            await self._on_event({"type": "turn_complete"})

    async def _handle_tool_call(self, tool_call) -> None:
        responses = []
        for call in tool_call.function_calls:
            tool = self._tools.get(call.name)
            if tool is None:
                result = {"status": "error", "message": f"Bilinmeyen araç: {call.name}"}
            else:
                try:
                    result = await asyncio.to_thread(tool.handler, **(call.args or {}))
                except Exception as error:
                    result = {"status": "error", "message": f"{call.name} çalıştırılamadı: {error}"}
            responses.append(types.FunctionResponse(id=call.id, name=call.name, response=result))
        await self._session.send_tool_response(function_responses=responses)
