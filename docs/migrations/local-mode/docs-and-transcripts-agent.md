---
date_started: 2026-05-30
date_phase_h: 2026-05-30
status: migrated, soaking
agent_old_id: agent-398b4f6c-6afa-493f-8063-897c6b171a0d
agent_old_name_now: XXX-PRE-LOCAL-docs-and-transcripts-agent
agent_new_id: agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a
agent_new_name: docs-and-transcripts-agent-local
model: lmstudio/kimi-k2p6 (was lmstudio/gpt-4.1-mini/docs)
backup: /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/docs-and-transcripts-agent/
launcher: ~/bin/letta-docs
launch_cwd: /Volumes/main-drive/letta-launchpad
---

# Docs migration log

First per-agent local-mode migration, executed 2026-05-30. Pilot for the
fleet migration arc.

## What migrated

- Agent record + system prompt → local backend
- 7 system/*.md memfs files (all valid frontmatter, no `read_only` violations)
- Persona + tool-use guidelines

## What did NOT migrate

- **4,043 archival passages** (218 MB) preserved on the Docker agent. Local
  agent starts with empty archival.
- The agent's 30 attached Letta tools — replaced by host CLIs
  (`granola`, `drive-rag-curl`, `gws`, `signal`). See
  `/tmp/tool-mapping-docs-and-transcripts-agent.md` for the full mapping.
- 0 cron jobs (Docs agent had none).

## Two-headed runtime state

The Docker agent is renamed and "retired" by name, but **still receiving
data from active ingest pipelines**:

| Pipeline | Source ref | Posting to |
|---|---|---|
| granola-ingest container | `docker-compose.yml:503` (GRANOLA_AGENT_ID) | agent-398b4f6c |
| drive-task-queue container | `docker-compose.yml:1094` (DRIVE_TASK_QUEUE_AGENT_ID) | agent-398b4f6c |
| granola-watcher launchd plist | `letta/com.ai-pa.granola-watcher.plist:31` | agent-398b4f6c |
| granola-mcp-ingest launchd plist | `letta/com.ai-pa.granola-mcp-ingest.plist:33` | agent-398b4f6c |
| granola-ingest/ingest.py | env default at line 27 | agent-398b4f6c |

These keep working against the renamed Docker agent (agent_id unchanged).
The local agent does on-demand queries via host CLIs (`granola list`,
`drive-rag-curl search`, etc.) and doesn't depend on the ingest pipelines.

**Defer decommission of these pipelines** until:
1. Local-mode soak proves on-demand query is sufficient for daily use
2. We decide whether to retire pre-ingestion entirely or redirect somewhere
   (canonical store? new local-mode archival?)

If on-demand turns out to be too slow or incomplete, we'd consider
re-pointing the pipelines to write into `agents-canonical/` instead and
have the local agent query that.

## Lessons learned (carry forward to remaining migrations)

1. **`memory` core tool strips YAML frontmatter** when projecting block
   edits to disk. Pre-commit hook catches it. Workaround: agent edits via
   `Edit` tool (preserves frontmatter), avoids `memory` for memfs files,
   or manually restores frontmatter before commit. Documented in
   `system/tool_use_guidelines_meetings_docs.md` for the migrated agent.

2. **Bash `cd` doesn't persist across calls.** Every memfs git op must
   be chained: `cd "$MEMORY_DIR" && git add ... && git commit ...` in
   ONE Bash call. Same guideline file documents this.

3. **TUI typing lag** was a project-skill-discovery scan walking the
   ai-PA tree (243K files). Mitigated by launching from a small
   dedicated dir (`/Volumes/main-drive/letta-launchpad`). Wrapper
   script `~/bin/letta-docs` enforces this. The launch dir is the same
   regardless of agent; agent uses absolute paths in Bash. Full audit
   tracked in `docs/followups/2026-05-30-ai-pa-directory-bloat-audit.md`.

4. **Cold-cache penalty per agent per process.** OpenAI prompt cache TTL
   ~5min; Kimi K2.6 on Fireworks shows 22-25s on cold tool-using turn,
   5-7s warm. Live with it; keep tmux panes warm for high-traffic agents.
   Full investigation: `docs/followups/2026-05-30-letta-code-tui-latency.md`.

5. **Model swap was trivial.** `jq '.model = "..."'` on the agent
   record JSON. No re-registration of provider, no agent re-create
   needed. Kimi K2.6 via Fireworks ~3-4× faster than gpt-4.1-mini on
   raw API calls.

6. **Local backend = minimal agent record.** Only `description`, `id`,
   `model`, `name`, `system`, `tags`, `model_settings` are stored on
   disk; `llm_config` is resolved at runtime via litellm. The runbook
   Phase C3 "PATCH context_window" step is unnecessary — context window
   comes from litellm's model_info.

7. **`enableMemfsForCreatedAgent` warning during `letta agents create`
   is harmless in pure local mode.** It tries to sync to Docker
   server's Gitea; safely fails; memfs git repo is still initialized
   correctly with a baseline commit.

8. **pa-web-ui has no local-mode routing.** New agent doesn't appear in
   the web picker. Deferred per Option C; TUI is the primary local-mode
   surface for now.

## Rollback path (if needed during soak)

Within first 7 days:
1. Rename Docker agent back:
   `curl -X PATCH http://localhost:8283/v1/agents/agent-398b4f6c... \
     -d '{"name":"docs-and-transcripts-agent"}'`
2. Stop using `~/bin/letta-docs` (delete the wrapper or rename).
3. The Docker agent's tools are intact (never detached). Pipelines
   still feeding archival. Use immediately resumes.

Local agent + memfs + launch-dir state can be left alone; just stop
invoking them.

After 7+ days, see runbook Phase I "When NOT to roll back" + rollback
cost matrix.

## Next agent

`calendar-agent_copy` (`agent-892a2d58-b9f6-4baf-84f3-c431fe46487d`).
4 tools, exercised heavily during 2026-05-29 hardening, smallest fleet
migration target. orchestrate-scheduling CLI ready. Outstanding
pre-reqs not gating: item A (preferences canonical dedup), item G
(slackbot routing decision).
