# Archive Embedding Configuration Migration Plan

**Date:** 2026-02-23
**Status:** Draft
**Risk Level:** Medium (data loss possible if rollback not followed)
**Estimated Duration:** 1-2 hours hands-on, plus 24-hour verification soak

---

## Problem Statement

Five Letta archives have mismatched or missing embedding configurations. All 25 agents use `openai/text-embedding-3-small` (1536-dim), but these archives either have `embedding_config: null` (no embeddings at all) or use `letta/letta-free` (4096-dim padded vectors incompatible with the 1536-dim OpenAI model). Semantic search (`/v1/passages/search`) fails or returns garbage results for affected archives.

The Letta API does not support patching `embedding_config` on existing archives (`PATCH /v1/archives/{id}` only accepts `name` and `description`). The only fix is to create new archives with the correct config and migrate passages.

---

## Affected Archives

| # | Archive Name | Archive ID | Embedding Config | Passages | Used By | Risk |
|---|---|---|---|---|---|---|
| 1 | `companion-agent-1758923939659's Archive` | `archive-5268deab-d883-483d-bfd7-b4b0e54451f5` | `letta/letta-free` (4096-dim) | unknown | Orphaned (archived agent `XXX-ARCHIVE-companion-agent-original`) | None |
| 2 | `pulse-monitor-agent-sleeptime's Archive` | *(query at runtime)* | `letta/letta-free` (4096-dim) | 0 (empty) | `pulse-monitor-agent-sleeptime` (`agent-66c4a151-7182-4cfc-9195-68b2e34d0847`) | Low |
| 3 | `pulse-monitor-agent_copy's Archive` | *(query at runtime)* | `letta/letta-free` (4096-dim) | 11 | `pulse-monitor-agent_copy` (`agent-2ed14ef4-6289-453a-ae27-290b6ed196b8`) | Low |
| 4 | `main-assistant-agent-samantha's Archive` | *(query at runtime)* | `letta/letta-free` (4096-dim) | 4 | `main-assistant-agent-samantha` | Low |
| 5 | `extracted_tasks_archive` | `archive-3f0530eb-82db-463a-a28b-f4752a95d7d5` | `null` (no embeddings) | ~10 | `email-agent`, `tasks-agent-sleeptime`, `tasks-agent` + 4 tool source files | **High** |

### Archives Already OK (no action needed)

- `pulse-monitor-agent-sleeptime_copy's Archive` -- `openai/text-embedding-3-small`
- `docs-and-transcripts-agent's Archive` -- `openai/text-embedding-3-small`

---

## Files Containing Hardcoded Archive ID `archive-3f0530eb-82db-463a-a28b-f4752a95d7d5`

### Tool Source Files (MUST update + re-register)

| File | Line(s) | Variable |
|---|---|---|
| `letta/extracted_tasks_tool.py` | 337 | `ARCHIVE_ID = "archive-3f0530eb-..."` |
| `letta/sync_omnifocus_completions_tool.py` | 48 | `ARCHIVE_ID = "archive-3f0530eb-..."` |
| `letta/retrieve_task_info_tool.py` | 70 | `ARCHIVE_ID = "archive-3f0530eb-..."` |
| `letta/task_lifecycle_tools.py` | 53, 195, 376 | `ARCHIVE_ID = "archive-3f0530eb-..."` (3 functions) |

### Documentation / Plan Files (update for reference only)

| File | Notes |
|---|---|
| `docs/plans/2026-02-16-email-task-queue.md` | Example curl command |
| `docs/plans/2026-02-17-drive-comment-task-queue-impl.md` | Config table + example curl |
| `docs/plans/2026-02-17-drive-comment-task-queue-design.md` | Config table |

### Registration Scripts (no archive ID, but must be re-run)

| Script | Registers | Attaches To |
|---|---|---|
| `letta/register_extracted_tasks_tool.py` | `add_extracted_tasks` | (manual attach) |
| `letta/attach_extracted_tasks_tool_to_agents.py` | -- | All agents |
| `letta/register_retrieve_task_info_tool.py` | `retrieve_task_info` | (manual attach) |
| `letta/register_sync_omnifocus_tool.py` | `sync_omnifocus_completions` | `tasks-agent-sleeptime` |

**Note:** `task_lifecycle_tools.py` contains 3 functions (`update_extracted_task`, `transition_extracted_task`, `merge_extracted_tasks`). There is no dedicated registration script found in the repo -- these were likely registered via an ad-hoc script or `create_from_function` call. A registration script will need to be created or the tools re-registered manually.

---

## Pre-Migration Checklist

### 1. Backup Current State

```bash
# Export all archives metadata
curl -s http://localhost:8283/v1/archives | python3 -m json.tool > /tmp/archives-backup-$(date +%Y%m%d).json

# Export passages from extracted_tasks_archive (the critical one)
curl -s "http://localhost:8283/v1/archives/archive-3f0530eb-82db-463a-a28b-f4752a95d7d5/passages?limit=1000" \
  | python3 -m json.tool > /tmp/extracted-tasks-passages-backup-$(date +%Y%m%d).json

# Export passages from each letta-free archive (query IDs first)
# For pulse-monitor-agent_copy's archive:
curl -s "http://localhost:8283/v1/archives/<ARCHIVE_ID>/passages?limit=1000" \
  | python3 -m json.tool > /tmp/pulse-monitor-copy-passages-backup.json

# For main-assistant-agent-samantha's archive:
curl -s "http://localhost:8283/v1/archives/<ARCHIVE_ID>/passages?limit=1000" \
  | python3 -m json.tool > /tmp/samantha-passages-backup.json

# Backup the extracted_tasks memory block
curl -s http://localhost:8283/v1/blocks | python3 -c "
import sys, json
blocks = json.load(sys.stdin)
for b in blocks:
    if b.get('label') == 'extracted_tasks':
        json.dump(b, open('/tmp/extracted-tasks-block-backup.json', 'w'), indent=2)
        print(f'Backed up block {b[\"id\"]}: {len(b.get(\"value\",\"\"))} chars')
"

# Snapshot agent-archive attachments
curl -s http://localhost:8283/v1/agents | python3 -c "
import sys, json
agents = json.load(sys.stdin)
for a in agents:
    archives = a.get('sources', []) or []
    if archives:
        print(f'{a[\"name\"]} ({a[\"id\"][:12]}): {[ar[\"id\"] for ar in archives]}')
" > /tmp/agent-archive-attachments-backup.txt
```

### 2. Verify Current State

```bash
# Confirm which archives have wrong embedding configs
curl -s http://localhost:8283/v1/archives | python3 -c "
import sys, json
archives = json.load(sys.stdin)
for a in archives:
    ec = a.get('embedding_config')
    model = ec.get('embedding_model', 'null') if ec else 'null'
    dim = ec.get('embedding_dim', '?') if ec else '?'
    print(f'{a[\"name\"]}: model={model}, dim={dim}, id={a[\"id\"][:20]}...')
"

# Count passages in each affected archive
for ARCHIVE_ID in archive-3f0530eb-82db-463a-a28b-f4752a95d7d5; do
  COUNT=$(curl -s "http://localhost:8283/v1/archives/$ARCHIVE_ID/passages?limit=1" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
  echo "$ARCHIVE_ID: $COUNT passages (showing up to 1)"
done
```

### 3. Verify OpenAI API Key Works

```bash
# This should succeed -- confirms embeddings will work for new archives
curl -s http://localhost:8283/v1/archives | python3 -c "
import sys, json
archives = json.load(sys.stdin)
for a in archives:
    ec = a.get('embedding_config')
    if ec and ec.get('embedding_model') == 'text-embedding-3-small':
        print(f'Working OpenAI archive found: {a[\"name\"]} ({a[\"id\"][:20]}...)')
        break
"
```

### 4. Timing Window

- **Do this during a low-activity period** (no active task extraction or OmniFocus sync running)
- Pause the `sync_omnifocus_completions` scheduler job before starting
- Notify agents are temporarily unable to write to extracted_tasks_archive

---

## Migration Steps

### Phase 1: Orphaned Archive Cleanup (Risk: None)

**Target:** `companion-agent-1758923939659's Archive` (`archive-5268deab-d883-483d-bfd7-b4b0e54451f5`)

This archive belongs to an archived agent. No live agent uses it.

```bash
# Step 1.1: Verify no active agent references this archive
curl -s http://localhost:8283/v1/agents | python3 -c "
import sys, json
agents = json.load(sys.stdin)
for a in agents:
    for src in (a.get('sources') or []):
        if src.get('id') == 'archive-5268deab-d883-483d-bfd7-b4b0e54451f5':
            print(f'ACTIVE REFERENCE: {a[\"name\"]} ({a[\"id\"]})')
"
# Expected: no output

# Step 1.2: Delete the orphaned archive
curl -X DELETE http://localhost:8283/v1/archives/archive-5268deab-d883-483d-bfd7-b4b0e54451f5

# Step 1.3: Verify deletion
curl -s http://localhost:8283/v1/archives/archive-5268deab-d883-483d-bfd7-b4b0e54451f5
# Expected: 404
```

**Rollback:** Not needed. Archive was orphaned. If mistakenly deleted an active archive, passages were backed up in pre-migration step.

---

### Phase 2: Empty letta-free Archive (Risk: Low)

**Target:** `pulse-monitor-agent-sleeptime's Archive` (0 passages, `letta/letta-free`)
**Agent:** `pulse-monitor-agent-sleeptime` (`agent-66c4a151-7182-4cfc-9195-68b2e34d0847`)

```bash
# Step 2.1: Get the current archive ID
OLD_ARCHIVE=$(curl -s http://localhost:8283/v1/agents/agent-66c4a151-7182-4cfc-9195-68b2e34d0847 | python3 -c "
import sys, json
agent = json.load(sys.stdin)
for src in (agent.get('sources') or []):
    ec = src.get('embedding_config')
    if ec and ec.get('embedding_model') == 'letta-free':
        print(src['id'])
        break
")
echo "Old archive: $OLD_ARCHIVE"

# Step 2.2: Confirm 0 passages
curl -s "http://localhost:8283/v1/archives/$OLD_ARCHIVE/passages?limit=10" | python3 -c "
import sys, json; passages = json.load(sys.stdin); print(f'{len(passages)} passages')
"
# Expected: 0 passages

# Step 2.3: Create new archive with correct embedding config
NEW_ARCHIVE=$(curl -s -X POST http://localhost:8283/v1/archives/ \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"pulse-monitor-agent-sleeptime's Archive\", \"embedding\": \"openai/text-embedding-3-small\"}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "New archive: $NEW_ARCHIVE"

# Step 2.4: Detach old archive, attach new archive
curl -X PATCH "http://localhost:8283/v1/agents/agent-66c4a151-7182-4cfc-9195-68b2e34d0847/archives/detach/$OLD_ARCHIVE"
curl -X PATCH "http://localhost:8283/v1/agents/agent-66c4a151-7182-4cfc-9195-68b2e34d0847/archives/attach/$NEW_ARCHIVE"

# Step 2.5: Rename old archive with DEPRECATED prefix
curl -X PATCH "http://localhost:8283/v1/archives/$OLD_ARCHIVE" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"DEPRECATED-pulse-monitor-agent-sleeptime-letta-free\"}"

# Step 2.6: Verify
curl -s http://localhost:8283/v1/agents/agent-66c4a151-7182-4cfc-9195-68b2e34d0847 | python3 -c "
import sys, json
agent = json.load(sys.stdin)
for src in (agent.get('sources') or []):
    ec = src.get('embedding_config', {}) or {}
    print(f'  Archive: {src[\"id\"][:20]}... model={ec.get(\"embedding_model\",\"?\")}, dim={ec.get(\"embedding_dim\",\"?\")}')
"
```

**Rollback:** Detach new archive, re-attach old archive (it was just renamed, not deleted).

---

### Phase 3: Small letta-free Archives with Passages (Risk: Low)

**Targets:**
- `pulse-monitor-agent_copy's Archive` (11 passages) -- Agent: `agent-2ed14ef4-6289-453a-ae27-290b6ed196b8`
- `main-assistant-agent-samantha's Archive` (4 passages) -- Agent: look up at runtime

Repeat for each:

```bash
# Variables (set per archive)
AGENT_ID="agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"  # pulse-monitor-agent_copy
ARCHIVE_NAME="pulse-monitor-agent_copy's Archive"

# Step 3.1: Get old archive ID
OLD_ARCHIVE=$(curl -s "http://localhost:8283/v1/agents/$AGENT_ID" | python3 -c "
import sys, json
agent = json.load(sys.stdin)
for src in (agent.get('sources') or []):
    ec = src.get('embedding_config')
    if ec and ec.get('embedding_model') == 'letta-free':
        print(src['id'])
        break
")
echo "Old archive: $OLD_ARCHIVE"

# Step 3.2: Read all passages from old archive
curl -s "http://localhost:8283/v1/archives/$OLD_ARCHIVE/passages?limit=1000" \
  | python3 -m json.tool > /tmp/migrate-passages-$OLD_ARCHIVE.json
PASSAGE_COUNT=$(python3 -c "import json; print(len(json.load(open('/tmp/migrate-passages-$OLD_ARCHIVE.json'))))")
echo "Passages to migrate: $PASSAGE_COUNT"

# Step 3.3: Create new archive with correct embedding config
NEW_ARCHIVE=$(curl -s -X POST http://localhost:8283/v1/archives/ \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$ARCHIVE_NAME\", \"embedding\": \"openai/text-embedding-3-small\"}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "New archive: $NEW_ARCHIVE"

# Step 3.4: Insert passages into new archive (text + tags only; embeddings auto-generated)
python3 -c "
import json, urllib.request

passages = json.load(open('/tmp/migrate-passages-$OLD_ARCHIVE.json'))
new_archive = '$NEW_ARCHIVE'

for i, p in enumerate(passages):
    data = json.dumps({
        'text': p['text'],
        'tags': p.get('tags', [])
    }).encode('utf-8')
    req = urllib.request.Request(
        f'http://localhost:8283/v1/archives/{new_archive}/passages',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    print(f'  [{i+1}/{len(passages)}] Inserted passage {result[\"id\"][:12]}...')

print(f'Done. Migrated {len(passages)} passages.')
"

# Step 3.5: Verify passage count in new archive
curl -s "http://localhost:8283/v1/archives/$NEW_ARCHIVE/passages?limit=1000" | python3 -c "
import sys, json; print(f'New archive has {len(json.load(sys.stdin))} passages')
"

# Step 3.6: Swap archives on agent
curl -X PATCH "http://localhost:8283/v1/agents/$AGENT_ID/archives/detach/$OLD_ARCHIVE"
curl -X PATCH "http://localhost:8283/v1/agents/$AGENT_ID/archives/attach/$NEW_ARCHIVE"

# Step 3.7: Rename old archive
curl -X PATCH "http://localhost:8283/v1/archives/$OLD_ARCHIVE" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"DEPRECATED-$ARCHIVE_NAME-letta-free\"}"

# Step 3.8: Test semantic search on new archive
curl -s -X POST http://localhost:8283/v1/passages/search \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"test\", \"archive_id\": \"$NEW_ARCHIVE\", \"limit\": 3}" | python3 -m json.tool | head -20
# Expected: results with score values (not empty)
```

**Repeat the above block** for `main-assistant-agent-samantha`, substituting the correct `AGENT_ID` and `ARCHIVE_NAME`. Look up the agent ID:

```bash
curl -s http://localhost:8283/v1/agents | python3 -c "
import sys, json
for a in json.load(sys.stdin):
    if 'samantha' in a['name'].lower():
        print(f'{a[\"name\"]}: {a[\"id\"]}')
"
```

**Rollback:** Detach new archive, re-attach old (renamed but not deleted). Old passages are intact.

---

### Phase 4: Critical Archive -- `extracted_tasks_archive` (Risk: HIGH)

**Target:** `extracted_tasks_archive` (`archive-3f0530eb-82db-463a-a28b-f4752a95d7d5`)
**Problem:** `embedding_config: null` -- no embeddings at all
**Passages:** ~10, all with `embedding: null`
**Impact:** 4 tool source files, 3+ agents, active task extraction pipeline

#### Step 4.0: Pause Dependent Services

```bash
# Pause the sync_omnifocus_completions scheduler job
# (via scheduler-service API or temporarily disable in n8n)
# This prevents race conditions during migration.
```

#### Step 4.1: Read All Passages from Old Archive

```bash
curl -s "http://localhost:8283/v1/archives/archive-3f0530eb-82db-463a-a28b-f4752a95d7d5/passages?limit=1000" \
  | python3 -m json.tool > /tmp/extracted-tasks-passages-migrate.json

PASSAGE_COUNT=$(python3 -c "import json; print(len(json.load(open('/tmp/extracted-tasks-passages-migrate.json'))))")
echo "Passages to migrate: $PASSAGE_COUNT"
```

#### Step 4.2: Create New Archive with Correct Embedding Config

```bash
NEW_ARCHIVE=$(curl -s -X POST http://localhost:8283/v1/archives/ \
  -H "Content-Type: application/json" \
  -d '{"name": "extracted_tasks_archive", "embedding": "openai/text-embedding-3-small"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "New extracted_tasks_archive: $NEW_ARCHIVE"
# SAVE THIS ID -- it goes into 4 tool source files
```

#### Step 4.3: Insert Passages into New Archive

```bash
python3 -c "
import json, urllib.request

passages = json.load(open('/tmp/extracted-tasks-passages-migrate.json'))
new_archive = '$NEW_ARCHIVE'

for i, p in enumerate(passages):
    data = json.dumps({
        'text': p['text'],
        'tags': p.get('tags', [])
    }).encode('utf-8')
    req = urllib.request.Request(
        f'http://localhost:8283/v1/archives/{new_archive}/passages',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    print(f'  [{i+1}/{len(passages)}] Inserted: REF_ID match in text: {\"REF_ID\" in p[\"text\"]}')

print(f'Done. Migrated {len(passages)} passages to {new_archive}.')
"
```

#### Step 4.4: Verify New Archive

```bash
# Verify passage count matches
curl -s "http://localhost:8283/v1/archives/$NEW_ARCHIVE/passages?limit=1000" | python3 -c "
import sys, json
passages = json.load(sys.stdin)
print(f'New archive: {len(passages)} passages')
for p in passages:
    embedding = p.get('embedding')
    has_embedding = embedding is not None and len(embedding) > 0
    print(f'  {p[\"id\"][:12]}... embedding={\"yes\" if has_embedding else \"NO\"} tags={p.get(\"tags\",[])}')
"

# Verify semantic search works
curl -s -X POST http://localhost:8283/v1/passages/search \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"TASK\", \"archive_id\": \"$NEW_ARCHIVE\", \"limit\": 3}" | python3 -c "
import sys, json
results = json.load(sys.stdin)
print(f'Search returned {len(results)} results')
for r in results:
    p = r.get('passage', r)
    print(f'  Score: {r.get(\"score\",\"?\")} | {p.get(\"text\",\"\")[:80]}...')
"
```

#### Step 4.5: Swap Archives on All Attached Agents

```bash
OLD_ARCHIVE="archive-3f0530eb-82db-463a-a28b-f4752a95d7d5"

# Find all agents with this archive attached
curl -s http://localhost:8283/v1/agents | python3 -c "
import sys, json
agents = json.load(sys.stdin)
for a in agents:
    for src in (a.get('sources') or []):
        if src.get('id') == '$OLD_ARCHIVE':
            print(f'{a[\"name\"]}: {a[\"id\"]}')
" > /tmp/agents-with-old-archive.txt

cat /tmp/agents-with-old-archive.txt

# For EACH agent listed, detach old + attach new:
while IFS=': ' read -r NAME AGENT_ID; do
  echo "Swapping archive for $NAME ($AGENT_ID)..."
  curl -s -X PATCH "http://localhost:8283/v1/agents/$AGENT_ID/archives/detach/$OLD_ARCHIVE"
  curl -s -X PATCH "http://localhost:8283/v1/agents/$AGENT_ID/archives/attach/$NEW_ARCHIVE"
  echo "  Done."
done < /tmp/agents-with-old-archive.txt
```

#### Step 4.6: Update Tool Source Code

Replace the old archive ID with the new one in all 4 tool files. Use a single sed command:

```bash
OLD_ID="archive-3f0530eb-82db-463a-a28b-f4752a95d7d5"
NEW_ID="$NEW_ARCHIVE"  # The ID from Step 4.2

# Update all 4 tool source files
for FILE in \
  /Volumes/main-drive/ai-PA/letta/extracted_tasks_tool.py \
  /Volumes/main-drive/ai-PA/letta/sync_omnifocus_completions_tool.py \
  /Volumes/main-drive/ai-PA/letta/retrieve_task_info_tool.py \
  /Volumes/main-drive/ai-PA/letta/task_lifecycle_tools.py; do
  echo "Updating $FILE..."
  sed -i '' "s|$OLD_ID|$NEW_ID|g" "$FILE"
  grep -n "ARCHIVE_ID" "$FILE"
done

# Verify no references to old ID remain in tool files
grep -r "archive-3f0530eb" /Volumes/main-drive/ai-PA/letta/*.py
# Expected: no matches (only tmp files and docs should remain)
```

#### Step 4.7: Re-register All 6 Tools with Letta

The tool source code has changed, so each tool must be deleted and re-created in Letta. The registration scripts have interactive prompts, so run them one at a time:

```bash
export LETTA_BASE_URL=http://localhost:8283

# Tool 1: add_extracted_tasks
python /Volumes/main-drive/ai-PA/letta/register_extracted_tasks_tool.py
# Answer 'y' to re-register

# Tool 2: retrieve_task_info
python /Volumes/main-drive/ai-PA/letta/register_retrieve_task_info_tool.py
# Answer 'y' to re-register

# Tool 3: sync_omnifocus_completions
python /Volumes/main-drive/ai-PA/letta/register_sync_omnifocus_tool.py
# Answer 'y' to re-register

# Tools 4-6: task_lifecycle_tools (update, transition, merge)
# No dedicated registration script exists. Register manually:
python3 -c "
import sys
sys.path.insert(0, '/Volumes/main-drive/ai-PA/letta')
import os
os.environ['LETTA_BASE_URL'] = 'http://localhost:8283'

from letta_client import Letta
from task_lifecycle_tools import update_extracted_task, transition_extracted_task, merge_extracted_tasks

client = Letta(base_url='http://localhost:8283')

# Delete existing versions
existing = client.tools.list()
for tool in existing:
    if tool.name in ('update_extracted_task', 'transition_extracted_task', 'merge_extracted_tasks'):
        print(f'Deleting old {tool.name} ({tool.id})...')
        client.tools.delete(tool.id)

# Register updated versions
for func in [update_extracted_task, transition_extracted_task, merge_extracted_tasks]:
    t = client.tools.create_from_function(func=func, tags=['tasks', 'lifecycle'])
    print(f'Registered {t.name}: {t.id}')
"
```

After re-registration, tools need to be re-attached to agents. The registration scripts for `add_extracted_tasks` and `sync_omnifocus_completions` handle attachment. For lifecycle tools, verify they are still attached:

```bash
# Check which agents had lifecycle tools and re-attach if needed
python3 -c "
from letta_client import Letta
client = Letta(base_url='http://localhost:8283')

tools = {t.name: t.id for t in client.tools.list() if t.name in ('update_extracted_task', 'transition_extracted_task', 'merge_extracted_tasks')}
print('New tool IDs:', tools)

agents = client.agents.list()
for agent in agents:
    agent_tools = client.agents.tools.list(agent.id)
    agent_tool_names = [t.name for t in agent_tools]
    for tname, tid in tools.items():
        if tname not in agent_tool_names:
            # Only attach to agents that should have it (check agent name)
            pass  # Manual decision needed
        else:
            print(f'{agent.name} already has {tname}')
"
```

#### Step 4.8: Also Remove the sync_omnifocus_completions Workaround

The `sync_omnifocus_completions_tool.py` contains a workaround comment (lines 50-53) explaining that it uses agent archival-memory endpoint because the archive has no `embedding_config`:

```python
# The tasks-agent-sleeptime has the archive attached and supports
# substring search via its archival-memory endpoint. The archive
# itself has no embedding_config, so /v1/passages/search (semantic)
# returns empty. Using agent archival-memory ?search= instead.
```

After migration, the new archive WILL have `embedding_config`, so this comment is no longer accurate. The tool can optionally be updated to use `/v1/passages/search` directly (which is more reliable and does not require knowing a specific agent ID). However, this is a **functional change** and should be tracked as a separate task. For now, just update the comment to note the workaround is legacy but still functional.

#### Step 4.9: Rename Old Archive

```bash
curl -X PATCH "http://localhost:8283/v1/archives/archive-3f0530eb-82db-463a-a28b-f4752a95d7d5" \
  -H "Content-Type: application/json" \
  -d '{"name": "DEPRECATED-extracted_tasks_archive-no-embedding"}'
```

#### Step 4.10: Resume Dependent Services

```bash
# Re-enable the sync_omnifocus_completions scheduler job
# Verify scheduler-service is running: curl http://localhost:8001/health
```

**Rollback for Phase 4:**

1. Re-attach old archive to all agents (reverse Step 4.5)
2. Revert tool source files: `git checkout -- letta/extracted_tasks_tool.py letta/sync_omnifocus_completions_tool.py letta/retrieve_task_info_tool.py letta/task_lifecycle_tools.py`
3. Re-register tools with old code (run registration scripts again)
4. Delete the new archive
5. Rename old archive back: `curl -X PATCH ... -d '{"name": "extracted_tasks_archive"}'`

---

## Post-Migration Verification

### Immediate Checks (within 15 minutes)

```bash
# 1. Verify all archives have correct embedding config
curl -s http://localhost:8283/v1/archives | python3 -c "
import sys, json
for a in json.load(sys.stdin):
    ec = a.get('embedding_config')
    model = ec.get('embedding_model', 'null') if ec else 'null'
    if 'DEPRECATED' not in a.get('name', ''):
        print(f'{a[\"name\"]}: {model}')
        assert model != 'null' and model != 'letta-free', f'BAD CONFIG: {a[\"name\"]}'
print('All active archives OK')
"

# 2. Test semantic search on new extracted_tasks_archive
curl -s -X POST http://localhost:8283/v1/passages/search \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"task\", \"archive_id\": \"$NEW_ARCHIVE\", \"limit\": 5}" | python3 -c "
import sys, json
results = json.load(sys.stdin)
assert len(results) > 0, 'Semantic search returned no results!'
print(f'Semantic search OK: {len(results)} results')
"

# 3. Test add_extracted_tasks tool (via agent message)
# Send a test task extraction request to tasks-agent-sleeptime
curl -s -X POST "http://localhost:8283/v1/agents/agent-62edcfac-2cc7-41a5-a3c2-d417da393397/messages" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Extract test task: [MIGRATION-TEST] Verify archive embedding migration. Source: manual test, from: system, reference_id: test-migration-001, location: migration-plan, location_id: n/a, source_timestamp: 2026-02-23T00:00:00Z, source_text: This is a migration verification test."}]}'
# Then verify the passage appeared in the new archive with an embedding

# 4. Verify retrieve_task_info works on a known ref_id
# (use a ref_id from the migrated passages)
```

### 24-Hour Soak Verification

- Monitor Letta logs for any `NameError`, `404`, or embedding-related errors
- Verify `sync_omnifocus_completions` runs successfully on its next scheduled invocation
- Confirm new task extractions from email-agent and other agents write to the new archive
- Check that `transition_extracted_task` (confirm action) works when confirming a task

### Cleanup (after 7-day soak)

```bash
# Delete DEPRECATED archives
curl -s http://localhost:8283/v1/archives | python3 -c "
import sys, json
for a in json.load(sys.stdin):
    if 'DEPRECATED' in a.get('name', ''):
        print(f'DELETE: {a[\"name\"]} ({a[\"id\"]})')
        # Uncomment to actually delete:
        # import urllib.request
        # urllib.request.urlopen(urllib.request.Request(
        #     f'http://localhost:8283/v1/archives/{a[\"id\"]}', method='DELETE'))
"

# Update documentation files (optional, low priority)
# - docs/plans/2026-02-16-email-task-queue.md
# - docs/plans/2026-02-17-drive-comment-task-queue-impl.md
# - docs/plans/2026-02-17-drive-comment-task-queue-design.md
```

---

## Git Commit Plan

After Phase 4 code changes are verified working:

```bash
cd /Volumes/main-drive/ai-PA

# Stage only the tool source files
git add \
  letta/extracted_tasks_tool.py \
  letta/sync_omnifocus_completions_tool.py \
  letta/retrieve_task_info_tool.py \
  letta/task_lifecycle_tools.py

git commit -m "fix: migrate extracted_tasks_archive to openai embedding config

Replace hardcoded archive ID in all task tools after creating new archive
with openai/text-embedding-3-small embedding config. The old archive had
embedding_config: null which prevented semantic search from working.

Files updated:
- letta/extracted_tasks_tool.py
- letta/sync_omnifocus_completions_tool.py
- letta/retrieve_task_info_tool.py
- letta/task_lifecycle_tools.py"
```

---

## Summary of Changes by Phase

| Phase | Archives Affected | Passages Migrated | Code Changes | Tool Re-registrations |
|---|---|---|---|---|
| 1: Orphan Cleanup | 1 deleted | 0 | None | None |
| 2: Empty letta-free | 1 replaced | 0 | None | None |
| 3: Small letta-free | 2 replaced | ~15 | None | None |
| 4: extracted_tasks | 1 replaced | ~10 | 4 files | 6 tools |
| **Total** | **5** | **~25** | **4 files** | **6 tools** |

---

## Open Questions / Future Work

1. **Optimize sync_omnifocus_completions_tool:** Now that the archive has embeddings, consider switching from agent archival-memory substring search to direct `/v1/passages/search` with tag filtering. This removes the dependency on a specific agent ID. Track as a separate task.

2. **Prevent recurrence:** Consider adding a validation check to the agent creation workflow that verifies new archives always get `openai/text-embedding-3-small` config. Could be a health check script.

3. **letta-free usage in upload_amex_statement.py:** The file `letta/upload_amex_statement.py` deliberately uses `letta/letta-free` for filesystem folders (not archives). This is intentional for Letta filesystem operations and does NOT need migration. Archives and filesystem folders are different Letta concepts.
