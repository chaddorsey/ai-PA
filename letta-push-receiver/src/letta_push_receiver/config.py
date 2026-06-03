"""Configuration for the push receiver.

Defaults are hard-coded to local-mode-fleet ids; overrideable via
LETTA_PUSH_RECEIVER_CONFIG=/path/to/yaml or individual env vars.

Each agent in the AGENTS table maps:
  source slug → (agent_id, wrapper_path, role_description)

The wrapper_path is the existing ~/bin/letta-* script. We don't
re-implement the env block; we use the wrapper. To do that, we wrap
the wrapper: spawn `letta-tasks` as a subprocess, but force
--output-format stream-json + --input-format stream-json + --yolo
into the args before --conversation. See dispatcher.py for details.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class AgentSpec:
    slug: str            # 'tasks' | 'email' | 'pulse' | 'docs' | 'calendar' | 'mc'
    agent_id: str        # agent-local-<uuid>
    wrapper_path: str    # ~/bin/letta-<slug>
    role: str            # one-line description for logs


# Default fleet mapping. Source agents are the owners for their media.
# Tasks agent handles enrichment + the user-driven TUI cases.
DEFAULT_AGENTS: Dict[str, AgentSpec] = {
    "tasks": AgentSpec(
        slug="tasks",
        agent_id="agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4",
        wrapper_path=str(Path.home() / "bin" / "letta-tasks"),
        role="Substrate + enrichment (Phase B) + TUI coordination",
    ),
    "email": AgentSpec(
        slug="email",
        agent_id="agent-local-93241bd6-ce9c-4ea6-89ca-318a6d873b0f",
        wrapper_path=str(Path.home() / "bin" / "letta-email"),
        role="Gmail thread expertise + email task extraction",
    ),
    "pulse": AgentSpec(
        slug="pulse",
        agent_id="agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a",
        wrapper_path=str(Path.home() / "bin" / "letta-pulse"),
        role="Slack media expertise + slack task extraction",
    ),
    "docs": AgentSpec(
        slug="docs",
        agent_id="agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a",
        wrapper_path=str(Path.home() / "bin" / "letta-docs"),
        role="Meetings + Drive + Granola expertise",
    ),
    "calendar": AgentSpec(
        slug="calendar",
        agent_id="agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c",
        wrapper_path=str(Path.home() / "bin" / "letta-calendar"),
        role="Scheduling slot-finder",
    ),
    "mc": AgentSpec(
        slug="mc",
        agent_id="agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d",
        wrapper_path=str(Path.home() / "bin" / "letta-mc"),
        role="Fleet orchestrator; task-completion consumer",
    ),
}


# Source → owner agent. This is the routing table for producer pushes.
# Producers don't have to know which agent owns their source; they POST
# with {agent: "X"} explicitly OR omit agent and rely on source routing.
DEFAULT_SOURCE_ROUTING: Dict[str, str] = {
    "email": "email",
    "email-watch": "email",
    "slack": "pulse",
    "drive": "docs",
    "meeting": "docs",
    "meeting_marker": "docs",
    "google-docs-comment": "docs",
    "docs-meeting": "docs",
    "mc-completion": "mc",
}


def listen_host() -> str:
    return os.environ.get("LETTA_PUSH_RECEIVER_HOST", "127.0.0.1")


def listen_port() -> int:
    return int(os.environ.get("LETTA_PUSH_RECEIVER_PORT", "8099"))


def log_dir() -> Path:
    p = Path(
        os.environ.get(
            "LETTA_PUSH_RECEIVER_LOG_DIR",
            "/Volumes/main-drive/ai-PA/logs/health",
        )
    )
    p.mkdir(parents=True, exist_ok=True)
    return p
