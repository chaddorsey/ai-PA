---
description: drive-rag-service interaction skill. Agent-first CLI wrapping the 8-endpoint REST surface. Replaces ad-hoc curl recipes for searching the 45k-doc indexed corpus, fetching/snapshot-refreshing specific Drive files, and reading diff/edit history.
applies-to: any local-mode agent that needs to search the Drive corpus, refresh a snapshot before reasoning, or track edits on an actively-modified doc. Primary users (in fleet-migration order): Docs, MC, Tasks.
replaces: ad-hoc `curl http://drive-rag-service:8000/v1/...` recipes (no Letta tool — the previous pattern was inline Bash with embedded URLs)
cli: scripts/drive-rag-curl
---

# Drive RAG CLI Skill

## When to use

- **Find docs you don't have an ID for**: semantic search across the
  indexed corpus (`drive-rag-curl search <query>`). 45,357 documents,
  299,215 chunks. Returns ranked results with `similarity` scores
  (cosine 0.0–1.0; 0.7+ strong).
- **Fetch indexed content for a known file_id**: `drive-rag-curl get
  <file_id>`. Returns the indexed copy (may be stale; check `status`
  if freshness matters).
- **Check freshness before reasoning**: `drive-rag-curl status
  <file_id>` returns `last_indexed_at`, `chunk_count`, and whether
  the doc is indexed at all.
- **Force a fresh snapshot of an actively-edited doc**: `drive-rag-curl
  ingest <file_id>`. Drive-rag pulls fresh content from Drive,
  re-chunks, re-embeds, persists. Result includes status `ok` (fresh
  ingest) or `skipped` / `Revision unchanged` (no new revision yet —
  Google hasn't surfaced one).
- **See what changed**: `drive-rag-curl diff <file_id>` returns textual
  diff between recent snapshots. `drive-rag-curl edits <file_id>`
  returns the edit history (modifier, modified_time).
- **Service-wide stats**: `drive-rag-curl stats` returns indexed counts.

This skill replaces the inline curl pattern that lived in MC's
`system/drive_content_protocol.md`. The protocol file still documents
the underlying semantics (when to use which channel; the field name
discipline; the gws-vs-rag tradeoff); this CLI is the agent-callable
implementation.

## When NOT to use

- **Reading the current state of a Google Doc you have an ID for**:
  use `gws docs export` (live, no staleness). The rag service may be
  tier-cool and minutes stale; `gws` is always current.
- **Editing or writing to a Google Doc**: this skill is read-only.
  Writes go through `gws docs documents batchUpdate` (and watch for
  the suggestions-in-doc gotcha — see drive_content_protocol.md).
- **Drive operations beyond search/snapshot/diff**: file listing,
  folder discovery, sharing, permissions all go through gws.

## Prerequisites

- The `drive-rag-service` Docker container must be running:

  ```bash
  docker ps --filter name=drive-rag-service --format '{{.Status}}'
  # should show "Up ... (healthy)"
  ```

- `jq` must be installed. (Already in pa-web-ui container as of
  2026-05-28; also standard on the host.)

- Service URL is auto-detected: the CLI tries `http://localhost:8095`
  (host) then `http://drive-rag-service:8000` (Docker network). Set
  `DRIVE_RAG_BASE_URL` to skip detection.

## Subcommands

### Semantic search

```bash
# Default: JSON output (machine-readable, agent-first)
drive-rag-curl search "FY26 NSF DRK-12 proposal"

# Limit + field-mask for context-window discipline
drive-rag-curl search "interest development" --limit 5 \
    --fields similarity,title,drive_file_id

# Human-readable summary (use when the agent wants to surface to user)
drive-rag-curl search "wearable technology STEM" --limit 5 --pretty
```

**Output field convention**: each result has `similarity` (NOT
`score`), `title`, `drive_file_id`, `chunk_text`, `outline_path`.
The similarity is cosine in [0, 1]; 0.7+ is a strong match, 0.6–0.7
plausible, <0.6 weak. Sort by `-similarity` to rank explicitly:

```bash
drive-rag-curl search "X" --limit 20 | jq 'sort_by(-.similarity)'
```

### Fetch / status / refresh

```bash
# Fetch a doc's indexed copy
drive-rag-curl get 1eX-ArIpYGDMMJ9nLnE7dLdYeplpY6aMMvF9gjYZUsog

# Check when it was last indexed
drive-rag-curl status 1eX-ArIpYGDMMJ9nLnE7dLdYeplpY6aMMvF9gjYZUsog

# Force a fresh re-ingest (useful when the doc is actively edited)
drive-rag-curl ingest 1eX-ArIpYGDMMJ9nLnE7dLdYeplpY6aMMvF9gjYZUsog
```

Possible `ingest` response statuses:
- `ok` — fresh content pulled and re-embedded; subsequent search /
  diff / edits queries reflect the new state.
- `skipped`, `reason: "Revision unchanged"` — no new revision yet
  (Google may not have surfaced one despite live edits). Fall back to
  `gws docs export` for the truly current text.

### Diff and edit history

```bash
# Textual diff between recent snapshots
drive-rag-curl diff 1eX-ArIpYGDMMJ9nLnE7dLdYeplpY6aMMvF9gjYZUsog

# Edit history (modifier, modified_time)
drive-rag-curl edits 1eX-ArIpYGDMMJ9nLnE7dLdYeplpY6aMMvF9gjYZUsog
```

Useful when reasoning over an evolving proposal — *"what changed
since my last read?"* doesn't require re-reading the whole doc.

### Entity-based search

```bash
drive-rag-curl entities "Concord Consortium" --limit 10
```

### Stats + health

```bash
drive-rag-curl stats    # total_documents, total_chunks, avg_chunks_per_document
drive-rag-curl health   # liveness probe
```

## Pattern: snapshot-then-diff for actively-edited docs

When a user is editing a doc live and you're reasoning over it:

```bash
# Step 1: force fresh snapshot
drive-rag-curl ingest <FILE_ID>

# Step 2: do your search / read
drive-rag-curl get <FILE_ID>

# Step 3 (later, after user has edited more): see what changed
drive-rag-curl diff <FILE_ID>
```

For **the absolute latest content** (newer than the ingested
snapshot), bypass rag entirely and use `gws docs export`:

```bash
gws docs export --params '{"documentId":"<FILE_ID>","mimeType":"text/markdown"}' > /tmp/live.md
```

## Failure modes + remediation

- **Service unreachable**: `cannot reach drive-rag-service at
  http://localhost:8095 or http://drive-rag-service:8000`. Restart
  the container: `docker-compose restart drive-rag-service`.
- **HTTP 404 on `get`**: the file_id isn't indexed. Try `ingest`
  first, then `get`. Or use `gws drive files get` to confirm the
  file_id is valid.
- **HTTP 500 on `ingest`**: was historically caused by a PostgREST
  on_conflict bug; resolved 2026-05-28 (see alignment doc I-ter).
  If you see this again, the bug regressed — file a bug.
- **`Revision unchanged` on ingest** — see "When NOT to use"; fall
  back to gws for truly current state.

## Migration history

- **Before 2026-05-29**: the rag service was accessed via inline curl
  commands in agents' Bash flows, with the URL `http://drive-rag-service:8000`
  hardcoded. The field-name discipline (`similarity` not `score`)
  was undocumented; MC repeatedly guessed `.score` and got 0.00
  scores back.
- **2026-05-28**: drive-rag-service's `/v1/ingest/{id}` was fixed (the
  PostgREST `on_conflict` upsert bug). Until that fix, snapshot-on-
  command didn't work.
- **2026-05-29**: this CLI shipped. Migration target for Docs, MC,
  Tasks pre-local-mode. Per the alignment doc, the rag service is
  in healthy state — this CLI just makes its surface predictable.

## Validation history

- **2026-05-29** — Shipped + smoke-tested all 7 subcommands:
  - `health` returns `healthy`
  - `stats` returns 45,357 docs / 299,215 chunks
  - `search "NSF DRK-12 proposal" --limit 3 --pretty` returns
    similarity 0.83+ matches with file_ids and snippets
  - `search "interest development" --limit 2` returns JSON-shaped
    results sortable by `.similarity`
  - `status` on a real proposal doc returns `indexed: true` with
    `last_indexed_at`, `chunk_count`
  - `--help` renders cleanly
  - Unknown subcommand returns `ERROR: unknown subcommand` and
    exits non-zero
