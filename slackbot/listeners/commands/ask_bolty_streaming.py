# listeners/commands/ask_bolty_streaming.py
from logging import Logger
from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time

from ai.providers.letta_stream import LettaAPIStreaming

# Throttle updates to avoid Slack rate limits
THROTTLE_SECONDS = 0.5          # minimum time between edits
MAX_MESSAGE_LEN = 39000         # stay below Slack hard limits
BATCH_CHUNKS = 5                # also edit every N chunks (in addition to time)

def _stream_to_message(client: WebClient, channel_id: str, ts: str, system: str, user_prompt: str):
    """Stream Letta chunks and update a Slack message in-place."""
    streamer = LettaAPIStreaming()
    chunks, last_edit = [], 0.0

    try:
        for i, delta in enumerate(streamer.chat_stream(system, user_prompt), start=1):
            if not isinstance(delta, str):
                delta = str(delta)
            chunks.append(delta)

            now = time.time()
            if (now - last_edit) >= THROTTLE_SECONDS or (i % BATCH_CHUNKS) == 0:
                partial = "".join(chunks)
                if len(partial) > MAX_MESSAGE_LEN:
                    partial = partial[:MAX_MESSAGE_LEN] + "…"
                client.chat_update(channel=channel_id, ts=ts, text=partial)
                last_edit = now

        # Final update
        final_text = "".join(chunks).strip() or "(no content)"
        if len(final_text) > MAX_MESSAGE_LEN:
            final_text = final_text[:MAX_MESSAGE_LEN] + "…"
        client.chat_update(channel=channel_id, ts=ts, text=final_text)
        
    except Exception as e:
        # Update message with error
        client.chat_update(channel=channel_id, ts=ts, text=f"Received an error from Bolty:\n{e}")

def _handle_ask_bolty_streaming(ack, respond, command: dict, client: WebClient, logger: Logger):
    # 1) Acknowledge fast so Slack doesn't time out
    ack()

    user_id = command["user_id"]
    channel_id = command["channel_id"]
    prompt = (command.get("text") or "").strip()

    if not prompt:
        respond("Usage: /ask-bolty <question>")
        return

    # Let the user know we're going to stream somewhere
    respond("Got it — streaming a reply as a message (if I can't post here, I'll DM you).")

    system = "You are a helpful Slack bot. Be concise and helpful."
    user_prompt = f"User <@{user_id}> says:\n{prompt}"

    # 2) Try to post in-channel
    try:
        waiting = client.chat_postMessage(channel=channel_id, text="Thinking…")
        _stream_to_message(client, channel_id, waiting["ts"], system, user_prompt)
        return
    except SlackApiError as e:
        # Common reasons: bot not in channel or channel is private
        err = getattr(e, "response", {}).get("error")
        logger.warning("chat_postMessage failed in-channel (%s): %s", err, e)
        if err not in {"channel_not_found", "not_in_channel", "is_archived", "missing_scope", "restricted_action"}:
            # Unknown failure: surface the error and bail
            respond(f"Sorry, I couldn't post in this channel: `{err or e}`")
            return

    # 3) Fallback: open a DM with the user and stream there
    try:
        dm = client.conversations_open(users=[user_id])
        dm_channel = dm["channel"]["id"]
        waiting = client.chat_postMessage(channel=dm_channel, text="Thinking…")
        _stream_to_message(client, dm_channel, waiting["ts"], system, user_prompt)
    except SlackApiError as e:
        logger.exception("Fallback DM streaming failed")
        respond(f"Sorry, I couldn't open a DM to stream the reply: `{getattr(e, 'response', {}).get('error')}`")
    except Exception as e:
        logger.exception("Unexpected error while streaming to DM")
        respond(f"Sorry, an unexpected error occurred: `{e}`")

def register(app: App):
    @app.command("/ask-bolty")
    def _on_cmd(ack, respond, command, client, logger):
        _handle_ask_bolty_streaming(ack, respond, command, client, logger)
