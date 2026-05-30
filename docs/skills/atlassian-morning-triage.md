---
description: Recipe — morning Jira triage. Pulls everything assigned to the user that's been touched recently, groups by status + priority, produces a compact briefing-ready summary. Replaces the "what's on my Jira plate today?" workflow.
applies-to: MC (briefing assembly), Pulse Agent (status monitoring), any agent producing a daily/morning summary.
requires:
  cli: scripts/atlassian
  skills: ["atlassian"]
---

# Recipe — Morning Jira Triage

Goal: produce a compact, status-grouped summary of "what's on my plate
right now" suitable for a morning briefing or a quick standup answer.

## Pre-flight

```bash
atlassian health | jq -e '.status == "healthy"' > /dev/null \
  || { echo "atlassian service unhealthy — see atlassian.md re-auth"; exit 1; }
```

## Step 1 — pull assigned + recently touched

The window is configurable; defaults to **7 days** since most active
work shows up in that period.

```bash
WINDOW="${TRIAGE_WINDOW:--7d}"
atlassian jql "assignee = currentUser() AND updated > $WINDOW ORDER BY priority DESC, updated DESC" \
  --limit 50 \
  --fields summary,status,priority,updated,project \
  > /tmp/triage.json
```

## Step 2 — group by status

```bash
jq '.issues
    | group_by(.fields.status.name)
    | map({
        status: .[0].fields.status.name,
        count: length,
        issues: map({
          key,
          summary: .fields.summary,
          priority: .fields.priority.name,
          updated: .fields.updated,
        })
      })' /tmp/triage.json > /tmp/triage-by-status.json
```

## Step 3 — produce a human-readable summary

```bash
jq -r '.[] | "## \(.status) (\(.count))\n" +
  (.issues | map("- **\(.key)** [\(.priority)] \(.summary)") | join("\n"))' \
  /tmp/triage-by-status.json
```

Sample output:

```
## In Progress (3)
- **GRANT-28** [High] 397 Valhalla DSR
- **INGEST-42** [Medium] Refresh Drive RAG indices
- **INFRA-7** [Low] Bump letta-code to 0.27

## To Do (5)
...
```

## Step 4 — flag overdue / stale

Stale = no update in 14+ days but status is "In Progress":

```bash
jq '.issues | map(select(
      (.fields.status.name == "In Progress") and
      ((now - (.fields.updated | fromdateiso8601)) > (14*24*3600))
   ))' /tmp/triage.json
```

## Variations

- **Different assignee**: replace `currentUser()` with `assignee =
  "username"` or `accountId = "..."`.
- **Cross-project view by priority**: drop the project field and group
  by `priority` instead.
- **Just-unblocked work**: filter `status CHANGED TO "In Progress"
  DURING (-1d, now())` — useful for "what just got unblocked"
  briefings.
- **Add Confluence**: chain a `atlassian cql 'lastModified > now("-1d")
  AND space = "DEV"'` for active design work.

## Output to canonical signal (when run as a cron)

```bash
DIGEST=$(jq -r '...' /tmp/triage-by-status.json)
signal emit --slug "jira-triage" --source "pulse" --body "$DIGEST"
```

The Pulse Agent's daily briefing reads recent signals; emitting under
`signals/<date>/pulse-jira-triage.md` makes the triage visible to
everyone reading the day's roll-up.

## Failure modes

- **`assignee = currentUser()` returns nothing**: the OAuth grant
  may not include the right user. Check `atlassian resources` to
  see which workspace you're in; `atlassian jql "assignee =
  '<your-username>'"` as a fallback.
- **`unhealthy`**: see [atlassian.md re-auth procedure](./atlassian.md#re-auth-procedure).
- **JQL syntax error**: cross-check against
  `docs/reference/jql-docs/jql-operators.md` and
  `docs/reference/jql-docs/jql-functions.md`.
