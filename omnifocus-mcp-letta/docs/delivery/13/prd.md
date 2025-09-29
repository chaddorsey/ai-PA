# PBI-13: Centralize Tool Metadata and Profiles

## Overview
Refactor OmniFocus MCP tool definitions into reusable metadata and schema modules so multiple server profiles (simplified, full, future variants) can share a single source of truth.

## Problem Statement
Tool lists are currently hard-coded in server entry files (`server-mcp-full-8124.ts`, `server-mcp-simplified.ts`). This makes updates error-prone and duplicates schema definitions, making it difficult to keep profiles in sync.

## User Stories
- As an MCP maintainer, I want tool definitions in a central registry so changes apply consistently across server modes.
- As a contributor, I want to add new tools by editing metadata rather than updating multiple server files.
- As a documentation owner, I want tool documentation generated from the same metadata to avoid drift.

## Technical Approach
- Extract tool metadata (name, description, OmniFocus command, profile tags) into structured modules.
- Move schemas into shared Zod/JSON schema files to avoid duplication.
- Build a tool registry module that can produce tool lists for different profiles.
- Update server entry points to consume the registry and register tools programmatically.
- Generate docs/tests from the metadata where possible.

## Acceptance Criteria
1. Tool metadata registry replaces hard-coded arrays.
2. Simplified and full profiles reference the registry (no duplicate definitions).
3. Legacy `server-mcp-full-8124.ts` is removed or reduced to thin adapter.
4. Documentation and smoke tests update automatically or are generated from metadata.

## Dependencies
- Existing simplified/full server implementations.
- Schema definitions established in PBI 12.

## Open Questions
- Should schemas be shared between plugin and MCP server codebase?
- Do we need runtime toggles for experimental tools within profiles?

## Related Tasks
- [Tasks for PBI 13](./tasks.md)
