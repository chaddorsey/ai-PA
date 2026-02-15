# Entity Extraction Infrastructure

**Date**: 2026-02-15
**Status**: Pilot complete, incremental enabled, backfill ready

## Current State (Post-Pilot)

### What's Running

- **Incremental extraction**: ENABLED via `ENABLE_ENTITY_EXTRACTION=true` in drive-rag-service
- New/modified documents get entities extracted automatically during the 10-minute sync cycle
- Graphiti MCP processes documents via GPT-4.1-mini

### Pilot Results (10 documents, 2026-02-15)

| Metric | Value |
|--------|-------|
| Documents processed | 9/10 (PDF unsupported by extract endpoint) |
| Entities created | 65 (26 people, 12 software, 8 orgs, 7 projects, 5 generic) |
| Relationships | 202 (105 MENTIONS, 97 RELATES_TO) |
| Episodes | 7 (Graphiti deduplicates) |
| Avg time per doc | 2.9s via HTTP endpoint |
| Quality | Good — rich summaries, correct entity types, meaningful relationships |

### Entity Examples from Pilot

- **[Project] Mapping Time**: "Project aimed at enhancing geospatial data analysis and visualization tools, especially for temporal and spatial datasets..."
- **[Project] DS4E**: "Project focused on integrating data science practices into K-12 science education, aligning with NGSS standards..."
- **[Person]** Various team members correctly identified
- **[Software]** CODAP, ArcGIS, etc. correctly categorized

## Backfill: Full Corpus Extraction

### Cost Estimate

| Metric | Value |
|--------|-------|
| Documents | 44,353 |
| Total text | 914M chars (0.9 GB) |
| Avg per doc | 20,616 chars |
| Est. input tokens | ~228M |
| Est. output tokens | ~15.5M |
| **Est. cost (GPT-4.1-mini)** | **~$116** |
| Est. time (sequential) | ~209 hours (~8.7 days) |

*Note: Pilot showed ~2.9s/doc via HTTP vs 17s/doc in the standalone script. Actual time may be faster than estimated.*

### How to Run the Backfill

The existing batch script at `drive-rag-service/scripts/extract_entities.py` handles everything, but it requires drive-rag-service Python dependencies (structlog, pydantic-settings, etc.) which aren't on the host system Python.

**Option A: Call the HTTP endpoint directly (recommended)**

The service's `POST /v1/entities/extract/{file_id}` endpoint works and handles fetching content + sending to Graphiti. A simple script can iterate over document IDs:

```bash
# Get all document file IDs
docker exec supabase-db psql -U postgres -d postgres -t -A -c \
  "SELECT drive_file_id FROM rag.document_state ORDER BY modified_time DESC;" \
  > /tmp/doc_ids.txt

# Count
wc -l /tmp/doc_ids.txt

# Run extraction (sequential, with progress)
python3 -c "
import urllib.request, json, time, sys

with open('/tmp/doc_ids.txt') as f:
    doc_ids = [line.strip() for line in f if line.strip()]

total = len(doc_ids)
success = errors = 0
start_time = time.time()

for i, fid in enumerate(doc_ids, 1):
    try:
        req = urllib.request.Request(f'http://localhost:8095/v1/entities/extract/{fid}', method='POST')
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
            if data.get('status') == 'ok':
                success += 1
            else:
                errors += 1
    except Exception as e:
        errors += 1
        if '400' not in str(e):  # Skip expected PDF 400s
            print(f'  Error [{i}]: {fid[:20]}... {str(e)[:60]}')

    if i % 100 == 0 or i == total:
        elapsed = time.time() - start_time
        rate = i / elapsed if elapsed > 0 else 0
        eta_hours = (total - i) / rate / 3600 if rate > 0 else 0
        print(f'  Progress: {i}/{total} ({i*100//total}%%) - OK: {success}, Err: {errors}, Rate: {rate:.1f}/s, ETA: {eta_hours:.1f}h')
    sys.stdout.flush()

print(f'Done: {success}/{total} success, {errors} errors, {time.time()-start_time:.0f}s total')
"
```

**Option B: Run inside Docker container**

Copy the script into the container and run with the service's Python:

```bash
docker cp drive-rag-service/scripts/extract_entities.py drive-rag-service:/tmp/
docker exec -e GRAPHITI_BASE_URL=http://graphiti-mcp-server:8000 \
  drive-rag-service python /tmp/extract_entities.py --verbose
```

**Option C: Install dependencies on host**

```bash
cd drive-rag-service
pip3 install structlog pydantic-settings google-auth google-auth-oauthlib google-api-python-client httpx pypdf
python3 scripts/extract_entities.py --verbose
```

### Monitoring During Backfill

```bash
# Check Neo4j entity growth
docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo \
  "MATCH (n) RETURN labels(n) as type, count(n) as cnt ORDER BY cnt DESC;"

# Check relationship growth
docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo \
  "MATCH ()-[r]->() RETURN type(r) as rel_type, count(r) as cnt ORDER BY cnt DESC;"

# Check episode count (one per document)
docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo \
  "MATCH (e:Episodic) RETURN count(e);"

# Check Graphiti MCP health
curl -s http://localhost:8082/

# Check drive-rag-service logs for extraction activity
docker compose logs drive-rag-service --tail=20 | grep -i entity
```

### Known Limitations

- **PDFs**: The `POST /v1/entities/extract/{file_id}` endpoint returns 400 for PDFs. The endpoint only supports Google Docs, Sheets, and Slides. PDFs would need the batch script (Option B/C) which has Drive API fallback.
- **Sequential processing**: The HTTP endpoint approach processes one doc at a time. Graphiti's `SEMAPHORE_LIMIT=10` could support parallelism but would need a concurrent script.
- **No resume**: If interrupted, re-running will re-process already-extracted docs (Graphiti deduplicates, so this is safe but wastes time/money). To resume, filter out already-processed file IDs.

### After Backfill

When the graph is substantially populated:

1. **Restore consolidation code** from git (commit `e79b406`) if entity deduplication is needed
2. **Update agent tools** — the existing `explore_document_entities`, `extract_document_entities`, and `find_related_documents` tools will automatically return real data
3. **Consider entity-based search** — the local `document_entities` PostgreSQL table exists but is unused; could be populated from Neo4j for faster queries

## Architecture

### Data Flow

```
Document (Google Drive)
  → ingest_document() [drive-rag-service/src/drive_rag/ingestion.py:495]
    → extract_entities_from_document() [entities.py:234]
      → GraphitiClient.add_episode() [entities.py:49]
        → POST http://graphiti-mcp-server:8000/mcp (MCP tools/call add_memory)
          → Graphiti uses GPT-4.1-mini to extract entities + relationships
            → Stored in Neo4j (bolt://neo4j:7687)
```

### Configuration

| Env Var | Service | Value | Purpose |
|---------|---------|-------|---------|
| `ENABLE_ENTITY_EXTRACTION` | drive-rag-service | `true` | Enable extraction during ingestion |
| `GRAPHITI_BASE_URL` | drive-rag-service | `http://graphiti-mcp-server:8000` | Graphiti endpoint |
| `MODEL_NAME` | graphiti-mcp-server | `gpt-4.1-mini` | LLM for extraction |
| `GRAPHITI_USE_CUSTOM_ENTITIES` | graphiti-mcp-server | `true` | Use research entity types |
| `GRAPHITI_ENTITY_TYPE_SET` | graphiti-mcp-server | `research` | Entity type schema |
| `SEMAPHORE_LIMIT` | graphiti-mcp-server | `10` | Max concurrent processing |

### Services

| Service | Port (external) | Port (internal) | Purpose |
|---------|----------------|-----------------|---------|
| drive-rag-service | 8095 | 8000 | RAG + entity extraction trigger |
| graphiti-mcp-server | 8082 | 8000 | Entity extraction + graph queries |
| neo4j | none (internal only) | 7474/7687 | Graph storage |

### Files Reference

| File | Purpose |
|------|---------|
| `drive-rag-service/src/drive_rag/entities.py` | Extraction logic, Graphiti HTTP client |
| `drive-rag-service/src/drive_rag/ingestion.py` | Calls extraction at line 495 |
| `drive-rag-service/src/drive_rag/main.py` | `/v1/entities/extract/{id}` and `/v1/entities/document/{id}` endpoints |
| `drive-rag-service/scripts/extract_entities.py` | Batch extraction script (host-side) |
| `letta/drive_rag_tools.py` | Agent tools: explore/extract/find_related |
| `docker-compose.yml` | Service config, env vars |
| `graphiti/mcp_server/graphiti_mcp_server.py` | Graphiti MCP server (custom entity types, LLM config) |
| `graphiti/mcp_server/graphiti_http_wrapper.py` | HTTP wrapper for MCP transport |
