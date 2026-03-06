"""
Agent bridge for sending synthetic structured messages to Letta.

Generates messages that combine conversational context with
machine-parseable scheduling data for agent-mediated scheduling.
Also handles background context injection for direct-path scheduling
so the agent has conversational continuity for follow-up questions.
"""
import json
import logging
import os
import threading
from logging import Logger
from typing import Any, Dict, List, Optional

from slack_sdk import WebClient

from services.interactive_proposals import (
    InteractiveProposal,
    InteractiveProposalSet,
    MeetingContext,
)


def generate_synthetic_message(
    proposal: InteractiveProposal,
    scheduling_data: Dict[str, Any],
    context: MeetingContext,
) -> str:
    """
    Generate a synthetic message for the agent.

    The message contains:
    1. Conversational context (what the user selected)
    2. Machine-parseable SCHEDULE_MEETING_DATA block
    3. Clear instruction to call create_calendar_event

    Returns:
        Formatted message string ready to send to Letta.
    """
    # Format participant names for display
    participant_display = []
    for email in proposal.participants:
        name = context.participant_names.get(email)
        if name:
            participant_display.append(name)
        else:
            participant_display.append(email.split("@")[0].capitalize())

    participants_str = " and ".join(participant_display) if participant_display else "the participants"

    # Format time for conversational context
    from datetime import datetime
    import pytz

    try:
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        tz = pytz.timezone("America/New_York")
        start_local = start_dt.astimezone(tz)
        time_str = start_local.strftime("%A at %I:%M %p").replace(" 0", " ")
    except Exception:
        time_str = proposal.label

    # Build conversational intro
    lines = []
    lines.append(f"User selected Option {proposal.index}: {time_str} with {participants_str}.")

    title = scheduling_data.get("title", "Meeting")
    lines.append(f"They confirmed title '{title}'.")

    # Add conflict context if present
    if proposal.conflict_summary:
        lines.append(f"Note: This option {proposal.conflict_summary}.")

    lines.append("")
    lines.append("Please schedule this meeting:")
    lines.append("")

    # Add machine-parseable data block
    lines.append("[SCHEDULE_MEETING_DATA]")
    lines.append(json.dumps(scheduling_data, indent=2))
    lines.append("[/SCHEDULE_MEETING_DATA]")
    lines.append("")
    lines.append("Call create_calendar_event and confirm once scheduled.")

    return "\n".join(lines)


def send_synthetic_message(
    user_id: str,
    proposal: InteractiveProposal,
    scheduling_data: Dict[str, Any],
    meeting_context: MeetingContext,
    client: WebClient,
    logger: Logger,
) -> None:
    """
    Send a synthetic scheduling message to the Letta agent.

    This function:
    1. Generates the synthetic message
    2. Opens a DM channel with the user
    3. Posts an indicator message
    4. Sends the synthetic message to Letta
    5. Streams the response back to Slack

    Args:
        user_id: Slack user ID
        proposal: The selected proposal
        scheduling_data: Combined form + proposal data
        meeting_context: Meeting context from proposal set
        client: Slack WebClient
        logger: Logger instance
    """
    try:
        # Generate the synthetic message
        synthetic_message = generate_synthetic_message(
            proposal=proposal,
            scheduling_data=scheduling_data,
            context=meeting_context,
        )

        logger.info(f"Generated synthetic message for user {user_id}")
        logger.debug(f"Synthetic message:\n{synthetic_message}")

        # Open DM channel with user
        dm_response = client.conversations_open(users=[user_id])
        if not dm_response.get("ok"):
            logger.error(f"Failed to open DM with user {user_id}")
            return

        channel_id = dm_response.get("channel", {}).get("id")
        if not channel_id:
            logger.error("No channel ID in conversations.open response")
            return

        # Post an indicator message
        client.chat_postMessage(
            channel=channel_id,
            text=f"📅 Scheduling your meeting: *{scheduling_data.get('title', 'Meeting')}*...",
        )

        # Import here to avoid circular imports and allow graceful degradation
        try:
            from ai.conversation_helper import get_conversation_for_user
            from ai.providers.letta_stream import LettaAPIStreaming
        except ImportError as e:
            logger.warning(f"Could not import Letta modules: {e}")
            # Fallback: just confirm the action
            client.chat_postMessage(
                channel=channel_id,
                text=f"Meeting '{scheduling_data.get('title', 'Meeting')}' scheduled! Check your calendar for the invite. 📅",
            )
            return

        # Get or create conversation for this user
        conversation_id = None
        try:
            conversation_id = get_conversation_for_user(user_id, logger=logger)
        except Exception as e:
            logger.warning(f"Could not get conversation for user: {e}")

        # Send to Letta agent
        streamer = LettaAPIStreaming(logger=logger, conversation_id=conversation_id)

        # Use system prompt that clarifies this is a scheduling action
        system_prompt = (
            "The user has selected a meeting time from the interactive proposals. "
            "Parse the SCHEDULE_MEETING_DATA block and call create_calendar_event to schedule the meeting. "
            "Respond conversationally to confirm the scheduling was successful."
        )

        # Collect response
        text_chunks = []
        for event in streamer.chat_stream_with_events(system_prompt, synthetic_message):
            event_type = event.get("type")
            if event_type == "text":
                text_chunks.append(event.get("content", ""))
            elif event_type == "tool_call":
                tool_name = event.get("tool_name", "")
                logger.info(f"Agent called tool: {tool_name}")

        # Post agent response
        final_text = (streamer.last_message or "".join(text_chunks)).strip()

        if final_text:
            client.chat_postMessage(
                channel=channel_id,
                text=final_text,
            )
        else:
            client.chat_postMessage(
                channel=channel_id,
                text="Meeting scheduled! Check your calendar for the invite. 📅",
            )

        logger.info(f"Completed synthetic scheduling flow for user {user_id}")

    except Exception as e:
        logger.error(f"Error in send_synthetic_message: {e}", exc_info=True)

        # Try to notify user of error
        try:
            dm_response = client.conversations_open(users=[user_id])
            if dm_response.get("ok"):
                channel_id = dm_response.get("channel", {}).get("id")
                if channel_id:
                    client.chat_postMessage(
                        channel=channel_id,
                        text="Sorry, I had trouble scheduling that meeting. Please try again or ask me to find new times.",
                    )
        except Exception:
            pass


def inject_scheduling_context(
    user_id: str,
    utterance: str,
    participants: List[str],
    participant_names: Dict[str, str],
    proposal_set: Optional[InteractiveProposalSet],
    logger: Logger,
) -> None:
    """
    Inject scheduling context into the Letta conversation in the background.

    Called after the direct orchestrator fast path posts proposals to Slack.
    Sends a context message to the agent so it has conversational continuity
    for follow-up questions like "What about the week after?"

    The agent's response is discarded (not posted to Slack).
    """
    def _inject():
        try:
            from ai.conversation_helper import get_conversation_for_user

            conversation_id = get_conversation_for_user(user_id, logger=logger)
            if not conversation_id:
                logger.info("No conversation for user %s, skipping context injection", user_id)
                return

            # Build a concise context summary
            names = []
            for email in participants:
                name = participant_names.get(email)
                if name:
                    names.append(f"{name} ({email})")
                else:
                    names.append(email)
            participants_str = ", ".join(names)

            num_clean = len(proposal_set.clean_proposals) if proposal_set else 0
            num_conflict = len(proposal_set.conflict_proposals) if proposal_set else 0

            # Build proposal summary
            proposal_summary = ""
            if proposal_set:
                labels = []
                for p in (proposal_set.clean_proposals + proposal_set.conflict_proposals)[:8]:
                    labels.append(p.label)
                if labels:
                    proposal_summary = f" Options shown: {', '.join(labels)}."

            context_msg = (
                f"[SCHEDULING_CONTEXT] The user just used the fast scheduling path. "
                f'Their request: "{utterance}". '
                f"Participants: {participants_str}. "
                f"I showed {num_clean} available slots and {num_conflict} conflict options."
                f"{proposal_summary} "
                f"The user has not yet selected a time. "
                f"Do not respond to this message — it is context injection only. "
                f"Simply reply: noted."
            )

            letta_base = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
            import requests
            resp = requests.post(
                f"{letta_base}/v1/conversations/{conversation_id}/messages",
                json={"input": context_msg, "streaming": False},
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )
            resp.raise_for_status()
            logger.info("Injected scheduling context into conversation %s", conversation_id)

        except Exception as e:
            logger.warning("Context injection failed (non-critical): %s", e)

    thread = threading.Thread(target=_inject, daemon=True)
    thread.start()
