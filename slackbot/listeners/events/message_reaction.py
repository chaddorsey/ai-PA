# listeners/events/message_reaction.py
from logging import Logger
from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time
import random

from ai.providers.letta_stream import LettaAPIStreaming


def _handle_message_reaction(event: dict, client: WebClient, logger: Logger):
    """Handle reactions to messages - add a thoughtful response reaction."""
    
    # Only react to messages that aren't from bots (including ourselves)
    if event.get("subtype") or event.get("bot_id"):
        return
    
    # Only react to messages in channels or DMs
    channel_type = event.get("channel_type")
    if channel_type not in ["channel", "group", "im"]:
        return
    
    channel_id = event.get("channel")
    user_id = event.get("user")
    text = (event.get("text") or "").strip()
    
    # Only react to messages that mention the bot or seem like questions
    should_react = False
    
    # Check if message mentions the bot (this would need bot_id from app)
    if "bolty" in text.lower() or "bot" in text.lower():
        should_react = True
    
    # Check if it's a question
    if text.endswith("?") and len(text) > 10:
        should_react = True
    
    # Check if it's a request for help
    help_words = ["help", "how", "what", "why", "when", "where", "can you", "could you"]
    if any(word in text.lower() for word in help_words):
        should_react = True
    
    if not should_react:
        return
    
    # Add a thoughtful reaction
    reactions = ["🤔", "💭", "🧠", "✨", "👍", "💡"]
    reaction = random.choice(reactions)
    
    try:
        client.reactions_add(
            channel=channel_id,
            timestamp=event["ts"],
            name=reaction.replace(":", "")  # Remove colons if present
        )
        logger.info(f"Added reaction {reaction} to message in {channel_id}")
        
        # Optional: Add a follow-up message after a delay for questions
        if text.endswith("?") and len(text) > 20:
            time.sleep(2)  # Brief pause before responding
            
            system = "You are a helpful Slack bot. Be concise and helpful."
            user_prompt = f"User <@{user_id}> asked: {text}"
            
            try:
                streamer = LettaAPIStreaming()
                response = "".join(streamer.chat_stream(system, user_prompt)).strip()
                
                if response:
                    # Post the response
                    client.chat_postMessage(
                        channel=channel_id,
                        text=response,
                        thread_ts=event["ts"]  # Reply in thread
                    )
                    logger.info(f"Posted response to question in thread {event['ts']}")
                    
            except Exception as e:
                logger.exception(f"Failed to generate response to question: {e}")
                
    except SlackApiError as e:
        logger.warning(f"Failed to add reaction: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error adding reaction: {e}")


def register(app: App):
    @app.event("message")
    def _on_message(event, client, logger):
        _handle_message_reaction(event, client, logger)
