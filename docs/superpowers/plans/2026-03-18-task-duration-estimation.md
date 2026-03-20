# Task Duration Estimation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-generated time estimates to the task extraction pipeline, displayed as editable inline badges on task cards, flowing through to OmniFocus as estimatedDuration and Agent Estimate note line.

**Architecture:** The Letta tasks agent generates an estimate (minutes) during extraction, stored in both the block line and archival passage. The pa-web sidebar displays it as an editable H:MM badge. At OmniFocus creation, the estimate becomes `estimatedMinutes` and a standalone `Agent Estimate:` note line that the timer widget picks up.

**Tech Stack:** Python (Flask backend), JavaScript (sidebar frontend), Letta API (extraction tool), OmniFocus JavaScript plugin (timer parser)

**Spec:** `docs/superpowers/specs/2026-03-18-task-duration-estimation-design.md`

---

## Chunk 1: Backend — Extraction Tool + Parser

### Task 1: Add `estimate_minutes` to extraction tool

**Files:**
- Modify: `letta/extracted_tasks_tool.py:13-31` (function signature)
- Modify: `letta/extracted_tasks_tool.py:253` (block line construction)
- Modify: `letta/extracted_tasks_tool.py:294-309` (TASK METADATA section)

- [ ] **Step 1: Add `estimate_minutes` parameter to `add_extracted_tasks`**

Add after the `origin` parameter (line 28):

```python
    estimate_minutes: Optional[int] = None,
```

Add to the docstring Args section:

```python
        estimate_minutes: Estimated task duration in minutes. LLM-generated
            based on task complexity and context. Integer.
```

- [ ] **Step 2: Add `est:` field to block line**

Modify line 253 — add estimate to the block line format:

```python
        origin_part = f"; origin: {origin}" if origin else ""
        est_part = f"; est: {estimate_minutes}" if estimate_minutes else ""
        task_line = f"[extracted_time: {timestamp_str}; ref_id: {ref_id}{origin_part}{est_part}] {task_description}\n\n"
```

- [ ] **Step 3: Add `- Estimate:` to TASK METADATA section**

Modify lines 294-309 — add estimate to metadata_lines:

```python
        metadata_lines = []
        if estimate_minutes:
            metadata_lines.append(f"- Estimate: {estimate_minutes}")
        if due_date:
            metadata_lines.append(f"- Due: {due_date}")
        if defer_date:
            metadata_lines.append(f"- Defer: {defer_date}")
        if priority:
            metadata_lines.append(f"- Priority: {priority}")
```

- [ ] **Step 4: Register updated tool with Letta**

```bash
LETTA_BASE_URL=http://localhost:8283 python letta/extracted_tasks_tool.py
```

Verify the tool is updated (check the parameter list includes estimate_minutes).

- [ ] **Step 5: Commit**

```bash
git add letta/extracted_tasks_tool.py
git commit -m "feat: add estimate_minutes parameter to add_extracted_tasks tool"
```

### Task 2: Update backend parsers for estimate field

**Files:**
- Modify: `pa-web-ui/app.py:1539-1542` (TASK_LINE_PATTERN regex)
- Modify: `pa-web-ui/app.py:1545-1560` (parse_task_block)
- Modify: `pa-web-ui/app.py:1563-1644` (parse_archival_passage)

- [ ] **Step 1: Update TASK_LINE_PATTERN to capture optional `est:` field**

Replace lines 1539-1542:

```python
TASK_LINE_PATTERN = re.compile(
    r'\[extracted_time:\s*([^;]+);\s*ref_id:\s*([a-f0-9]+)'
    r'(?:;\s*origin:\s*([^\];]*))?'
    r'(?:;\s*est:\s*(\d+))?\]\s*(.+)'
)
```

Groups: 1=time, 2=ref_id, 3=origin, 4=estimate_minutes, 5=description

- [ ] **Step 2: Update `parse_task_block` to extract estimate**

Replace lines 1553-1558:

```python
        if m:
            est_raw = m.group(4)
            tasks.append({
                "extracted_time": m.group(1).strip(),
                "ref_id": m.group(2).strip(),
                "origin": (m.group(3) or "").strip() or None,
                "estimate_minutes": int(est_raw) if est_raw else None,
                "description": m.group(5).strip(),
            })
```

- [ ] **Step 3: Update `parse_archival_passage` to extract estimate from TASK METADATA**

Add after the ORIGIN parsing (after line 1580):

```python
    # TASK METADATA - Estimate
    m = re.search(r'^- Estimate:\s*(\d+)', text, re.MULTILINE)
    if m:
        result['estimate_minutes'] = int(m.group(1))
```

- [ ] **Step 4: Rebuild pa-web-ui**

```bash
docker-compose up -d --build pa-web-ui
```

Verify: `curl -s http://localhost:5200/api/tasks | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),indent=2))"` — tasks should include `estimate_minutes` field (null for existing tasks).

- [ ] **Step 5: Commit**

```bash
git add pa-web-ui/app.py
git commit -m "feat: parse estimate_minutes from task block lines and archival passages"
```

### Task 3: Add estimate to PATCH endpoint

**Files:**
- Modify: `pa-web-ui/app.py:1752-1810` (api_update_task)

- [ ] **Step 1: Accept `estimate_minutes` in PATCH body**

Modify `api_update_task` to handle the new field. After the existing task_description handling (around line 1757):

```python
    try:
        data = request.get_json()
        task_description = data.get('task_description')
        estimate_minutes = data.get('estimate_minutes')

        if not task_description and estimate_minutes is None:
            return jsonify({"error": "task_description or estimate_minutes required"}), 400
```

- [ ] **Step 2: Update archival passage estimate**

After the task description substitution block (after line 1787), add:

```python
            # Update estimate in passage if provided
            if estimate_minutes is not None:
                est_pattern = r'^- Estimate:\s*\d+$'
                est_line = f'- Estimate: {estimate_minutes}'
                if re.search(est_pattern, new_text, re.MULTILINE):
                    new_text = re.sub(est_pattern, est_line, new_text, count=1, flags=re.MULTILINE)
                else:
                    # Add to TASK METADATA section, or create it
                    meta_match = re.search(r'(TASK METADATA\n)', new_text)
                    if meta_match:
                        new_text = new_text[:meta_match.end()] + est_line + '\n' + new_text[meta_match.end():]
                    else:
                        # Insert TASK METADATA section after ORIGIN line
                        origin_match = re.search(r'(ORIGIN: .+\n)', new_text)
                        if origin_match:
                            new_text = new_text[:origin_match.end()] + f'\nTASK METADATA\n{est_line}\n' + new_text[origin_match.end():]
```

- [ ] **Step 3: Update block line estimate**

After the existing block line update (around line 1800), add estimate update:

```python
            # Update estimate in block line if provided
            if estimate_minutes is not None:
                # Replace or add est: field in block line
                est_re = rf'(\[extracted_time: [^;]+; ref_id: {re.escape(ref_id)}(?:; origin: [^\];]*)?)(; est: \d+)?(\])'
                new_val = re.sub(
                    est_re,
                    rf'\g<1>; est: {estimate_minutes}\3',
                    new_val,
                )
```

- [ ] **Step 4: Rebuild and test**

```bash
docker-compose up -d --build pa-web-ui
```

Test: `curl -s -X PATCH http://localhost:5200/api/tasks/67f9073d -H 'Content-Type: application/json' -d '{"estimate_minutes": 20}'`

- [ ] **Step 5: Commit**

```bash
git add pa-web-ui/app.py
git commit -m "feat: support estimate_minutes in task PATCH endpoint"
```

---

## Chunk 2: Frontend — Card Badge + Confirm Dialog

### Task 4: Add inline estimate badge to task cards

**Files:**
- Modify: `pa-web-ui/static/js/sidebar.js` — `buildTaskCard()`, add `startEstimateEdit()` method
- Modify: `pa-web-ui/static/css/styles.css` — estimate badge styles

- [ ] **Step 1: Add estimate badge HTML in `buildTaskCard`**

In `buildTaskCard()`, in the metadata row area (after the task-time span in the card.innerHTML template), add the estimate badge:

```javascript
    const estValue = task.estimate_minutes;
    const estDisplay = estValue ? this.formatEstimate(estValue) : '—';
    const estClass = estValue ? '' : ' est-empty';
```

Add to the `task-card-meta` div in the template:

```html
<span class="task-est-badge${estClass}" data-minutes="${estValue || ''}" title="Estimated duration">⏱ ${estDisplay}</span>
```

- [ ] **Step 2: Add `formatEstimate` and `parseEstimate` utility methods**

Add to the TaskSidebar class:

```javascript
  formatEstimate(minutes) {
    if (!minutes || minutes <= 0) return '—';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}:${m < 10 ? '0' : ''}${m}`;
  }

  parseEstimate(str) {
    if (!str || str === '—') return null;
    const parts = str.split(':');
    if (parts.length === 2) {
      const h = parseInt(parts[0], 10) || 0;
      const m = parseInt(parts[1], 10) || 0;
      return h * 60 + m;
    }
    const num = parseInt(str, 10);
    return isNaN(num) ? null : num;
  }
```

- [ ] **Step 3: Add click-to-edit behavior for the estimate badge**

Bind click handler after card creation (alongside the description edit handler):

```javascript
    const estBadge = card.querySelector('.task-est-badge');
    estBadge?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.startEstimateEdit(estBadge, task.ref_id, task);
    });
```

Add `startEstimateEdit` method:

```javascript
  startEstimateEdit(badgeEl, refId, task) {
    if (badgeEl.querySelector('input')) return;

    const current = this.formatEstimate(task.estimate_minutes) || '';
    const originalHtml = badgeEl.innerHTML;

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'est-inline-input';
    input.value = current;
    input.placeholder = 'H:MM';
    input.size = 5;

    badgeEl.textContent = '⏱ ';
    badgeEl.appendChild(input);
    input.focus();
    input.select();

    const commit = async () => {
      const parsed = this.parseEstimate(input.value);
      badgeEl.innerHTML = `⏱ ${parsed ? this.formatEstimate(parsed) : '—'}`;
      badgeEl.classList.toggle('est-empty', !parsed);
      badgeEl.dataset.minutes = parsed || '';
      task.estimate_minutes = parsed;

      if (parsed !== task.estimate_minutes) {
        try {
          await fetch(`/api/tasks/${refId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ estimate_minutes: parsed }),
          });
        } catch { /* silent */ }
      }
    };

    input.addEventListener('blur', commit, { once: true });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      if (e.key === 'Escape') { badgeEl.innerHTML = originalHtml; }
    });
  }
```

- [ ] **Step 4: Add CSS for estimate badge**

Add to `styles.css` after the existing task-card-meta styles:

```css
.task-est-badge {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    font-size: 0.72rem;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 1px 5px;
    border-radius: 3px;
    border: 1px solid transparent;
    transition: border-color 0.15s, background 0.15s;
}

.task-est-badge:hover {
    border-color: var(--sb-card-border);
    background: rgba(255, 255, 255, 0.04);
}

.task-est-badge.est-empty {
    opacity: 0.4;
}

.est-inline-input {
    width: 3.5em;
    font-size: 0.72rem;
    padding: 1px 3px;
    background: var(--bg-tertiary);
    border: 1px solid var(--sb-teal-dim);
    border-radius: 3px;
    color: var(--text-primary);
    font-family: inherit;
    outline: none;
}
```

- [ ] **Step 5: Commit**

```bash
git add pa-web-ui/static/js/sidebar.js pa-web-ui/static/css/styles.css
git commit -m "feat: add inline editable estimate badge to task cards"
```

### Task 5: Add read-only estimate to confirm dialog

**Files:**
- Modify: `pa-web-ui/static/js/sidebar.js` — `onConfirm()` method
- Modify: `pa-web-ui/templates/index.html` — OF dialog HTML
- Modify: `pa-web-ui/static/css/styles.css` — estimate display in dialog

- [ ] **Step 1: Add estimate display element to OF dialog HTML**

In `index.html`, after the `of-dialog-task-input` textarea wrapper, add:

```html
<div class="of-dialog-estimate" id="of-dialog-estimate"></div>
```

- [ ] **Step 2: Populate estimate in `onConfirm`**

In `onConfirm()`, after setting the textarea value:

```javascript
    const estEl = document.getElementById('of-dialog-estimate');
    if (task && task.estimate_minutes) {
      estEl.textContent = `⏱ ${this.formatEstimate(task.estimate_minutes)} estimated`;
      estEl.style.display = '';
    } else {
      estEl.style.display = 'none';
    }
```

- [ ] **Step 3: Add CSS for dialog estimate**

```css
.of-dialog-estimate {
    padding: 0.4rem 1.25rem;
    font-size: 0.78rem;
    color: var(--text-secondary);
    font-style: italic;
}
```

- [ ] **Step 4: Commit**

```bash
git add pa-web-ui/static/js/sidebar.js pa-web-ui/templates/index.html pa-web-ui/static/css/styles.css
git commit -m "feat: show read-only estimate in OmniFocus confirm dialog"
```

---

## Chunk 3: OmniFocus Creation + Timer Integration

### Task 6: Pass estimate through to OmniFocus creation

**Files:**
- Modify: `pa-web-ui/static/js/sidebar.js` — `confirmOFDialog()`, `buildOFNote()`
- Modify: `pa-web-ui/app.py` — `api_omnifocus_create()`

- [ ] **Step 1: Add `estimatedMinutes` to create request**

In `confirmOFDialog()`, where the create request is built (the `fetch('/api/tasks/omnifocus-create', ...)` call), add `estimatedMinutes`:

```javascript
      const createResp = await fetch('/api/tasks/omnifocus-create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: taskName,
          projectId: this.selectedProjectId,
          note: note,
          estimatedMinutes: task ? task.estimate_minutes : null,
        }),
      });
```

- [ ] **Step 2: Add `Agent Estimate:` line to `buildOFNote`**

In `buildOFNote()`, after the `Origin:` line (around line 710), add:

```javascript
    // Agent Estimate (standalone line for timer widget to pick up)
    if (details.estimate_minutes) {
      const mins = details.estimate_minutes;
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      const s = 0;
      let formatted;
      if (h > 0) {
        formatted = `${h}h ${m < 10 ? '0' : ''}${m}m ${s < 10 ? '0' : ''}${s}s`;
      } else {
        formatted = `${m}m ${s < 10 ? '0' : ''}${s}s`;
      }
      lines.push(`Agent Estimate: ${formatted}`);
    }
```

- [ ] **Step 3: Pass `estimatedMinutes` through backend to bridge**

In `app.py` `api_omnifocus_create()`, add to the args dict:

```python
        estimated = data.get('estimatedMinutes')
        if estimated:
            args["estimatedMinutes"] = int(estimated)
```

- [ ] **Step 4: Rebuild and test end-to-end**

```bash
docker-compose up -d --build pa-web-ui
```

Test: Create a task with estimate, confirm to OmniFocus. Verify in OmniFocus that:
- Task has estimatedMinutes set
- Note contains `Agent Estimate: Xm 00s` line
- Note does NOT contain `--- Time Tracking ---` block

- [ ] **Step 5: Commit**

```bash
git add pa-web-ui/static/js/sidebar.js pa-web-ui/app.py
git commit -m "feat: pass estimatedMinutes to OmniFocus and write Agent Estimate note line"
```

### Task 7: Update timer parser to find Agent Estimate outside block

**Files:**
- Modify: `omnifocus-timer/omnifocus-timer.omnifocusjs/Resources/timerLib.js` — `parseNoteBlock()`

- [ ] **Step 1: Add outside-block scan for Agent Estimate**

In `parseNoteBlock()`, after the main parsing loop ends (after the `for` loop that processes lines inside the block), add a fallback scan of the full note text:

```javascript
    // If no agent estimate was found inside the block, check outside it
    if (!result.agentEstimate) {
      var fullLines = noteText.split("\n");
      for (var k = 0; k < fullLines.length; k++) {
        var fl = fullLines[k].trim();
        // Skip lines inside the block
        if (fl === NOTE_BLOCK_START) {
          while (k < fullLines.length - 1 && fullLines[++k].trim() !== NOTE_BLOCK_END) {}
          continue;
        }
        var extAgentMatch = fl.match(/^Agent Estimate:\s*(.+)$/);
        if (extAgentMatch) {
          result.agentEstimate = extAgentMatch[1].trim();
          break;
        }
      }
    }
```

- [ ] **Step 2: Deploy plugin to OmniFocus**

```bash
# Copy updated plugin to OmniFocus plugin directory
cp omnifocus-timer/omnifocus-timer.omnifocusjs/Resources/timerLib.js \
   ~/Library/Containers/com.omnigroup.OmniFocus4/Data/Library/Application\ Support/Plug-Ins/omnifocus-timer.omnifocusjs/Resources/timerLib.js
```

Also deploy to laptop via existing deploy script:
```bash
omnifocus-timer/deploy-widget.sh
```

- [ ] **Step 3: Test timer integration**

1. Create a task in OmniFocus with a note containing `Agent Estimate: 15m 00s` (standalone, no block)
2. Start the timer on that task
3. Verify the time tracking block is created and includes `Agent Estimate: 15m 00s` inside it
4. Verify `Original Estimate:` is populated from the task's estimatedMinutes

- [ ] **Step 4: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/Resources/timerLib.js
git commit -m "feat: timer parser finds Agent Estimate outside time tracking block"
```

### Task 8: Update agent extraction guidelines

**Files:**
- Letta memory block: `task_extraction_tool_use_guidelines` (block-e8bf985e) on tasks agent

- [ ] **Step 1: Update extraction guidelines via Letta API**

Add instruction to the `task_extraction_tool_use_guidelines` block telling the agent to estimate duration. The instruction should be added to the section about calling `add_extracted_tasks`:

```
When calling add_extracted_tasks, always include estimate_minutes — your best estimate of how long the task will take in minutes. Consider:
- Task description complexity and scope
- Number of URLs/documents to review
- Whether it requires composing a response or just reviewing
- Typical durations: quick review 5-10 min, document review 15-30 min, drafting/composing 30-60 min
Round to the nearest 5 minutes. Minimum 5, maximum 120 for a single task.
```

Use: `curl -sL -X PATCH 'http://localhost:8283/v1/blocks/block-e8bf985e-9f11-44f4-b889-4bba07e2fd17' -H 'Content-Type: application/json' -d '{"value": "<updated block content>"}'`

- [ ] **Step 2: Verify by triggering a test extraction**

Send a test message to the tasks agent and verify the resulting passage includes `- Estimate: <N>` in TASK METADATA and the block line includes `; est: <N>`.

- [ ] **Step 3: Commit guidelines update (document the change)**

No code file to commit — the guidelines live in Letta. Document the change in the plan as completed.
