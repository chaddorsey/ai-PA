# Entity Extraction Infrastructure

**Date**: 2026-02-15
**Status**: Schema finalized, incremental enabled, backfill ready

## Current State

### What's Running

- **Incremental extraction**: ENABLED via `ENABLE_ENTITY_EXTRACTION=true` in drive-rag-service
- New/modified documents get entities extracted automatically during the 10-minute sync cycle
- Graphiti MCP processes documents via GPT-4.1-mini
- All document types supported: Google Docs, Sheets, Slides, PDFs, text/markdown

### Entity Type Schema (4 types)

| Type | Additional Fields | Purpose |
|------|-------------------|---------|
| **Project** | `funding_program`, `funder`, `description` | Research projects, grants, initiatives |
| **Organization** | `org_type`, `description` | Institutions, agencies, funders, foundations |
| **Person** | `role`, `affiliation`, `description` | People with roles and affiliations |
| **Software** | `software_type`, `description` | Tools, platforms, frameworks |

Plus Graphiti's built-in **Entity** catch-all for anything that doesn't match.

**Schema rationale**: FundingProgram and Funder were merged into Organization (2026-02-15). The pilot showed 0 FundingProgram and 1 Funder across 9 docs — too sparse to justify separate types. Funding info is captured on Project (`funding_program`, `funder` fields) and Organization (`org_type='Funding Agency'`). These types can be re-added for targeted re-extraction if needed.

Defined in: `graphiti/mcp_server/research_entities.py`

### Models In Use (3 independent models)

| Purpose | Model | Service | Notes |
|---------|-------|---------|-------|
| Entity extraction (LLM reasoning) | `gpt-4.1-mini` | graphiti-mcp-server | Extracts entities + relationships from text |
| Entity/edge embeddings (graph search) | `text-embedding-3-small` | graphiti-mcp-server | Vector similarity for graph queries |
| RAG chunk embeddings (doc search) | `text-embedding-ada-002` | drive-rag-service | Vector similarity for document search |

These are fully independent — changing one does not affect the others.

### Pilot Results (10 documents, 2026-02-15)

| Metric | Value |
|--------|-------|
| Documents processed | 9/10 (1 PDF failed — since fixed) |
| Entities created | 65 (26 people, 12 software, 8 orgs, 7 projects, 5 generic) |
| Relationships | 202 (105 MENTIONS, 97 RELATES_TO) |
| Episodes | 7 (Graphiti deduplicates) |
| Avg time per doc | 2.9s via HTTP endpoint |
| Quality | Good — rich summaries, correct entity types, meaningful relationships |

Entity examples:
- **[Project] Mapping Time**: "Project aimed at enhancing geospatial data analysis and visualization tools..."
- **[Person] Bob Kolvoord**: "...actively involved in a geospatial educational project, collaborating with JMU..."
- **[Software] CODAP**: "...educational analysis and visualization platform focused on geospatial data..."
- **[Organization] JMU**: "...actively involved in the 'Mapping Time' geospatial semester project..."

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
| Est. time (sequential) | ~36 hours at 2.9s/doc (pilot rate) |

*Pilot showed ~2.9s/doc via HTTP endpoint. The batch script estimates 17s/doc but that includes overhead not present in the HTTP path.*

### How to Run the Backfill

**Recommended: Call the HTTP endpoint directly**

The service's `POST /v1/entities/extract/{file_id}` endpoint handles fetching content + sending to Graphiti for all supported types (Docs, Sheets, Slides, PDFs, text/markdown).

```bash
# Step 1: Get all document file IDs
docker exec supabase-db psql -U postgres -d postgres -t -A -c \
  "SELECT drive_file_id FROM rag.document_state ORDER BY modified_time DESC;" \
  > /tmp/doc_ids.txt

# Verify count
wc -l /tmp/doc_ids.txt
# Expected: ~44,353

# Step 2: Run extraction (sequential, with progress reporting)
# Recommend running in tmux/screen so it survives terminal disconnection
python3 -c "
import urllib.request, json, time, sys

with open('/tmp/doc_ids.txt') as f:
    doc_ids = [line.strip() for line in f if line.strip()]

total = len(doc_ids)
success = errors = skipped = 0
start_time = time.time()

for i, fid in enumerate(doc_ids, 1):
    try:
        req = urllib.request.Request(f'http://localhost:8095/v1/entities/extract/{fid}', method='POST')
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
            if data.get('status') == 'ok':
                success += 1
            elif data.get('status') == 'skipped':
                skipped += 1
            else:
                errors += 1
    except Exception as e:
        errors += 1
        if '400' not in str(e):
            print(f'  Error [{i}]: {fid[:20]}... {str(e)[:60]}')

    if i % 100 == 0 or i == total:
        elapsed = time.time() - start_time
        rate = i / elapsed if elapsed > 0 else 0
        eta_hours = (total - i) / rate / 3600 if rate > 0 else 0
        print(f'  Progress: {i}/{total} ({i*100//total}%%) - OK: {success}, Skip: {skipped}, Err: {errors}, Rate: {rate:.1f}/s, ETA: {eta_hours:.1f}h')
    sys.stdout.flush()

elapsed = time.time() - start_time
print(f'Done: {success}/{total} success, {skipped} skipped, {errors} errors, {elapsed:.0f}s total ({elapsed/3600:.1f}h)')
"
```

**Alternative: Run inside Docker container** (uses service's Python with all dependencies)

```bash
docker cp drive-rag-service/scripts/extract_entities.py drive-rag-service:/tmp/
docker exec -e GRAPHITI_BASE_URL=http://graphiti-mcp-server:8000 \
  drive-rag-service python /tmp/extract_entities.py --verbose
```

### Resuming After Interruption

Graphiti deduplicates, so re-processing is safe but wastes time/money. To skip already-processed docs:

```bash
# Get episode count to see how many docs have been processed
docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo \
  "MATCH (e:Episodic) RETURN count(e);" 2>/dev/null

# To create a filtered list, get episode names and cross-reference
# (episode names contain the document title, not file_id directly)
```

### Monitoring During Backfill

```bash
# Entity count by type
docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo \
  "MATCH (n) RETURN labels(n) as type, count(n) as cnt ORDER BY cnt DESC;"

# Relationship count by type
docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo \
  "MATCH ()-[r]->() RETURN type(r) as rel_type, count(r) as cnt ORDER BY cnt DESC;"

# Episode count (roughly = documents processed)
docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo \
  "MATCH (e:Episodic) RETURN count(e);"

# Graphiti MCP health
curl -s http://localhost:8082/

# drive-rag-service extraction logs
docker compose logs drive-rag-service --tail=20 | grep -i entity

# OpenAI API cost check — confirm spend is tracking to ~$116 estimate
# https://platform.openai.com/usage
```

### Known Considerations

- **Sequential processing**: The HTTP endpoint processes one doc at a time. Graphiti's `SEMAPHORE_LIMIT=10` could support parallelism but would need a concurrent script.
- **Name deduplication**: Graphiti deduplicates by embedding similarity, but name variants ("Bob" vs "Bob Kolvoord") may create separate nodes at scale. Post-backfill consolidation may be needed.
- **Long-running**: At ~2.9s/doc, 44K docs takes ~36 hours. Run in tmux/screen so it survives terminal disconnection.
- **Cost is per-run**: Re-running already-extracted docs costs money even though Graphiti deduplicates. Resume from where you left off if interrupted.

### After Backfill

When the graph is substantially populated:

1. **Agent tools work automatically** — `explore_document_entities`, `extract_document_entities`, and `find_related_documents` will return real data from the populated graph
2. **Consider entity consolidation** — if name deduplication issues are visible, restore consolidation code from git (commit `e79b406`)
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
| `graphiti/mcp_server/research_entities.py` | Entity type definitions (4 types) |
| `graphiti/mcp_server/graphiti_mcp_server.py` | Graphiti MCP server (inline fallback types, LLM config) |
| `graphiti/mcp_server/graphiti_http_wrapper.py` | HTTP wrapper for MCP transport |
| `drive-rag-service/src/drive_rag/entities.py` | Extraction logic, Graphiti HTTP client |
| `drive-rag-service/src/drive_rag/ingestion.py` | Calls extraction at line 495 |
| `drive-rag-service/src/drive_rag/main.py` | `/v1/entities/extract/{id}` and `/v1/entities/document/{id}` endpoints |
| `drive-rag-service/scripts/extract_entities.py` | Batch extraction script (needs service deps) |
| `letta/drive_rag_tools.py` | Agent tools: explore/extract/find_related |
| `docker-compose.yml` | Service config, env vars |
