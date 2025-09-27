#!/usr/bin/env python3
"""
Proper Letta Voice Agent with Cartesia TTS
Uses the correct LiveKit AgentSession API
"""

import os
import asyncio
from dotenv import load_dotenv
from letta_client import Letta
from letta_client.types.message_create import MessageCreate

from livekit import agents
from livekit.agents import AgentSession, Agent, AutoSubscribe
from livekit.plugins import deepgram, cartesia
from livekit.agents.llm import (
    LLM,
    LLMStream,
    ChatContext,
    ChatRole,
    ChatChunk,
    ChoiceDelta,
    AudioContent,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from typing import AsyncIterator
from contextlib import asynccontextmanager

load_dotenv()

# Environment variables
LETTA_AGENT_ID = os.getenv('LETTA_AGENT_ID')
LETTA_BASE_URL = os.getenv('LETTA_BASE_URL')
LIVEKIT_URL = os.getenv('LIVEKIT_URL')
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
CARTESIA_API_KEY = os.getenv('CARTESIA_API_KEY')

if not all([LETTA_AGENT_ID, LETTA_BASE_URL, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, DEEPGRAM_API_KEY, CARTESIA_API_KEY]):
    raise ValueError("Missing required environment variables")

# Initialize Letta client
letta_client = Letta(base_url=LETTA_BASE_URL)

# Custom Letta LLM to bypass LiveKit plugin's cloud-specific integration
class LettaLLM(LLM):
    def __init__(self, letta_client, agent_id):
        super().__init__()
        self.letta_client = letta_client
        self.agent_id = agent_id

    @asynccontextmanager
    async def chat(
        self,
        chat_ctx: ChatContext = None,
        *,
        ctx: ChatContext = None,
        fnc_ctx: dict = None,
        **kwargs,
    ) -> AsyncIterator[LLMStream]:
        """Bridge LiveKit chat requests to the Letta client."""

        context = chat_ctx or ctx
        if context is None:
            raise ValueError("Chat context was not provided to LettaLLM.chat")

        # Build messages list, supporting both list and object-style contexts
        if isinstance(context, ChatContext):
            raw_messages = list(context.items)
        elif isinstance(context, dict):
            raw_messages = context.get("messages") or []
        elif isinstance(context, (list, tuple)):
            raw_messages = list(context)
        else:
            raw_messages = []

        def _coerce_text(part) -> str:
            if isinstance(part, str):
                return part

            if isinstance(part, dict):
                for key in ("text", "content", "value"):
                    val = part.get(key)
                    if isinstance(val, str):
                        return val
                    if isinstance(val, list):
                        joined = "\n".join(filter(None, (_coerce_text(p) for p in val)))
                        if joined:
                            return joined

                inner = part.get("data") or part.get("args")
                if isinstance(inner, (str, list)):
                    return _coerce_text(inner) if isinstance(inner, str) else "\n".join(filter(None, (_coerce_text(p) for p in inner)))

            if isinstance(part, AudioContent):
                if part.transcript:
                    return part.transcript

            text_attr = getattr(part, "text", None)
            if isinstance(text_attr, str) and text_attr:
                return text_attr

            transcript_attr = getattr(part, "transcript", None)
            if isinstance(transcript_attr, str) and transcript_attr:
                return transcript_attr

            content_attr = getattr(part, "content", None)
            if isinstance(content_attr, str) and content_attr:
                return content_attr

            if isinstance(part, list):
                return "\n".join(filter(None, (_coerce_text(p) for p in part)))

            return ""

        messages = []
        for msg in raw_messages:
            msg_type = getattr(msg, "type", "message")
            if msg_type not in ("message", None):
                continue

            role = getattr(msg, "role", "user") or "user"

            if role not in {"user", "assistant", "system", "developer"}:
                normalized_role = "user"
            else:
                normalized_role = role if isinstance(role, str) else str(role)

            text_content = getattr(msg, "text_content", None)
            if not text_content:
                content_value = getattr(msg, "content", "")
                if isinstance(content_value, list):
                    text_content = "\n".join(
                        filter(None, (_coerce_text(part) for part in content_value))
                    )
                elif isinstance(content_value, AudioContent):
                    text_content = content_value.transcript or ""
                else:
                    coalesced = _coerce_text(content_value)
                    text_content = coalesced if coalesced else str(content_value) if content_value else ""

            messages.append({
                "role": normalized_role,
                "content": text_content or "",
            })

        user_message = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user" and m["content"]),
            None,
        )
        if not user_message:
            user_message = messages[-1]["content"] if messages else "Hello"
        print(f"🤖 Sending to Letta: {user_message}")

        try:
            # Send message to Letta agent
            message = MessageCreate(
                role="user",
                content=user_message
            )
            response = self.letta_client.agents.messages.create(
                agent_id=self.agent_id,
                messages=[message]
            )

            # Extract response text from the messages
            response_text = "I received your message. How can I help you?"
            if hasattr(response, 'messages') and response.messages:
                for msg in response.messages:
                    if hasattr(msg, 'message_type') and msg.message_type == 'assistant_message':
                        if hasattr(msg, 'content') and msg.content:
                            response_text = msg.content
                            break

            print(f"🎯 Letta response: {response_text}")

        except Exception as e:
            print(f"❌ Error calling Letta: {e}")
            response_text = f"I'm sorry, I encountered an error: {e}"

        class LettaStream(LLMStream):
            def __init__(
                self,
                llm: "LettaLLM",
                chat_ctx: ChatContext,
                response_text: str,
            ):
                super().__init__(
                    llm,
                    chat_ctx=chat_ctx,
                    tools=[],
                    conn_options=DEFAULT_API_CONNECT_OPTIONS,
                )
                self._response_text = response_text

            async def _run(self) -> None:
                chunk = ChatChunk(
                    id="letta-response",
                    delta=ChoiceDelta(role="assistant", content=self._response_text),
                )
                self._event_ch.send_nowait(chunk)

            def to_text_iterable(self) -> AsyncIterator[str]:
                async def _iter() -> AsyncIterator[str]:
                    yield self._response_text

                return _iter()

        stream = LettaStream(self, context, response_text)
        try:
            yield stream
        finally:
            await stream.aclose()

async def entrypoint(ctx: agents.JobContext):
    print("🎤 PROPER CARTESIA VOICE AGENT")
    print(f"Using agent id: {LETTA_AGENT_ID}")
    print(f"Using base URL: {LETTA_BASE_URL}")

    # Set a dummy API key for LiveKit plugin if not set, for self-hosted Letta
    if not os.getenv('LETTA_API_KEY'):
        os.environ['LETTA_API_KEY'] = 'self-hosted-letta-token'

    # Use custom LettaLLM
    llm = LettaLLM(letta_client=letta_client, agent_id=LETTA_AGENT_ID)
    
    # Use Cartesia TTS (proper implementation)
    tts = cartesia.TTS(api_key=CARTESIA_API_KEY)
    print("🔊 Using Cartesia TTS")
    
    # Use Deepgram STT
    stt = deepgram.STT(api_key=DEEPGRAM_API_KEY)
    print("🎤 Using Deepgram STT")
    
    session = AgentSession(
        llm=llm,
        stt=stt,
        tts=tts,
    )
    
    await session.start(
        room=ctx.room,
        agent=Agent(instructions="You are a helpful voice assistant powered by Letta."),
    )
    
    print("🎤 Voice agent ready! Say something...")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

if __name__ == "__main__":
    # Set the specific agent ID you want to use
    os.environ['LETTA_AGENT_ID'] = 'agent-f33376c1-ef6a-4a52-add3-afddec3b6628'
    
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
