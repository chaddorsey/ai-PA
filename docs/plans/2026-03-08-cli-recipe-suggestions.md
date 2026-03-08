# Suggested Recipes for OmniFocus CLI and Slack CLI

**Date:** 2026-03-08
**Status:** Proposals only — not yet implemented
**Related:** [Letta Code Migration Assessment](2026-03-07-letta-code-migration-assessment.md)

These recipes follow the [OpenClaw SKILL.md format](https://github.com/googleworkspace/cli/tree/main/skills) used by gws. Each is a multi-step workflow template (2-5 steps) that an AI agent follows, adapting parameters to context.

Recipes are consumed two ways:
- **Letta Code agents**: As `.skills/` SKILL.md files (direct)
- **Standard Letta agents**: Via archival memory passages with `[RECIPE:namespace:name]` prefix, indexed by a `workflow_recipes` core memory block

---

## OmniFocus CLI Recipes

### Review & Planning

| Recipe ID | Description | Steps |
|-----------|-------------|-------|
| `RECIPE:omnifocus:daily-review` | Morning review of inbox, due, overdue, and flagged items | 1. List inbox items 2. List tasks due today 3. List overdue tasks 4. List flagged tasks 5. Summarize: items needing attention, quick wins, blockers |
| `RECIPE:omnifocus:weekly-planning` | Weekly review: stalled projects, completed tasks, upcoming due dates | 1. List projects with no next action (stalled) 2. List tasks completed this week 3. List tasks due next week 4. Flag top priorities for the week |
| `RECIPE:omnifocus:project-health` | Audit all active projects for staleness | 1. List all active projects 2. For each: count remaining tasks, check if next action exists 3. Flag projects with no next action or no recent activity |

### Inbox & Triage

| Recipe ID | Description | Steps |
|-----------|-------------|-------|
| `RECIPE:omnifocus:inbox-triage` | Process all inbox items to zero | 1. List inbox items 2. For each: assign project, set defer/due dates, add tags 3. Verify inbox is empty |
| `RECIPE:omnifocus:defer-sweep` | Find tasks with past defer dates and re-schedule | 1. List tasks with defer dates in the past 2. Review each: re-defer to appropriate date or flag for immediate action 3. Report count adjusted |

### Context & Focus

| Recipe ID | Description | Steps |
|-----------|-------------|-------|
| `RECIPE:omnifocus:context-switch` | Show tasks for a specific context (e.g., @office, @calls, @errands) | 1. List tasks tagged with target context 2. Sort by due date 3. Show top 5-10 actionable items |
| `RECIPE:omnifocus:focus-session` | Prepare a focused work session for a specific project | 1. List all available tasks in target project 2. Sort by sequential order 3. Show next 3 actions with estimated effort |

### Integration & Sync

| Recipe ID | Description | Steps |
|-----------|-------------|-------|
| `RECIPE:omnifocus:completion-report` | Generate a summary of recently completed tasks | 1. List tasks completed in date range 2. Group by project 3. Include completion dates and any notes |
| `RECIPE:omnifocus:meeting-action-check` | Before a meeting, check status of related tasks | 1. Search tasks tagged with meeting name or project 2. List outstanding items 3. List recently completed items for status update |
| `RECIPE:omnifocus:tag-cleanup` | Find and consolidate unused or duplicate tags | 1. List all tags with task counts 2. Identify tags with 0 tasks 3. Identify potential duplicates (similar names) 4. Report for manual cleanup |

---

## Slack CLI Recipes

### Daily Productivity

| Recipe ID | Description | Steps |
|-----------|-------------|-------|
| `RECIPE:slack:daily-digest` | Summarize today's activity across key channels | 1. Search messages in key channels from today 2. Search DMs from today 3. Summarize highlights by channel |
| `RECIPE:slack:channel-catchup` | Catch up on a channel since last read | 1. Get channel history since timestamp 2. Filter by reactions/replies (signal vs noise) 3. Summarize key discussions and decisions |
| `RECIPE:slack:notification-review` | Review unresolved mentions | 1. Search mentions of current user in date range 2. Filter for threads where user hasn't replied 3. List with surrounding context |

### Search & Discovery

| Recipe ID | Description | Steps |
|-----------|-------------|-------|
| `RECIPE:slack:find-action-items` | Search for commitments and action items in messages | 1. Search messages with action language ("need to", "please", "can you", "will do") in date range 2. Group by channel 3. Extract apparent commitments |
| `RECIPE:slack:user-activity` | Summarize a person's Slack activity | 1. Search messages from specific user in date range 2. Group by channel 3. Summarize topics and message frequency |
| `RECIPE:slack:topic-search` | Deep search on a topic across channels and time | 1. Search messages matching topic keywords 2. Identify key threads 3. For top threads: fetch full thread replies 4. Summarize findings chronologically |

### Documentation & Export

| Recipe ID | Description | Steps |
|-----------|-------------|-------|
| `RECIPE:slack:thread-export` | Export a thread as a readable transcript | 1. Get thread parent message 2. Get all replies 3. Resolve user IDs to display names 4. Format as timestamped transcript |
| `RECIPE:slack:file-roundup` | List files shared in a date range | 1. List files in date range 2. Filter by type (docs, images, code, etc.) 3. Group by channel and sender |
| `RECIPE:slack:decision-log` | Find decisions made in a channel over a period | 1. Search for decision language ("decided", "agreed", "going with", "approved") 2. Include surrounding context 3. Format as decision log with dates |

### Communication

| Recipe ID | Description | Steps |
|-----------|-------------|-------|
| `RECIPE:slack:send-update` | Post a formatted update to a channel | 1. Compose message with sections (header, body, action items) 2. Post to target channel 3. Pin if marked important |
| `RECIPE:slack:broadcast` | Send the same message to multiple channels | 1. Compose message 2. Post to each target channel 3. Report success/failure per channel |

---

## Cross-Service Recipes

These combine multiple CLIs and would live in a shared recipe namespace.

### Task Capture

| Recipe ID | Description | CLIs | Steps |
|-----------|-------------|------|-------|
| `RECIPE:cross:email-to-task` | Triage Gmail, create OmniFocus tasks for actionable emails | gws, omnifocus | 1. List unread primary inbox 2. Identify actionable emails 3. For each: create OmniFocus task with email subject + link 4. Label email as processed |
| `RECIPE:cross:slack-to-task` | Capture bookmarked Slack messages as tasks | slack, omnifocus | 1. Search for bookmarked or reacted messages 2. For each: create OmniFocus task with message text + permalink 3. Reply in thread confirming capture |

### Reporting & Summaries

| Recipe ID | Description | CLIs | Steps |
|-----------|-------------|------|-------|
| `RECIPE:cross:daily-standup` | Compile standup from tasks, calendar, and Slack | omnifocus, gws, slack | 1. List OmniFocus tasks completed yesterday 2. List OmniFocus tasks due today 3. Check today's calendar 4. Compose standup message 5. Post to standup Slack channel |
| `RECIPE:cross:weekly-report` | Generate weekly summary across all systems | omnifocus, gws, slack | 1. OmniFocus: completed tasks this week 2. Slack: highlights from key channels 3. Calendar: meetings attended 4. Create Google Doc with formatted summary |

### Meeting Workflows

| Recipe ID | Description | CLIs | Steps |
|-----------|-------------|------|-------|
| `RECIPE:cross:meeting-followup` | Post-meeting: check task status, notify team | gws, omnifocus, slack | 1. Get today's completed meetings 2. For each: search OmniFocus for related tasks 3. List outstanding action items 4. Post summary to relevant Slack channel |
| `RECIPE:cross:meeting-prep` | Pre-meeting: gather context from all sources | gws, omnifocus, slack | 1. Get next meeting details from Calendar 2. Search OmniFocus for tasks related to attendees/topic 3. Search Slack for recent discussions with attendees 4. Search Drive for shared documents 5. Compile brief |

### Notifications

| Recipe ID | Description | CLIs | Steps |
|-----------|-------------|------|-------|
| `RECIPE:cross:completion-notify` | Notify stakeholders when tasks complete | omnifocus, slack, gws | 1. Check recently completed OmniFocus tasks 2. For tasks with external origins: identify source (Slack/email/doc) 3. Send notification to appropriate channel (Slack reply, email, or doc comment) |

---

## Implemented Recipes (from existing agent workflows)

These recipes formalize multi-step procedures already documented in agent memory blocks. Unlike CLI-only recipes, these reference Letta tools (`run_gws`, `add_extracted_tasks`, etc.) because the workflows span the agent's tool ecosystem. The format is identical — numbered steps the agent follows — but the commands are tool calls rather than bash.

### RECIPE:cross:completion-feedback

```
[RECIPE:cross:completion-feedback]
Completion Feedback Loop — Notify stakeholders when externally-originated tasks are completed in OmniFocus
CLIs/Tools: sync_omnifocus_completions, prepare_completion_feedback, send_slack_dm
Agents: tasks-agent

Steps:
1. Run sync_omnifocus_completions to check for newly completed tasks.
   Filter results to tasks where has_external_origin is true.
2. For each externally-originated completion, call prepare_completion_feedback(ref_id)
   to get source context (original comment/message, document title, reply thread, routing info).
3. Craft a context-aware reply:
   - Read source_comment_text to understand the original request
   - Review comment_thread for existing replies (avoid duplicating)
   - Write a natural 1-2 sentence reply confirming completion, referencing what was done
   - For dropped tasks, briefly explain why
4. Present draft to user via send_slack_dm with:
   - text: summary of completed task and proposed action
   - suggested_reply: the crafted reply (not the raw template)
   - detail: "On [document_title], [from_person] wrote: [source_comment_text]"
   - reply_context: JSON with routing tool, args, resolve tool, resolve args
5. Wait for user response via Slack buttons (Send Reply / Modify / Skip).
   On approval: call the routing tool with provided args and reply text.
   If resolve_after_reply is true, also call the resolve tool.
6. For email sources (should_send_feedback: false), send informational DM only:
   "You may want to follow up on [task] with [person]."

Rules:
- Never send feedback without presenting to user first
- Match tone of the original comment
- Skip tasks without external origins
```

### RECIPE:cross:email-task-extract

```
[RECIPE:cross:email-task-extract]
Email Task Extraction — Extract actionable tasks from Gmail messages into the extracted_tasks system
CLIs/Tools: run_gws (Gmail), add_extracted_tasks, update_tasks_section, report_refs
Agents: email-agent

Steps:
1. Retrieve email context:
   - For queued items: read queued_tasks_from_email block, get message IDs
   - For inbox scans: run_gws(command="gmail users messages list", params='{"userId":"me","q":"<query>","maxResults":10}')
   - For each actionable message: run_gws(command="gmail users threads get", params='{"userId":"me","id":"THREAD_ID","format":"full"}')
2. Parse and normalize:
   - Split multi-ask emails into single-action, verb-led tasks
   - Derive task description from message body (not subject line)
   - Use imperative mood, remove filler
   - For evolving threads, extract the most current version of the ask
3. Deduplicate:
   - Check extracted_tasks block for existing entries
   - Account for forwarded messages, reply chains, CC'd copies
   - Keep earliest occurrence; prefer original requesting email
4. Format and store:
   - reference_id: email-{message_id}
   - Entry format: [extracted_time: YYYY-MM-DD HH:MM; ref_id: <hash>] <Task> --> email:<message_id> | subject: <subject> | from: <sender> | date: <date>
   - Context block: brief actionable excerpt (1-3 sentences), To/CC if relevant, Gmail web link
   - Call add_extracted_tasks with source_type="email", source_text=<full message body for archival>
5. For queued entries: pass cleanup_block_id and cleanup_entry_identifier to remove from queue.
   Check marker_type: "explicit" means task_hint IS the task; "pointer" means expand from email body.
6. Call report_refs to enable user follow-up on referenced content.

Rules:
- Use ONLY add_extracted_tasks or update_tasks_section for writes (never memory_replace)
- Thread-level collapse: group related asks from same thread under earliest message's ref_id
- Include due_date/defer_date/priority only when explicit in source
- Check important_people block to resolve first-name-only references
```

### RECIPE:cross:doc-task-extract

```
[RECIPE:cross:doc-task-extract]
Document & Transcript Task Extraction — Extract tasks assigned to user from Drive docs, meeting transcripts, and doc comments
CLIs/Tools: search_documents, fetch_document_from_drive, search_meetings_smart, get_meeting_details, get_document_comments, add_extracted_tasks
Agents: docs-and-transcripts-agent

Steps:
1. Retrieve source content:
   - Drive docs: search_documents or fetch_document_from_drive
   - Meeting transcripts: search_meetings_smart + get_meeting_details
   - Doc comments: get_document_comments
   Always retrieve full context before extracting.
2. Parse and filter:
   - Split multi-ask content into single-action, verb-led tasks
   - Only extract tasks explicitly assigned to user ("Chad will...", "Chad:", "Assign to Chad", "cdorsey")
   - If ownership is ambiguous, flag for human review
   - In meetings, action items often cluster after "next steps" or at section boundaries
3. Deduplicate:
   - Check extracted_tasks block before adding
   - Skip exact matches
   - Use update_extracted_task if newer version supersedes older entry
4. Format by source type and store:

   MEETING TRANSCRIPTS:
   - reference_id: meeting-{meeting_id}
   - Entry: [extracted_time; ref_id] <Task> --> meeting:{meeting_id} | title | date | attendees
   - Context: Granola link + 1-3 sentence excerpt of assignment context
   - add_extracted_tasks: source_type="meeting", source_text=<relevant transcript excerpt>

   GOOGLE DOCS:
   - reference_id: gdocs-{file_id}
   - Entry: [extracted_time; ref_id] <Task> --> gdocs:{file_id} | title | url
   - Context: excerpt from document where task was found
   - add_extracted_tasks: source_type="google-docs", source_text=<verbatim excerpt>

   DOC COMMENTS:
   - reference_id: gdocs-comment-{file_id}-{comment_id}
   - Entry: [extracted_time; ref_id] <Task> --> gdocs-comment:{file_id}/{comment_id} | doc | author | date
   - Context: verbatim comment text + reply thread if relevant
   - add_extracted_tasks: source_type="google-docs-comment", source_text=<comment + replies>

5. Call report_refs to enable user follow-up.
   Check important_people block to resolve first-name references.

Rules:
- Use ONLY add_extracted_tasks or update_tasks_section (never memory_replace)
- Include due_date/defer_date/priority only when explicit in source
- Source_text for archival should be the actionable excerpt, not the full document/transcript
- Every entry must include source ID (meeting_id, file_id, comment_id) for traceability
```

### RECIPE:slack:pulse-report

```
[RECIPE:slack:pulse-report]
Slack Pulse Report — Generate a structured Slack activity summary for a time period
CLIs/Tools: get_slack_messages, search_slack_messages, get_slack_channels, get_recently_changed_documents
Agents: pulse-monitor-agent

Steps:
1. Personal Channels section:
   - Search DMs and MPDMs for the requested period
   - Summarize top topics and key posters (play-by-play style)
   - Bullet what key posters are asking about or advocating for
   - Note sentiment/mood if notable
   - List all URLs and files shared in DMs/MPDMs (raw list)
2. Public Activity section:
   - Identify top-traffic public channels (from analytics or channel list)
   - For each channel: get message history for the period
   - Write 1-2 paragraph play-by-play of discussions, questions, key contributions
   - Bullet what key posters are asking or advocating for
   - List important links/files shared (skip bot/mundane links)
   - @-mentions sub-section: list all personal @-mentions received, formatted as:
     "From [First Name] in #[channel] on [Date, Time]: [message excerpt]"
     Hyperlink "in #[channel]" to the Slack post permalink
3. Document Activity section (optional):
   - Call get_recently_changed_documents(since="yesterday") for Drive activity
   - Surface: most-edited documents, who's been active, docs related to Slack discussions
   - Cross-reference document edits with Slack topics for fuller context

Formatting rules:
- Hyperlink the first couple words of each bullet to the relevant Slack message permalink
- Use channel names with # prefix
- Group by channel in public section
- Keep excerpts concise but attributable
```

---

## Implementation Notes

### For Letta Code Agents
Each recipe becomes a `SKILL.md` file in `.skills/recipe-<name>/`:
```yaml
---
name: recipe-<name>
version: 1.0.0
description: "<description>"
metadata:
  openclaw:
    category: "recipe"
    domain: "<domain>"
    requires:
      bins: ["omnifocus-cli"]  # or ["slack-cli"] or multiple
      skills: ["omnifocus-tasks"]  # prerequisite service skills
---
```

### For Standard Letta Agents
Each recipe becomes an archival passage:
```
[RECIPE:omnifocus:daily-review]
Daily Review — Morning review of inbox, due, overdue, and flagged items
CLIs: omnifocus-cli

Steps:
1. omnifocus-cli inbox list --format json
2. omnifocus-cli task list --filter due:today --format json
3. omnifocus-cli task list --filter overdue --format json
4. omnifocus-cli task list --filter flagged --format json
5. Summarize: items needing attention, quick wins, blockers
```

The `workflow_recipes` core memory block is updated to include the new recipe IDs alongside the gws recipes.

### Authoring Guidelines
- Keep recipes to 2-5 steps (agent can elaborate within each step)
- Use concrete CLI commands with placeholder values
- List prerequisite skills/CLIs in metadata
- Cross-service recipes should declare all required CLIs
- Recipes should be idempotent where possible (safe to re-run)
- Include "verify" steps for destructive operations
