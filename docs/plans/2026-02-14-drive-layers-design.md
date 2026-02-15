# Google Drive Tool Layers: Architecture & Implementation Plan

**Date:** 2026-02-14
**Status:** Design
**Agent:** docs-and-transcripts-agent (`agent-398b4f6c-6afa-493f-8063-897c6b171a0d`)

## Problem Statement

The docs-and-transcripts agent needs a coherent set of Google Drive tools organized
by user intent, not implementation backend. Currently there are 16+ Drive-related
tools scattered across agents, split between two backends (drive-rag-service and
direct Google API), with no tools actually attached to the agent that should own them.
The agent also lacks automatic change monitoring, live diff capability, and a path
to content reading for non-Google-Doc file types.

## Current State Assessment

### What Exists

**drive-rag-service** (HTTP API at `drive-rag-service:8000`):
- Semantic search via pgvector embeddings (`/v1/search`)
- Document ingestion with structure-aware chunking (`/v1/ingest/`)
- Live content fetch for Google Docs, Sheets, Slides (`/v1/fetch/`)
- Snapshot storage and block-level diffing (`/v1/diff/`)
- Edit history from stored revisions (`/v1/edits/`)
- Change detection via Drive Changes API (`/v1/sync/changes`)
- Entity extraction to Graphiti/Neo4j (`/v1/entities/`)

**Direct Google API tools** (Letta sandbox, OAuth credentials):
- `search_drive_activity` - workspace activity search (Admin Reports API)
- `get_document_events` - per-document event timeline (Admin Reports API)
- `get_document_comments` - comment retrieval (Drive API v3)
- `get_drive_documents` - file search/listing (Drive API v3)

**12 RAG tools** registered in Letta from `letta/drive_rag_tools.py` (none attached
to docs-and-transcripts-agent).

**4 direct API tools** registered, currently on pulse-monitor-agent.

### Overengineering Analysis

#### 1. Scan vs Sync: REDUNDANT (remove scan)

Two change detection mechanisms exist in `change_monitor.py`:

- **`scan_for_changes()`** - Per-document polling with priority tiers
  (HIGH/MEDIUM/LOW based on recency). Makes N API calls to check N documents.
- **`sync_changes_from_drive()`** - Drive Changes API. Single API call returns
  ALL changes since last sync token.

The scan method adds no value over sync. The priority tier system is designed for
100K+ document scenarios that don't apply here. The sync method is strictly superior:
fewer API calls, catches new files and deletions automatically, maintains its own
state token.

**Recommendation:** Remove `scan_for_changes()` and its priority tier infrastructure.
Use `sync_changes_from_drive()` exclusively.

#### 2. Snapshot/Diff System: UNDERUTILIZED

The snapshot system (`snapshots.py`, `differ.py`) stores gzipped normalized text
per revision on the filesystem. The differ computes block-level changes between
two stored snapshots.

**Current problems:**
- Snapshots are only created during ingestion, not for every revision
- No automatic scheduling means snapshots become stale quickly
- The `/v1/diff/` endpoint requires both "before" and "after" snapshots to exist
- If a document was ingested yesterday and edited today, there's no "after" snapshot
  until someone triggers re-ingestion

**However, the diff system IS valuable** for its core purpose: understanding
*what content changed* in a document. The Drive Changes API and revision list
only tell you *who* changed *when* - they don't tell you what text was added or
removed. Google provides no diff API. The only way to know what changed is to
compare two versions of the document content.

**The issue is not the diff system itself, but its dependency on pre-stored
snapshots.** The fix is a live diff capability (see Phase 2 below).

**Recommendation:** Keep the diff infrastructure. Add live diff capability so
diffs work without requiring pre-stored snapshots. Remove the per-document scan
polling that was supposed to feed snapshots but never ran automatically.

#### 3. Entity Extraction: FRAGILE, LIKELY UNUSED

The entity extraction system (`entities.py`, `consolidation.py`) is partially
integrated with Graphiti/Neo4j:

- The `document_entities` database table exists but is never populated by any code
- Entity extraction calls Graphiti's MCP endpoint, which has known auth issues
- No evidence of successful entity extraction in production
- The consolidation analysis endpoint exists but operates on an empty dataset
- `find_related_documents` and `explore_document_entities` have no data to return

**Recommendation:** Defer entity extraction. Remove from the docs-and-transcripts
agent tool set. If cross-document entity search is needed later, redesign with
entities stored in the drive-rag-service database rather than depending on
external Graphiti.

#### 4. Normalizer & Chunker: WELL-JUSTIFIED

The normalizer (606 lines, 5 MIME type handlers) and chunker (190 lines,
structure-aware section boundaries) are appropriate complexity:
- Unicode NFC normalization, whitespace canonicalization
- Heading hierarchy tracking for outline_path (valuable for retrieval context)
- Stable content hashes for change detection
- Section-respecting chunk boundaries with soft min / hard max sizing

**Recommendation:** Keep as-is.

## Target Architecture

### Three Functional Layers

```
Layer 1: Content Layer (drive-rag-service)
  "What does this document say? Find information across documents."
  Backend: RAG index (pgvector) + live Drive API fetch

Layer 2: Activity Layer (direct Google API)
  "Who did what? What happened? What are people saying?"
  Backend: Admin Reports API, Drive Activity API, Drive API v3

Layer 3: Sync Layer (drive-rag-service, automated)
  "Keep the index fresh. Detect changes. Capture snapshots."
  Backend: Drive Changes API + scheduled ingestion
```

### Agent Tool Taxonomy (11 tools)

**Content tools** (what's IN the documents):

| Tool | Backend | Data Freshness | Purpose |
|------|---------|---------------|---------|
| `search_documents` | RAG index | Last sync cycle | Semantic search across all indexed docs |
| `read_document` | drive-rag-service `/v1/fetch/` | Always live | Get full text of a specific document |
| `find_related_documents` | RAG entity search | Last sync cycle | Cross-document entity/topic discovery |

**Activity tools** (what's HAPPENING with documents):

| Tool | Backend | Data Freshness | Purpose |
|------|---------|---------------|---------|
| `get_recently_changed_documents` | drive-rag-service | Last sync cycle | Quick list of recently changed docs |
| `get_document_edits` | Drive API revisions | Always live | Who edited a specific doc, when |
| `get_document_changes` | drive-rag-service `/v1/diff/` | Live (with enhancement) | What content changed between versions |
| `search_drive_activity` | Admin Reports API | Always live | Broad "what did the team work on" |
| `get_document_events` | Admin Reports API | Always live | Detailed event timeline for specific docs |

**Collaboration tools:**

| Tool | Backend | Data Freshness | Purpose |
|------|---------|---------------|---------|
| `get_document_comments` | Drive API v3 | Always live | Read comments and reply threads |
| `reply_to_comment` (future) | Drive API v3 | N/A | Respond to document comments |

**Discovery tools:**

| Tool | Backend | Data Freshness | Purpose |
|------|---------|---------------|---------|
| `get_drive_documents` | Drive API v3 | Always live | Find docs by owner, name, type, folder |

**Admin tools (sleeptime agent, not docs-and-transcripts):**

| Tool | Purpose |
|------|---------|
| `ingest_document` | Add/re-index a document |
| `extract_document_entities` | Trigger entity extraction (when ready) |
| `explore_document_entities` | View entities in a document |
| `analyze_entity_consolidation` | Dedup entities |

### Tools to DROP

| Tool | Reason |
|------|--------|
| `get_document_content` | Redundant with `read_document` (live fetch) and `search_documents` (semantic search). Reconstructing from chunks is worse than either. |
| `list_indexed_documents` | Subsumed by `get_drive_documents` for discovery. Move to sleeptime for admin use only. |
| `get_index_stats` | Admin-only. Move to sleeptime or remove. |

### System Prompt Decision Guide

```
<tool_guide>
FIND INFORMATION IN DOCUMENTS:
- search_documents: "Find info about X across all docs" (semantic search)
- read_document: "Show me the content of this specific doc" (full text, always current)
- find_related_documents: "What docs mention person/project Y?"

UNDERSTAND WHAT'S HAPPENING:
- get_recently_changed_documents: "What changed since this morning?" (overview)
- get_document_edits: "Who edited doc X and when?" (revision list, always live)
- get_document_changes: "What content changed in doc X?" (text diff)
- search_drive_activity: "What did the team work on this week?" (broad activity)
- get_document_events: "Show me the full activity timeline for doc X"

COLLABORATION:
- get_document_comments: "What comments are on doc X?"

DISCOVER DOCUMENTS:
- get_drive_documents: "Find docs owned by Z" / "Show me spreadsheets about budget"

DECISION GUIDE:
- "What does doc X say?" -> read_document
- "Find info about Y" -> search_documents
- "What changed recently?" -> get_recently_changed_documents
- "Who edited doc X?" -> get_document_edits (always live from Drive API)
- "What was changed in doc X?" -> get_document_changes (content diff)
- "What did the team do today?" -> search_drive_activity
- "Show me comments on X" -> get_document_comments

NOTE ON FRESHNESS:
- search_documents works on indexed content (updated every ~10 minutes)
- read_document always fetches live from Google Drive
- Activity and comment tools always query Google APIs live
- If a document isn't indexed, offer to request indexing
</tool_guide>
```

## Implementation Plan

### Phase 1: Tool Consolidation & Attachment (no service changes)

**Goal:** Get the right tools attached to docs-and-transcripts-agent with clear
guidance. No code changes to drive-rag-service.

**Work:**
1. Update system prompt with tool guide (decision tree above)
2. Attach existing tools to docs-and-transcripts-agent:
   - From drive_rag_tools.py: `search_documents`, `fetch_document_from_drive`
     (rename to `read_document`), `find_related_documents`,
     `get_recently_changed_documents`, `get_document_edits`,
     `get_document_changes`
   - From drive_analytics_tools.py: `search_drive_activity`,
     `get_document_events`, `get_document_comments`, `get_drive_documents`
3. Move admin tools to sleeptime agent: `ingest_document`,
   `extract_document_entities`, `explore_document_entities`,
   `analyze_entity_consolidation`, `list_indexed_documents`, `get_index_stats`
4. Detach/remove `get_document_content` from all agents (redundant)
5. Improve tool docstrings with "USE THIS WHEN" / "NOT FOR" patterns

**Depends on:** Nothing. Can start immediately.

### Phase 2: Scheduled Sync & Live Diff (service enhancement)

**Goal:** Automatic change detection and real-time diff capability.

**Work:**

**2a. Scheduled sync via scheduler-service:**
- Create a recurring job: `POST drive-rag-service:8000/v1/sync/changes` every
  5-10 minutes
- When sync detects changes: auto-trigger `POST /v1/ingest/{file_id}` for each
  changed document
- This keeps the RAG index fresh and creates snapshots for diffing
- Monitor via `/v1/sync/status`

**2b. Live diff endpoint:**
- Enhance `/v1/diff/{file_id}` to accept `?to=live` parameter
- When `to=live`: fetch current document content on the fly, normalize it,
  diff against last stored snapshot
- No need for a stored "after" snapshot - computed in real time
- Also add `POST /v1/snapshot/{file_id}` for lightweight snapshot capture
  without full re-indexing (no chunking/embedding, just normalized text storage)

**2c. Enhance `get_document_edits` tool:**
- Currently queries the drive-rag-service database (stale)
- Add option to query Drive API `revisions.list` directly for always-live
  "who edited when" data
- Or: create a new Letta tool that calls Drive revisions API directly (simpler,
  avoids modifying existing tool)

**2d. Remove scan infrastructure:**
- Remove `scan_for_changes()` from change_monitor.py
- Remove priority tier constants and logic
- Remove `/v1/scan/changes` endpoint
- Keep only `sync_changes_from_drive()` and `/v1/sync/changes`

**Depends on:** Phase 1 (tools attached and working).

### Phase 3: Enhanced Content Reading (service enhancement)

**Goal:** `read_document` works for all file types, not just Google Docs.

**Work:**

**3a. PDF text extraction via fetch:**
- The ingestion pipeline already extracts PDF text (uses pypdf in normalizer.py)
- Wire the same extraction logic into `/v1/fetch/{file_id}` for PDFs
- Currently fetch returns metadata-only for PDFs with "use ingest" note

**3b. Multi-sheet Sheets support:**
- Currently `/v1/fetch/` exports only the first sheet as CSV
- Use Sheets API to enumerate all sheets, export each, return combined

**3c. Optional: Word/PowerPoint support:**
- Add `python-docx` and `python-pptx` dependencies to drive-rag-service
- Download binary, extract text, return
- Lower priority - most org docs are native Google formats

**3d. Auto-index suggestion:**
- When `read_document` fetches a document that isn't indexed, include a note
  in the response: "This document is not indexed for semantic search"
- Agent system prompt guidance: offer to request indexing when this note appears

**Depends on:** Phase 2 (scheduled sync running so newly indexed docs stay fresh).

### Phase 4: Comment Interaction (new capability)

**Goal:** Agent can reply to document comments.

**Work:**
- New Letta tool: `reply_to_comment(file_id, comment_id, reply_text)`
- Requires `drive` scope (not just `drive.readonly`) in OAuth credentials
- Drive API v3: `comments.replies.create(fileId, commentId, body={content: text})`
- Update OAuth scopes in drive-rag-service and/or analytics credentials

**Depends on:** Phase 1 (comments tool attached and working).

### Phase 5: Cleanup (simplification)

**Goal:** Remove dead code and unused infrastructure.

**Work:**
- Remove `scan_for_changes()` and priority tier system (done in Phase 2d)
- Evaluate entity extraction: if Graphiti integration is not working, remove
  `entities.py`, `consolidation.py`, related endpoints, and `document_entities` table
- Remove `get_document_content` tool registration from Letta
- Clean up any orphaned tool registrations
- Update CLAUDE.md and documentation

**Depends on:** Phases 1-4 complete, system stable.

## Key Design Decisions

### Why keep snapshots despite their complexity?

The Drive API tells you WHO changed WHEN. It does NOT tell you WHAT changed.
Google provides no diff API. The only way to answer "what was added to this
document during the meeting?" is to compare two versions of the content.
Snapshots make this possible without re-fetching old revisions (which Google
may not retain in exportable form).

The enhancement (live diff) reduces snapshot dependency for ad-hoc queries,
while scheduled sync ensures snapshots exist for historical comparison.

### Why not merge all activity tools into one?

`get_document_edits` (who edited specific doc), `search_drive_activity`
(broad workspace search), and `get_document_events` (detailed timeline) use
different APIs with different capabilities:
- Admin Reports API: has view tracking, workspace-wide, but slower
- Drive Activity API: per-file, faster, but no view tracking
- Drive revisions: per-file, always current, but only revision metadata

Merging them would create a complex router that hides important capability
differences. Better to keep them separate with clear guidance.

### Why organize by intent rather than backend?

The agent shouldn't need to know whether "search_documents" uses pgvector
embeddings or whether "get_document_edits" calls Drive API vs database.
Organizing by "what question am I answering" (content / activity / collaboration /
discovery) maps to how users actually ask questions.

## Meeting Scenario: End-to-End

After a meeting ends, the user asks: "Who edited the project doc during the
meeting, and what did they change?"

With this architecture:

1. Agent calls `get_document_edits(file_id, since="2026-02-14T10:00:00")`
   - Queries Drive API revisions.list directly (always live)
   - Returns: "Alice edited at 10:15, Bob at 10:32"

2. Agent calls `get_document_changes(file_id, to="live")`
   - drive-rag-service fetches current content, diffs against last snapshot
   - Returns: "3 blocks added in Section 2, 1 block modified in Summary"

3. Agent synthesizes: "During the meeting, Alice added three paragraphs about
   the Q2 timeline in Section 2, and Bob updated the executive summary."

Total latency: ~5-10 seconds. No pre-scheduling needed for the specific document.

## Related Design Documents

- `docs/design/ChatGPT-RAG vs Google Drive API.md` - Three-layer architecture
  discussion (RAG vs metadata vs change tracking)
- `docs/design/reading_document_contents.md` - PDF/content extraction exploration
- `docs/design/cursor_google_drive_mentions_tool_issue.md` - Mentions tool fixes,
  two-tier collection/retrieval pattern, Letta tool compliance patterns
- `docs/plans/2026-02-05-drive-rag-phase2-monitoring.md` - Phase 2 monitoring plan
- `docs/plans/2026-01-31-drive-rag-system.md` - Original drive-rag system design
