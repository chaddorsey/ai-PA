---
date: 2026-06-07
purpose: revert the pulse analytics cron jobs from extension tools back to server tools
risk: low (inverse string-swap of the action message; tools both still exist)
---

# Rollback: pulse analytics cron flip (extension → server tools)

On 2026-06-07 the three "Daily Analytics" cron jobs were flipped from the
server tools to the deterministic extension tools (pilot of the off-server
migration). All three triggered green via the `_ext` path.

| Job ID | Title | Flipped tool |
|---|---|---|
| `d955e69f-b8a7-47a8-8b76-299bff179f67` | Quantitative Snapshot | `collect_analytics_snapshot` → `collect_analytics_snapshot_ext` |
| `dc52c731-df9b-46c8-9152-cbe00af04fed` | Snapshot Re-collection (T+2) | `collect_analytics_snapshot` → `collect_analytics_snapshot_ext` |
| `111217cc-d389-4acf-83e6-1727b2de35b4` | Compose Morning Briefing | `compose_daily_briefing` → `compose_daily_briefing_ext` |

## Revert (inverse swap)

The flip only changed the tool name (added `_ext`) in each job's action
message. To revert, swap it back via the scheduler API:

```python
import json, urllib.request
JOBS={"d955e69f-b8a7-47a8-8b76-299bff179f67":"collect_analytics_snapshot",
      "dc52c731-df9b-46c8-9152-cbe00af04fed":"collect_analytics_snapshot",
      "111217cc-d389-4acf-83e6-1727b2de35b4":"compose_daily_briefing"}
for jid,tool in JOBS.items():
    j=json.load(urllib.request.urlopen(f"http://localhost:8087/v1/jobs/{jid}"))
    for a in j["actions"]:
        c=a.get("config",{}); c["message"]=c.get("message","").replace(tool+"_ext(", tool+"(")
    urllib.request.urlopen(urllib.request.Request(
        f"http://localhost:8087/v1/jobs/{jid}",
        data=json.dumps({"actions":j["actions"]}).encode(),
        method="PATCH", headers={"Content-Type":"application/json"}))
```

(The server tools `collect_analytics_snapshot` / `compose_daily_briefing` were
left in place, so reverting needs no re-registration. Pre-flip action configs
were also snapshotted to `/tmp/cron_flip_backup.json` during the flip — ephemeral;
this runbook is the durable record.)

## When to revert
- If the extension path regresses (e.g., the pa-tools venv or
  `~/.letta/extensions/pa-tools.ts` is broken) and the briefing must run.
- Note: reverting reintroduces the LET-9147 non-determinism. Prefer fixing the
  extension (`letta --no-extensions` recovers the TUI; check
  `~/.letta/extensions/diagnostics/latest.json`).
