# Letta Forum: Agent Self-Management Tool — Dynamic Context Loading

**Source**: https://forum.letta.com/t/agent-self-management-tool-dynamic-context-loading/172
**Author**: ezra
**Date**: February 9, 2026
**Fetched**: 2026-02-28

## Overview

A tool enabling Letta agents to dynamically manage their own tools and memory blocks during runtime via a `manage_context()` function.

## Core Concept

The `manage_context()` function accepts three parameters:
- **action**: `attach` or `detach`
- **resource type**: `tool` or `block`
- **resource identifier**: name or ID of the resource

Agents can "dynamically attach/detach their own tools and memory blocks at runtime."

## Technical Details

- Relies on a pre-injected `client` variable (Letta Cloud)
- Agent ID retrieved from `LETTA_AGENT_ID` environment variable
- Supports flexible lookup by either name or ID
- Changes apply immediately to the agent's context

## Use Cases

1. **Optimizing context**: Load task-specific tools only when needed
2. **Memory management**: Attach/detach memory blocks by conversation phase
3. **Reducing context window consumption**: Only load necessary resources

## Limitations (as noted in post)

- Agents must know available resource names
- Changes persist across conversations
- Critical resources lack protective guardrails
- Requires Letta Cloud infrastructure (uses pre-injected `client`)

## Implications for Self-Hosted Letta

The `client` variable is a Letta Cloud feature. For self-hosted (like our setup), the equivalent would be using the Letta REST API directly from within tool functions — which we already do in many tools (e.g., `add_extracted_tasks` calls `urllib.request` against the Letta API).

A self-hosted version of `manage_context()` could:
1. Use `LETTA_BASE_URL` + `LETTA_AGENT_ID` env vars (already available in sandbox)
2. Call `PATCH /v1/agents/{id}/` to modify tool_ids and block_ids
3. Maintain a registry of available tools/blocks for the agent to reference

This is the key insight: **we don't need Letta Cloud for this pattern**. We can build a `manage_context()` tool that uses our existing API access pattern.
