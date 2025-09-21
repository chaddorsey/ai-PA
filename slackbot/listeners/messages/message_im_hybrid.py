# listeners/messages/message_im_hybrid.py
from logging import Logger
from slack_bolt import App, Say
from slack_sdk import WebClient
import time
import random

from ai.providers.letta_stream import LettaAPIStreaming
from listeners.listener_utils.listener_constants import DEFAULT_LOADING_TEXT
from listeners.listener_utils.parse_conversation import parse_conversation


def _handle_dm_hybrid(event: dict, client: WebClient, logger: Logger, say: Say):
    if event.get("channel_type") != "im" or event.get("subtype"):
        return

    channel_id = event.get("channel")
    user_id = event.get("user")
    text = (event.get("text") or "").strip()

    try:
        history = client.conversations_history(channel=channel_id, limit=10)["messages"]
        conversation_context = parse_conversation(history[:-1])

        user_prompt = (
            (f"DM so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text or 'Hello'}"

        # Phase 1: Ultra-fast initial feedback
        waiting = client.chat_postMessage(channel=channel_id, text="...")
        
        # Get the full response while showing sophisticated dot animation
        system = "You are a helpful Slack bot. Be concise and helpful."
        streamer = LettaAPIStreaming()
        
        # Start streaming response in background while showing dots
        import threading
        full_response = ""
        response_ready = threading.Event()
        
        def get_response():
            nonlocal full_response
            full_response = "".join(streamer.chat_stream(system, user_prompt)).strip()
            response_ready.set()
        
        # Start getting response in background
        response_thread = threading.Thread(target=get_response)
        response_thread.start()
        
        # Sophisticated dot animation
        dot_count = 3
        animation_phase = 1  # 1: initial 3 dots, 2: growing to 7, 3: cycling
        
        # Phase 1: Quick initial 3 dots (already shown)
        # Phase 2: Add one dot per second until 7 dots
        while not response_ready.is_set() and dot_count < 7:
            time.sleep(1.0)
            if not response_ready.is_set():  # Check again after sleep
                dot_count += 1
                client.chat_update(channel=channel_id, ts=waiting["ts"], text="." * dot_count)
        
        # Phase 3: Cycle between 1 and 7 dots if response still not ready
        while not response_ready.is_set():
            # Reset to 1 dot
            dot_count = 1
            client.chat_update(channel=channel_id, ts=waiting["ts"], text=".")
            time.sleep(1.0)
            
            if response_ready.is_set():
                break
                
            # Add dots back up to 7
            while not response_ready.is_set() and dot_count < 7:
                time.sleep(1.0)
                if not response_ready.is_set():
                    dot_count += 1
                    client.chat_update(channel=channel_id, ts=waiting["ts"], text="." * dot_count)
        
        # Wait for response thread to complete
        response_thread.join()
        
        # Phase 2: Smart sentence-based chunking
        words = full_response.split()
        current_text = ""
        i = 0
        
        while i < len(words):
            # Find the next sentence boundary
            sentence_end = i
            for j in range(i, len(words)):
                word = words[j]
                if word.endswith('.') or word.endswith('!') or word.endswith('?'):
                    sentence_end = j + 1
                    break
            
            # Determine chunk size based on sentence length
            sentence_length = sentence_end - i
            if sentence_length <= 6:
                # Short sentence: deliver in 1-2 chunks
                chunk_size = random.choices([sentence_length, sentence_length//2 + 1], weights=[3, 2])[0]
            else:
                # Longer sentence: deliver in 2 chunks
                chunk_size = random.choices([3, 4, 5, 6, 7, 8, 9], weights=[1, 2, 4, 4, 3, 2, 1])[0]
                chunk_size = min(chunk_size, sentence_length)
            
            # Don't exceed remaining words
            chunk_size = min(chunk_size, len(words) - i)
            
            # Add the chunk
            chunk_words = words[i:i + chunk_size]
            current_text += " ".join(chunk_words) + " "
            client.chat_update(channel=channel_id, ts=waiting["ts"], text=current_text.strip())
            
            # Calculate delay based on chunk characteristics
            chunk_text = " ".join(chunk_words)
            base_delay = 0.2 + (len(chunk_text) * 0.015)  # Faster base delay
            variable_delay = random.uniform(0.05, 0.2)    # Less variation
            delay = base_delay + variable_delay
            
            # Cap the delay to prevent it from being too slow
            delay = min(delay, 0.8)
            
            time.sleep(delay)
            i += chunk_size

    except Exception as e:
        logger.exception(e)
        try:
            client.chat_postMessage(channel=channel_id, text=f"Received an error from Bolty:\n{e}")
        except Exception:
            pass


def register(app: App):
    @app.event("message")
    def _on_dm(event, client, logger, say):
        _handle_dm_hybrid(event, client, logger, say)
