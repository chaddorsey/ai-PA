# listeners/events/assistant_thread_context_changed.py
from logging import Logger

from slack_bolt import App
from slack_sdk import WebClient


def _handle_assistant_thread_context_changed(event: dict, client: WebClient, logger: Logger):
    """Handle when user switches channels while the AI assistant container is open.
    
    This can be used to:
    1. Track the active context of a user in Slack
    2. Update prompts or behavior based on the new channel context
    3. Invalidate or update cached context-specific state
    """
    logger.info(f"Assistant thread context changed: {event}")
    
    channel_id = event.get("assistant_thread", {}).get("channel_id")
    thread_ts = event.get("assistant_thread", {}).get("thread_ts")
    context = event.get("assistant_thread", {}).get("context", {})
    
    if not channel_id or not thread_ts:
        logger.warning("Missing channel_id or thread_ts in assistant_thread_context_changed event")
        return
    
    logger.info(
        f"Assistant context changed - channel={channel_id}, thread={thread_ts}, "
        f"new_context={context}"
    )
    
    # Future enhancement: Update suggested prompts based on new channel context
    # For now, just log the context change for awareness


def register(app: App):
    """Register the assistant_thread_context_changed event handler."""
    
    @app.event("assistant_thread_context_changed")
    def handle_context_changed(event, client, logger):
        _handle_assistant_thread_context_changed(event, client, logger)

