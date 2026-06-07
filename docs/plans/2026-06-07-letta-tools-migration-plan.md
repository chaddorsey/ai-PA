---
date: 2026-06-07
status: proposed plan (for review; no execution beyond the validated pilot)
depends_on:
  - docs/superpowers/specs/2026-06-07-pulse-analytics-extension-pilot-design.md  (proven template)
  - docs/followups/2026-06-07-letta-server-tools-migration-stock.md  (inventory)
  - docs/followups/2026-06-07-letta-code-0276-capabilities-migration-fit.md  (capabilities)
letta_bug: LET-9147
---

# Migration plan: off Docker + Letta-server tools → local Letta Code extensions

## Goal & why

Move every capability the fleet still relies on off the **Docker Letta server**
(server-registered tools + the sandbox) onto **local Letta Code extensions**, so:
- tool execution is **deterministic** (pinned interpreter — fixes LET-9147),
- there is **no Docker-Letta dependency** (the local-mode direction),
- secrets/deps/creds are provisioned explicitly, not via ambient interpreter
  state.

The pilot proved the mechanism end-to-end (5/5 green). This plan scales it.

## What needs migrating — in what form, for what reason

| What | Count / scope | Target form | Reason |
|---|---|---|---|
| **Custom server tools** | 202 (all `pip_requirements: none`) | **Extension tools** that `execFile` a pinned venv via the generic `_ext_run.py` (thin wrappers; native TS only for trivial ones) | Determinism (LET-9147), Docker independence, explicit deps/creds |
| **Model providers** | ChatGPT (quota), Kimi, etc. | **Provider extensions** (`letta.providers.register`, litellm `openai-completions` at :4000) | Quota resilience, cross-provider flexibility, local-agent native |
| **Workflows** | daily briefing, schedule, analytics rundown, meeting prep | **Slash commands + skills** (durable workflow = skill + thin launcher) | First-class UX; matches skill-first pattern |
| **Harness guardrails** | approvals, notifications, safety | **Hooks + permissions** (settings.json) | Deterministic enforcement outside the LLM |
| **Cron callers** | scheduler-service jobs invoking the tools | Repoint job messages to `_ext` tools | So automation uses the deterministic path |
| **Docker Letta server + sandbox** | the container + `LocalSandboxConfig` | **Decommission** (last) | End-state: no server tools, no Docker dependency |

### Tool tiers (from the stock-take) drive sequencing
- **Tier A (high risk):** exotic dep (psycopg/pytz/google) AND/OR cred-file
  AND/OR sibling-import. The pulse analytics cluster, email/drive/gmail,
  tasks-postgres, fetch_source_content, scan_meeting_notes. Migrate first
  (these are where LET-9147 actually bites).
- **Tier B (medium):** `requests`-only (~50): sports/media, watch-history,
  Jira/Confluence-over-http, curator, RAG ingest. Usually "work," but declare
  deps + pin for determinism.
- **Tier C (low):** stdlib/API-only (~120): most Slack, scheduler, Jira/
  Confluence, calendly, granola wrappers. Cheapest; batch last.

## Held against the new patterns/capabilities (what we learned)

- **Template works:** pinned `pa-tools` venv + `_ext_run.py(module,func,json)` +
  a `dateTool`-style factory in one extension file. Adding a tool = a few lines.
- **Extension tools surface to server-based local agents** without server
  registration — so we can re-home incrementally, coexisting under distinct
  names, then remove the server tool.
- **`.ts` loads natively; runner loads extensions per-invocation** (no `/reload`
  for cron). Recovery: `letta --no-extensions`.
- **Boundaries to honor:** absolute paths in the extension should become
  derived/configurable; one canonical venv (consolidate the scattered interim
  installs); secrets via a 600 env file; per-tool approval policy; drop
  deprecated memory-block writes (compose's `block_written:False` is the
  deprecated path — move fully to signals + markdown/memfs).

## Ideal path forward (phases)

- **Phase 0 — Pilot (DONE):** `collect_analytics_snapshot_ext` validated 5/5;
  `compose_daily_briefing_ext` built (Phase-1 clean). Template + venv + env
  file established.
- **Phase 1 — Finish the analytics/pulse cluster:** agent-validate compose;
  add email/drive/slack analytics tools to the extension; consolidate the
  canonical venv + requirements; **flip the pulse cron jobs** to `_ext`; remove
  the server registrations once green. (This is the in-flight "a".)
- **Phase 2 — Tier A by domain:** email (gmail send/draft/read/search),
  drive, tasks-postgres, meeting/transcript. Per domain: re-home → N-run
  reliability → flip callers → remove server tool. Resolve creds via absolute
  env paths available to the pinned venv (no Docker mount).
- **Phase 3 — Provider extensions + workflows + hooks:** formalize the model
  providers (litellm/kimi — already manually switched; make it a provider
  extension); convert briefing/schedule to slash commands backed by skills;
  add harness hooks/permissions for guardrails.
- **Phase 4 — Tier B then Tier C (bulk):** declare deps, wrap, validate, flip,
  remove. Largely mechanical with the template.
- **Phase 5 — Decommission:** once no caller uses server tools, retire the
  Docker Letta server + sandbox; delete server tool registrations; remove the
  two-headed (server+local) execution paths.

## Sequencing rationale

1. **Canary-first, risk-tiered:** Tier A is where LET-9147 actually causes
   failures, so it delivers the most reliability per unit effort and surfaces
   idiosyncrasies early.
2. **Dependency-aware:** consolidate one canonical venv + the `_ext_run.py`
   template + the env/secret pattern in Phase 1, so Phases 2–4 are mechanical.
3. **Coexist-then-remove:** distinct `_ext` names let each tool be validated
   live before removing the server version — no big-bang cutover.
4. **Decommission last:** only pull the Docker server when nothing calls it,
   so rollback stays trivial throughout.

## Cross-cutting decisions to confirm

- **One canonical venv** (`~/.letta/pa-tools-venv`) for all migrated tools, with
  a single tracked `requirements.txt`; retire the interim per-interpreter
  installs from the debugging phase.
- **Secret/env strategy:** a single `~/.letta/pa-tools.env` (600) vs per-domain
  files.
- **Approval policy** per tool (cron-unattended vs interactive-risky).
- **Drop deprecated memory-block writes** during migration (signals + memfs).
- **Atlassian/external-API tools** (Jira/Confluence): confirm whether they need
  the venv at all or are fine as stdlib/requests extension tools.

## Open questions

- **Desktop app** (now local-mode compatible): evaluate as an additional surface
  — does it change provider/extension deployment?
- **Agents themselves:** already local; confirm none still depend on the Docker
  server for memory/blocks after tools migrate.
- **Scope confirmation** before any phase touches live cron/automation (the
  guardrail correctly blocked an unconfirmed live-cron flip 2026-06-07).
