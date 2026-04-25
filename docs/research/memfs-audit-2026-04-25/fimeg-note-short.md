# Note for Fimeg — patch 02 delete propagation, multi-agent setups

Hey — running letta-external-memfs against a 44-agent self-hosted ecosystem. Patch 02 (`server_sync_delete_propagation.patch`) does what Vee's #3 wanted, but the implementation deletes too much when blocks are shared across agents.

In `_delete_block_from_postgres`:

```python
await session.execute(delete(BlocksAgents).where(BlocksAgents.block_id == block.id))
await block.hard_delete_async(...)
```

The `BlocksAgents` delete isn't scoped to `agent_id`, so it strips the block from every attached agent. Then `hard_delete_async` destroys the block. In a single-agent or no-shared-blocks setup this is invisible; in any setup with shared blocks (we have 12-way and 15-way attachment), syncing one agent silently removes the block from all readers.

Suggested fix:

```python
# detach this agent only
await session.execute(
    delete(BlocksAgents).where(
        BlocksAgents.agent_id == agent_id,
        BlocksAgents.block_id == block.id,
    )
)
await session.flush()

# only hard-delete if globally orphaned
remaining = await session.execute(
    select(func.count()).select_from(BlocksAgents).where(BlocksAgents.block_id == block.id)
)
if remaining.scalar() == 0:
    await block.hard_delete_async(db_session=session, actor=actor)
```

Single-agent behavior unchanged. Multi-agent setups stay intact.

Verified empirically against a 2-agent shared block on our patched server — works as expected.

Happy to PR if useful.
