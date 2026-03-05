# Gmail Drafts Sidebar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Drafts tab to the pa-web-ui sidebar for reviewing, editing, and sending agent-generated Gmail drafts, powered by a gws CLI sidecar container.

**Architecture:** gws-bridge (Node.js/Express sidecar, linux/amd64 via Rosetta) wraps `gws` CLI as HTTP on `pa-internal:8098`. pa-web-ui Flask backend proxies `/api/drafts/*` to the bridge. Frontend adds a tabbed sidebar with TASKS/DRAFTS tabs and a full compose editor modal.

**Tech Stack:** Node.js/Express (gws-bridge), Python/Flask (pa-web-ui backend), vanilla JS/CSS (frontend)

**Design doc:** `docs/plans/2026-03-04-gmail-drafts-sidebar-design.md`

---

## Task 1: gws Auth Setup on Host

**Files:**
- Create: `gws-bridge/credentials.json` (gitignored)
- Modify: `.gitignore`

**Step 1: Authenticate gws on host**

The existing `~/.gmail-mcp/gcp-oauth.keys.json` uses `"web"` client type. `gws auth login` needs an `"installed"` (desktop) client type. Check if the existing key works first:

```bash
# Try with existing key
cp ~/.gmail-mcp/gcp-oauth.keys.json ~/.config/gws/client_secret.json
gws auth login
```

If it fails with a client type error, create a new Desktop OAuth client in the same GCP project (Google Cloud Console → APIs & Services → Credentials → Create OAuth Client ID → Desktop app) and download as `client_secret.json`.

**Step 2: Export credentials for the container**

```bash
gws auth export --unmasked > gws-bridge/credentials.json
```

**Step 3: Verify auth works**

```bash
gws gmail users.drafts list --params '{"userId": "me", "maxResults": 3}' --format json
```

Expected: JSON response with draft list.

**Step 4: Add to .gitignore**

Add `gws-bridge/credentials.json` to `.gitignore` if not already covered by `*.json` patterns. Check first:

```bash
grep -n 'gws-bridge' .gitignore || echo 'gws-bridge/credentials.json' >> .gitignore
```

**Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore gws-bridge credentials"
```

---

## Task 2: gws-bridge Service — Scaffold & Health Check

**Files:**
- Create: `gws-bridge/Dockerfile`
- Create: `gws-bridge/package.json`
- Create: `gws-bridge/server.js`

**Step 1: Create `gws-bridge/package.json`**

```json
{
  "name": "gws-bridge",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "express": "^4.21.0"
  }
}
```

**Step 2: Create `gws-bridge/Dockerfile`**

```dockerfile
FROM node:20-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install gws CLI globally
RUN npm install -g @googleworkspace/cli

WORKDIR /app
COPY package.json ./
RUN npm install --production
COPY server.js ./

EXPOSE 8098
CMD ["node", "server.js"]
```

**Step 3: Create `gws-bridge/server.js` with health endpoint only**

```javascript
const express = require('express');
const { execFileSync } = require('child_process');

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 8098;
const GWS = 'gws';

function runGws(args, timeoutMs = 15000) {
  const result = execFileSync(GWS, args, {
    encoding: 'utf-8',
    timeout: timeoutMs,
    env: { ...process.env },
  });
  return JSON.parse(result);
}

// Health check
app.get('/health', (_req, res) => {
  try {
    const status = runGws(['auth', 'status']);
    const healthy = status.credential_source && status.credential_source !== 'none';
    res.json({
      status: healthy ? 'healthy' : 'unhealthy',
      gws_version: '0.3.4',
      auth: status,
    });
  } catch (err) {
    res.status(503).json({
      status: 'unhealthy',
      error: err.message,
    });
  }
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`gws-bridge listening on :${PORT}`);
});
```

**Step 4: Test the build locally**

```bash
cd gws-bridge
docker build --platform linux/amd64 -t gws-bridge-test .
docker run --rm --platform linux/amd64 \
  -v "$(pwd)/credentials.json:/root/.gws/credentials.json:ro" \
  -e GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/root/.gws/credentials.json \
  -p 8098:8098 gws-bridge-test
```

In another terminal:
```bash
curl http://localhost:8098/health
```

Expected: `{"status":"healthy","gws_version":"0.3.4","auth":{...}}`

**Step 5: Commit**

```bash
git add gws-bridge/Dockerfile gws-bridge/package.json gws-bridge/server.js
git commit -m "feat: scaffold gws-bridge service with health check"
```

---

## Task 3: gws-bridge — Gmail Draft Endpoints

**Files:**
- Modify: `gws-bridge/server.js`

**Step 1: Add list drafts endpoint**

Append to `server.js` before the `app.listen` call:

```javascript
// List drafts, optionally filtered by Gmail query
app.get('/gmail/drafts', (req, res) => {
  try {
    const q = req.query.q || '';
    const maxResults = parseInt(req.query.maxResults) || 20;
    const params = { userId: 'me', maxResults };
    if (q) params.q = q;

    const data = runGws([
      'gmail', 'users.drafts', 'list',
      '--params', JSON.stringify(params),
      '--format', 'json',
    ]);

    // gws returns raw Gmail API response: { drafts: [...], resultSizeEstimate: N }
    // Each draft has { id, message: { id, threadId } }
    // We need to fetch metadata for each draft to get subject/to/labels
    const drafts = data.drafts || [];
    const enriched = drafts.map(draft => {
      try {
        const full = runGws([
          'gmail', 'users.drafts', 'get',
          '--params', JSON.stringify({ userId: 'me', id: draft.id, format: 'metadata' }),
          '--format', 'json',
        ], 10000);

        const headers = full.message?.payload?.headers || [];
        const headerMap = {};
        headers.forEach(h => { headerMap[h.name.toLowerCase()] = h.value; });

        return {
          id: draft.id,
          messageId: full.message?.id || '',
          threadId: full.message?.threadId || '',
          subject: headerMap['subject'] || '(no subject)',
          to: headerMap['to'] || '',
          cc: headerMap['cc'] || '',
          from: headerMap['from'] || '',
          date: headerMap['date'] || '',
          snippet: full.message?.snippet || '',
          labelIds: full.message?.labelIds || [],
          internalDate: full.message?.internalDate || '',
        };
      } catch {
        return { id: draft.id, subject: '(failed to load)', error: true };
      }
    });

    res.json({ drafts: enriched, count: enriched.length });
  } catch (err) {
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});
```

**Step 2: Add get single draft endpoint (with full body)**

```javascript
// Get single draft with full body
app.get('/gmail/drafts/:id', (req, res) => {
  try {
    const data = runGws([
      'gmail', 'users.drafts', 'get',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id, format: 'full' }),
      '--format', 'json',
    ]);

    const headers = data.message?.payload?.headers || [];
    const headerMap = {};
    headers.forEach(h => { headerMap[h.name.toLowerCase()] = h.value; });

    // Extract body text — prefer text/plain, fall back to text/html
    let bodyText = '';
    const payload = data.message?.payload || {};

    function findBody(part) {
      if (part.mimeType === 'text/plain' && part.body?.data) {
        return Buffer.from(part.body.data, 'base64url').toString('utf-8');
      }
      if (part.parts) {
        for (const sub of part.parts) {
          const found = findBody(sub);
          if (found) return found;
        }
      }
      // Fall back to text/html
      if (part.mimeType === 'text/html' && part.body?.data) {
        return Buffer.from(part.body.data, 'base64url').toString('utf-8');
      }
      return null;
    }

    bodyText = findBody(payload) || '';

    res.json({
      id: data.id,
      messageId: data.message?.id || '',
      threadId: data.message?.threadId || '',
      subject: headerMap['subject'] || '',
      to: headerMap['to'] || '',
      cc: headerMap['cc'] || '',
      from: headerMap['from'] || '',
      body: bodyText,
      labelIds: data.message?.labelIds || [],
    });
  } catch (err) {
    if (err.message?.includes('404') || err.message?.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});
```

**Step 3: Add update draft endpoint**

```javascript
// Update draft (to, cc, subject, body)
app.put('/gmail/drafts/:id', (req, res) => {
  try {
    const { to, cc, subject, body } = req.body;

    // Build RFC 2822 message
    const lines = [];
    if (to) lines.push(`To: ${to}`);
    if (cc) lines.push(`Cc: ${cc}`);
    if (subject) lines.push(`Subject: ${subject}`);
    lines.push('Content-Type: text/plain; charset=utf-8');
    lines.push('');
    lines.push(body || '');
    const raw = Buffer.from(lines.join('\r\n')).toString('base64url');

    const data = runGws([
      'gmail', 'users.drafts', 'update',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id }),
      '--json', JSON.stringify({ message: { raw } }),
      '--format', 'json',
    ], 20000);

    res.json({ status: 'ok', id: data.id || req.params.id });
  } catch (err) {
    if (err.message?.includes('404') || err.message?.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});
```

**Step 4: Add send draft endpoint**

```javascript
// Send a draft
app.post('/gmail/drafts/:id/send', (req, res) => {
  try {
    const data = runGws([
      'gmail', 'users.drafts', 'send',
      '--json', JSON.stringify({ id: req.params.id }),
      '--params', JSON.stringify({ userId: 'me' }),
      '--format', 'json',
    ], 20000);

    res.json({ status: 'ok', messageId: data.id || '' });
  } catch (err) {
    if (err.message?.includes('404') || err.message?.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found (may already be sent)' });
    }
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});
```

**Step 5: Add delete draft endpoint**

```javascript
// Delete (discard) a draft
app.delete('/gmail/drafts/:id', (req, res) => {
  try {
    runGws([
      'gmail', 'users.drafts', 'delete',
      '--params', JSON.stringify({ userId: 'me', id: req.params.id }),
      '--format', 'json',
    ]);
    res.json({ status: 'ok' });
  } catch (err) {
    if (err.message?.includes('404') || err.message?.includes('Not Found')) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    res.status(502).json({ error: `gws error: ${err.message}` });
  }
});
```

**Step 6: Test draft endpoints manually**

Rebuild and restart the container, then:
```bash
# List drafts
curl http://localhost:8098/gmail/drafts?q=label:Followup

# Get a specific draft (use an ID from the list response)
curl http://localhost:8098/gmail/drafts/DRAFT_ID

# Update a draft
curl -X PUT http://localhost:8098/gmail/drafts/DRAFT_ID \
  -H 'Content-Type: application/json' \
  -d '{"to":"test@example.com","subject":"Test","body":"Hello"}'
```

Do NOT test send/delete with real drafts unless you intend to lose them.

**Step 7: Commit**

```bash
git add gws-bridge/server.js
git commit -m "feat: add Gmail draft CRUD endpoints to gws-bridge"
```

---

## Task 4: Docker Compose Integration

**Files:**
- Modify: `docker-compose.yml` (after the `pa-routing-handler` service block, ~line 1297)
- Modify: `docker-compose.yml` (pa-web-ui `depends_on` block, ~line 1305)
- Modify: `docker-compose.yml` (pa-web-ui `environment` block, ~line 1312)

**Step 1: Add gws-bridge service to docker-compose.yml**

Add after the `pa-routing-handler` service block (before `pa-web-ui`):

```yaml
  gws-bridge:
    build:
      context: ./gws-bridge
      dockerfile: Dockerfile
    platform: linux/amd64
    container_name: gws-bridge
    restart: unless-stopped
    networks: [pa-internal]
    environment:
      - GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/root/.gws/credentials.json
      - PORT=8098
    volumes:
      - ./gws-bridge/credentials.json:/root/.gws/credentials.json:ro
    ports:
      - "8098:8098"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8098/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    labels:
      - "service=gws-bridge"
      - "component=gmail"
      - "network=pa-internal"
```

**Step 2: Add gws-bridge as dependency to pa-web-ui**

In the `pa-web-ui` service `depends_on` block (~line 1305), add:

```yaml
      gws-bridge:
        condition: service_healthy
```

**Step 3: Add GWS_BRIDGE_URL env var to pa-web-ui**

In the `pa-web-ui` `environment` block (~line 1312), add:

```yaml
      - GWS_BRIDGE_URL=http://gws-bridge:8098
```

**Step 4: Build and start gws-bridge**

```bash
docker-compose up -d --build gws-bridge
docker-compose logs -f gws-bridge
```

Expected: `gws-bridge listening on :8098`, health check passing.

**Step 5: Verify from pa-web-ui container**

```bash
docker exec pa-web-ui curl -s http://gws-bridge:8098/health
```

Expected: `{"status":"healthy",...}`

**Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add gws-bridge sidecar to Docker Compose"
```

---

## Task 5: pa-web-ui Backend — Draft Proxy Routes

**Files:**
- Modify: `pa-web-ui/app.py` (add routes after the omnifocus-create route, ~line 1673)

**Step 1: Add GWS_BRIDGE_URL constant**

Near the other URL constants at the top of `app.py` (~line 110-113), add:

```python
GWS_BRIDGE_URL = os.getenv("GWS_BRIDGE_URL", "http://gws-bridge:8098")
```

**Step 2: Add draft proxy routes**

Insert before the `if __name__ == "__main__":` block (~line 1675):

```python
# ── Gmail Drafts API (proxied via gws-bridge) ──

@app.route('/api/drafts', methods=['GET'])
def api_list_drafts():
    """List Gmail drafts filtered by Followup label."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{GWS_BRIDGE_URL}/gmail/drafts",
                params={"q": "label:Followup", "maxResults": 50},
            )
            resp.raise_for_status()
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        logger.error("api_list_drafts_error", status=e.response.status_code)
        return jsonify({"error": f"Bridge error: {e.response.status_code}"}), 502
    except Exception as e:
        logger.error("api_list_drafts_error", error=str(e))
        return jsonify({"error": str(e)}), 502


@app.route('/api/drafts/<draft_id>', methods=['GET'])
def api_get_draft(draft_id):
    """Get a single draft with full body."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{GWS_BRIDGE_URL}/gmail/drafts/{draft_id}")
            resp.raise_for_status()
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            return jsonify({"error": "Draft not found"}), 404
        return jsonify({"error": f"Bridge error: {status}"}), 502
    except Exception as e:
        logger.error("api_get_draft_error", error=str(e))
        return jsonify({"error": str(e)}), 502


@app.route('/api/drafts/<draft_id>', methods=['PUT'])
def api_update_draft(draft_id):
    """Update a draft's to, cc, subject, or body."""
    try:
        data = request.get_json()
        with httpx.Client(timeout=30) as client:
            resp = client.put(
                f"{GWS_BRIDGE_URL}/gmail/drafts/{draft_id}",
                json=data,
            )
            resp.raise_for_status()
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            return jsonify({"error": "Draft not found"}), 404
        return jsonify({"error": f"Bridge error: {status}"}), 502
    except Exception as e:
        logger.error("api_update_draft_error", error=str(e))
        return jsonify({"error": str(e)}), 502


@app.route('/api/drafts/<draft_id>/send', methods=['POST'])
def api_send_draft(draft_id):
    """Send a draft."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{GWS_BRIDGE_URL}/gmail/drafts/{draft_id}/send")
            resp.raise_for_status()
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            return jsonify({"error": "Draft not found (may already be sent)"}), 404
        return jsonify({"error": f"Bridge error: {status}"}), 502
    except Exception as e:
        logger.error("api_send_draft_error", error=str(e))
        return jsonify({"error": str(e)}), 502


@app.route('/api/drafts/<draft_id>', methods=['DELETE'])
def api_delete_draft(draft_id):
    """Delete (discard) a draft."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.delete(f"{GWS_BRIDGE_URL}/gmail/drafts/{draft_id}")
            resp.raise_for_status()
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            return jsonify({"error": "Draft not found"}), 404
        return jsonify({"error": f"Bridge error: {status}"}), 502
    except Exception as e:
        logger.error("api_delete_draft_error", error=str(e))
        return jsonify({"error": str(e)}), 502
```

**Step 3: Add `from flask import request` if not already imported**

Check line 1 area — `request` should already be imported via Flask. Verify:

```bash
grep 'from flask import' pa-web-ui/app.py
```

If `request` is missing, add it to the import.

**Step 4: Test the proxy routes**

```bash
docker-compose up -d --build pa-web-ui
curl http://localhost:5200/api/drafts
```

Expected: JSON with `{ "drafts": [...], "count": N }`

**Step 5: Commit**

```bash
git add pa-web-ui/app.py
git commit -m "feat: add draft proxy routes to pa-web-ui backend"
```

---

## Task 6: Frontend — Tabbed Sidebar Structure

**Files:**
- Modify: `pa-web-ui/templates/index.html` (lines 41-59, sidebar toggle + sidebar header)
- Modify: `pa-web-ui/static/css/styles.css` (add tab styles)
- Modify: `pa-web-ui/static/js/sidebar.js` (add tab orchestration)

**Step 1: Update index.html — sidebar toggle and header**

Replace the sidebar toggle button (lines 42-45):

```html
        <!-- Sidebar toggle tab -->
        <button id="sidebar-toggle" class="sidebar-toggle">
            <span class="sidebar-toggle-label">TASKS</span>
            <span id="task-badge" class="task-badge"></span>
        </button>
```

With:

```html
        <!-- Sidebar toggle tab -->
        <button id="sidebar-toggle" class="sidebar-toggle">
            <span class="sidebar-toggle-label" id="sidebar-toggle-label">TASKS</span>
            <span id="sidebar-badge" class="task-badge"></span>
        </button>
```

Replace the sidebar header (lines 48-52):

```html
        <aside id="task-sidebar" class="task-sidebar">
            <div class="sidebar-header">
                <h2>Task Review</h2>
                <button class="sidebar-close-btn">&times;</button>
            </div>
```

With:

```html
        <aside id="task-sidebar" class="task-sidebar">
            <div class="sidebar-header">
                <div class="sidebar-tabs">
                    <button class="sidebar-tab active" data-tab="tasks">
                        Tasks <span id="tasks-tab-count" class="tab-count"></span>
                    </button>
                    <button class="sidebar-tab" data-tab="drafts">
                        Drafts <span id="drafts-tab-count" class="tab-count"></span>
                    </button>
                </div>
                <button class="sidebar-close-btn">&times;</button>
            </div>
```

Add a drafts content area after the task-list div (after line 53):

```html
            <div id="draft-list" class="task-list" style="display:none"></div>
```

**Step 2: Add tab styles to styles.css**

Add after the `.sidebar-header` styles (find the existing sidebar-header block):

```css
/* ── Sidebar Tabs ── */

.sidebar-tabs {
    display: flex;
    gap: 2px;
}

.sidebar-tab {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 6px 12px;
    cursor: pointer;
    border-radius: 4px 4px 0 0;
    border-bottom: 2px solid transparent;
    transition: color 0.2s, border-color 0.2s;
}

.sidebar-tab:hover {
    color: var(--text-primary);
}

.sidebar-tab.active {
    color: var(--sb-teal);
    border-bottom-color: var(--sb-teal);
}

.tab-count {
    font-size: 0.65rem;
    opacity: 0.7;
}

.tab-count:not(:empty)::before {
    content: '(';
}

.tab-count:not(:empty)::after {
    content: ')';
}
```

**Step 3: Update sidebar.js — add tab switching**

Add tab management to the `TaskSidebar` constructor, after `this.bindEvents()` (line 23):

```javascript
    // Tab management
    this.activeTab = 'tasks';
    this.draftsSidebar = null; // Set after DraftsSidebar loads
    this.bindTabEvents();
```

Add `bindTabEvents` method after `bindEvents`:

```javascript
  bindTabEvents() {
    document.querySelectorAll('.sidebar-tab').forEach(tab => {
      tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
    });
  }

  switchTab(tabName) {
    if (tabName === this.activeTab) return;
    this.activeTab = tabName;

    // Update tab UI
    document.querySelectorAll('.sidebar-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === tabName);
    });

    // Update toggle label
    const label = document.getElementById('sidebar-toggle-label');
    label.textContent = tabName === 'tasks' ? 'TASKS' : 'DRAFTS';

    // Switch content
    const taskList = document.getElementById('task-list');
    const draftList = document.getElementById('draft-list');
    const bulkBar = document.getElementById('bulk-actions-bar');

    if (tabName === 'tasks') {
      taskList.style.display = '';
      draftList.style.display = 'none';
      bulkBar.style.display = '';
      this.stopPolling();
      this.loadTasks();
      this.startPolling();
    } else {
      taskList.style.display = 'none';
      draftList.style.display = '';
      bulkBar.style.display = 'none';
      this.stopPolling();
      if (this.draftsSidebar) {
        this.draftsSidebar.loadDrafts();
        this.draftsSidebar.startPolling();
      }
    }
  }
```

Update the existing `open()` method to be tab-aware:

```javascript
  open() {
    this.isOpen = true;
    this.sidebar.classList.add('open');
    this.toggleTab.classList.add('active');
    if (this.activeTab === 'tasks') {
      this.loadTasks();
      this.startPolling();
    } else if (this.draftsSidebar) {
      this.draftsSidebar.loadDrafts();
      this.draftsSidebar.startPolling();
    }
  }
```

Update the existing `close()` method:

```javascript
  close() {
    this.isOpen = false;
    this.sidebar.classList.remove('open');
    this.toggleTab.classList.remove('active');
    this.stopPolling();
    if (this.draftsSidebar) this.draftsSidebar.stopPolling();
  }
```

Update `updateBadge` to use the new badge ID and also update tab counts:

```javascript
  updateBadge(count) {
    const badge = document.getElementById('sidebar-badge');
    const tabCount = document.getElementById('tasks-tab-count');
    if (count > 0) {
      if (this.activeTab === 'tasks') {
        badge.textContent = count;
        badge.classList.add('visible');
      }
      tabCount.textContent = count;
    } else {
      if (this.activeTab === 'tasks') {
        badge.textContent = '0';
        badge.classList.remove('visible');
      }
      tabCount.textContent = '';
    }
  }
```

**Step 4: Test tab switching**

Rebuild pa-web-ui, open sidebar, verify:
- Two tabs visible (Tasks / Drafts)
- Clicking Drafts switches content area (shows empty for now)
- Clicking Tasks switches back
- Toggle label updates

**Step 5: Commit**

```bash
git add pa-web-ui/templates/index.html pa-web-ui/static/css/styles.css pa-web-ui/static/js/sidebar.js
git commit -m "feat: add tabbed sidebar with Tasks/Drafts tabs"
```

---

## Task 7: Frontend — DraftsSidebar Class (List + Cards)

**Files:**
- Create: `pa-web-ui/static/js/drafts.js`
- Modify: `pa-web-ui/templates/index.html` (add script tag)

**Step 1: Create `pa-web-ui/static/js/drafts.js`**

```javascript
// Gmail Drafts Sidebar — view, edit, send, and discard agent-generated drafts

class DraftsSidebar {
  constructor(taskSidebar) {
    this.taskSidebar = taskSidebar;
    this.drafts = [];
    this.pollInterval = null;
    this.draftList = document.getElementById('draft-list');
  }

  // ── Polling ──

  startPolling() {
    this.stopPolling();
    this.pollInterval = setInterval(() => this.loadDrafts(), 30000);
  }

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  // ── Loading ──

  async loadDrafts() {
    try {
      this.draftList.classList.add('loading');
      const resp = await fetch('/api/drafts');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.drafts = data.drafts || [];
      this.updateBadge(this.drafts.length);
      this.renderDraftList();
    } catch (e) {
      this.draftList.innerHTML = `<div class="sidebar-error">Unable to load drafts<br><small>${this.escapeHtml(e.message)}</small></div>`;
    } finally {
      this.draftList.classList.remove('loading');
    }
  }

  updateBadge(count) {
    const badge = document.getElementById('sidebar-badge');
    const tabCount = document.getElementById('drafts-tab-count');
    tabCount.textContent = count > 0 ? count : '';
    if (this.taskSidebar.activeTab === 'drafts') {
      if (count > 0) {
        badge.textContent = count;
        badge.classList.add('visible');
      } else {
        badge.textContent = '0';
        badge.classList.remove('visible');
      }
    }
  }

  // ── Rendering ──

  renderDraftList() {
    if (this.drafts.length === 0) {
      this.draftList.innerHTML = '<div class="sidebar-empty"><span class="empty-icon">&#9993;</span>No drafts</div>';
      return;
    }

    this.draftList.innerHTML = '';
    this.drafts.forEach(draft => {
      if (!draft.error) {
        this.draftList.appendChild(this.buildDraftCard(draft));
      }
    });
  }

  buildDraftCard(draft) {
    const card = document.createElement('div');
    card.className = 'draft-card';
    card.dataset.draftId = draft.id;

    const labels = (draft.labelIds || [])
      .filter(l => ['Followup', 'Proposed'].includes(l) || l.startsWith('Label_'))
      .map(l => `<span class="draft-label">${this.escapeHtml(l)}</span>`)
      .join('');

    // Gmail labelIds are IDs not names — we'll show known ones
    const hasProposed = (draft.labelIds || []).some(l => l === 'Proposed' || draft.snippet?.includes('[Proposed]'));
    const labelTags = `<span class="draft-label">Followup</span>${hasProposed ? '<span class="draft-label draft-label-proposed">Proposed</span>' : ''}`;

    const timeLabel = draft.internalDate
      ? this.formatTime(new Date(parseInt(draft.internalDate)))
      : (draft.date ? this.formatTime(new Date(draft.date)) : '');

    card.innerHTML = `
      <div class="draft-card-body">
        <div class="draft-card-subject">${this.escapeHtml(draft.subject || '(no subject)')}</div>
        <div class="draft-card-to">To: ${this.escapeHtml(draft.to || '(no recipient)')}</div>
        <div class="draft-card-meta">
          ${labelTags}
          <span class="draft-time">${this.escapeHtml(timeLabel)}</span>
        </div>
      </div>
      <div class="draft-card-actions">
        <button class="draft-btn draft-btn-edit" title="Edit">&#9998;</button>
        <button class="draft-btn draft-btn-send" title="Send">&#10148;</button>
        <button class="draft-btn draft-btn-discard" title="Discard">&#10005;</button>
      </div>
    `;

    card.querySelector('.draft-btn-edit').addEventListener('click', () => this.openEditModal(draft.id));
    card.querySelector('.draft-btn-send').addEventListener('click', () => this.sendDraft(draft.id, draft.to));
    card.querySelector('.draft-btn-discard').addEventListener('click', () => this.discardDraft(draft.id, card));

    return card;
  }

  formatTime(date) {
    try {
      const now = new Date();
      const diffMs = now - date;
      const diffHours = diffMs / (1000 * 60 * 60);

      if (diffHours < 1) return `${Math.max(1, Math.floor(diffMs / 60000))}m ago`;
      if (diffHours < 24) return `${Math.floor(diffHours)}h ago`;
      if (diffHours < 48) return 'yesterday';
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  }

  // ── Edit Modal ──

  async openEditModal(draftId) {
    const overlay = document.getElementById('draft-edit-overlay');
    const toInput = document.getElementById('draft-edit-to');
    const ccInput = document.getElementById('draft-edit-cc');
    const subjectInput = document.getElementById('draft-edit-subject');
    const bodyInput = document.getElementById('draft-edit-body');
    const errorEl = document.getElementById('draft-edit-error');

    // Reset
    toInput.value = '';
    ccInput.value = '';
    subjectInput.value = '';
    bodyInput.value = '';
    errorEl.textContent = '';
    errorEl.style.display = 'none';
    overlay.dataset.draftId = draftId;

    overlay.classList.add('visible');

    // Load full draft
    try {
      const resp = await fetch(`/api/drafts/${draftId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      toInput.value = data.to || '';
      ccInput.value = data.cc || '';
      subjectInput.value = data.subject || '';
      bodyInput.value = data.body || '';
    } catch (e) {
      errorEl.textContent = `Failed to load draft: ${e.message}`;
      errorEl.style.display = 'block';
    }
  }

  async saveDraft() {
    const overlay = document.getElementById('draft-edit-overlay');
    const draftId = overlay.dataset.draftId;
    const errorEl = document.getElementById('draft-edit-error');
    const saveBtn = document.getElementById('draft-edit-save-btn');

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving\u2026';
    errorEl.style.display = 'none';

    try {
      const resp = await fetch(`/api/drafts/${draftId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to: document.getElementById('draft-edit-to').value,
          cc: document.getElementById('draft-edit-cc').value,
          subject: document.getElementById('draft-edit-subject').value,
          body: document.getElementById('draft-edit-body').value,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      this.closeEditModal();
      await this.loadDrafts();
    } catch (e) {
      errorEl.textContent = `Save failed: ${e.message}`;
      errorEl.style.display = 'block';
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Draft';
    }
  }

  async sendFromModal() {
    const overlay = document.getElementById('draft-edit-overlay');
    const draftId = overlay.dataset.draftId;
    const to = document.getElementById('draft-edit-to').value;

    // Save first, then send
    const errorEl = document.getElementById('draft-edit-error');
    const sendBtn = document.getElementById('draft-edit-send-btn');

    if (!confirm(`Send this email to ${to}?`)) return;

    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending\u2026';
    errorEl.style.display = 'none';

    try {
      // Save current edits
      await fetch(`/api/drafts/${draftId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to: document.getElementById('draft-edit-to').value,
          cc: document.getElementById('draft-edit-cc').value,
          subject: document.getElementById('draft-edit-subject').value,
          body: document.getElementById('draft-edit-body').value,
        }),
      });

      // Send
      const resp = await fetch(`/api/drafts/${draftId}/send`, { method: 'POST' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      this.closeEditModal();
      this.drafts = this.drafts.filter(d => d.id !== draftId);
      this.updateBadge(this.drafts.length);
      this.renderDraftList();
    } catch (e) {
      errorEl.textContent = `Send failed: ${e.message}`;
      errorEl.style.display = 'block';
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = 'Send';
    }
  }

  closeEditModal() {
    document.getElementById('draft-edit-overlay')?.classList.remove('visible');
  }

  // ── Card Actions ──

  async sendDraft(draftId, to) {
    if (!confirm(`Send this email to ${to || 'recipient'}?`)) return;

    try {
      const resp = await fetch(`/api/drafts/${draftId}/send`, { method: 'POST' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const card = this.draftList.querySelector(`.draft-card[data-draft-id="${draftId}"]`);
      if (card) this.removeCard(card);
      this.drafts = this.drafts.filter(d => d.id !== draftId);
      this.updateBadge(this.drafts.length);
    } catch (e) {
      alert(`Send failed: ${e.message}`);
    }
  }

  async discardDraft(draftId, card) {
    if (!confirm('Permanently delete this draft?')) return;

    try {
      const resp = await fetch(`/api/drafts/${draftId}`, { method: 'DELETE' });
      if (!resp.ok && resp.status !== 404) throw new Error(`HTTP ${resp.status}`);

      this.removeCard(card);
      this.drafts = this.drafts.filter(d => d.id !== draftId);
      this.updateBadge(this.drafts.length);
    } catch (e) {
      alert(`Discard failed: ${e.message}`);
    }
  }

  removeCard(card) {
    card.classList.add('removing');
    card.addEventListener('transitionend', () => card.remove(), { once: true });
    setTimeout(() => { if (card.parentNode) card.remove(); }, 500);
  }

  // ── Utilities ──

  escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}
```

**Step 2: Add edit modal HTML to index.html**

Add after the Merge Dialog block (after line 97):

```html
    <!-- Draft Edit Dialog -->
    <div id="draft-edit-overlay" class="dialog-overlay">
        <div class="dialog draft-edit-dialog">
            <div class="dialog-header">
                <h3>Edit Draft</h3>
                <button class="dialog-close" id="draft-edit-cancel">&times;</button>
            </div>
            <div class="draft-edit-fields">
                <label class="draft-field-label">
                    <span>To</span>
                    <input type="text" id="draft-edit-to" class="draft-field-input" placeholder="recipient@example.com" />
                </label>
                <label class="draft-field-label">
                    <span>Cc</span>
                    <input type="text" id="draft-edit-cc" class="draft-field-input" placeholder="cc@example.com" />
                </label>
                <label class="draft-field-label">
                    <span>Subject</span>
                    <input type="text" id="draft-edit-subject" class="draft-field-input" />
                </label>
                <textarea id="draft-edit-body" class="draft-edit-body" rows="12" placeholder="Email body..."></textarea>
            </div>
            <div id="draft-edit-error" class="draft-edit-error" style="display:none"></div>
            <div class="dialog-footer">
                <div class="dialog-footer-buttons">
                    <button class="dialog-btn dialog-btn-cancel" id="draft-edit-cancel-btn">Cancel</button>
                    <button class="dialog-btn dialog-btn-confirm" id="draft-edit-save-btn">Save Draft</button>
                    <button class="dialog-btn draft-send-btn" id="draft-edit-send-btn">Send</button>
                </div>
            </div>
        </div>
    </div>
```

**Step 3: Add drafts.js script tag to index.html**

After the sidebar.js script tag (line 100):

```html
    <script src="{{ url_for('static', filename='js/drafts.js') }}?v=1"></script>
```

**Step 4: Wire DraftsSidebar into TaskSidebar initialization**

Update the DOMContentLoaded handler at the bottom of `sidebar.js` (line 742-744):

```javascript
document.addEventListener('DOMContentLoaded', () => {
  window.taskSidebar = new TaskSidebar();
  window.draftsSidebar = new DraftsSidebar(window.taskSidebar);
  window.taskSidebar.draftsSidebar = window.draftsSidebar;

  // Draft edit modal events
  document.getElementById('draft-edit-overlay')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) window.draftsSidebar.closeEditModal();
  });
  document.getElementById('draft-edit-cancel')?.addEventListener('click', () => window.draftsSidebar.closeEditModal());
  document.getElementById('draft-edit-cancel-btn')?.addEventListener('click', () => window.draftsSidebar.closeEditModal());
  document.getElementById('draft-edit-save-btn')?.addEventListener('click', () => window.draftsSidebar.saveDraft());
  document.getElementById('draft-edit-send-btn')?.addEventListener('click', () => window.draftsSidebar.sendFromModal());

  // Load initial draft count
  window.draftsSidebar.loadDrafts();
});
```

Also add draft edit modal to the Escape key handler in `bindEvents`:

```javascript
    // Update escape handler (inside bindEvents)
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (document.getElementById('draft-edit-overlay')?.classList.contains('visible')) {
          window.draftsSidebar?.closeEditModal();
        } else if (document.getElementById('of-dialog-overlay')?.classList.contains('visible')) {
          this.closeOFDialog();
        } else if (document.getElementById('merge-dialog-overlay')?.classList.contains('visible')) {
          this.closeMergeDialog();
        } else if (this.isOpen) {
          this.close();
        }
      }
    });
```

**Step 5: Commit**

```bash
git add pa-web-ui/static/js/drafts.js pa-web-ui/templates/index.html pa-web-ui/static/js/sidebar.js
git commit -m "feat: add DraftsSidebar class with list, edit modal, send, and discard"
```

---

## Task 8: Frontend — Draft Card & Modal Styles

**Files:**
- Modify: `pa-web-ui/static/css/styles.css`

**Step 1: Add draft card styles**

Add after the task card styles block (after the `.task-card` section, ~line 920):

```css
/* ── Draft Cards ── */

.draft-card {
    background: var(--sb-card);
    border: 1px solid var(--sb-card-border);
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 8px;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    transition: background 0.15s, border-color 0.15s, opacity 0.3s, transform 0.3s;
}

.draft-card:hover {
    background: var(--sb-card-hover);
    border-color: #2f3560;
}

.draft-card.removing {
    opacity: 0;
    transform: translateX(100%);
    pointer-events: none;
}

.draft-card-body {
    flex: 1;
    min-width: 0;
}

.draft-card-subject {
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 3px;
}

.draft-card-to {
    font-size: 0.72rem;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 6px;
}

.draft-card-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
}

.draft-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(0, 212, 170, 0.12);
    color: var(--sb-teal-dim);
    border: 1px solid rgba(0, 212, 170, 0.2);
}

.draft-label-proposed {
    background: rgba(255, 171, 64, 0.12);
    color: var(--sb-amber);
    border-color: rgba(255, 171, 64, 0.2);
}

.draft-time {
    font-size: 0.65rem;
    color: var(--text-secondary);
    opacity: 0.6;
}

.draft-card-actions {
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.15s;
}

.draft-card:hover .draft-card-actions {
    opacity: 1;
}

.draft-btn {
    width: 28px;
    height: 28px;
    border-radius: 5px;
    border: 1px solid var(--sb-card-border);
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.draft-btn-edit:hover {
    background: rgba(0, 212, 170, 0.15);
    color: var(--sb-teal);
    border-color: var(--sb-teal-dim);
}

.draft-btn-send:hover {
    background: rgba(0, 212, 170, 0.15);
    color: var(--sb-teal);
    border-color: var(--sb-teal-dim);
}

.draft-btn-discard:hover {
    background: rgba(233, 69, 96, 0.15);
    color: var(--accent);
    border-color: var(--accent);
}
```

**Step 2: Add draft edit modal styles**

```css
/* ── Draft Edit Modal ── */

.draft-edit-dialog {
    max-width: 600px;
    width: 90vw;
}

.draft-edit-fields {
    padding: 0 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.draft-field-label {
    display: flex;
    align-items: center;
    gap: 10px;
}

.draft-field-label span {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    font-weight: 500;
    color: var(--text-secondary);
    text-transform: uppercase;
    width: 55px;
    flex-shrink: 0;
}

.draft-field-input {
    flex: 1;
    background: var(--bg-primary);
    border: 1px solid var(--sb-card-border);
    border-radius: 4px;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.82rem;
    padding: 6px 10px;
}

.draft-field-input:focus {
    outline: none;
    border-color: var(--sb-teal-dim);
}

.draft-edit-body {
    width: 100%;
    min-height: 200px;
    max-height: 50vh;
    background: var(--bg-primary);
    border: 1px solid var(--sb-card-border);
    border-radius: 4px;
    color: var(--text-primary);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    padding: 10px;
    resize: vertical;
    margin: 0 1.5rem;
}

.draft-edit-body:focus {
    outline: none;
    border-color: var(--sb-teal-dim);
}

.draft-edit-error {
    margin: 8px 1.5rem 0;
    padding: 8px 12px;
    background: rgba(233, 69, 96, 0.15);
    border: 1px solid var(--accent);
    border-radius: 4px;
    color: var(--accent);
    font-size: 0.75rem;
}

.draft-send-btn {
    background: var(--sb-teal) !important;
    color: var(--sb-bg) !important;
    border-color: var(--sb-teal) !important;
    font-weight: 600;
}

.draft-send-btn:hover:not(:disabled) {
    background: var(--sb-teal-dim) !important;
}
```

**Step 3: Commit**

```bash
git add pa-web-ui/static/css/styles.css
git commit -m "feat: add draft card and edit modal styles"
```

---

## Task 9: Meeting Pipeline — Followup Label

**Files:**
- Modify: `letta/meeting_followup_tool.py` (~lines 215-242)

**Step 1: Add Followup label application to all drafts**

In `meeting_followup_tool.py`, after the draft is created (after line 213 `message_id = draft_message.get("id", "")`), add the Followup label logic. Replace the existing label block (lines 215-242) with:

```python
        # Apply "Followup" label to all meeting drafts
        label_applied_followup = False
        label_applied_proposed = False
        if message_id:
            labels_resp = gmail.users().labels().list(userId="me").execute()
            all_labels = labels_resp.get("labels", [])

            # Find or create "Followup" label
            FOLLOWUP_LABEL_NAME = "Followup"
            followup_label_id = None
            for label in all_labels:
                if label["name"] == FOLLOWUP_LABEL_NAME:
                    followup_label_id = label["id"]
                    break
            if not followup_label_id:
                new_label = gmail.users().labels().create(
                    userId="me",
                    body={
                        "name": FOLLOWUP_LABEL_NAME,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                ).execute()
                followup_label_id = new_label["id"]

            label_ids_to_add = [followup_label_id]

            # Additionally apply "Proposed" label if AI-proposed (no user markers)
            if proposed:
                PROPOSED_LABEL_NAME = "Proposed"
                proposed_label_id = None
                for label in all_labels:
                    if label["name"] == PROPOSED_LABEL_NAME:
                        proposed_label_id = label["id"]
                        break
                if not proposed_label_id:
                    new_label = gmail.users().labels().create(
                        userId="me",
                        body={
                            "name": PROPOSED_LABEL_NAME,
                            "labelListVisibility": "labelShow",
                            "messageListVisibility": "show",
                        },
                    ).execute()
                    proposed_label_id = new_label["id"]
                label_ids_to_add.append(proposed_label_id)

            gmail.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": label_ids_to_add},
            ).execute()
            label_applied_followup = True
            label_applied_proposed = proposed
```

Update the return block (~line 244) to include the new field:

```python
        return {
            "status": "ok",
            "draft_id": draft_id,
            "message_id": message_id,
            "thread_id": draft_message.get("threadId", ""),
            "email_to": ", ".join(emails_list),
            "email_subject": subject,
            "followup_label": label_applied_followup,
            "proposed_label": label_applied_proposed,
        }
```

**Step 2: Re-register the tool with Letta**

```bash
LETTA_BASE_URL=http://localhost:8283 python letta/register_meeting_processing_tools.py
```

**Step 3: Verify the tool is updated**

```bash
curl -s http://localhost:8283/v1/tools?limit=50 | python3 -c "
import sys,json
tools = json.load(sys.stdin)
for t in tools:
    if t['name'] == 'prepare_meeting_followup':
        print(f'ID: {t[\"id\"]}')
        print('Source contains Followup:', 'Followup' in t.get('source_code',''))
"
```

Expected: `Source contains Followup: True`

**Step 4: Commit**

```bash
git add letta/meeting_followup_tool.py
git commit -m "feat: apply Followup label to all meeting draft emails"
```

---

## Task 10: End-to-End Testing & Verification

**Files:** None (testing only)

**Step 1: Rebuild all affected services**

```bash
docker-compose up -d --build gws-bridge pa-web-ui
```

**Step 2: Verify gws-bridge health**

```bash
curl http://localhost:8098/health
```

Expected: `{"status":"healthy",...}`

**Step 3: Verify draft listing via pa-web-ui**

```bash
curl http://localhost:5200/api/drafts
```

Expected: JSON with drafts array (may be empty if no `Followup`-labeled drafts exist yet)

**Step 4: Create a test draft with Followup label (if none exist)**

Using existing gmail tools or Gmail UI, create a draft and apply the `Followup` label. Then verify it appears:

```bash
curl http://localhost:5200/api/drafts
```

**Step 5: Test the UI**

Open `http://localhost:5200` in a browser:
1. Click sidebar toggle — verify tabs appear
2. Click "Drafts" tab — verify drafts load
3. Click "Edit" on a draft — verify modal opens with correct fields
4. Edit the body, click "Save Draft" — verify save succeeds
5. Click "Send" on a draft — verify confirmation appears, then draft sends and disappears
6. Click "Discard" on a draft — verify confirmation appears, then draft deletes and disappears

**Step 6: Verify task sidebar still works**

Switch to "Tasks" tab, verify all existing task functionality is intact.

**Step 7: Commit any fixes**

If any issues were found and fixed during testing:
```bash
git add -A
git commit -m "fix: address issues found during e2e testing"
```

---

## Task 11: Update WIP Tracker & Design Doc

**Files:**
- Modify: `docs/plans/2026-02-23-wip-system-updates.md`
- Modify: `docs/plans/2026-03-04-gws-cli-gmail-experiment-design.md`

**Step 1: Update WIP item 16 status**

Change status from "On hold" to "Experiment deployed" and note the drafts sidebar as the validation use case.

**Step 2: Update the gws design doc status**

Change status from "On hold" to "Experiment active — powering Gmail drafts sidebar in pa-web-ui via x86_64 sidecar".

**Step 3: Commit**

```bash
git add docs/plans/
git commit -m "docs: update WIP tracker and gws design with experiment status"
```
