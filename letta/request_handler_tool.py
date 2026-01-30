"""
Request Handler Tool for Routing to Subagents

This tool routes requests to specialist agents (task, calendar, pulse) and returns
their responses. It acts as a proxy that the main agent can use to delegate
requests to domain-specific subagents.
"""

from typing import Dict, Any


def delegate_to_specialist(domain: str, request: str) -> str:
    """
    Route request to specialist agent and return the response.
    
    This tool sends a request to a specialized agent based on the domain
    and returns the agent's response. The main agent handles routing decisions
    and uses this tool to ferry requests to the appropriate specialist.
    
    Args:
        domain: The domain to route to. Must be one of: 'task', 'calendar', 'pulse'
        request: The specific request message to send to the specialist agent
    
    Returns:
        String containing the response from the specialist agent, or an error message
        if routing failed.
    """
    # Import required modules inside function for Letta tool extraction
    import os
    import traceback
    import requests
    import json
    
    # Wrap entire function in try-except
    try:
        # Validate domain
        agent_map = {
            "task": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
            "calendar": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
            "pulse": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"
        }
        
        if domain not in agent_map:
            return f"Unknown domain: {domain}. Options: {list(agent_map.keys())}"
        
        # Get agent ID for the domain
        agent_id = agent_map[domain]
        
        # Use direct HTTP requests to avoid SDK auto-reading empty LETTA_API_KEY from env
        letta_base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        letta_api_key = os.getenv("LETTA_API_KEY")
        
        # Construct the API endpoint
        api_url = f"{letta_base_url}/v1/agents/{agent_id}/messages"
        
        # Prepare the request payload
        payload = {
            "messages": [
                {"role": "user", "content": request}
            ]
        }
        
        # Prepare headers
        # For self-hosted Letta, API key may not be required when calling from within the network
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add Authorization header only if API key is available and non-empty
        if letta_api_key and letta_api_key.strip():
            headers["Authorization"] = f"Bearer {letta_api_key.strip()}"
        
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
        
        # Extract assistant message content from response
        response_text = None
        for msg in messages:
            if isinstance(msg, dict):
                # Check if this is an assistant message
                if msg.get('message_type') == 'assistant_message' and msg.get('content'):
                    # Extract text content from assistant message
                    content = msg.get('content')
                    if isinstance(content, str):
                        response_text = content
                        break
                    elif isinstance(content, list):
                        # Handle structured content (list of content blocks)
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict) and block.get('type') == 'text':
                                text_parts.append(block.get('text', ''))
                        if text_parts:
                            response_text = '\n'.join(text_parts)
                            break
                    elif isinstance(content, dict):
                        # Handle dict content
                        if content.get('type') == 'text':
                            response_text = content.get('text', '')
                            break
                # Fallback: check for role == 'assistant'
                elif msg.get('role') == 'assistant' and msg.get('content'):
                    content = msg.get('content')
                    if isinstance(content, str):
                        response_text = content
                        break
                    elif isinstance(content, list):
                        # Handle list content
                        text_parts = []
                        for part in content:
                            if isinstance(part, str):
                                text_parts.append(part)
                            elif isinstance(part, dict) and part.get('type') == 'text':
                                text_parts.append(part.get('text', ''))
                        if text_parts:
                            response_text = '\n'.join(text_parts)
                            break
        
        # Return response or default message
        if response_text:
            return response_text
        else:
            return "No response received from specialist agent."
    
    except Exception as e:
        # Safe error handling
        error_msg = f"Error routing request to {domain} agent: {str(e)}"
        try:
            error_details = traceback.format_exc()
            return f"{error_msg}\n\nDetails:\n{error_details}"
        except:
            return error_msg
