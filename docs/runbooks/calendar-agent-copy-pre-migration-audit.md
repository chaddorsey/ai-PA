# Pre-migration audit — calendar-agent_copy

- **agent_id**: `agent-892a2d58-b9f6-4baf-84f3-c431fe46487d`
- **agent_type**: `letta_v1_agent`
- **created**: 2026-01-30T04:36:38.959617Z
- **updated**: 2026-04-20T04:39:45.274229Z
- **system prompt**: 2292 bytes

## System prompt preview

```
You are a calendar management specialist.

<your_role>
You manage Google Calendar operations:
- Viewing events and schedules
- Creating and modifying meetings
- Finding availability windows
- Coordinating Calendly bookings
- Looking up colleague schedules
</your_role>

<memory_system>
You maintain m
```

## Blocks (18)

| Label | ID | Bytes | Shared with N other agents | Notes |
|---|---|---|---|---|
| `task_extraction_tool_use_guidelines` | `block-e8bf985e-9f11-44f4-b889-4bba07e2fd17` | 5664 | 10 | — |
| `agent_info` | `block-e1ec8c4a-6c16-44d3-9955-329246876854` | 128 | 0 | — |
| `orchestrate_scheduling_tool_use_guidelines` | `block-e3c3d16a-a40c-4b04-8537-b52299de21bd` | 6716 | 0 | — |
| `persona` | `block-b76c1ddb-91b2-45b9-a093-3bf851d23d43` | 3246 | 0 | **persona candidate → system/persona.md** |
| `preferences_U02V91KU8` | `block-0a89b20d-6930-4ff5-a816-fda35b5fbd39` | 273 | 0 | — |
| `preferences_U0AB18G54ET` | `block-352c527c-7fad-45bd-ac17-85b6caedc9b3` | 315 | 0 | — |
| `preferences_identity-42c594bb-92bd-45ff-ad1a-2e609976eb1c` | `block-1853a4a5-981c-41ee-a027-08e121660de1` | 83 | 0 | — |
| `response_formatting_guidelines` | `block-f0baa22e-117f-4c91-a8c7-8d979020a4c9` | 833 | 0 | — |
| `scheduling_context` | `block-24c0a4c1-7660-4964-9b86-22133782edd0` | 418 | 0 | — |
| `user_calendar_context` | `block-179cf43f-5acd-4acb-9884-a6edae1d4f5c` | 108 | 0 | — |
| `user_preferences` | `block-551d65df-c63d-4aa1-abc2-a07c06a16ef2` | 76 | 0 | — |
| `preferences_identity-4b355b96-5a33-48c7-bac1-f2b88b517e12` | `block-a003caac-ebd7-408d-a168-c49c84e277ee` | 83 | 0 | — |
| `human` | `block-e5a68c10-03c1-4c85-9831-930b3ac9c4c7` | 1243 | 5 | — |
| `important_people` | `block-02add39d-4f74-4f3c-881f-9b0b4aa30aae` | 627 | 11 | — |
| `calendar_preferences` | `block-9b2abec6-eb23-4218-b81d-8e9130468f86` | 1364 | 0 | — |
| `extracted_tasks_archived` | `block-5a516880-1e01-4da5-a71b-23cad597a339` | 586 | 1 | — |
| `coordination_task_smoke-v2-test3` | `block-c4d76867-6c20-4f06-bf3d-e5fe25b07508` | 293 | 5 | — |
| `coordination_gathered_smoke-v2-test3_calendar` | `block-ac896575-ad07-4954-82c2-8015641ac6ad` | 264 | 0 | — |

## Tools (21)

```
  calendly_book_slot, calendly_create_booking_link, calendly_slots, create_user_memory_block
  explore_document_entities, extract_document_entities, find_my_availability, find_related_documents
  find_user_blocks, get_index_stats, get_recently_changed_documents, ingest_document
  list_indexed_documents, lookup_staff, memory, orchestrate_scheduling
  report_refs, run_gws, search_documents, send_message_to_agent
  update_tasks_section
```

**Persona candidate**: `persona` (3246 bytes) → becomes `system/persona.md` post-migration

## Cron jobs targeting this agent (0)

(none)

## Migration plan (Unit 16)

1. Phase A inspect (per `docs/runbooks/memfs-migration-per-agent.md`).
2. Phase B detach **stale** blocks: (none)
3. Phase B detach **shared** blocks (those attached_elsewhere > 0) per the runbook's per-pair detach pattern. Re-attach post-migration if still needed; the canonical-store skill is the new vector for shared knowledge.
4. Phases C-E: standard /memfs enable → bridge → /memfs enable → verify.
5. Phase G post-tests: smoke-test the role-specific behavior. For this agent specifically:
   - Calendar query smoke (next 5 events).
