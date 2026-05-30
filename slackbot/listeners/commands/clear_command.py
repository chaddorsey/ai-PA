"""
/clear slash command — mirror of Letta Code's /clear semantics.

Starts a fresh conversation on the same agent, keeping all memory blocks
intact. Use when the active conversation context is stale, poisoned,
or too long. Does NOT delete the agent's memory or history.

Per Letta support guidance:
  - cancel/finish any active run on the old conv (best effort)
  - create a new conversation for the same agent
  - route future messages in this DM channel to the new conv
  - do NOT delete agent memory
"""

from logging import Logger

from slack_bolt import Ack, App, Respond

from ai.letta_conversation import clear_letta_conversation, DEFAULT_AGENT_ID


def clear_callback(command, ack: Ack, respond: Respond, logger: Logger):
    """Handle /clear from a DM or channel.

    Bolt requires ack() within 3s. The clear work itself is fast (a
    Letta create + a Supabase upsert), but we ack first regardless.
    """
    try:
        ack()
    except Exception as exc:
        logger.error("clear_command_ack_failed: %s", exc)

    user_id = command.get("user_id")
    if not user_id:
        respond(":warning: /clear could not identify the user")
        return

    try:
        old_conv_id, new_conv_id = clear_letta_conversation(
            user_id=user_id,
            agent_id=DEFAULT_AGENT_ID,
            log=logger,
        )
    except Exception as exc:
        logger.error("clear_command_failed: %s", exc, exc_info=True)
        respond(f":x: /clear failed: {exc}")
        return

    if not new_conv_id:
        respond(
            ":warning: Couldn't create a fresh conversation. Old context is still active."
        )
        return

    if old_conv_id:
        msg = (
            "✨ Fresh start. The previous conversation is preserved but "
            "future messages route to a new context. Agent memory is unchanged.\n"
            f"_old: `{old_conv_id[:18]}…`  →  new: `{new_conv_id[:18]}…`_"
        )
    else:
        msg = (
            "✨ Started a new conversation. (No prior context was tracked for this DM.)\n"
            f"_new: `{new_conv_id[:18]}…`_"
        )
    respond(msg)


def register(app: App):
    app.command("/clear")(clear_callback)
