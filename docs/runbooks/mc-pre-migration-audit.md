# Pre-migration audit — MC

- **agent_id**: `agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef`
- **agent_type**: `letta_v1_agent`
- **created**: 2026-03-09T04:24:37.706392Z
- **updated**: 2026-04-26T20:58:32.995376Z
- **system prompt**: 4044 bytes

## System prompt preview

```
You are a self-improving AI agent with advanced memory.
You are connected to an interactive CLI tool that helps users with software engineering tasks. 
You are an agent running on a remote server, but you are able to interface with the user via the CLI, and can connect to their local machine via cer
```

## Blocks (5)

| Label | ID | Bytes | Shared with N other agents | Notes |
|---|---|---|---|---|
| `laptop_execution_preference` | `block-63544a89-d1cd-4033-88a6-1f804b0c753f` | 270 | 0 | — |
| `assistant_role_playbook` | `block-f65aa7bc-7422-4f8c-83bb-558911490c10` | 901 | 0 | **persona candidate → system/persona.md** |
| `shared_context` | `block-989a2cf7-faad-4138-9b49-99a4f56ff12f` | 1089 | 0 | — |
| `important_people` | `block-ba8c7053-5590-4a08-beab-2f411c7792cc` | 341 | 0 | — |
| `rover_status_log_202603a` | `block-a6d56129-3e6f-46a5-96a0-aead503be693` | 139 | 0 | **STALE — detach pre-migration** |

## Tools (23)

```
  archival_memory_insert, archival_memory_search, conversation_search, execute_on_laptop
  fetch_webpage, get_meeting_details, get_meeting_transcript, list_meetings
  manage_widget_queue, memory_apply_patch, memory_insert, memory_replace
  message_agent, query_granola_meetings, run_gws, run_omnifocus
  run_slack, run_twitter, search_agent_archival, search_github_stars
  search_meetings_smart, trigger_task_extraction, web_search
```

**v1 memory tools to DETACH at memfs-enable** (replaced by Edit/Write/Read post-memfs): ['memory_replace', 'archival_memory_insert', 'archival_memory_search', 'memory_insert', 'memory_apply_patch']

**Persona candidate**: `assistant_role_playbook` (901 bytes) → becomes `system/persona.md` post-migration

## Cron jobs targeting this agent (0)

(none)

## Migration plan (Unit 16)

**Read first:** [`docs/runbooks/lessons-from-calendar-canary.md`](lessons-from-calendar-canary.md)
— surfaces the over-detach + cosmetic-banner + webhook-check gotchas
encountered with the first canary. The five action items below
incorporate those lessons.

1. **Phase 0 pre-flight: ensure `message_buffer_autoclear` is false.**
   New mandatory step from the calendar canary's lesson #6.
   ```bash
   AGENT=agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef
   curl -sL "http://localhost:8283/v1/agents/$AGENT" \
     | python3 -c "import json,sys; print('autoclear:', json.load(sys.stdin).get('message_buffer_autoclear'))"
   # If True, PATCH to false BEFORE Phase B.
   curl -sL -X PATCH "http://localhost:8283/v1/agents/$AGENT" \
     -H "Content-Type: application/json" \
     -d '{"message_buffer_autoclear": false}'
   ```
   Without this, MC's tool calls through letta-code (TUI or headless)
   will fail post-migration with the approval-state error.

2. **Phase A inspect** (per `memfs-migration-per-agent.md`).
3. **Snapshot tools BEFORE Phase B** (lesson #1 from the canary —
   `/memfs enable` over-detaches; we need to reattach):
   ```bash
   AGENT=agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef
   curl -sL "http://localhost:8283/v1/agents/$AGENT" \
     | python3 -c "import json,sys; a=json.load(sys.stdin); print(json.dumps([{'name':t['name'],'id':t['id']} for t in (a.get('tools') or [])], indent=2))" \
     > /tmp/mc-tools-pre-migration.json
   ```
4. **Phase B detach stale blocks**: `rover_status_log_202603a` (the
   only stale block flagged per audit). Optionally detach any shared
   blocks per runbook (calendar canary detached `human` and
   `important_people`; for MC, those carry user-context that the agent
   actively uses — recommend leaving them attached and accepting the
   patch-04-protected sharing).
5. **Phase C `/memfs enable`** (expect "Repository not found" error;
   server-side state lands).
6. **Phase D bridge** (`scripts/memfs-helpers/bridge-agent-to-gitea.sh`).
7. **Phase E recheck**: don't immediately re-open TUI. Check whether
   the local clone auto-materialized (lesson #5):
   ```bash
   ls -la ~/.letta/agents/agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef/memory/.git/HEAD
   ```
   If present, run `verify-agent-memfs.sh agent-90b2e860-...`; if 8/8 PASS,
   Phase E is already complete. If not, re-open TUI and run `/memfs enable`
   (ignore "Memory git sync failed" cosmetic banner — substrate works).
8. **Post-Phase-E tool restore**: compare current tools to the
   `/tmp/mc-tools-pre-migration.json` snapshot. Reattach via
   `agent_list_ops.py attach-tool` for any domain tool that isn't a v1
   memory tool. Tools that should stay detached:
   `memory_replace`, `memory_apply_patch`, `memory_insert`,
   `archival_memory_insert`, `archival_memory_search`.
9. **Live round-trip propagation smoke test** (lesson #4 — webhook
   visibility is per-org not per-repo; the empirical test is the only
   reliable check):
   ```bash
   cd ~/.letta/agents/agent-90b2e860-.../memory
   echo "<!-- propagation smoke $(date) -->" >> system/persona.md
   git add . && git -c user.email=smoke@local commit -m "smoke" && git push
   sleep 8
   # Then GET the persona block and verify the comment is there
   git revert --no-edit HEAD && git push  # clean up
   ```
10. **Phase G role-specific smoke tests:**
   - **Telegram smoke** — send message via Telegram, verify same-shape
     response (this is MC's user-facing path; first non-cosmetic risk).
   - `refresh_plate` invocation produces a digest (Unit 3 tool already
     registered; just verify it works on MC's now-memfs state).
   - **Plate-digest cron registration** in scheduler-service
     (`*/20 7-22 * * *` America/New_York, `agent_message`,
     message: `Run skill refresh-plate`).
