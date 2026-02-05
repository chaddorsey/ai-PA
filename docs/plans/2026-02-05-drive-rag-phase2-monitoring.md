# Drive RAG Phase 2 Completion: Change Monitoring & Retention

## Overview

Complete Phase 2 of Drive RAG by adding:
1. **Change Monitoring** - Detect Drive file edits and trigger snapshot/diff pipeline
2. **Retention Policy** - Automated snapshot cleanup (7-day full, 90-day daily)

**Note**: AI summarization deferred - agents will use existing `get_document_changes()` tool and handle summarization in conversation context.

## Current State

- **44,353 documents** indexed in pgvector
- **44,349 snapshots** (826MB compressed) at `/Volumes/main-filestore/ai-PA-data/drive-rag-snapshots/`
- **Diff engine** working (`differ.py`)
- **API endpoints**: `/v1/edits/{file_id}`, `/v1/diff/{file_id}`
- **Letta tools**: `get_document_edits()`, `get_document_changes()` - agents already have structured change data

---

## Component 1: Change Monitoring System

### Architecture Decision: Polling via Drive Changes API

**Rationale**:
- Push notifications require public webhook URL and channel renewal every 7 days
- Polling is simpler, reliable, and sufficient for our use case
- 15-minute latency for "hot" documents is acceptable
- Both methods provide same information (file changed) - neither provides text-level diffs (we compute those ourselves)

### Change Detection Flow (Already Exists in ingestion.py)

The monitoring system leverages existing 2-tier change detection:
1. **Fast check**: Compare `headRevisionId` from Drive API vs stored `last_seen_revision_id`
2. **Content check**: If revision differs, fetch content, compute `normalized_hash`, compare to stored `content_hash`
3. **Skip if unchanged**: Even if revision changed, skip if content hash matches (handles comments-only changes)

### Design: Batched Priority-Based Polling

Rather than poll all 44K documents, use priority tiers:

| Tier | Criteria | Check Frequency |
|------|----------|-----------------|
| High | Modified in last 24h | Every 15 min |
| Medium | Modified 1-7 days ago | Every 2 hours |
| Low | Older documents | Daily (rotating sample) |

### Implementation

**New file: `drive-rag-service/src/drive_rag/change_monitor.py`**

```python
# Key functions:
async def scan_for_changes(priority: str, batch_size: int) -> ScanResult
async def get_documents_to_check(priority: str, batch_size: int) -> list[str]
async def check_drive_revisions(file_ids: list[str]) -> dict[str, bool]
```

**New endpoint in `main.py`:**

```
POST /v1/scan/changes
  ?priority=high|medium|low|all
  &batch_size=100
  &dry_run=false

Returns:
  - documents_scanned: int
  - documents_changed: int
  - documents_reindexed: int
  - errors: list[str]
```

**Scheduler Jobs** (via scheduler-service HTTP action):

1. **High-priority scan**: Every 15 minutes, batch_size=100
2. **Full daily scan**: 3 AM daily, processes all documents in batches

### Database Changes

Add index to `document_state` for efficient priority queries:
```sql
CREATE INDEX idx_doc_state_indexed_at ON rag.document_state(last_indexed_at);
```

---

## Component 2: Documents Changed Query

### Design

New endpoint to answer "what documents changed since X?" for agent queries.

**New endpoint:**
```
GET /v1/documents/changed
  ?since=<ISO-date or relative: yesterday, last-week>
  &limit=50
  &owner_email=optional-filter

Returns:
  - documents: list[{file_id, title, modified_time, modifier, change_summary}]
  - total_changed: int
```

**New Letta tool in `letta/drive_rag_tools.py`:**

```python
def get_recently_changed_documents(
    since: Optional[str] = None,  # "yesterday", "last-week", ISO date
    limit: int = 20,
) -> Dict[str, Any]:
    """Get list of documents that changed recently."""
```

This enables queries like "what documents were edited in the last 24 hours?"

---

## Component 3: Retention Policy

### Retention Rules

| Age | Policy |
|-----|--------|
| 0-7 days | Keep ALL snapshots (full edit history) |
| 8-90 days | Keep ONE snapshot per day per document |
| 90+ days | Keep ONE snapshot per document (most recent before 90-day cutoff) |

**Note**: No snapshots are deleted entirely - we always keep at least one persistent copy per document. This preserves the ability to diff against historical versions while managing storage for frequently-edited documents.

### Implementation

**New file: `drive-rag-service/src/drive_rag/retention.py`**

```python
async def apply_retention_policy(dry_run: bool = True) -> RetentionResult
```

**New endpoint:**
```
POST /v1/admin/cleanup/snapshots
  ?dry_run=true
  &tier2_days=90

Returns:
  - snapshots_analyzed: int
  - snapshots_kept: int
  - snapshots_deleted: int
  - space_freed_bytes: int
```

**Scheduler Job**: Weekly cleanup (Sunday 4 AM)

---

## Files to Create/Modify

### New Files
1. `drive-rag-service/src/drive_rag/change_monitor.py` - Change detection and batch scanning
2. `drive-rag-service/src/drive_rag/retention.py` - Retention policy logic

### Modified Files
1. `drive-rag-service/src/drive_rag/main.py` - Add endpoints: `/v1/scan/changes`, `/v1/documents/changed`, `/v1/admin/cleanup/snapshots`
2. `drive-rag-service/src/drive_rag/settings.py` - Add config for monitoring/retention
3. `drive-rag-service/src/drive_rag/db.py` - Add `get_all_snapshots()`, `get_changed_documents()` methods
4. `letta/drive_rag_tools.py` - Add `get_recently_changed_documents()` tool

---

## Configuration Additions

**settings.py:**
```python
# Change monitoring
change_scan_batch_size: int = 100
change_scan_high_priority_hours: int = 24
change_scan_medium_priority_days: int = 7

# Retention
snapshot_full_retention_days: int = 7
snapshot_daily_retention_days: int = 90
```

---

## Implementation Phases

### Phase 2A: Change Monitoring
1. Create `change_monitor.py` with batch scanning logic
2. Add `/v1/scan/changes` endpoint to main.py
3. Add database index for efficient priority queries
4. Create scheduler jobs via scheduler-service
5. Test with subset of documents

### Phase 2B: Changed Documents Query
1. Add `get_changed_documents()` to db.py
2. Add `/v1/documents/changed` endpoint
3. Add `get_recently_changed_documents()` Letta tool
4. Register tool with agents

### Phase 2C: Retention Policy
1. Create `retention.py` with tiered cleanup logic
2. Add `get_all_snapshots()` to db.py
3. Add `/v1/admin/cleanup/snapshots` endpoint
4. Create weekly cleanup scheduler job
5. Run initial dry-run analysis

---

## Verification Plan

1. **Change Monitoring**:
   - Manually edit a test document in Google Drive
   - Run `POST /v1/scan/changes?priority=high&batch_size=50`
   - Verify new snapshot created for edited document
   - Verify diff available via `GET /v1/diff/{file_id}`

2. **Changed Documents Query**:
   - Call `GET /v1/documents/changed?since=yesterday`
   - Verify recently edited document appears in list
   - Test Letta tool via agent: "what documents changed in the last 24 hours?"

3. **Retention**:
   - Run `POST /v1/admin/cleanup/snapshots?dry_run=true`
   - Review output: snapshots to keep vs consolidate
   - Verify: 7-day full, 90-day daily, 90+ keeps one per document
   - Run without dry_run, verify duplicates removed while preserving one copy

---

## Decisions Made

1. **Polling over webhooks**: Simpler, no public URL needed, 15-min latency acceptable
2. **Tiered frequency**: High-priority (15min), Medium (2hr), Low (daily)
3. **All 44K documents**: Monitor everything, hash comparison ensures only changed docs are reprocessed
4. **Agent-side summarization**: Agents use `get_document_changes()` data and summarize in conversation
