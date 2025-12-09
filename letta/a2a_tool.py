"""
Agent-to-Agent Messaging Tool for Letta v1 Architecture

This tool implements agent-to-agent communication as a workaround for the
known issues with the built-in send_message_to_agent_async tool.

Based on community workaround from:
https://forum.letta.com/t/custom-agent-to-agent-messaging-tool-for-v1-architecture/127

Author: Community contribution by Michael Hayes (adapted for this project)
"""

import os
import requests
import json
from typing import List, Dict, Any, Optional


def send_message_to_agent(
    sender_agent_id: str,
    recipient_agent_id: str,
    message: str
) -> str:
    """
    Send a message to another Letta agent in the same org and return the API response.

    This tool rebuilds send_message_to_agent_and_wait_for_reply as send_message_to_agent
    with compatibility for v1 agents. The implementation flow is the same except the
    system message sent to the recipient agent has been updated to return an assistant
    message instead of using the deprecated send_message tool.

    Args:
        sender_agent_id: The ID of the agent that is sending the message (you).
        recipient_agent_id: The ID of the target agent to receive the message.
        message: The message content.

    Returns:
        A JSON string containing the replies received from the recipient agent.
        Format: {"replies": [list of reply strings], "status": "ok" or "error", "error": "error message if any"}
    """
    # Import required modules (needed when Letta generates wrapper code)
    import os
    import requests
    import json
    
    letta_api_key = os.environ.get("LETTA_API_KEY")
    letta_base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
    
    # Construct the API endpoint
    api_url = f"{letta_base_url}/v1/agents/{recipient_agent_id}/messages"
    
    # Prepare the request payload
    # The system message includes instructions for the recipient agent to respond
    # using assistant messages instead of the deprecated send_message tool
    payload = {
        "messages": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"[Incoming message from external Letta agent {sender_agent_id} - "
                            f"to reply to the requesting agent, simply send an assistant message "
                            f"with your response. The system will relay the message to the sender. "
                            f"send_message tool is now deprecated.] {message}"
                        )
                    }
                ]
            }
        ]
    }
    
    # Prepare headers
    # For self-hosted Letta, API key may not be required when calling from within the network
    headers = {
        "Content-Type": "application/json"
    }
    
    # Add Authorization header only if API key is available
    if letta_api_key:
        headers["Authorization"] = f"Bearer {letta_api_key}"
    
    try:
        # Make the POST request
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=60  # 60 second timeout for agent responses
        )
        
        # Check for HTTP errors
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        messages = data.get('messages', [])
        
        # Extract assistant messages (replies from the recipient agent)
        replies = []
        for m in messages:
            if isinstance(m, dict):
                # Check if this is an assistant message
                if m.get('message_type') == 'assistant_message' and m.get('content'):
                    # Extract text content from assistant message
                    content = m.get('content')
                    if isinstance(content, str):
                        replies.append(content)
                    elif isinstance(content, list):
                        # Handle structured content (list of content blocks)
                        for block in content:
                            if isinstance(block, dict) and block.get('type') == 'text':
                                replies.append(block.get('text', ''))
                    elif isinstance(content, dict):
                        # Handle dict content
                        if content.get('type') == 'text':
                            replies.append(content.get('text', ''))
        
        # Return results as JSON string
        return json.dumps({
            "status": "ok",
            "replies": replies,
            "num_replies": len(replies)
        }, indent=2)
        
    except requests.exceptions.RequestException as e:
        error_msg = f"HTTP request failed: {str(e)}"
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                error_msg += f" - {json.dumps(error_detail)}"
            except:
                error_msg += f" - Status: {e.response.status_code}"
        
        return json.dumps({
            "status": "error",
            "error": error_msg,
            "replies": []
        })
    
    except json.JSONDecodeError as e:
        return json.dumps({
            "status": "error",
            "error": f"Failed to parse response JSON: {str(e)}",
            "replies": []
        })
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": f"Unexpected error: {str(e)}",
            "replies": []
        })

