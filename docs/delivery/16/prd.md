# PBI-16: Enhance OmniFocus MCP Tool Guidance

## Overview
Improve the OmniFocus simplified MCP server metadata and onboarding experience so that conversational agents receive sufficient guidance to call tools correctly on first attempt.

## Problem Statement
Current tool descriptions and schemas are terse, leaving LLM clients to guess required parameters or supported filters. Additionally, there is no in-band help, so repeated failures occur before a human intervenes.

## User Stories
- As a conversational AI designer, I want descriptive tool metadata so that an LLM can infer the required parameters without experimentation.
- As an LLM orchestrator, I want a help tool that returns quick-start guidance so that an agent can self-serve examples before invoking other tools.
- As a support engineer, I want a welcome notification pointing to the help resource so that new sessions discover the documentation automatically.

## Technical Approach
- Expand tool descriptions and property annotations in `server-mcp-simplified.ts` to clarify required/optional fields, defaults, and response shapes.
- Expose a lightweight `docs/getHelp` MCP tool that returns curated markdown examples and troubleshooting tips sourced from maintained documentation.
- Emit an informational notification after session initialization advertising the help tool and reference documentation.
- Update smoke/manual tests to confirm the help tool appears in `tools/list` and that the notification fires during initialization.

## UX/UI Considerations
- Keep metadata concise but informative; highlight required parameters, optional filters, and typical usage patterns.
- The help payload should be markdown formatted for easy rendering in chat UIs.
- Notification text must be short and suitable for logging, with a direct pointer (help tool name or URL).

## Acceptance Criteria
1. Tool descriptions in `tools/list` explicitly describe required parameters, defaults, and common variants.
2. A new `docs/getHelp` tool is registered and returns markdown guidance including example MCP calls.
3. Session initialization emits a single welcome notification mentioning the help tool and documentation location.
4. Smoke test or curl script verifies the help tool is discoverable and returns content without errors.

## Dependencies
- Existing OmniFocus simplified MCP server infrastructure.
- Current documentation maintained under `docs/delivery/14` and `docs/delivery/15` for reuse.

## Open Questions
- Should the help tool support locales or multiple verbosity levels? (Default to single markdown response for now.)
- Do we need rate limiting on notifications? (Likely unnecessary; one per session is acceptable.)

## Related Tasks
- [Tasks for PBI 16](./tasks.md)

[View in Backlog](../backlog.md#user-content-16)
