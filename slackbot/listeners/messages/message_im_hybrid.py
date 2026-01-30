# listeners/messages/message_im.py
import os
import threading
import time
from logging import Logger
from typing import Dict, List, Optional, Tuple

from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ai.providers.letta_stream import LettaAPIStreaming
from ai.conversation_helper import get_conversation_for_user
from listeners.messages.status_messages import get_status_for_tool, get_default_status

MAX_SLACK_MESSAGE_LENGTH = 3500  # Slack hard limit is 4000 characters; keep buffer for formatting
MAX_STREAM_PREVIEW_LENGTH = 1200

_STREAM_FLAG_VALUES = {"1", "true", "yes", "on"}


def _is_streaming_enabled() -> bool:
    return os.getenv("ENABLE_SLACK_STREAMING", "false").strip().lower() in _STREAM_FLAG_VALUES


def _set_assistant_status(
    client: WebClient,
    logger: Logger,
    channel_id: str,
    thread_ts: str,
    status: str,
    loading_messages: Optional[List[str]] = None,
) -> None:
    try:
        # Build kwargs - only include loading_messages if explicitly provided
        # Passing loading_messages=None may trigger Slack's default bubble behavior
        kwargs = {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "status": status,
        }
        if loading_messages is not None:
            kwargs["loading_messages"] = loading_messages

        logger.error(f"🚀 CALLING assistant_threads_setStatus: {kwargs}")
        result = client.assistant_threads_setStatus(**kwargs)
        logger.error(f"✅ assistant_threads_setStatus SUCCESS: {result}")
    except Exception as error:  # pragma: no cover - non-critical feedback
        logger.error(
            f"❌ assistant_threads_setStatus FAILED (status={status}, channel={channel_id}, ts={thread_ts}): {error}",
            exc_info=True,
        )


def _show_typing_indicator(
    client: WebClient,
    logger: Logger,
    channel_id: str,
    stop_event: threading.Event,
) -> None:
    """Show native typing indicator, refreshing every 2 seconds until stopped."""
    while not stop_event.is_set():
        try:
            client.chat_typingIndicator(channel=channel_id)
            logger.debug("Typing indicator sent for channel %s", channel_id)
        except Exception as error:
            logger.debug("typing indicator failed: %s", error)
        
        # Wait 2 seconds or until stopped
        stop_event.wait(timeout=2.0)


def _should_use_streaming(logger: Logger) -> bool:
    flag = _is_streaming_enabled()
    if not flag:
        return False
    if os.getenv("DISABLE_ASSISTANT_STREAMING", "false").strip().lower() in _STREAM_FLAG_VALUES:
        logger.info("Streaming disabled via DISABLE_ASSISTANT_STREAMING flag")
        return False
    return True


def _stream_dm_reply(
    client: WebClient,
    logger: Logger,
    channel_id: str,
    thread_ts: str,
    system_prompt: str,
    user_prompt: str,
    *,
    recipient_user_id: Optional[str] = None,
    recipient_team_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """Attempt to stream a Letta response using Slack's chat.stream helpers."""

    streamer = LettaAPIStreaming(logger=logger)
    slack_stream = None
    collected: List[str] = []

    try:
        stream_kwargs = {
            "channel": channel_id,
            "thread_ts": thread_ts,
            "buffer_size": 80,
        }
        if recipient_user_id:
            stream_kwargs["recipient_user_id"] = recipient_user_id
        if recipient_team_id:
            stream_kwargs["recipient_team_id"] = recipient_team_id
        
        logger.error(f"🚀 chat.stream kwargs: {stream_kwargs}")
        slack_stream = client.chat_stream(**stream_kwargs)

        for chunk in streamer.chat_stream(system_prompt, user_prompt):
            if not chunk:
                continue
            collected.append(chunk)
            try:
                slack_stream.append(markdown_text=chunk)
            except SlackApiError as append_error:  # pragma: no cover - Slack API failure
                logger.error(
                    "Slack append stream failed for channel=%s ts=%s: %s",
                    channel_id,
                    thread_ts,
                    append_error,
                    exc_info=True,
                )
                raise

        final_text = (streamer.last_message or "".join(collected)).strip()
        slack_stream.stop(markdown_text=final_text or " ")
        return True, final_text

    except Exception as exc:  # pragma: no cover - network/runtime issues
        logger.error("Streaming DM response failed", exc_info=True)
        fallback_text = (streamer.last_message or "".join(collected)).strip()

        if slack_stream is not None:
            try:
                slack_stream.stop(markdown_text=fallback_text or " ")
                return True, fallback_text
            except Exception:  # pragma: no cover - Slack closure failure
                logger.debug("Unable to close Slack stream cleanly", exc_info=True)

        return False, fallback_text
def _force_open_dm_channel(client: WebClient, user_id: str, logger: Logger) -> Tuple[Optional[str], Dict[str, object]]:
    debug: Dict[str, object] = {}
    try:
        response = client.conversations_open(users=[user_id])
        data = getattr(response, "data", response)
        debug["force_open"] = data
        logger.debug("force conversations.open response: %s", data)
        if response.get("ok"):
            channel_id = response.get("channel", {}).get("id")
            if channel_id:
                return channel_id, debug
    except Exception as exc:  # pragma: no cover - network failure
        logger.debug("force conversations.open failed: %s", exc)
    return None, debug



def _resolve_dm_channel(
    client: WebClient,
    user_id: Optional[str],
    fallback_channel: Optional[str],
    logger: Logger,
):
    """Try to obtain the bot-writable DM channel for the given user."""

    channel_debug: dict[str, object] = {}

    if not user_id:
        logger.error("❌ Cannot resolve DM channel: missing user_id")
        return fallback_channel, channel_debug

    try:
        open_response = client.conversations_open(users=[user_id])
        open_data = getattr(open_response, "data", open_response)
        channel_debug["conversations_open"] = open_data
        ok = open_response.get("ok")
        channel_id = open_response.get("channel", {}).get("id") if ok else None
        logger.info("conversations.open response: %s", open_data)
        if not ok:
            logger.warning("conversations.open error response: %s", open_data)
        if channel_id:
            return channel_id, channel_debug
    except Exception as open_error:  # pragma: no cover - network failure
        logger.error(f"conversations.open failed: {open_error}")

    try:
        users_conversations = client.users_conversations(types="im", limit=100)
        conv_data = getattr(users_conversations, "data", users_conversations)
        channel_debug["users_conversations"] = conv_data
        logger.info("users.conversations response: %s", conv_data)
        channels = conv_data.get("channels") or []
        if not channels:
            logger.warning("users.conversations returned no channels for user %s", user_id)
        for channel in channels:
            if channel.get("user") == user_id:
                resolved = channel.get("id")
                logger.info(
                    "users.conversations matched user %s → channel %s",
                    user_id,
                    resolved,
                )
                if resolved:
                    return resolved, channel_debug
        else:
            logger.warning(
                "users.conversations could not resolve channel for user %s; channels=%s",
                user_id,
                channels,
            )
        logger.warning(
            "users.conversations did not contain DM channel for user %s", user_id
        )
    except Exception as conv_error:  # pragma: no cover - network failure
        logger.error(f"users.conversations failed: {conv_error}")

    if fallback_channel:
        logger.warning(
            "⚠️ Falling back to event channel '%s' due to channel resolution failure",
            fallback_channel,
        )
    else:
        logger.error("❌ No DM channel available after resolution attempts")
    return fallback_channel, channel_debug


def _handle_dm(event: dict, client: WebClient, logger: Logger):
    if event.get("channel_type") != "im" or event.get("subtype"):
        return

    # Get basic event info
    channel_id = event.get("channel")
    user_id = event.get("user")
    text = (event.get("text") or "").strip()
    user_message_ts = event.get("ts")  # Used for setStatus loading animation
    streaming_enabled = _should_use_streaming(logger)

    # Set initial status with loading_messages for animated indented bubbles
    if channel_id and streaming_enabled and user_message_ts:
        default_status = get_default_status()
        _set_assistant_status(
            client,
            logger,
            channel_id,
            user_message_ts,
            status=default_status["status"],
            loading_messages=default_status["loading_messages"],
        )

    # Ignore messages sent BY the bot itself (to prevent echo loops)
    sender_user_id = user_id
    if sender_user_id:
        try:
            bot_user_id = client.auth_test().get("user_id")
            if sender_user_id == bot_user_id:
                logger.info("Ignoring DM sent by bot itself (user=%s)", sender_user_id)
                return
        except Exception as auth_err:
            logger.warning("Unable to check bot user ID: %s", auth_err)

    logger.debug("DM received from user %s in channel %s", user_id, channel_id)

    # Validate channel_id
    if not channel_id:
        logger.error(f"❌ No channel_id found in DM event!")
        return

    # Debug: Log the actual channel and user IDs received
    logger.info(
        "DM Event - Channel ID: '%s', User ID: '%s', Channel Type: '%s'",
        channel_id,
        user_id,
        event.get("channel_type"),
    )
    logger.info(f"Full DM event keys: {list(event.keys())}")

    # Use the event's channel_id directly - that's where the user sent their message
    # and where they expect the response. Don't resolve to a different channel.
    working_channel = channel_id
    logger.info(f"Using event channel for response: {working_channel}")

    try:
        # Skip conversation history due to permissions issues - mirror slash command behaviour
        conversation_context = ""

        user_prompt = (
            (f"DM so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text or 'Hello'}"

        system_prompt = "You are a helpful Slack bot. Be concise and helpful."

        # Status already set above - no need to set again

        # Get or create conversation for this user (enables per-user context isolation)
        # Falls back to None (legacy agent-level messaging) if lookup/creation fails
        conversation_id = None
        try:
            conversation_id = get_conversation_for_user(user_id, logger=logger)
            if conversation_id:
                logger.info(f"Using Letta conversation: {conversation_id} for user {user_id}")
            else:
                logger.info(f"Using legacy agent messaging for user {user_id} (no conversation)")
        except Exception as conv_err:
            logger.warning(f"Conversation lookup failed, using legacy messaging: {conv_err}")

        # Get full response from Letta with event detection
        streamer = LettaAPIStreaming(logger=logger, conversation_id=conversation_id)
        text_chunks = []
        
        for event in streamer.chat_stream_with_events(system_prompt, user_prompt):
            event_type = event.get("type")
            logger.error(f"📨 Event received: type={event_type}, keys={list(event.keys())}")
            
            if event_type == "tool_call":
                # Update status with tool-specific loading messages
                tool_name = event.get("tool_name", "")
                logger.error(f"🔧 TOOL CALL EVENT: {tool_name}")
                if streaming_enabled and user_message_ts and tool_name:
                    tool_status = get_status_for_tool(tool_name)
                    _set_assistant_status(
                        client,
                        logger,
                        working_channel,
                        user_message_ts,
                        status=tool_status["status"],
                        loading_messages=tool_status["loading_messages"],
                    )
            elif event_type == "text":
                # Accumulate text
                text_chunks.append(event.get("content", ""))

        final_text = (streamer.last_message or "".join(text_chunks)).strip()

        # Check if response contains scheduling proposals
        proposals_posted = False
        has_best_options = "## Best Options" in final_text
        has_conflict_options = "## If We Can Move" in final_text
        has_verbatim = "[VERBATIM_USER_OUTPUT]" in final_text
        logger.error(f"🔍 PROPOSAL DETECTION: has_best_options={has_best_options}, has_conflict={has_conflict_options}, has_verbatim={has_verbatim}, text_len={len(final_text)}")

        if has_best_options or has_conflict_options or has_verbatim:
            try:
                import uuid as uuid_module
                from services.proposal_formatter import parse_orchestrator_proposals
                from services.proposal_cache import proposal_cache
                from adapters.slack_proposal_adapter import render_proposal_blocks

                # Generate a unique session ID
                session_id = f"sess_{uuid_module.uuid4().hex[:12]}"
                logger.error(f"🔍 PROPOSAL PARSING: session_id={session_id}")

                # Extract participants from orchestrator output
                # Format: [PARTICIPANTS:email1@domain.com,email2@domain.com]
                # Format: [PARTICIPANT_NAMES:email1@domain.com=Name1,email2@domain.com=Name2]
                import re as re_module
                from services.interactive_proposals import MeetingContext
                participants = []
                participant_names = {}  # email -> display name

                # First, try to get resolved names from PARTICIPANT_NAMES tag (from identity service)
                names_match = re_module.search(r'\[PARTICIPANT_NAMES:([^\]]+)\]', final_text)
                if names_match:
                    # Parse email=name pairs
                    for pair in names_match.group(1).split(','):
                        if '=' in pair:
                            email, name = pair.split('=', 1)
                            email = email.strip()
                            name = name.strip()
                            if email and name:
                                participant_names[email] = name

                # Extract participant emails from PARTICIPANTS tag
                participants_match = re_module.search(r'\[PARTICIPANTS:([^\]]+)\]', final_text)
                if participants_match:
                    participants = [p.strip() for p in participants_match.group(1).split(',') if p.strip()]
                    # For any participants without resolved names, fall back to email prefix
                    for email in participants:
                        if email not in participant_names and '@' in email:
                            name = email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
                            participant_names[email] = name

                logger.info(f"Extracted participants: {participants}, names: {participant_names}")

                # Build meeting context with participant names
                meeting_context = MeetingContext(
                    participant_names=participant_names,
                )

                # Parse proposals from the response
                proposal_set = parse_orchestrator_proposals(
                    output=final_text,
                    session_id=session_id,
                    user_id=user_id,
                    participants=participants,
                    meeting_context=meeting_context,
                )
                logger.error(f"🔍 PROPOSAL PARSED: clean={len(proposal_set.clean_proposals)}, conflict={len(proposal_set.conflict_proposals)}")

                # Only proceed if we found proposals
                if proposal_set.clean_proposals or proposal_set.conflict_proposals:
                    # Store in cache
                    proposal_cache.store(session_id, proposal_set)

                    # Render interactive blocks
                    proposal_blocks = render_proposal_blocks(proposal_set)
                    logger.error(f"🔍 PROPOSAL BLOCKS: {len(proposal_blocks)} blocks")

                    # Post interactive buttons only (suppress text version)
                    if proposal_blocks:
                        from adapters.slack_proposal_adapter import INTRO_TEXT

                        # Add intro section at the beginning
                        intro_block = {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": INTRO_TEXT,
                            },
                        }
                        full_blocks = [intro_block] + proposal_blocks

                        # Post proposals as regular DM message
                        client.chat_postMessage(
                            channel=working_channel,
                            text=INTRO_TEXT,  # Fallback for notifications
                            blocks=full_blocks,
                        )
                        proposals_posted = True
                        logger.error(f"✅ PROPOSALS POSTED: session={session_id}")

                    logger.info(f"Posted interactive scheduling proposals for session {session_id}")
                else:
                    logger.error("⚠️ PROPOSAL PARSING: No proposals found in output")

            except Exception as proposal_err:
                logger.error(f"❌ PROPOSAL ERROR: {proposal_err}", exc_info=True)
                # Fall through to regular posting

        # Post regular response if proposals weren't handled
        if not proposals_posted:
            final_chunks = list(_chunk_text(final_text)) or [""]

            # Post response as regular DM message
            post_response = client.chat_postMessage(
                channel=working_channel,
                text=final_chunks[0],
            )
            reply_ts = post_response.get("ts")

            # Post any overflow chunks
            for extra_chunk in final_chunks[1:]:
                client.chat_postMessage(
                    channel=working_channel,
                    text=extra_chunk,
                )

        # Clear the loading status now that response is complete
        if streaming_enabled and user_message_ts:
            _set_assistant_status(
                client,
                logger,
                working_channel,
                user_message_ts,
                status="",  # Empty status clears the indicator
            )

    except Exception as e:
        logger.exception(e)
        try:
            # Use the working channel for error messages too
            error_channel = working_channel if 'working_channel' in locals() else channel_id
            client.chat_postMessage(channel=error_channel, text=f"Received an error from Bolty:\n{e}")
        except Exception:
            pass
        # Clear status on error as well
        try:
            if 'streaming_enabled' in locals() and streaming_enabled and 'user_message_ts' in locals() and user_message_ts:
                err_channel = working_channel if 'working_channel' in locals() else channel_id
                _set_assistant_status(client, logger, err_channel, user_message_ts, status="")
        except Exception:
            pass


def _truncate(message: str) -> str:
    if len(message) <= MAX_SLACK_MESSAGE_LENGTH:
        return message
    truncated = message[: MAX_SLACK_MESSAGE_LENGTH - 1].rstrip()
    return f"{truncated}…"


def _chunk_text(message: str):
    if not message:
        yield ""
        return
    for start in range(0, len(message), MAX_SLACK_MESSAGE_LENGTH):
        yield message[start : start + MAX_SLACK_MESSAGE_LENGTH]


def register(app: App):
    @app.event("message")
    def _on_dm(event, client, logger, say):
        _handle_dm(event, client, logger)
