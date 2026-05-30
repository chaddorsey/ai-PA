---
date: 2026-05-30
status: backlog — review after Tasks agent migration soak
review_after: 2026-06-30 (or sooner if Tasks soak completes)
related:
  - docs/migrations/local-mode/strip-letta-identities-phase4.md
  - docs/followups/2026-05-30-strip-letta-identities.md
  - docs/runbooks/letta-local-mode-per-agent-migration.md
---

# task-cli refactor follow-up

The `task` CLI shipped 2026-05-30 as an Option-1 design (per the
[strip-Letta-identities work](2026-05-30-strip-letta-identities.md)
discussion): wrap the existing pg-canonical Python implementations in
`letta/*_tool.py` and `letta/tools/*.py` with a Click entrypoint, keep
the Python files where they are during the Tasks migration soak so
Docker rollback stays viable.

## What's transitional and needs review

After Tasks migration succeeds and the soak window passes (target
≥ 2 weeks of stable local-mode operation), revisit:

1. **Relocate the lib modules** from `letta/` to `task-cli/src/task_cli/lib/`:

   ```
   letta/retrieve_task_info_tool.py    →  task-cli/src/task_cli/lib/retrieve.py
   letta/backtrace_task_tool.py         →  task-cli/src/task_cli/lib/backtrace.py
   letta/refine_task_description_tool.py →  task-cli/src/task_cli/lib/refine.py
   letta/fetch_source_content_tool.py   →  task-cli/src/task_cli/lib/fetch_source.py
   letta/write_packet_info_tool.py      →  task-cli/src/task_cli/lib/packet.py
   letta/tools/add_extracted_tasks_postgres.py → task-cli/src/task_cli/lib/write.py
   letta/tools/consume_queue.py         →  task-cli/src/task_cli/lib/queue.py
   letta/tools/refresh_plate.py         →  task-cli/src/task_cli/lib/plate.py
   ```

   Each file currently has "all imports inside function body" because
   that was required for Letta tool extraction. Module-level imports
   are cleaner; refactor at relocation time.

2. **Detach the Letta tool registrations** from any remaining Docker
   agents (Tasks should be the only one). After Tasks migrates, these
   tools have no agent users; the registrations should go (we already
   deleted process_spark_queue / update_tasks_section / report_refs;
   the remaining set is what task-cli wraps).

3. **Update the CLI's import paths** when moving the lib modules:
   `from letta.retrieve_task_info_tool import retrieve_task_info` →
   `from task_cli.lib.retrieve import retrieve_task_info`. One-line
   change per subcommand in `cli.py`.

4. **Remove PA_AI_REPO_ROOT env var workaround** in cli.py. Without
   the cross-repo import, sys.path manipulation goes away entirely.

5. **Consider a `--dry-run` flag for `queue-claim`** — the current
   subcommand has side effects (atomic UPDATE on the queue table) on
   every call, which makes accidental smoke-tests problematic. Either
   add `--dry-run` that runs the SELECT without the UPDATE, or expose
   a separate `task queue-peek` read-only subcommand.

6. **Audit `--max-tasks`, `--window-days` defaults** against actual
   usage patterns observed during soak. Current defaults (12 active /
   7 days due-soon) inherited from `refresh_plate`'s constants.

## Why a review window vs immediate cleanup

The Docker rollback path needs the existing Letta tool registrations
to remain functional. Leaving the Python files at their current
locations means:

- Docker Tasks agent (XXX-PRE-LOCAL-...) keeps working if soak fails.
- Both interfaces (Letta tool callable, CLI subcommand) call the same
  function — bug fixes land once.
- One-line CLI import update is mechanical at refactor time.

If Tasks soak passes cleanly, the cost of the relocation is small
(~30 min: git mv, update imports, reinstall pipx, verify). Risk of
rushing the refactor before soak is high (would force re-investing
in rollback if local agent fails).

## Test plan for the relocation

```bash
# 1. Move files
git mv letta/retrieve_task_info_tool.py task-cli/src/task_cli/lib/retrieve.py
# (etc — see list above)

# 2. Update imports in cli.py (8 lines)
# 3. Refactor each lib file's "imports inside function" → module-level

# 4. Reinstall + verify
pipx reinstall task-cli
task health
task read <known-ref-id>
task search --status active --limit 3

# 5. Confirm no remaining callers in the repo still expect the old
#    letta/ paths
git grep -E "from letta\.(retrieve_task_info|backtrace_task|refine_task_description|fetch_source_content|write_packet_info)_tool"
git grep -E "from letta\.tools\.(add_extracted_tasks_postgres|consume_queue|refresh_plate)"

# 6. Detach the Letta tool registrations from any remaining agents
#    (curl PATCH /v1/agents/<id>/tools/detach/<tid>) and delete the
#    tool records (curl DELETE /v1/tools/<tid>).
```

## When to do this

Earliest: 2 weeks of stable Tasks-agent-local operation in production.
Latest: at the next clean-up sweep that touches the `letta/` directory
(e.g., MC migration).

Don't do during active migration of another agent — keep this isolated.
