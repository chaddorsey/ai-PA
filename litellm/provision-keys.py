"""Create LiteLLM virtual keys for each active Letta agent for cost tracking.

Run after LiteLLM is up and healthy:
    python litellm/provision-keys.py

Requires: requests
"""
import os
import sys
import requests

LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000")
MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-dev-litellm-master-key")
LETTA_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

HEADERS = {"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"}


def get_active_agents():
    """Fetch all non-archived Letta agents that use OpenAI models."""
    resp = requests.get(f"{LETTA_URL}/v1/agents/?limit=50")
    resp.raise_for_status()
    agents = resp.json()
    active = {}
    for a in agents:
        name = a.get("name", "")
        if name.startswith("XXX-ARCHIVE"):
            continue
        provider = a.get("llm_config", {}).get("provider_name", "")
        # Only create keys for OpenAI-routed agents (going through LiteLLM)
        if provider == "openai":
            active[name] = a["id"]
    return active


def provision_user_and_key(agent_name, agent_id):
    """Create a LiteLLM user and virtual key for an agent."""
    # Create user
    resp = requests.post(f"{LITELLM_URL}/user/new", headers=HEADERS, json={
        "user_id": agent_name,
        "user_alias": agent_id,
    })
    if resp.ok:
        print(f"  User created: {agent_name}")
    elif resp.status_code == 400 and "already exists" in resp.text.lower():
        print(f"  User exists: {agent_name}")
    else:
        print(f"  User error: {resp.status_code} {resp.text}")
        return None

    # Create key
    resp = requests.post(f"{LITELLM_URL}/key/generate", headers=HEADERS, json={
        "user_id": agent_name,
        "key_alias": f"letta-{agent_name}",
        "metadata": {"letta_agent_id": agent_id},
    })
    if resp.ok:
        key = resp.json().get("key")
        print(f"  Key: {key}")
        return key
    else:
        print(f"  Key error: {resp.status_code} {resp.text}")
        return None


def main():
    print(f"LiteLLM: {LITELLM_URL}")
    print(f"Letta:   {LETTA_URL}")
    print()

    # Verify LiteLLM is up (liveliness doesn't require auth)
    try:
        resp = requests.get(f"{LITELLM_URL}/health/liveliness")
        resp.raise_for_status()
        print("LiteLLM healthy\n")
    except Exception as e:
        print(f"ERROR: LiteLLM not reachable: {e}")
        sys.exit(1)

    agents = get_active_agents()
    print(f"Found {len(agents)} active OpenAI agents:\n")

    for name, aid in sorted(agents.items()):
        print(f"[{name}] ({aid})")
        provision_user_and_key(name, aid)
        print()

    print("Done. Check spend with:")
    print(f"  curl '{LITELLM_URL}/spend/logs' -H 'Authorization: Bearer {MASTER_KEY}'")


if __name__ == "__main__":
    main()
