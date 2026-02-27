"""Point each Letta agent's model_endpoint at LiteLLM proxy and set per-agent model alias.

Each agent gets a unique model name (e.g., gpt-4.1-mini/calendar) that LiteLLM
maps to the same underlying model but with that agent's dedicated OpenAI API key.

Usage:
    # Dry run (shows what would change)
    python litellm/update-agent-endpoints.py --dry-run

    # Apply changes
    python litellm/update-agent-endpoints.py

Requires: requests
"""
import os
import sys
import requests

LETTA_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LITELLM_ENDPOINT = "http://litellm:4000/v1"

DRY_RUN = "--dry-run" in sys.argv
REVERT = "--revert" in sys.argv

# Agent name -> model alias suffix
# Agents not listed here keep the default model name (shared/fallback key)
AGENT_MODEL_ALIASES = {
    # Active agents — each gets its own OpenAI API key
    "calendar-agent_copy": "calendar",
    "docs-and-transcripts-agent": "docs",
    "email-agent": "email",
    "pulse-monitor-agent": "old",
    "pulse-monitor-agent_copy": "pulse",
    "tasks-agent": "tasks",
    "tasks-agent-sleeptime": "tasks-sleep",
    "main-assistant-agent-kinara": "kinara",
    "daily-schedule-agent-sleeptime": "schedule",
    "sports_and_media_maven": "media",
    "sports_and_media_maven_sleeptime": "media-sleep",
    # Old/archived agents that aren't XXX-ARCHIVE prefixed
    "calendar-agent": "old",
}

# Original OpenAI endpoint for revert
OPENAI_ENDPOINT = "https://api.openai.com/v1"


def get_aliased_model(current_model, agent_name):
    """Return model alias like 'gpt-4.1-mini/calendar' for known agents."""
    base_model = strip_alias(current_model)
    alias = AGENT_MODEL_ALIASES.get(agent_name)
    if alias:
        return f"{base_model}/{alias}"
    return base_model


def strip_alias(model_name):
    """Remove alias suffix: 'gpt-4.1-mini/calendar' -> 'gpt-4.1-mini'."""
    return model_name.split("/")[0] if "/" in model_name else model_name


def main():
    print(f"Letta:    {LETTA_URL}")
    print(f"Target:   {LITELLM_ENDPOINT}")
    if DRY_RUN:
        print("DRY RUN - no changes will be made")
    if REVERT:
        print("REVERT MODE - restoring original OpenAI endpoints")
    print()

    resp = requests.get(f"{LETTA_URL}/v1/agents/?limit=50")
    resp.raise_for_status()
    agents = resp.json()

    updated = 0
    skipped = 0

    for agent in sorted(agents, key=lambda a: a.get("name", "")):
        name = agent.get("name", "unknown")
        agent_id = agent["id"]
        llm_config = agent.get("llm_config", {})
        emb_config = agent.get("embedding_config", {})
        provider = llm_config.get("provider_name", "")
        current_endpoint = llm_config.get("model_endpoint", "")
        current_model = llm_config.get("model", "")

        if name.startswith("XXX-ARCHIVE"):
            continue

        if provider != "openai":
            print(f"  SKIP {name}: provider={provider}")
            skipped += 1
            continue

        if REVERT:
            base_model = strip_alias(current_model)
            target_endpoint = OPENAI_ENDPOINT
            target_model = base_model
        else:
            target_endpoint = LITELLM_ENDPOINT
            target_model = get_aliased_model(current_model, name)

        changes = {}
        if current_endpoint != target_endpoint:
            changes["model_endpoint"] = target_endpoint
        if current_model != target_model:
            changes["model"] = target_model

        if not changes:
            print(f"  OK   {name}: already configured")
            skipped += 1
            continue

        if DRY_RUN:
            for field, val in changes.items():
                old = llm_config.get(field, "")
                print(f"  WOULD {name}.{field}: {old} -> {val}")
            updated += 1
            continue

        new_llm = {**llm_config, **changes}
        # Also update embedding endpoint to go through LiteLLM
        new_emb = {**emb_config}
        if not REVERT and emb_config.get("embedding_endpoint") == OPENAI_ENDPOINT:
            new_emb["embedding_endpoint"] = LITELLM_ENDPOINT

        patch_body = {"llm_config": new_llm}
        if new_emb != emb_config:
            patch_body["embedding_config"] = new_emb

        resp = requests.patch(f"{LETTA_URL}/v1/agents/{agent_id}", json=patch_body)
        if resp.ok:
            for field, val in changes.items():
                old = llm_config.get(field, "")
                print(f"  UPDATED {name}.{field}: {old} -> {val}")
            updated += 1
        else:
            print(f"  ERROR {name}: {resp.status_code} {resp.text[:200]}")

    print(f"\nUpdated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
