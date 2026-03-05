# Design: Gmail Drafts Sidebar in pa-web-ui (via gws CLI Sidecar)

**Date:** 2026-03-04
**Status:** Approved — ready for implementation planning
**Depends on:** gws-bridge sidecar (new), meeting pipeline labeling change

---

## Overview

Add a "Drafts" tab to the pa-web-ui sidebar that lists agent-generated Gmail drafts (meeting follow-up emails), with full compose editing and send/discard actions. This also serves as a practical experiment for the Google Workspace CLI (`gws`) as a backend for Gmail operations.

## Architecture

```
Browser                pa-web-ui (Flask)        gws-bridge           Gmail API
  │                         │                      │                    │
  │  GET /api/drafts        │  GET /drafts         │  gws gmail        │
  │ ───────────────────►    │ ──────────────────►   │  users.drafts     │
  │                         │                      │  list ──────────► │
  │  ◄─────────────────     │  ◄──────────────────  │  ◄────────────── │
  │                         │                      │                    │
  │  PUT /api/drafts/{id}   │  PUT /drafts/{id}    │  gws gmail        │
  │ ───────────────────►    │ ──────────────────►   │  users.drafts     │
  │  {to,cc,subject,body}   │                      │  update ────────► │
  │                         │                      │                    │
  │  POST /api/drafts/{id}  │  POST /drafts/{id}   │  gws gmail        │
  │       /send             │       /send           │  users.drafts     │
  │ ───────────────────►    │ ──────────────────►   │  send ──────────► │
```

**pa-web-ui** gets new `/api/drafts/*` routes that proxy to the bridge.
**gws-bridge** is a Docker Compose sidecar (`platform: linux/amd64`, Rosetta emulation) wrapping `gws` CLI commands as HTTP.
**No Letta tools involved** — this is a direct pa-web-ui → bridge → Gmail path.

---

## Component 1: gws-bridge Service

Thin Node.js/Express service in Docker Compose on `pa-internal` network.

### Endpoints

| Method | Path | gws command | Purpose |
|--------|------|------------|---------|
| GET | `/health` | `gws auth status` | Health check |
| GET | `/gmail/drafts` | `gws gmail users.drafts list` | List drafts, filterable by label query |
| GET | `/gmail/drafts/:id` | `gws gmail users.drafts get` | Get draft with full body |
| PUT | `/gmail/drafts/:id` | `gws gmail users.drafts update` | Update draft (to, cc, subject, body) |
| POST | `/gmail/drafts/:id/send` | `gws gmail users.drafts send` | Send a draft |
| DELETE | `/gmail/drafts/:id` | `gws gmail users.drafts delete` | Discard a draft |
| GET | `/gmail/labels` | `gws gmail users.labels list` | List labels |

### Auth

Credentials exported from host via `gws auth export`, mounted as a read-only file.

```bash
# One-time setup on host
gws auth login          # Opens browser, authenticates
gws auth export --unmasked > gws-bridge/credentials.json
```

Container reads via `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` env var.

### Docker Compose

```yaml
gws-bridge:
  build: ./gws-bridge
  platform: linux/amd64
  container_name: gws-bridge
  restart: unless-stopped
  networks: [pa-internal]
  environment:
    GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE: /root/.gws/credentials.json
    PORT: 8098
  volumes:
    - ${GWS_CREDENTIALS_FILE:-./gws-bridge/credentials.json}:/root/.gws/credentials.json:ro
  ports: ["8098:8098"]
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8098/health"]
    interval: 30s
    timeout: 10s
```

### Verified

`gws 0.3.4` installs and runs correctly in `node:20-slim` with `platform: linux/amd64` via Rosetta on Apple Silicon. Tested: `npm install -g @googleworkspace/cli`, `gws --version`, `gws auth status`, `gws gmail --help` all succeed.

---

## Component 2: pa-web-ui Backend Routes

New routes in `app.py` that proxy to `gws-bridge:8098`:

```
GET    /api/drafts              → GET  gws-bridge:8098/gmail/drafts?q=label:Followup
GET    /api/drafts/<id>         → GET  gws-bridge:8098/gmail/drafts/<id>
PUT    /api/drafts/<id>         → PUT  gws-bridge:8098/gmail/drafts/<id>
POST   /api/drafts/<id>/send    → POST gws-bridge:8098/gmail/drafts/<id>/send
DELETE /api/drafts/<id>         → DELETE gws-bridge:8098/gmail/drafts/<id>
```

The `/api/drafts` list endpoint filters by `label:Followup` to show only agent-generated drafts.

pa-web-ui's Docker Compose entry gains `gws-bridge` as a dependency:
```yaml
depends_on:
  gws-bridge: { condition: service_healthy }
```

---

## Component 3: Frontend — Tabbed Sidebar

### Tab Structure

The existing TASKS toggle button and sidebar panel become a tabbed container:

```
┌──────────────────────────────────┐
│  [TASKS (3)] [DRAFTS (2)]    ✕  │
│─────────────────────────────────│
│                                  │
│  (content area switches based    │
│   on active tab)                 │
│                                  │
└──────────────────────────────────┘
```

- Toggle button on right edge opens the sidebar (unchanged behavior)
- Badge shows count for the active tab
- Tabs switch content; only active tab polls (30s interval)

### Draft Cards

```
┌────────────────────────────────┐
│ Re: Harris Digital Learning    │
│ To: carly@harris.edu           │
│ Followup · Proposed · 2h ago   │
│                                │
│  [Edit]  [Send]  [Discard]    │
└────────────────────────────────┘
```

Each card shows: Subject, To, label tags (Followup, Proposed), relative time. Three action buttons.

### Edit Modal — Full Compose Editor

```
┌─────────────────────────────────────────┐
│  Edit Draft                          ✕  │
│─────────────────────────────────────────│
│                                         │
│  To:      [carly@harris.edu          ]  │
│  Cc:      [                          ]  │
│  Subject: [Re: Harris Digital Learn..]  │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │                                 │    │
│  │  Hi Carly,                      │    │
│  │                                 │    │
│  │  Following up on our call...    │    │
│  │                                 │    │
│  └─────────────────────────────────┘    │
│                                         │
│           [Cancel]  [Save Draft] [Send] │
└─────────────────────────────────────────┘
```

- To, Cc, Subject: editable text inputs
- Body: textarea (plain text for v1)
- Cancel: close modal, no changes
- Save Draft: PUT to update draft, close modal, refresh card
- Send: confirmation dialog → POST to send → close modal → remove card with animation

### New JS File: `static/js/drafts.js`

`DraftsSidebar` class following same patterns as `TaskSidebar`:

| Method | Purpose |
|--------|---------|
| `loadDrafts()` | GET `/api/drafts`, update badge |
| `renderDraftList()` | Build draft cards |
| `buildDraftCard(draft)` | Create card DOM element |
| `openEditModal(draftId)` | GET full draft, populate modal |
| `saveDraft(draftId)` | PUT updated fields |
| `sendDraft(draftId)` | Confirmation → POST send → remove card |
| `discardDraft(draftId)` | Confirmation → DELETE → remove card |

### Sidebar Orchestration

`sidebar.js` gains tab management — tracks active tab, delegates render/poll to the active module (`TaskSidebar` or `DraftsSidebar`). Inactive tab stops polling.

---

## Component 4: Meeting Pipeline Labeling

Change to `prepare_meeting_followup` in `letta/meeting_followup_tool.py`:

**Current behavior:**
- `proposed=true` → adds `[Proposed]` to subject line, applies `Proposed` Gmail label
- `proposed=false` → no label applied

**New behavior:**
- **All drafts** → apply `Followup` label (new)
- `proposed=true` → additionally apply `Proposed` label and `[Proposed]` subject prefix (unchanged)
- `proposed=false` (marker-based) → `Followup` label only

**Implementation:** Add `get_or_create_label("Followup")` call and apply to every draft. ~2-3 lines changed.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| gws-bridge unreachable | Drafts tab shows "Unable to load drafts" message |
| gws auth expired | Health check fails; tab shows "Gmail auth expired" |
| Draft deleted in Gmail between load and action | Bridge returns 404; card removes itself |
| Edit save fails | Inline error in modal, modal stays open (no data loss) |
| Send clicked | Confirmation dialog: "Send this email to {recipients}?" |
| Discard clicked | Confirmation dialog: "Permanently delete this draft?" |

Polling (30s, active tab only) picks up external changes (drafts sent from Gmail, new agent drafts).

---

## Files Changed

### New Files
- `gws-bridge/Dockerfile` — linux/amd64 Node.js image with gws installed
- `gws-bridge/package.json` — Express dependency
- `gws-bridge/server.js` — HTTP endpoints wrapping gws CLI
- `gws-bridge/credentials.json` — Exported gws auth (gitignored)
- `pa-web-ui/static/js/drafts.js` — DraftsSidebar class

### Modified Files
- `docker-compose.yml` — Add gws-bridge service
- `pa-web-ui/app.py` — Add `/api/drafts/*` proxy routes, add gws-bridge dependency
- `pa-web-ui/templates/index.html` — Tab UI in sidebar header, edit modal HTML
- `pa-web-ui/static/css/styles.css` — Tab styles, draft card styles, edit modal styles
- `pa-web-ui/static/js/sidebar.js` — Tab orchestration, delegate to TaskSidebar/DraftsSidebar
- `letta/meeting_followup_tool.py` — Apply `Followup` label to all drafts

---

## Port Allocation

| Service | Port | Status |
|---------|------|--------|
| gws-bridge | 8098 | New |

---

## Success Criteria

1. **gws experiment validated:** Bridge serves Gmail draft operations reliably from Docker Compose
2. **Drafts visible:** Sidebar lists all `Followup`-labeled drafts with correct metadata
3. **Edit works:** Full compose editor saves changes back to Gmail draft
4. **Send works:** Draft sends and disappears from sidebar
5. **Discard works:** Draft deleted and disappears
6. **No disruption:** Existing task sidebar, Letta gmail tools, and meeting pipeline unaffected
7. **Auth stable:** gws credentials work for 24+ hours without manual intervention

## Future Extensions

- Rich text / HTML body editing (v2)
- Compose new draft from sidebar (not just edit existing)
- Draft reply threading (show original message context)
- Extend gws-bridge for Calendar, Drive operations (validates multi-service gws use)
