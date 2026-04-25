---
date: 2026-04-25
target: Fimeg / Vee / Ezra
status: empirical, patched locally, pending share-back
parent-finding: Vee's #3 (additive-only sync)
context: docs/research/memfs-audit-2026-04-25/AUDIT.md, docs/research/2026-04-25-c3-canary-r18-findings.md
---

# Fimeg patch 02 (delete propagation) is too aggressive in multi-agent ecosystems

## TL;DR

`server_sync_delete_propagation.patch` correctly addresses Vee's #3 ("stock sync is additive-only — orphaned blocks should be deleted") but the implementation does a global block delete plus an unscoped `BlocksAgents` row wipe, which destroys data shared across agents.

In a single-agent or 3-agent test (Vee's setup), this is invisible. In any multi-agent self-hosted ecosystem with shared blocks (12-way, 15-way attachment is common), running `sync-from-git` on one agent hard-deletes blocks that other agents still need.

## What the current patch does

`letta/services/block_manager_git.py:_delete_block_from_postgres` (post-patch-02):

```python
if block:
    # Delete from blocks_agents
    await session.execute(delete(BlocksAgents).where(BlocksAgents.block_id == block.id))
    # Delete the block
    await block.hard_delete_async(db_session=session, actor=actor)
```

Two issues:

1. The `delete(BlocksAgents).where(BlocksAgents.block_id == block.id)` is **not scoped to `agent_id`** — it removes the attachment from every agent currently attached to that block.
2. `block.hard_delete_async(...)` then destroys the block row itself.

## Concrete blast radius

In our 44-agent ecosystem with the audit at `docs/research/memfs-audit-2026-04-25/AUDIT.md`:

- `important_people` block is attached to 12 agents
- `extracted_tasks` (canonical) is attached to 8 agents
- `extracted_tasks` (legacy) is attached to 15 agents
- Six Class-B queue blocks (`queued_tasks_from_email`, etc.) have multi-agent + external-service writers

If we ran `sync-from-git` on one agent that has any of these blocks attached, all other readers would silently lose the block. The Class-B queue blocks would lose their external write targets.

For us this means: **memfs migration is presently unsafe for any agent that touches a shared block**, which is most agents.

## Proposed fix

Scope the detach to the (agent, block) pair, then conditionally hard-delete only if no attachments remain globally.

```python
if block:
    # Detach this agent only. Other agents keep their attachments.
    await session.execute(
        delete(BlocksAgents).where(
            BlocksAgents.agent_id == agent_id,
            BlocksAgents.block_id == block.id,
        )
    )
    await session.flush()

    # If no other agents reference the block, hard-delete it.
    remaining = await session.execute(
        select(func.count())
        .select_from(BlocksAgents)
        .where(BlocksAgents.block_id == block.id)
    )
    if remaining.scalar() == 0:
        await block.hard_delete_async(db_session=session, actor=actor)
        logger.info(
            f"Hard-deleted orphan block '{label}' (block_id={block.id}); "
            f"no remaining agent attachments"
        )
    else:
        logger.info(
            f"Detached agent {agent_id} from block '{label}' "
            f"(block_id={block.id}); block retained for other agents"
        )
```

Single-agent / no-shared-block setups: behavior is identical to current patch (block has 0 remaining attachments → hard delete fires).

Multi-agent setups: detach is per-agent; block stays alive for other readers; only deletes when truly globally orphaned.

## Why Vee's testing didn't surface this

Vee's report describes 3-agent testing without shared blocks. The over-aggressive delete only manifests when the deleted block is also attached to other agents. Stock Letta + 1-2 agents per memory block hides the bug; production self-hosted ecosystems expose it.

## Patch as applied locally

We're running this as a fourth patch layered on top of Fimeg's 1-3 (in `letta-memfs-patches/local/server_scoped_delete_propagation.patch`). Build wrapper produces `letta-local:0.16.7-memfs-v2`.

Verification:
- Smoke test (`letta memory status` against unrelated agent) still passes
- Empirical multi-agent verification pending (planned during scratch-agent first-port)

## Recommended actions

- **Fimeg**: refine `server_sync_delete_propagation.patch` upstream to use the scoped form. Without this, the patch is unsafe for any operator with multi-agent shared-block topology. Happy to PR if useful.
- **Letta team / Ezra**: this surfaces the broader question of whether `sync_blocks_from_git` should be aware of `BlocksAgents` semantics at all, or whether the cleanup logic belongs at a different layer (e.g., post-sync cleanup with per-agent affinity). Worth a design conversation if the patch ever moves upstream.
- **Vee**: not your bug to fix, but worth knowing — your #3 finding was correctly addressed by Fimeg, the implementation just didn't account for shared-block topology you didn't have in your test setup.
