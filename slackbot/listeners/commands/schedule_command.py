# listeners/commands/schedule_command.py
"""
/cal slash command — fast scheduling via direct orchestrator bypass.

Usage:
  /cal Find 30 min with Alex next week
  /cal                                   (opens modal for input)
"""
from logging import Logger

from slack_bolt import App
from slack_sdk import WebClient

MODAL_CALLBACK_ID = "schedule_modal_submit"


def _handle_schedule(ack, command: dict, client: WebClient, logger: Logger):
    ack()

    user_id = command["user_id"]
    prompt = (command.get("text") or "").strip()

    if prompt:
        # Text provided — run directly in background thread
        _run_scheduling(prompt, user_id, command["channel_id"], client, logger)
    else:
        # No text — open modal
        client.views_open(
            trigger_id=command["trigger_id"],
            view={
                "type": "modal",
                "callback_id": MODAL_CALLBACK_ID,
                "title": {"type": "plain_text", "text": "Quick Schedule"},
                "submit": {"type": "plain_text", "text": "Find Times"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "private_metadata": command["channel_id"],
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "schedule_input",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "utterance",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "e.g. Find 30 min with Alex and Priya next week",
                            },
                            "multiline": False,
                        },
                        "label": {"type": "plain_text", "text": "What do you want to schedule?"},
                    },
                ],
            },
        )


def _handle_modal_submit(ack, body: dict, view: dict, client: WebClient, logger: Logger):
    ack()

    user_id = body["user"]["id"]
    channel_id = view.get("private_metadata", "")
    utterance = (
        view["state"]["values"]["schedule_input"]["utterance"]["value"] or ""
    ).strip()

    if not utterance:
        return

    # If no channel from metadata, open a DM
    if not channel_id:
        dm = client.conversations_open(users=[user_id])
        channel_id = dm["channel"]["id"]

    _run_scheduling(utterance, user_id, channel_id, client, logger)


def _run_scheduling(utterance: str, user_id: str, channel_id: str, client: WebClient, logger: Logger):
    """Call orchestrator directly and post proposals."""
    from services.direct_scheduler import (
        resolve_user_email,
        call_orchestrator,
        extract_display_content,
        extract_participant_metadata,
    )

    # Post a "working on it" message
    status_msg = client.chat_postMessage(
        channel=channel_id,
        text=":calendar: Finding available times...",
    )

    user_email = resolve_user_email(user_id)
    if not user_email:
        client.chat_update(
            channel=channel_id,
            ts=status_msg["ts"],
            text="Could not resolve your email address. Please use the regular chat instead.",
        )
        return

    result = call_orchestrator(utterance=utterance, user_email=user_email)

    if result.get("status") == "error":
        client.chat_update(
            channel=channel_id,
            ts=status_msg["ts"],
            text=f"Scheduling error: {result.get('error_message', 'Unknown error')}",
        )
        return

    display_content = extract_display_content(result)
    if not display_content:
        client.chat_update(
            channel=channel_id,
            ts=status_msg["ts"],
            text="The scheduler couldn't find any options. Try rephrasing your request.",
        )
        return

    # Delete the "working on it" message
    try:
        client.chat_delete(channel=channel_id, ts=status_msg["ts"])
    except Exception:
        pass

    # Render interactive proposals
    has_proposals = "## Best Options" in display_content or "## If We Can Move" in display_content

    if has_proposals:
        try:
            import uuid as uuid_module
            from services.proposal_formatter import parse_orchestrator_proposals
            from services.proposal_cache import proposal_cache
            from adapters.slack_proposal_adapter import render_proposal_blocks, INTRO_TEXT
            from services.interactive_proposals import MeetingContext

            session_id = f"sess_{uuid_module.uuid4().hex[:12]}"
            participants, participant_names = extract_participant_metadata(result)

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
                    client.chat_postMessage(
                        channel=channel_id,
                        text=INTRO_TEXT,
                        blocks=[intro_block] + proposal_blocks,
                    )
                    logger.info("/cal: posted interactive proposals (session=%s)", session_id)
                    return
        except Exception as e:
            logger.error("/cal: proposal rendering failed: %s", e, exc_info=True)

    # Fallback: post raw text
    from listeners.messages.message_im_hybrid import _chunk_text
    for chunk in _chunk_text(display_content):
        client.chat_postMessage(channel=channel_id, text=chunk)


def register(app: App):
    @app.command("/cal")
    def _on_cmd(ack, command, client, logger):
        _handle_schedule(ack, command, client, logger)

    @app.view(MODAL_CALLBACK_ID)
    def _on_modal(ack, body, view, client, logger):
        _handle_modal_submit(ack, body, view, client, logger)
