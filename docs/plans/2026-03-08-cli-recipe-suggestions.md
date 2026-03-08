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
