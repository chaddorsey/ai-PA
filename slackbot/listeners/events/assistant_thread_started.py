# listeners/events/assistant_thread_started.py
from logging import Logger
from typing import List, Optional

from slack_bolt import App
from slack_sdk import WebClient


def _handle_assistant_thread_started(event: dict, client: WebClient, logger: Logger):
    """Handle when user opens the AI assistant container.
    
    According to Slack docs, this is the first impression moment where we can:
    1. Set a loading status if we need time to generate prompts
    2. Send suggested prompts to help the user get started
    """
    logger.info(f"Assistant thread started: {event}")
    
    channel_id = event.get("assistant_thread", {}).get("channel_id")
    thread_ts = event.get("assistant_thread", {}).get("thread_ts")
    context = event.get("assistant_thread", {}).get("context", {})
    
    if not channel_id or not thread_ts:
        logger.warning("Missing channel_id or thread_ts in assistant_thread_started event")
        return
    
    logger.info(
        f"Assistant thread started - channel={channel_id}, thread={thread_ts}, context={context}"
    )
    
    # Offer suggested prompts to help user get started
    suggested_prompts = _get_suggested_prompts(context, logger)
    
    if suggested_prompts:
        try:
            client.assistant_threads_setSuggestedPrompts(
                channel_id=channel_id,
                thread_ts=thread_ts,
                prompts=suggested_prompts,
            )
            logger.info(f"Set {len(suggested_prompts)} suggested prompts for thread {thread_ts}")
        except Exception as e:
            logger.error(f"Failed to set suggested prompts: {e}")


def _get_suggested_prompts(context: dict, logger: Logger) -> List[dict]:
    """Generate context-aware suggested prompts.
    
    Args:
        context: The context object from assistant_thread_started event
        logger: Logger instance
        
    Returns:
        List of prompt dictionaries with 'title' and 'message' keys
    """
    # Default prompts that work in any context
    default_prompts = [
        {
            "title": "Get help",
            "message": "What can you help me with?",
        },
        {
            "title": "Check status",
            "message": "What's my current status or recent activity?",
        },
        {
            "title": "Quick question",
            "message": "I have a quick question about...",
        },
    ]
    
    # Could extend this to provide context-specific prompts based on the channel
    # For example, if context contains a specific channel, offer channel-specific prompts
    
    return default_prompts


def register(app: App):
    """Register the assistant_thread_started event handler."""
    
    @app.event("assistant_thread_started")
    def handle_thread_started(event, client, logger):
        _handle_assistant_thread_started(event, client, logger)

