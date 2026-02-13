# Archiving Task Source References in Archival Memory

When you extract a task from any source, archive a source reference passage so the task remains traceable, searchable, and status-aware. This structure applies to all source types.

## Workflow

1. Call `add_extracted_tasks(task_description)` — returns `ref_id` (8-char hex)
2. Call `archival_memory_insert` with the passage below, using the same `ref_id`

The `ref_id` is the link between the extracted task entry in the `extracted_tasks` memory block and the detailed source reference in archival memory.

## Passage Format

```
TASK: [concise verb-led task title]
REF_ID: [8-char hex from add_extracted_tasks response]

SOURCE REFERENCE
- Type: [source type shorthand]
- Context: [human-readable origin description]
- Reference ID: [canonical unique identifier]

SOURCE METADATA
- Timestamp: [source creation timestamp, ISO 8601]
- From: [person name or ID who originated the task]
- Location: [channel, document URL, meeting ID, etc.]
- Location ID: [machine-readable location identifier]

TIMESTAMPS
- Source: [when the source message/document was created]
- Extracted: [when you extracted the task]
- OmniFocus: [when sent to OmniFocus, or "pending"]

OMNIFOCUS
- Task ID: [OmniFocus task ID, or "pending"]
- Status: [extracted | sent-to-omnifocus | completed]

SOURCE TEXT
[verbatim relevant text from the source — do NOT summarize]
```

## Source Types and Reference ID Formats

| Type shorthand | Use for | Reference ID format | Location field |
|---|---|---|---|
| `slack` | DMs, channels, MPDMs | `slack-{channel_id}-{ts}` | Channel name or "directmessage" |
| `google-docs` | Docs, Sheets, Slides | `gdocs-{document_id}` | Full document URL |
| `meeting` | Granola, calendar meetings | `meeting-{meeting_id}` | Meeting title |
| `email` | Gmail, other email | `email-{message_id}` | Subject line |

## Tag Formula (exactly 3-4 tags)

1. **Source type** (required): `source:slack`, `source:google-docs`, `source:meeting`, `source:email`
2. **Temporal** (required): `YYYY-MM` from extraction timestamp (e.g. `2026-02`)
3. **Status** (required): `status:extracted`, `status:sent-to-omnifocus`, `status:completed`
4. **Project** (optional, only if clearly relevant): `project:{name}`

All other data goes in the passage text, not in tags.

## Rules

- **REF_ID** must match the `ref_id` returned by `add_extracted_tasks`.
- The passage must be **self-contained** — readable without any other context.
- Use the **same format every time**, regardless of source type.
- **Source Text** is always verbatim. Do not summarize or paraphrase.
- **Reference ID** must be deterministic — the same source always produces the same ID.
- **Status** reflects the current state at time of archival. Update the passage (delete and re-insert) when status changes.
- If a field is not yet known (e.g. OmniFocus ID before sending), use `"pending"`.

## Examples

### Slack DM

```
archival_memory_insert(
  text="""TASK: Review agenda items highlighted in yellow on worksheet (individuals and institutions tabs)
REF_ID: a3f7b2c1

SOURCE REFERENCE
- Type: slack
- Context: Direct message from Danielle Kehoe
- Reference ID: slack-D09DLK9KRB4-1769606904.463859

SOURCE METADATA
- Timestamp: 2026-02-11T06:37:00Z
- From: Danielle Kehoe (U09B5JUK2TY)
- Location: directmessage
- Location ID: D09DLK9KRB4

TIMESTAMPS
- Source: 2026-02-11T06:37:00Z
- Extracted: 2026-02-12T21:20:00Z
- OmniFocus: pending

OMNIFOCUS
- Task ID: pending
- Status: extracted

SOURCE TEXT
the items highlighted in yellow on the worksheet are my agenda items for you for tomorrow. There are two tabs-individuals and institutions. Let me know if you have questions. Thanks! https://docs.google.com/spreadsheets/d/1TtLX2xWMWMNGhkHBfputIB-HAeJQwUQOQrmV7lj86h4/edit?gid=760208541#gid=760208541""",
  tags=["source:slack", "2026-02", "status:extracted"]
)
```

### Google Doc

```
archival_memory_insert(
  text="""TASK: Review the Moore briefing and finalize questions
REF_ID: e9d4f081

SOURCE REFERENCE
- Type: google-docs
- Context: Shared document from Danielle Kehoe via Slack
- Reference ID: gdocs-1yulbpdIROPKxZJOunpv_UrLrW0LiqW6FMrFPHT35m34

SOURCE METADATA
- Timestamp: 2026-02-11T06:38:00Z
- From: Danielle Kehoe
- Location: https://docs.google.com/document/d/1yulbpdIROPKxZJOunpv_UrLrW0LiqW6FMrFPHT35m34/edit
- Location ID: 1yulbpdIROPKxZJOunpv_UrLrW0LiqW6FMrFPHT35m34

TIMESTAMPS
- Source: 2026-02-11T06:38:00Z
- Extracted: 2026-02-12T21:25:00Z
- OmniFocus: pending

OMNIFOCUS
- Task ID: pending
- Status: extracted

SOURCE TEXT
a reminder to you to review the briefing and finalize the questions for Moore. I've made few more edits and refined based on what Notebook found. The Notebook Link is in the briefing. Thanks!""",
  tags=["source:google-docs", "2026-02", "status:extracted"]
)
```

## Key Principles

- All data fields go IN the passage text (not tags)
- Only 3-4 tags for filtering/retrieval
- Text is self-contained — readable without context
- Consistent structure — same format every time
- REF_ID links the extracted task entry to the archival passage
- Reference IDs are deterministic — same source = same ID
