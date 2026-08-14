# Pre-migration audit — daily-schedule-agent

- **agent_id**: `agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2`
- **agent_type**: `sleeptime_agent`
- **created**: 2025-10-16T11:24:06.726771Z
- **updated**: 2026-04-26T16:06:54.869606Z
- **system prompt**: 2424 bytes

## System prompt preview

```
<base_instructions>
You are Letta-Sleeptime-Memory, the latest version of Limnal Corporation's memory management system, developed in 2025.

You run in the background, organizing and maintaining the memories of an agent assistant who chats with the user.

Core memory (limited size):
Your core memory
```

## Blocks (26)

| Label | ID | Bytes | Shared with N other agents | Notes |
|---|---|---|---|---|
| `key_tasks_and_projects` | `block-8f922166-b2cb-428c-a66e-24ada3369121` | 2120 | 1 | — |
| `task_management_best_practices` | `block-e97c685d-fe1b-4cd2-8d54-af35e673d6ce` | 7456 | 1 | — |
| `upcoming_events_and_deadlines` | `block-c8dcfb08-3d02-439b-8ab6-5b35c6e08e53` | 607 | 1 | — |
| `zoom_meeting_info` | `block-f87464b4-df54-4c15-9afe-983eb4a2e967` | 777 | 1 | — |
| `human` | `block-238fb597-87a4-472d-9502-b31ce16ac461` | 545 | 1 | — |
| `executive_assistant_tasks_and_functions` | `block-97a3f8a4-768d-4921-940e-6ed4f25573e5` | 777 | 1 | — |
| `three_month_priorities` | `block-4a532465-8035-49d1-9e60-2ddbc37162bf` | 658 | 3 | — |
| `agent_info` | `block-61809ff0-0467-4fb7-8ee2-67655ef3f422` | 1534 | 3 | — |
| `assistant_discovery_log` | `block-ce9738ba-ff9a-4a01-9e40-d970d575b6bb` | 3125 | 1 | — |
| `assistant_confirmed_preferences` | `block-a21dc1fa-a048-41e2-915c-d0ff48b11f99` | 933 | 1 | — |
| `consolidation_instructions` | `block-522e367a-b03c-4525-a3dc-a7eafc1657ec` | 1352 | 0 | — |
| `reference_links` | `block-2178886c-18c7-46fc-8ea9-9f4ae31f28e6` | 3924 | 1 | — |
| `memory_persona` | `block-02c66398-574a-47fd-8e37-421bb9112d55` | 2772 | 0 | **persona candidate → system/persona.md** |
| `persona` | `block-660a2766-e7ff-4e58-8388-cb104d990f31` | 3513 | 1 | **persona candidate → system/persona.md** |
| `tool_use_guidelines` | `block-41482ea5-fc7e-45e6-a68c-09fa4cef6ff3` | 1486 | 1 | — |
| `task_extraction_tool_use_guidelines` | `block-e8bf985e-9f11-44f4-b889-4bba07e2fd17` | 5664 | 10 | — |
| `monitoring_recipes` | `block-53b7faf8-dbed-40ed-9e92-a28e14a65d9e` | 1144 | 1 | — |
| `active_scheduled_jobs` | `block-7be38536-640f-42d2-9a39-d5f29bff238a` | 684 | 0 | — |
| `weekly_priorities` | `block-4a7bc2a4-e9c5-4176-a7bf-ad117a4ed2fe` | 787 | 1 | — |
| `scheduling_rules_preferences_and_workflows` | `block-effc77a6-f018-4fc7-8c87-37b5e8b656b2` | 798 | 0 | — |
| `extracted_tasks` | `block-90300b77-6b72-42cb-8e67-c74fbb497cf6` | 53372 | 8 | — |
| `assistant_role_playbook` | `block-55f507ea-76ef-4df7-8fba-1638a8db488f` | 1503 | 1 | **persona candidate → system/persona.md** |
| `daily_awareness` | `block-c9b3f2aa-f33b-481d-a869-d0475ca3dbc5` | 214 | 1 | — |
| `relationship_context` | `block-65bcaa1e-56a8-4483-8d82-222a71ee7909` | 35 | 1 | — |
| `current_daily_schedule_and_available_time` | `block-28c6e49e-e2bf-4682-8b0c-68623fcee0c7` | 1640 | 1 | — |
| `important_people` | `block-02add39d-4f74-4f3c-881f-9b0b4aa30aae` | 627 | 11 | — |

## Tools (18)

```
  archival_memory_search, check_current_time, conversation_search, generate_daily_briefing
  memory, memory_finish_edits, memory_insert, memory_replace
  memory_rethink, recall_activity, scheduler_archive_job, scheduler_delete_job
  scheduler_get_job, scheduler_list_executions, scheduler_list_jobs, scheduler_search_jobs
  scheduler_update_job, send_message
```

**v1 memory tools to DETACH at memfs-enable** (replaced by Edit/Write/Read post-memfs): ['memory_replace', 'archival_memory_search', 'memory_insert', 'memory_rethink']

**Persona candidate**: `memory_persona` (2772 bytes) → becomes `system/persona.md` post-migration

## Cron jobs targeting this agent (0)

(none)

## Migration plan (Unit 16)

1. Phase A inspect (per `docs/runbooks/memfs-migration-per-agent.md`).
2. Phase B detach **stale** blocks: (none)
3. Phase B detach **shared** blocks (those attached_elsewhere > 0) per the runbook's per-pair detach pattern. Re-attach post-migration if still needed; the canonical-store skill is the new vector for shared knowledge.
4. Phases C-E: standard /memfs enable → bridge → /memfs enable → verify.
5. Phase G post-tests: smoke-test the role-specific behavior. For this agent specifically:
   - Trigger one of the 3 cron jobs manually; verify briefing produced.
