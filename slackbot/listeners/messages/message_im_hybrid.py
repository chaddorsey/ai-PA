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
from ai.letta_conversation import get_or_create_letta_conversation, get_cached_identity
from listeners.messages.status_messages import get_status_for_tool, get_default_status

MAX_SLACK_MESSAGE_LENGTH = 3500  # Slack hard limit is 4000 characters; keep buffer for formatting
MAX_STREAM_PREVIEW_LENGTH = 1200

_STREAM_FLAG_VALUES = {"1", "true", "yes", "on"}

# Cross-agent awareness: write DM summaries to main agent's archival memory
_MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"
_ARCHIVAL_WRITE_TIMEOUT = 10  # seconds


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


def _write_dm_to_archival(
    user_id: str,
    user_message: str,
    agent_response: str,
    logger: Logger,
    identity_id: Optional[str] = None,
) -> None:
    """Fire-and-forget: write DM exchange summary to main agent's archival.

    Mirrors Pattern 3 from pa-routing-handler. Non-blocking, non-critical.
    Failures are logged but never propagate.
    """
    import requests
    from datetime import datetime, timezone

    try:
        letta_base = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")

        user_preview = (user_message[:80] + "...") if len(user_message) > 80 else user_message
        response_preview = (agent_response[:120] + "...") if len(agent_response) > 120 else agent_response
        passage_text = (
            f"[Slack DM] User asked calendar-agent: {user_preview}. "
            f"Response: {response_preview}"
        )

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tags = [
            "memory:session",
            f"session:{today}",
            "agent:calendar-agent",
            "source:slack",
            f"user:{user_id}",
        ]
        if identity_id:
            tags.append(f"identity:{identity_id}")

        resp = requests.post(
            f"{letta_base}/v1/agents/{_MAIN_AGENT_ID}/archival-memory",
            json={"text": passage_text, "tags": tags},
            timeout=_ARCHIVAL_WRITE_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("archival_dm_write_success user=%s identity=%s len=%d", user_id, identity_id, len(passage_text))
    except Exception as exc:
        logger.warning("archival_dm_write_failed user=%s error=%s", user_id, exc)


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


def _try_direct_scheduling(
    text: str,
    user_id: str,
    channel_id: str,
    user_message_ts: Optional[str],
    streaming_enabled: bool,
    client: WebClient,
    logger: Logger,
) -> bool:
    """
    Attempt to handle a scheduling request via direct orchestrator call.

    Returns True if the message was handled (scheduling request detected and processed),
    False if it should fall through to the normal Letta agent path.
    """
    try:
        from services.direct_scheduler import (
            is_scheduling_request,
            resolve_user_email,
            call_orchestrator,
            extract_display_content,
            extract_participant_metadata,
        )
    except ImportError as e:
        logger.error("⚡ direct_scheduler import failed: %s", e)
        return False

    if not is_scheduling_request(text):
        return False

    logger.info("⚡ Fast path: scheduling request detected, bypassing Letta agent")

    # Update status to show we're working on scheduling
    if streaming_enabled and user_message_ts:
        _set_assistant_status(
            client, logger, channel_id, user_message_ts,
            status="Finding available times...",
            loading_messages=["Checking calendars", "Running scheduler"],
        )

    # Resolve user email from Slack ID
    user_email = resolve_user_email(user_id)
    if not user_email:
        logger.warning("⚡ Could not resolve email for Slack user %s, falling back to agent", user_id)
        return False

    # Call orchestrator directly
    result = call_orchestrator(utterance=text, user_email=user_email)

    if result.get("status") == "error":
        logger.warning("⚡ Orchestrator error, falling back to agent: %s", result.get("error_message"))
        return False

    # Extract display content
    display_content = extract_display_content(result)
    if not display_content:
        logger.warning("⚡ No display content from orchestrator, falling back to agent")
        return False

    # Try to render interactive proposals (same as agent path)
    proposals_posted = False
    has_best_options = "## Best Options" in display_content
    has_conflict_options = "## If We Can Move" in display_content

    if has_best_options or has_conflict_options:
        try:
            import uuid as uuid_module
            from services.proposal_formatter import parse_orchestrator_proposals
            from services.proposal_cache import proposal_cache
            from adapters.slack_proposal_adapter import render_proposal_blocks, INTRO_TEXT
            from services.interactive_proposals import MeetingContext

            session_id = f"sess_{uuid_module.uuid4().hex[:12]}"

            # Get participant metadata from result
            participants, participant_names = extract_participant_metadata(result)

            # Fallback: resolve names for any participants without display names
            for email in participants:
                if email not in participant_names and "@" in email:
                    name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
                    participant_names[email] = name

            meeting_context = MeetingContext(participant_names=participant_names)

            proposal_set = parse_orchestrator_proposals(
                output=display_content,
                session_id=session_id,
                user_id=user_id,
                participants=participants,
                meeting_context=meeting_context,
            )

            if proposal_set.clean_proposals or proposal_set.conflict_proposals:
                proposal_cache.store(session_id, proposal_set)
                proposal_blocks = render_proposal_blocks(proposal_set)

                if proposal_blocks:
                    intro_block = {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": INTRO_TEXT},
                    }
                    full_blocks = [intro_block] + proposal_blocks

                    client.chat_postMessage(
                        channel=channel_id,
                        text=INTRO_TEXT,
                        blocks=full_blocks,
                    )
                    proposals_posted = True
                    logger.info("⚡ Fast path: posted interactive proposals (session=%s)", session_id)
        except Exception as e:
            logger.error("⚡ Fast path proposal rendering failed: %s", e, exc_info=True)

    # If no interactive proposals, post the text content
    if not proposals_posted:
        # Strip internal markers before displaying
        import re as _re
        display_text = display_content
        for marker in ("[VERBATIM_USER_OUTPUT]", "[/VERBATIM_USER_OUTPUT]",
                       "[PARTICIPANTS:", "[PARTICIPANT_NAMES:"):
            while marker in display_text:
                idx = display_text.find(marker)
                end = display_text.find("]", idx)
                if end >= 0:
                    display_text = display_text[:idx] + display_text[end + 1:]
                else:
                    break
        display_text = display_text.strip()

        if display_text:
            for chunk in _chunk_text(display_text):
                client.chat_postMessage(channel=channel_id, text=chunk)
        else:
            client.chat_postMessage(
                channel=channel_id,
                text="I processed your scheduling request but couldn't generate proposals. Try rephrasing.",
            )

    return True


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

    # ── Thread-aware routing for agent notifications ──
    # If this message is a reply in a thread that matches a pending agent
    # notification, route it to the originating agent instead of default routing.
    thread_ts = event.get("thread_ts")
    if thread_ts and text:
        try:
            from services.pending_replies import get_pending_reply_by_thread
            pending = get_pending_reply_by_thread(thread_ts)
            if pending:
                logger.info(
                    "Thread reply matches pending notification %s — routing to agent %s",
                    pending["id"], pending["agent_id"],
                )
                from listeners.actions.notification_actions import _send_to_agent
                from services.pending_replies import resolve_pending_reply
                resolve_pending_reply(pending["id"])
                _send_to_agent(
                    agent_id=pending["agent_id"],
                    message=(
                        f"User replied to notification (ref_id {pending.get('reply_context', {}).get('ref_id', 'unknown')}): "
                        f"\"{text}\"\n\n"
                        f"Treat this as a custom reply for the completion feedback. "
                        f"Use this text as the reply_text when calling the routing tool."
                    ),
                    user_id=user_id,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    client=client,
                    logger=logger,
                )
                return
        except Exception as thread_err:
            logger.warning("Thread-aware routing check failed: %s", thread_err)

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

    # ── Fast path: direct orchestrator for scheduling requests ──
    # Detects scheduling keywords and calls the orchestrator HTTP service directly,
    # bypassing Letta LLM inference (~20s → ~2-3s).
    if text and _try_direct_scheduling(text, user_id, working_channel, user_message_ts, streaming_enabled, client, logger):
        return

    try:
        # Skip conversation history due to permissions issues - mirror slash command behaviour
        conversation_context = ""

        user_prompt = (
            (f"DM so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text or 'Hello'}"

        # No system prompt - the Letta agent already has its own system prompt.
        # Adding a competing "You are a helpful Slack bot" here confuses the model
        # and degrades multi-turn conversation quality.
        system_prompt = None

        # Status already set above - no need to set again

        # Get or create a Letta conversation for this Slack user.
        # Uses Letta Conversations API directly — each user gets an isolated
        # message history instead of sharing the agent's entire message buffer.
        conversation_id = None
        try:
            conversation_id = get_or_create_letta_conversation(user_id, logger=logger)
            if conversation_id:
                logger.error(f"Using Letta conversation: {conversation_id} for user {user_id}")
        except Exception as conv_err:
            logger.error(f"Conversation lookup failed, using legacy messaging: {conv_err}")

        # Get full response from Letta with event detection
        streamer = LettaAPIStreaming(logger=logger, conversation_id=conversation_id)
        text_chunks = []
        tool_return_content = ""  # Capture tool returns for proposal detection

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
            elif event_type == "tool_return":
                # Capture tool return content for proposal detection
                content = event.get("content", "")
                if content:
                    # Extract verbatim_user_output from tool return dict
                    # Tool returns are JSON strings: {"verbatim_user_output": "...", "status": "ok", ...}
                    if "'verbatim_user_output':" in content or '"verbatim_user_output":' in content:
                        try:
                            import json as json_module
                            parsed = json_module.loads(content)
                            if isinstance(parsed, dict) and 'verbatim_user_output' in parsed:
                                content = parsed['verbatim_user_output']
                                logger.error(f"🔧 TOOL RETURN: Extracted verbatim_user_output ({len(content)} chars)")
                        except (json_module.JSONDecodeError, TypeError):
                            # Letta truncates tool_return at ~50K chars, breaking JSON.
                            # Fallback: try ast.literal_eval for Python dict format
                            try:
                                import ast
                                parsed = ast.literal_eval(content)
                                if isinstance(parsed, dict) and 'verbatim_user_output' in parsed:
                                    content = parsed['verbatim_user_output']
                            except (ValueError, SyntaxError):
                                pass  # Fall through to marker extraction below
                                # Fallback: extract verbatim content via [VERBATIM_USER_OUTPUT] marker
                                # Raw dict string has escaped newlines (\n as literal backslash+n)
                                # which breaks multiline regex in the proposal parser
                                marker = '[VERBATIM_USER_OUTPUT]'
                                end_marker = '[/VERBATIM_USER_OUTPUT]'
                                marker_idx = content.find(marker)
                                if marker_idx >= 0:
                                    end_idx = content.find(end_marker, marker_idx)
                                    if end_idx >= 0:
                                        extracted = content[marker_idx:end_idx]
                                    else:
                                        extracted = content[marker_idx:]
                                    # The content is from a truncated JSON string value,
                                    # so it has JSON escapes (\n, \u2013, \", etc).
                                    # Decode all JSON escape sequences in one pass.
                                    import re as _re_mod
                                    _esc_map = {'\\n': '\n', '\\t': '\t', '\\r': '\r',
                                                '\\"': '"', "\\'": "'", '\\\\': '\\'}
                                    def _json_unescape_repl(m):
                                        tok = m.group(0)
                                        if tok.startswith('\\u') and len(tok) == 6:
                                            try:
                                                return chr(int(tok[2:], 16))
                                            except ValueError:
                                                return tok
                                        return _esc_map.get(tok, tok)
                                    extracted = _re_mod.sub(
                                        r'\\u[0-9a-fA-F]{4}|\\[ntr\\"\']',
                                        _json_unescape_repl,
                                        extracted,
                                    )
                                    content = extracted
                                    logger.error(f"🔧 TOOL RETURN: Extracted verbatim via marker ({len(content)} chars)")
                                else:
                                    logger.error(f"🔧 TOOL RETURN: No verbatim marker found, using raw")
                    # If this tool return has proposal content, REPLACE (not append)
                    # to avoid doubling when the orchestrator is called multiple times.
                    if "[VERBATIM_USER_OUTPUT]" in content or "## Best Options" in content or "## If We Can Move" in content:
                        tool_return_content = content
                        logger.error(f"🔧 TOOL RETURN (proposals): replaced with {len(content)} chars")
                    else:
                        tool_return_content += content
                        logger.error(f"🔧 TOOL RETURN captured: {len(content)} chars")
            elif event_type == "text":
                # Accumulate text
                text_chunks.append(event.get("content", ""))

        final_text = (streamer.last_message or "".join(text_chunks)).strip()

        # Check if response contains scheduling proposals
        # Prefer tool_return_content (verbatim orchestrator output) over final_text
        # to avoid duplicating proposals that appear in both sources.
        if tool_return_content and ("## Best Options" in tool_return_content or "## If We Can Move" in tool_return_content or "[VERBATIM_USER_OUTPUT]" in tool_return_content):
            combined_content = tool_return_content
        else:
            combined_content = final_text
        proposals_posted = False
        has_best_options = "## Best Options" in combined_content
        has_conflict_options = "## If We Can Move" in combined_content
        has_verbatim = "[VERBATIM_USER_OUTPUT]" in combined_content
        logger.error(f"🔍 PROPOSAL DETECTION: has_best_options={has_best_options}, has_conflict={has_conflict_options}, has_verbatim={has_verbatim}, text_len={len(final_text)}, tool_return_len={len(tool_return_content)}")

        if has_best_options or has_conflict_options or has_verbatim:
            try:
                import uuid as uuid_module
                from services.proposal_formatter import parse_orchestrator_proposals
                from services.proposal_cache import proposal_cache
                from adapters.slack_proposal_adapter import render_proposal_blocks

                # Generate a unique session ID
                session_id = f"sess_{uuid_module.uuid4().hex[:12]}"
                logger.error(f"🔍 PROPOSAL PARSING: session_id={session_id}")

                # Extract participants from orchestrator output (check both text and tool returns)
                # Format: [PARTICIPANTS:email1@domain.com,email2@domain.com]
                # Format: [PARTICIPANT_NAMES:email1@domain.com=Name1,email2@domain.com=Name2]
                import re as re_module
                from services.interactive_proposals import MeetingContext
                participants = []
                participant_names = {}  # email -> display name

                # Search both sources for metadata markers
                metadata_content = final_text + "\n" + tool_return_content

                # First, try to get resolved names from PARTICIPANT_NAMES tag (from identity service)
                names_match = re_module.search(r'\[PARTICIPANT_NAMES:([^\]]+)\]', metadata_content)
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
                participants_match = re_module.search(r'\[PARTICIPANTS:([^\]]+)\]', metadata_content)
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

                # Parse proposals from combined content (includes tool return with verbatim output)
                proposal_set = parse_orchestrator_proposals(
                    output=combined_content,
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
            # If the agent responded entirely via tool calls (no assistant text),
            # fall back to tool return content which has the readable output.
            display_text = final_text
            if not display_text and tool_return_content:
                display_text = tool_return_content
                # Strip internal markers before displaying
                for marker in ("[VERBATIM_USER_OUTPUT]", "[PARTICIPANTS:", "[PARTICIPANT_NAMES:"):
                    while marker in display_text:
                        idx = display_text.find(marker)
                        end = display_text.find("]", idx)
                        if end >= 0:
                            display_text = display_text[:idx] + display_text[end + 1:]
                        else:
                            break
                display_text = display_text.strip()
            if not display_text:
                display_text = "I processed your request but didn't generate a text response. Please try again."

            final_chunks = list(_chunk_text(display_text))

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

        # Cross-agent awareness: log DM exchange to main agent archival (fire-and-forget)
        try:
            if text and final_text:
                cached_identity = get_cached_identity(user_id)
                threading.Thread(
                    target=_write_dm_to_archival,
                    args=(user_id, text, final_text, logger, cached_identity),
                    daemon=True,
                ).start()
        except Exception:
            pass  # Never fail the DM response

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
