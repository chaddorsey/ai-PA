# LettaBot pa-web-ui Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make LettaBot the default chat backend in pa-web-ui, with slash commands routing to specialized agents via the existing router.

**Architecture:** The `/stream` endpoint in app.py gains a routing fork: messages without slash commands go to LettaBot's native `/api/v1/chat` SSE endpoint; messages with slash commands go through pa-routing-handler → Letta agents as before (with async summary to LettaBot). Heartbeat activity appears as lightweight collapsible messages in the chat feed.

**Tech Stack:** Python/Flask (backend), vanilla JS (frontend), httpx (HTTP client), LettaBot native API

---

### Task 1: Add LettaBot config and proxy route in app.py

**Files:**
- Modify: `pa-web-ui/app.py:1-10` (imports/constants)
- Modify: `pa-web-ui/app.py:644-843` (stream handler)

**Step 1: Add LettaBot constants at top of app.py**

After the existing imports and constants (around line 10), add:

```python
LETTABOT_API_URL = os.environ.get("LETTABOT_API_URL", "http://localhost:8080")
LETTABOT_API_KEY = os.environ.get("LETTABOT_API_KEY", "")
```

**Step 2: Add LettaBot stream helper function**

Add a new function before the `/stream` route (before line 586):

```python
def stream_lettabot(message: str, session_id: str) -> Generator[str, None, None]:
    """Stream a message through LettaBot's native API and translate to pa-web SSE format."""
    import uuid

    request_id = str(uuid.uuid4())

    # Emit routing event
    yield f"data: {json.dumps({'type': 'routing', 'agent_id': 'lettabot', 'agent_name': 'LettaBot', 'request_id': request_id})}\n\n"

    # Save user message (lightweight log)
    save_conversation_message(
        session_id=session_id,
        role="user",
        message=message,
        agent_id="lettabot",
        agent_name="LettaBot",
        request_id=request_id,
    )

    headers = {"Content-Type": "application/json"}
    if LETTABOT_API_KEY:
        headers["Authorization"] = f"Bearer {LETTABOT_API_KEY}"

    assistant_content = ""

    try:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            with client.stream(
                "POST",
                f"{LETTABOT_API_URL}/api/v1/chat",
                json={"message": message, "stream": True},
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'LettaBot returned {response.status_code}'})}\n\n"
                    return

                buffer = ""
                for chunk in response.iter_text():
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if not line or line.startswith(":"):
                            continue

                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                continue

                            try:
                                event = json.loads(data_str)
                                msg_type = event.get("type", "")

                                if msg_type == "assistant":
                                    content = event.get("content", "")
                                    if content:
                                        assistant_content += content
                                        yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"

                                elif msg_type == "tool_call":
                                    tool_name = event.get("toolName", event.get("name", "unknown"))
                                    tool_input = event.get("toolInput", event.get("args", {}))
                                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'args': tool_input})}\n\n"

                                elif msg_type == "tool_result":
                                    tool_content = event.get("content", "")
                                    is_error = event.get("isError", False)
                                    yield f"data: {json.dumps({'type': 'tool_result', 'content': tool_content, 'is_error': is_error})}\n\n"

                                elif msg_type == "reasoning":
                                    content = event.get("content", "")
                                    if content:
                                        yield f"data: {json.dumps({'type': 'thinking', 'content': content})}\n\n"

                                elif msg_type == "result":
                                    success = event.get("success", True)
                                    if not success:
                                        error_msg = event.get("error", "Unknown error")
                                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"

                                elif msg_type == "error":
                                    yield f"data: {json.dumps({'type': 'error', 'message': event.get('error', 'Unknown error')})}\n\n"

                            except json.JSONDecodeError:
                                pass

    except httpx.TimeoutException:
        yield f"data: {json.dumps({'type': 'error', 'message': 'LettaBot request timed out'})}\n\n"
    except Exception as e:
        logger.error("lettabot_stream_error", error=str(e))
        yield f"data: {json.dumps({'type': 'error', 'message': f'LettaBot error: {str(e)}'})}\n\n"

    # Save assistant response (lightweight log)
    if assistant_content:
        save_conversation_message(
            session_id=session_id,
            role="assistant",
            message=assistant_content,
            agent_id="lettabot",
            agent_name="LettaBot",
            request_id=request_id,
        )

    # Emit done
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
```

**Step 3: Modify the `/stream` route to fork on slash commands**

In the existing `/stream` handler (line 586), after the coordination slash command check (line 633), add the LettaBot fork. Replace the section that calls the routing handler with:

```python
    # Check if this is a slash command (explicit agent routing)
    is_slash_command = bool(slash_command) or bool(agent_id)

    if not is_slash_command:
        # Default: route to LettaBot
        logger.info(
            "lettabot_stream_request",
            session_id=session_id,
            message_length=len(message),
        )
        return Response(
            stream_lettabot(message, session_id),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Slash command path: use existing routing handler
    logger.info(
        "slash_routed_stream_request",
        session_id=session_id,
        agent_id=agent_id,
        slash_command=slash_command,
    )

    def generate() -> Generator[str, None, None]:
        # ... existing routing handler + Letta streaming code ...
```

**Step 4: Add summary posting to LettaBot after slash-routed responses**

At the end of the existing `generate()` function (after the Letta stream completes and response is saved), add:

```python
            # Post summary to LettaBot (fire-and-forget)
            if assistant_response_parts:
                summary_text = "".join(assistant_response_parts)[:500]
                try:
                    summary_headers = {"Content-Type": "application/json"}
                    if LETTABOT_API_KEY:
                        summary_headers["Authorization"] = f"Bearer {LETTABOT_API_KEY}"
                    with httpx.Client(timeout=10.0) as summary_client:
                        summary_client.post(
                            f"{LETTABOT_API_URL}/api/v1/chat/async",
                            json={
                                "message": f"[System: Agent handoff summary] The user invoked /{slash_command or 'agent'} and asked: \"{message[:200]}\"\n{agent_name} responded: \"{summary_text}\""
                            },
                            headers=summary_headers,
                        )
                except Exception as e:
                    logger.warning("lettabot_summary_failed", error=str(e))
```

**Step 5: Run the app locally to verify it starts**

Run: `cd /Volumes/main-drive/ai-PA/pa-web-ui && python app.py`
Expected: App starts on port 5200 without import errors

**Step 6: Commit**

```bash
git add pa-web-ui/app.py
git commit -m "feat: add LettaBot as default chat backend with slash command routing"
```

---

### Task 2: Update frontend slash command routing

**Files:**
- Modify: `pa-web-ui/static/js/chat.js:1-50` (slash command maps)
- Modify: `pa-web-ui/static/js/chat.js:379-396` (sendMessage routing logic)
- Modify: `pa-web-ui/static/js/chat.js:993-1001` (tool_call handler)

**Step 1: Keep slash command maps but remove auto-routing fallback**

The `SLASH_COMMAND_MAP` and `SLASH_COMMAND_NAMES` at lines 5-49 stay as-is — they're the explicit routing definitions.

**Step 2: Modify sendMessage to default to LettaBot (no agent_id)**

In `sendMessage()` at line 389, change the routing priority so no-slash-command messages send `agent_id: null`:

```javascript
    // Priority: slash command > reply mode (slash-routed agents only) > LettaBot (default)
    let agentId;
    if (slashCommand) {
        agentId = slashCommand.agentId;
    } else {
        agentId = null; // LettaBot handles all non-slash messages
    }
```

This removes the dropdown and reply-mode agent selection for non-slash messages. The backend `/stream` will see `agent_id=null` + no `slash_command` and route to LettaBot.

**Step 3: Add tool_result event handling in streamResponse**

After the `tool_call` handler (line 1001), add:

```javascript
                        } else if (event.type === 'tool_result') {
                            // Tool result from LettaBot - show in collapsible detail
                            const toolContent = event.content || '';
                            const isError = event.is_error || false;
                            // Append tool result to thinking accordion for now
                            const resultPrefix = isError ? '❌ Error: ' : '✅ Result: ';
                            thinkingContent += `\n\n${resultPrefix}${toolContent}`;
                            this.updateThinkingContent(threadCard, thinkingContent);
```

**Step 4: Verify frontend loads without errors**

Open `http://localhost:5200` in browser, check console for JS errors.
Expected: No errors, slash commands still resolve to agent IDs.

**Step 5: Commit**

```bash
git add pa-web-ui/static/js/chat.js
git commit -m "feat: update frontend routing - LettaBot default, slash commands for sub-agents"
```

---

### Task 3: Add heartbeat messages to chat feed

**Files:**
- Modify: `pa-web-ui/static/js/chat.js` (add heartbeat polling + rendering)
- Modify: `pa-web-ui/templates/index.html` (heartbeat message CSS)
- Modify: `pa-web-ui/app.py` (add heartbeat proxy endpoint)

**Step 1: Add heartbeat proxy endpoint in app.py**

Add a new route that proxies LettaBot's turn data, filtered for heartbeat triggers:

```python
@app.route("/api/heartbeats", methods=["GET"])
def get_heartbeats():
    """Fetch recent heartbeat turns from LettaBot."""
    since = request.args.get("since", "")  # ISO timestamp
    try:
        headers = {}
        if LETTABOT_API_KEY:
            headers["Authorization"] = f"Bearer {LETTABOT_API_KEY}"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{LETTABOT_API_URL}/turns/data",
                headers=headers,
            )
            if resp.status_code != 200:
                return jsonify({"heartbeats": []}), 200

            turns = resp.json()
            # Filter for heartbeat triggers only
            heartbeats = []
            for turn in turns:
                if turn.get("trigger") == "heartbeat":
                    ts = turn.get("ts", "")
                    if since and ts <= since:
                        continue
                    heartbeats.append({
                        "ts": ts,
                        "output": turn.get("output", ""),
                        "events": turn.get("events", []),
                        "durationMs": turn.get("durationMs"),
                    })
            return jsonify({"heartbeats": heartbeats}), 200
    except Exception as e:
        logger.warning("heartbeat_fetch_error", error=str(e))
        return jsonify({"heartbeats": []}), 200
```

**Step 2: Add heartbeat rendering in chat.js**

Add a new method to ChatUI and a polling setup in the constructor:

```javascript
    // In constructor, after existing setup:
    this.lastHeartbeatTs = '';
    this.startHeartbeatPolling();

    // New methods:
    startHeartbeatPolling() {
        // Poll every 60 seconds for new heartbeats
        this.heartbeatInterval = setInterval(() => this.checkHeartbeats(), 60000);
        // Also check on page load
        this.checkHeartbeats();
    }

    async checkHeartbeats() {
        try {
            const url = this.lastHeartbeatTs
                ? `/api/heartbeats?since=${encodeURIComponent(this.lastHeartbeatTs)}`
                : '/api/heartbeats';
            const resp = await fetch(url);
            if (!resp.ok) return;
            const data = await resp.json();
            for (const hb of (data.heartbeats || [])) {
                this.renderHeartbeatMessage(hb);
                if (hb.ts > this.lastHeartbeatTs) {
                    this.lastHeartbeatTs = hb.ts;
                }
            }
        } catch (e) {
            console.debug('Heartbeat poll error:', e);
        }
    }

    renderHeartbeatMessage(heartbeat) {
        if (!heartbeat.output && (!heartbeat.events || heartbeat.events.length === 0)) return;

        const card = document.createElement('div');
        card.className = 'heartbeat-card';

        const time = new Date(heartbeat.ts);
        const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        // Build detail content from events
        let detailHtml = '';
        if (heartbeat.events && heartbeat.events.length > 0) {
            const details = heartbeat.events
                .filter(e => e.type === 'tool_call' || e.type === 'tool_result')
                .map(e => {
                    if (e.type === 'tool_call') return `<div class="hb-event">🔧 ${this.escapeHtml(e.name || 'tool')}</div>`;
                    if (e.type === 'tool_result') return `<div class="hb-event hb-result">${this.escapeHtml((e.content || '').substring(0, 200))}</div>`;
                    return '';
                })
                .join('');
            if (details) {
                detailHtml = `
                    <div class="hb-details-toggle">▶ Show details</div>
                    <div class="hb-details" style="display: none;">${details}</div>
                `;
            }
        }

        card.innerHTML = `
            <div class="hb-header">
                <span class="hb-icon">💓</span>
                <span class="hb-label">LettaBot Heartbeat</span>
                <span class="hb-time">${timeStr}</span>
            </div>
            <div class="hb-summary">${this.escapeHtml(heartbeat.output || 'No action taken')}</div>
            ${detailHtml}
        `;

        // Wire up details toggle
        const toggle = card.querySelector('.hb-details-toggle');
        const details = card.querySelector('.hb-details');
        if (toggle && details) {
            toggle.addEventListener('click', () => {
                const showing = details.style.display !== 'none';
                details.style.display = showing ? 'none' : 'block';
                toggle.textContent = showing ? '▶ Show details' : '▼ Hide details';
            });
        }

        this.messagesContainer.appendChild(card);
        this.scrollToBottom();
    }
```

**Step 3: Add heartbeat CSS in index.html**

Add styles in the `<style>` section:

```css
.heartbeat-card {
    background: var(--card-bg, #1a1a2e);
    border-left: 3px solid #6c5ce7;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    opacity: 0.85;
    font-size: 0.9em;
}
.hb-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
}
.hb-icon { font-size: 0.85em; }
.hb-label { color: #6c5ce7; font-weight: 500; }
.hb-time { color: #888; font-size: 0.85em; margin-left: auto; }
.hb-summary { color: #ccc; }
.hb-details-toggle {
    color: #888;
    font-size: 0.85em;
    cursor: pointer;
    margin-top: 6px;
}
.hb-details-toggle:hover { color: #aaa; }
.hb-details {
    margin-top: 6px;
    padding: 8px;
    background: rgba(0,0,0,0.2);
    border-radius: 4px;
    font-size: 0.85em;
}
.hb-event { color: #aaa; padding: 2px 0; }
.hb-result { color: #888; padding-left: 16px; }
```

**Step 4: Verify heartbeat messages appear**

1. Enable heartbeat in `lettabot.yaml` (set `enabled: true`)
2. Restart lettabot
3. Wait for a heartbeat interval or manually trigger one
4. Open pa-web-ui and check that heartbeat card appears

**Step 5: Commit**

```bash
git add pa-web-ui/app.py pa-web-ui/static/js/chat.js pa-web-ui/templates/index.html
git commit -m "feat: add heartbeat activity feed to chat UI"
```

---

### Task 4: Update lettabot config and enable heartbeat

**Files:**
- Modify: `lettabot/lettabot.yaml`

**Step 1: Update lettabot.yaml with heartbeat enabled**

```yaml
server:
  mode: docker
  baseUrl: http://localhost:8283

agents:
  - name: LettaBot
    conversations:
      mode: shared
      heartbeat: last-active
    channels:
      telegram:
        enabled: true
        token: "<from .env>"
        dmPolicy: open

features:
  cron: false
  heartbeat:
    enabled: true
    intervalMin: 30
    skipRecentUserMin: 5
```

**Step 2: Restart lettabot**

```bash
# Kill existing lettabot process
pkill -f "tsx src/main.ts" || true
# Start in background
cd /Volumes/main-drive/ai-PA/lettabot && nohup npm run dev > /tmp/lettabot.log 2>&1 &
```

**Step 3: Verify heartbeat is active**

```bash
curl -s http://localhost:8080/health
# Expected: "ok"
tail -f /tmp/lettabot.log
# Expected: heartbeat timer messages after intervalMin
```

**Step 4: Commit**

```bash
git add lettabot/lettabot.yaml
git commit -m "feat: enable LettaBot heartbeat (30min interval)"
```

Note: `lettabot.yaml` is gitignored in the lettabot repo, but the token is sensitive. If committing to the parent ai-PA repo, ensure it's gitignored there too.

---

### Task 5: Add LettaBot environment to docker-compose and rebuild pa-web-ui

**Files:**
- Modify: `docker-compose.yml` (pa-web-ui service environment)
- Modify: `pa-web-ui/Dockerfile` (if deps changed — unlikely)

**Step 1: Add LETTABOT env vars to pa-web-ui service in docker-compose.yml**

In the `pa-web-ui` service environment section, add:

```yaml
      - LETTABOT_API_URL=http://host.docker.internal:8080
      - LETTABOT_API_KEY=${LETTABOT_API_KEY:-}
```

Note: LettaBot runs on the host (not in Docker), so use `host.docker.internal`.

**Step 2: Rebuild and restart pa-web-ui**

```bash
docker compose up -d --build pa-web-ui
```

**Step 3: Test end-to-end**

1. Open `http://localhost:5200`
2. Type a message (no slash command) — should route to LettaBot
3. Type `/calendar What's today?` — should route to Calendar Agent
4. Check heartbeat messages appear after interval

**Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: wire LettaBot API URL into pa-web-ui container"
```

---

### Task 6: Verify LettaBot native API SSE format and adjust translation

**Files:**
- Possibly modify: `pa-web-ui/app.py` (stream_lettabot function)

This is a validation task. The `stream_lettabot` function is based on the source code analysis of LettaBot's `streamToAgent` output types. After Task 5, test with real messages and verify:

**Step 1: Send a test message and check SSE events**

```bash
curl -N -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LETTABOT_API_KEY" \
  -d '{"message": "Hello, what can you do?", "stream": true}' 2>&1 | head -50
```

**Step 2: Verify event types match expected format**

Check that events have `type` field with values: `assistant`, `tool_call`, `tool_result`, `reasoning`, `result`, `error`.

If the format differs (e.g., field names like `toolName` vs `name`), update the `stream_lettabot` function in app.py accordingly.

**Step 3: Fix any format mismatches found**

Adjust field name mappings in `stream_lettabot` based on actual API output.

**Step 4: Commit if changes needed**

```bash
git add pa-web-ui/app.py
git commit -m "fix: adjust LettaBot SSE event field mappings"
```
