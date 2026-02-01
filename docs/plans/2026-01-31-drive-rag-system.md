# Google Drive Document RAG System - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a comprehensive document retrieval and RAG system for ~10K Google Drive documents with semantic search, edit tracking, and knowledge graph integration.

**Architecture:**
- pgvector in Supabase for document chunk embeddings
- Graphiti/Neo4j for entity knowledge graphs
- Custom ingestion pipeline following design doc architecture
- Coordination catalog for Drive ↔ RAG synchronization
- Letta MCP tools for agent access

**Tech Stack:** Python 3.10+, FastAPI, Google Drive/Docs APIs, pgvector, Graphiti, Letta, Supabase

**Storage Location:** `/Volumes/main-filestore/` for all large/growing data stores:
- pgvector data (via Supabase PostgreSQL data directory)
- Document snapshots (compressed text blobs)
- Future: dedicated vector DB if scaling beyond pgvector

**Reference Documents:**
- `docs/design/ChatGPT-RAG vs Google Drive API.md` - Detailed architecture design
- `docs/design/reading_document_contents.md` - Content extraction discussion

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DOCUMENT RAG SYSTEM                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │ Google Drive │───▶│  Ingestion   │───▶│  Supabase    │                  │
│  │   (Source)   │    │   Worker     │    │  (pgvector)  │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│         │                   │                    │                          │
│         │                   ▼                    │                          │
│         │           ┌──────────────┐            │                          │
│         │           │ Coordination │◀───────────┘                          │
│         │           │   Catalog    │                                        │
│         │           └──────────────┘                                        │
│         │                   │                                               │
│         ▼                   ▼                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   Snapshot   │    │  RAG MCP     │◀──▶│    Letta     │                  │
│  │    Store     │    │   Server     │    │   Agents     │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│                             │                                               │
│                             ▼                                               │
│                      ┌──────────────┐                                       │
│                      │  Graphiti    │ (Phase 3)                            │
│                      │  (Entities)  │                                       │
│                      └──────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phased Approach

| Phase | Focus | Capabilities |
|-------|-------|--------------|
| **Phase 1** | Foundation + Document Search | Basic RAG: semantic search across Google Docs |
| **Phase 2** | Edit Tracking + Attribution | Snapshots, diffs, "who changed what" queries |
| **Phase 3** | Knowledge Graph Integration | Entity extraction, cross-doc relationships |

---

## Phase 1: Foundation + Document Search (Google Docs Only)

**Goal:** Working RAG pipeline from Google Docs to semantic search via Letta agents.

### Task 1.1: Enable pgvector in Supabase

**Files:**
- Supabase SQL editor

**Steps:**

1. Enable the pgvector extension:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

2. Create the document chunks table:
```sql
CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE rag.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Drive/Docs metadata
    drive_file_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    title TEXT NOT NULL,

    -- Chunk identification
    chunk_id TEXT NOT NULL UNIQUE,  -- Stable hash-based ID
    outline_path TEXT[],            -- Heading hierarchy
    block_start_id TEXT,
    block_end_id TEXT,
    char_start INTEGER,
    char_end INTEGER,

    -- Content
    chunk_text TEXT NOT NULL,
    chunk_hash TEXT NOT NULL,       -- For change detection

    -- Vector embedding (1536 dims for OpenAI ada-002)
    embedding vector(1536),

    -- Timestamps
    indexed_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes
    CONSTRAINT unique_chunk UNIQUE (drive_file_id, chunk_id)
);

-- Vector similarity index (IVFFlat for ~10K docs)
CREATE INDEX idx_chunks_embedding ON rag.document_chunks
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Lookup indexes
CREATE INDEX idx_chunks_file_id ON rag.document_chunks(drive_file_id);
CREATE INDEX idx_chunks_revision ON rag.document_chunks(drive_file_id, revision_id);
```

3. Create the coordination catalog table:
```sql
CREATE TABLE rag.document_state (
    drive_file_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    mime_type TEXT,

    -- Revision tracking
    last_seen_revision_id TEXT,
    last_indexed_revision_id TEXT,
    last_indexed_at TIMESTAMPTZ,
    content_hash TEXT,              -- Hash of normalized content

    -- Metadata
    owner_email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_doc_state_indexed ON rag.document_state(last_indexed_at);
```

4. Verify tables exist:
```bash
docker exec supabase-db psql -U postgres -d postgres -c "\dt rag.*"
```

---

### Task 1.2: Create Document Ingestion Service

**Files:**
- Create: `drive-rag-service/` (new service directory)
- Create: `drive-rag-service/src/drive_rag/__init__.py`
- Create: `drive-rag-service/src/drive_rag/main.py`
- Create: `drive-rag-service/src/drive_rag/ingestion.py`
- Create: `drive-rag-service/src/drive_rag/normalizer.py`
- Create: `drive-rag-service/src/drive_rag/chunker.py`
- Create: `drive-rag-service/src/drive_rag/embedder.py`
- Create: `drive-rag-service/pyproject.toml`

**Architecture:**

```
drive-rag-service/
├── src/
│   └── drive_rag/
│       ├── __init__.py
│       ├── main.py              # FastAPI app + endpoints
│       ├── ingestion.py         # Main ingestion worker
│       ├── normalizer.py        # Docs API → normalized text
│       ├── chunker.py           # Structure-aware chunking
│       ├── embedder.py          # OpenAI embeddings
│       ├── models.py            # Pydantic models
│       └── db.py                # Supabase client
├── pyproject.toml
└── Dockerfile
```

**Key Components:**

**normalizer.py** - Convert Google Docs to stable text:
- Walk Docs API JSON structure
- Extract paragraphs, headings, lists, tables
- Build outline_path from heading hierarchy
- Normalize whitespace (NFC, collapse spaces, preserve paragraph breaks)
- Generate content_hash for change detection

**chunker.py** - Structure-aware chunking:
- Group blocks by outline_path
- Target ~1200-6000 chars per chunk
- Respect heading boundaries
- Generate stable chunk_id from file + outline + block range
- Output chunk records with char offsets

**embedder.py** - OpenAI embeddings:
- Batch embedding calls
- Use text-embedding-ada-002 (or text-embedding-3-small)
- Handle rate limiting with backoff

**ingestion.py** - Main worker:
```python
async def ingest_document(file_id: str) -> IngestionResult:
    # 1. Check if changed (revision_id comparison)
    # 2. Fetch Docs API content
    # 3. Normalize to stable text + blocks
    # 4. Compare content_hash - skip if unchanged
    # 5. Chunk from normalized text
    # 6. Diff chunks vs existing (incremental update)
    # 7. Embed only new/changed chunks
    # 8. Upsert to Supabase
    # 9. Update document_state
```

**Dependencies (pyproject.toml):**
```toml
[tool.poetry.dependencies]
python = "^3.10"
fastapi = "^0.109.0"
uvicorn = "^0.27.0"
google-api-python-client = "^2.100.0"
google-auth-oauthlib = "^1.2.0"
supabase = "^2.0.0"
openai = "^1.10.0"
structlog = "^24.1.0"
```

---

### Task 1.3: Google OAuth Setup for Docs API

**Files:**
- Use existing OAuth credentials from drive_analytics_tools.py
- Create: `drive-rag-service/src/drive_rag/auth.py`

**Scopes Required:**
```python
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',      # List/read files
    'https://www.googleapis.com/auth/documents.readonly',  # Read Docs content
]
```

**Token Management:**
- Reuse existing `token.pickle` or `token.json` if compatible
- Or create service-specific credentials

---

### Task 1.4: Add Ingestion Endpoints

**Endpoints in main.py:**

```python
POST /v1/ingest/{file_id}
    # Ingest single document
    # Returns: { status, revision_id, chunks_added, chunks_updated }

POST /v1/ingest/folder/{folder_id}
    # Ingest all Google Docs in a folder
    # Returns: { status, documents_processed, documents_skipped }

GET /v1/status/{file_id}
    # Get indexing status for a document
    # Returns: { indexed, revision_id, chunk_count, last_indexed_at }

POST /v1/search
    # Semantic search across all documents
    # Body: { query: str, limit: int, file_ids?: str[] }
    # Returns: { results: [{ file_id, title, chunk_text, similarity }] }
```

---

### Task 1.5: Create RAG MCP Tools for Letta

**Files:**
- Modify: `letta/drive_rag_tools.py` (new)
- Modify: `letta/configure_mcp_servers.py`
- Modify: `letta/letta_mcp_config.json`

**Tools to Create:**

```python
def search_documents(
    query: str,
    limit: int = 10,
    file_ids: Optional[str] = None  # Comma-separated
) -> Dict[str, Any]:
    """
    Search indexed Google Docs using semantic similarity.

    Args:
        query: Natural language search query
        limit: Maximum results (default 10, max 50)
        file_ids: Optional comma-separated file IDs to search within

    Returns:
        Dictionary with search results including file titles,
        matching text snippets, and similarity scores.
    """

def get_document_content(
    file_id: str,
    sections: Optional[str] = None  # "Summary,Conclusion"
) -> Dict[str, Any]:
    """
    Get full content or specific sections from an indexed document.

    Args:
        file_id: Google Drive file ID
        sections: Optional comma-separated section headings to retrieve

    Returns:
        Dictionary with document title, content, and metadata.
    """

def list_indexed_documents(
    folder_id: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    List all indexed documents with their status.

    Args:
        folder_id: Optional folder to filter by
        limit: Maximum results

    Returns:
        List of indexed documents with titles, IDs, and index dates.
    """
```

---

### Task 1.6: Docker Integration

**Files:**
- Modify: `docker-compose.yml`
- Create: `drive-rag-service/Dockerfile`

**Docker Compose Addition:**
```yaml
drive-rag-service:
  build:
    context: ./drive-rag-service
    dockerfile: Dockerfile
  container_name: drive-rag-service
  ports:
    - "8095:8000"
  environment:
    - SUPABASE_URL=${SUPABASE_URL}
    - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY}
    - OPENAI_API_KEY=${OPENAI_API_KEY}
    - GOOGLE_CREDENTIALS_PATH=/app/credentials/
  volumes:
    - ./credentials:/app/credentials:ro
  networks:
    - pa-internal
  restart: unless-stopped
```

---

### Task 1.7: Initial Document Ingestion

**Steps:**
1. Identify target Google Drive folder(s)
2. Run initial batch ingestion
3. Verify chunks in Supabase
4. Test search via MCP tools

---

## Phase 2: Edit Tracking + Attribution

**Goal:** Track document changes, store snapshots, enable "who changed what" queries.

### Task 2.1: Add Snapshot Storage

**Files:**
- Create: `drive-rag-service/src/drive_rag/snapshots.py`

**Supabase Schema:**
```sql
CREATE TABLE rag.document_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drive_file_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,

    -- Snapshot content (compressed)
    normalized_text_gz BYTEA NOT NULL,
    structure_json_gz BYTEA,

    -- Metadata
    content_hash TEXT NOT NULL,
    size_bytes INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Attribution from Drive API
    last_modifying_user_email TEXT,
    last_modifying_user_name TEXT,
    modified_time TIMESTAMPTZ,

    CONSTRAINT unique_snapshot UNIQUE (drive_file_id, revision_id)
);

CREATE INDEX idx_snapshots_file ON rag.document_snapshots(drive_file_id);
CREATE INDEX idx_snapshots_time ON rag.document_snapshots(modified_time DESC);
```

**Retention Policy:**
- Keep all snapshots for last 7 days
- Keep daily snapshots for 90 days
- Implement cleanup job

---

### Task 2.2: Add Revision Tracking

**Files:**
- Modify: `drive-rag-service/src/drive_rag/ingestion.py`

**Enhancement:**
- Call `revisions.list()` to get revision metadata
- Store revision → user attribution
- Track which revisions have been snapshotted

---

### Task 2.3: Implement Diff Engine

**Files:**
- Create: `drive-rag-service/src/drive_rag/differ.py`

**Capabilities:**
- Load two snapshots (baseline, target)
- Block-level diff using structure
- Output change records:
  - Inserted/deleted/modified blocks
  - Before/after context
  - Attribution (user, time)

---

### Task 2.4: Add Edit Tracking MCP Tools

**Tools:**

```python
def get_document_edits(
    file_id: str,
    since: Optional[str] = None,  # "yesterday", "2026-01-15", "last-week"
    by_user: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get summary of edits to a document.

    Args:
        file_id: Google Drive file ID
        since: Time filter (relative or absolute)
        by_user: Filter by user email

    Returns:
        List of edits with user attribution, timestamps, and summaries.
    """

def summarize_recent_changes(
    file_id: str,
    since: str = "yesterday"
) -> Dict[str, Any]:
    """
    Generate AI summary of document changes.

    Args:
        file_id: Google Drive file ID
        since: Time filter

    Returns:
        Natural language summary of what changed and by whom.
    """
```

---

## Phase 3: Knowledge Graph Integration

**Goal:** Extract entities from documents, connect to Graphiti for relationship queries.

### Task 3.1: Entity Extraction Pipeline

**Files:**
- Create: `drive-rag-service/src/drive_rag/entities.py`

**Approach:**
- Process document chunks through Graphiti's entity extraction
- Extract: People, Projects, Organizations, Topics
- Store entity → document mappings

---

### Task 3.2: Connect to Graphiti

**Integration:**
- On document ingestion, extract entities
- Create Graphiti episodes for document summaries
- Link entities to document chunks

---

### Task 3.3: Cross-Document Query Tools

**Tools:**

```python
def find_related_documents(
    entity: str,
    entity_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Find all documents mentioning an entity.
    """

def explore_document_relationships(
    file_id: str
) -> Dict[str, Any]:
    """
    Show entities and their relationships extracted from a document.
    """
```

---

## Files to Create/Modify Summary

### Phase 1 (New Files)
| File | Purpose |
|------|---------|
| `drive-rag-service/src/drive_rag/main.py` | FastAPI app |
| `drive-rag-service/src/drive_rag/ingestion.py` | Ingestion worker |
| `drive-rag-service/src/drive_rag/normalizer.py` | Docs → text |
| `drive-rag-service/src/drive_rag/chunker.py` | Text → chunks |
| `drive-rag-service/src/drive_rag/embedder.py` | Chunks → vectors |
| `drive-rag-service/src/drive_rag/db.py` | Supabase client |
| `drive-rag-service/src/drive_rag/models.py` | Pydantic models |
| `drive-rag-service/Dockerfile` | Container build |
| `drive-rag-service/pyproject.toml` | Dependencies |
| `letta/drive_rag_tools.py` | Letta MCP tools |

### Phase 1 (Modify)
| File | Changes |
|------|---------|
| `docker-compose.yml` | Add drive-rag-service |
| `letta/configure_mcp_servers.py` | Register drive-rag tools |
| `letta/letta_mcp_config.json` | Add drive-rag-tools entry |

### Phase 2 (New Files)
| File | Purpose |
|------|---------|
| `drive-rag-service/src/drive_rag/snapshots.py` | Snapshot storage |
| `drive-rag-service/src/drive_rag/differ.py` | Diff engine |

### Phase 3 (New Files)
| File | Purpose |
|------|---------|
| `drive-rag-service/src/drive_rag/entities.py` | Entity extraction |

---

## Verification Steps

### Phase 1 Verification

1. **Database Setup:**
```bash
docker exec supabase-db psql -U postgres -d postgres -c "SELECT COUNT(*) FROM rag.document_chunks;"
```

2. **Ingestion Test:**
```bash
curl -X POST http://localhost:8095/v1/ingest/{test-file-id}
```

3. **Search Test:**
```bash
curl -X POST http://localhost:8095/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "formative assessment proposals"}'
```

4. **Letta Tool Test:**
```python
# Via Letta agent
"Search my indexed documents for NSF proposals"
```

### Phase 2 Verification

1. **Snapshot Storage:**
```sql
SELECT drive_file_id, revision_id, size_bytes, created_at
FROM rag.document_snapshots
ORDER BY created_at DESC LIMIT 5;
```

2. **Edit Tracking:**
```python
# Via Letta agent
"Who edited the CODAP proposal since yesterday?"
```

### Phase 3 Verification

1. **Entity Extraction:**
```python
# Via Letta agent
"Find all documents mentioning William"
```

2. **Relationship Query:**
```python
# Via Graphiti
"Show projects connected to the assessment research"
```

---

## Success Criteria

| Criterion | Phase | Verification |
|-----------|-------|--------------|
| pgvector working | 1 | Vector similarity search returns ranked results |
| Google Docs indexed | 1 | 100+ docs ingested, chunks in database |
| Semantic search works | 1 | Natural language queries return relevant docs |
| Letta can search | 1 | Agent successfully uses search_documents tool |
| Snapshots stored | 2 | Compressed snapshots in database |
| Diffs computed | 2 | Can compare two revisions |
| Edit attribution | 2 | "Who changed X" queries work |
| Entities extracted | 3 | Documents linked to Graphiti entities |
| Cross-doc queries | 3 | "All docs mentioning Y" works |

---

## Estimated Scope

| Phase | Components | Complexity |
|-------|------------|------------|
| Phase 1 | 10 files, ~2000 LOC | Medium - Core pipeline |
| Phase 2 | 3 files, ~800 LOC | Medium - Snapshots + diffs |
| Phase 3 | 2 files, ~500 LOC | Lower - Integration with existing Graphiti |

---

## Storage Configuration

**Requirement:** All large/growing data must be stored on `/Volumes/main-filestore/` (external NAS with ample capacity) rather than `/Volumes/main-drive/` (SSD with limited space).

**Data to relocate or configure:**
| Data Type | Current Location | Target Location |
|-----------|------------------|-----------------|
| Supabase PostgreSQL data | Default Docker volume | `/Volumes/main-filestore/supabase-data/` |
| Document snapshots | rag.document_snapshots table | Same DB (BYTEA columns) |
| Neo4j/Graphiti data | Default Docker volume | `/Volumes/main-filestore/neo4j-data/` |

**Implementation Notes:**
- For Supabase: Update docker-compose.yml volume mount for `supabase-db` service
- For Neo4j: Already may be on external storage; verify and update if needed
- Snapshots stored as compressed BYTEA in PostgreSQL will grow with document count

---

## Dependencies

- OpenAI API key (for embeddings)
- Google OAuth credentials (Drive + Docs scopes)
- Supabase running with pgvector extension
- Graphiti + Neo4j running (for Phase 3)
