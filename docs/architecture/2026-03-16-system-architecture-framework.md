# AI Personal Assistant — System Architecture Framework

**Date:** 2026-03-16
**Status:** Working Document
**Purpose:** Reference architecture for agent roles, model tiers, memory management, and function allocation across the PA system.

---

## Core Principle: Thinking vs. Acting

The system separates cognitive work (interpretation, orchestration, synthesis) from execution work (commands, tool calls, UI management). This separation enables cost-effective model assignment: expensive reasoning models for thinking, cheap execution models for acting, with an intermediate tier for structured-but-cognitive tasks.

---

## Model Tiers

| Tier | Model Class | Cost Profile | Role |
|------|------------|-------------|------|
| **Thinking** | GPT-5.2, Claude Opus | High | Reasoning, synthesis, orchestration, writing |
| **In-Between** | GPT-4.1, GPT-5-small, Haiku, local mid-range | Medium | Structured filtering, lightweight reasoning, summarization |
| **Acting** | GPT-4.1-mini, local small model | Low | Command execution, tool calls, state management |
| **No-Model** | Direct code (Swift, Node.js, bash) | Zero LLM cost | UI rendering, event relay, file watching |

---

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    THINKING TIER (5.2)                       │
│                                                             │
│  Mission Control (server, always-on)                        │
│  The brain. All orchestration, planning, synthesis.         │
│                                                             │
│  Functions:                                                 │
│  • Morning/evening planning and priority management         │
│  • Task formulation, contextualization, and sequencing      │
│  • Pattern recognition from completion data                 │
│  • Exception handling and recovery planning                 │
│  • Email/document drafting and composition                  │
│  • Organizational pulse synthesis                           │
│  • Calendar-vs-priority conflict resolution                 │
│  • Resource identification and connection to tasks          │
│  • User tendency modeling and estimation improvement        │
│                                                             │
│  Memory: persona, goals, priorities, task-status-summary,   │
│          organizational-context, user-patterns              │
│  Tools: message_agent, archival search, web search          │
│                                                             │
│  Receives: status summaries, completion events, scanned     │
│            digests, calendar summaries, user signals         │
│  Outputs: ordered task lists, queue instructions, drafts,   │
│           resource maps, scheduling decisions                │
└────────────────────────────┬────────────────────────────────┘
                             │
                    decisions, instructions
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  IN-BETWEEN TIER (4.1 / local)              │
│                                                             │
│  Can be: MC's delegated tool-call chains, or a dedicated    │
│  lightweight "Scanner" agent. Functions here are structured  │
│  but require some reasoning — fetching, filtering, and      │
│  compressing information for the Thinking tier.             │
│                                                             │
│  Functions:                                                 │
│  • Email scanning, categorization, and triage               │
│  • Slack channel monitoring and signal extraction            │
│  • Calendar scanning and conflict detection                 │
│  • OmniFocus task search, filtering, and status gathering   │
│  • Document/article scanning and relevance assessment       │
│  • Duration estimation from historical data                 │
│  • Status summarization (raw data → compressed updates)     │
│  • Resource scanning and relevance filtering                │
│  • News/article monitoring against interest criteria        │
│  • Fuzzy matching of resources to task requirements         │
│                                                             │
│  Key pattern: fetch → filter → compress → deliver to MC     │
│  These functions are "cognitive janitorial" — structured     │
│  enough for a medium model, but requiring judgment that      │
│  pure action can't provide.                                 │
└────────────────────────────┬────────────────────────────────┘
                             │
                    filtered data, summaries,
                    specific execution commands
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    ACTION TIER (4.1-mini)                    │
│                                                             │
│  Rover / Letta Code (laptop)                                │
│  Pure execution. No reasoning about what to do — only how   │
│  to translate instructions into system calls.               │
│                                                             │
│  Functions:                                                 │
│  • Execute bash commands on laptop                          │
│  • Run AppleScript/osascript for OmniFocus, Calendar, etc.  │
│  • Manage widget queue (widget-queue.sh)                    │
│  • Start/stop/pause timers (omnifocus-cli)                  │
│  • File operations (copy, move, open, transfer)             │
│  • Browser window loading                                   │
│  • Email sending (pre-composed by Thinking tier)            │
│  • Calendar event creation/modification (pre-decided)       │
│  • Relay status events upward to Thinking tier              │
│  • Run predetermined scripts and cloud operations           │
│                                                             │
│  Memory: minimal — tool instructions only, no reasoning     │
│  Tools: bash, omnifocus-cli, widget-queue.sh, osascript,    │
│         file ops, browser control                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 NO-MODEL TIER (direct code)                  │
│                                                             │
│  Timer Widget (Swift)         — UI, animations, polling     │
│  Host Bridge (Node.js)        — event relay, command routing│
│  Toggle Script (bash)         — Caps Lock integration       │
│  OmniFocus Timer Plugin (JS)  — timer state, note logging   │
│  Scheduler Service (Python)   — cron jobs, scheduled tasks  │
└─────────────────────────────────────────────────────────────┘
```

---

## Function Allocation: Detailed Breakdown

### 1. Task Management

| Function | Tier | Agent | Notes |
|----------|------|-------|-------|
| Task creation and phrasing | Thinking | MC | Requires understanding of goals, context, and grain size |
| Task estimation | In-Between | Scanner/MC tool | Historical data lookup + lightweight reasoning |
| Task sequencing and prioritization | Thinking | MC | Requires understanding of dependencies, deadlines, user energy |
| Task surfacing (queue loading) | Action | Rover | `widget-queue.sh set id1 id2 id3` |
| Timer start/stop/pause | Action | Rover or No-Model | CLI commands or widget/Caps Lock |
| Task completion marking | Action | Rover or No-Model | `markComplete()` via osascript |
| Completion status relay | No-Model | Host bridge | Timer event → Letta message API |
| Completion pattern analysis | Thinking | MC | Estimate vs. actual variance over time |
| Task status summary generation | In-Between | Scanner | Periodic scan of OF → compressed block update |

### 2. Calendaring

| Function | Tier | Agent | Notes |
|----------|------|-------|-------|
| Calendar scanning (what's coming up) | In-Between | Scanner | Fetch events, extract key info |
| Schedule calculation (single event) | No-Model | Scheduler service | Already tooled, deterministic |
| Calendar-vs-priority comparison | Thinking | MC | "You have 3 hours before your meeting — here are tasks that fit" |
| Rescheduling decisions | Thinking | MC | "This meeting conflicts with your deadline — suggest moving it" |
| Calendar event creation/modification | Action | Rover | Pre-decided by MC, executed via AppleScript/API |
| Meeting preparation (resource gathering) | In-Between → Thinking | Scanner → MC | Scanner gathers docs; MC identifies what matters |
| Post-meeting follow-up generation | Thinking | MC | Granola transcript → action items → task creation |

### 3. Email

| Function | Tier | Agent | Notes |
|----------|------|-------|-------|
| Email inbox scanning | In-Between | Scanner | Fetch, categorize by urgency/sender/topic |
| Email triage (what needs attention) | In-Between → Thinking | Scanner → MC | Scanner filters; MC decides priority |
| Email summarization | In-Between | Scanner | Structured extraction of key points |
| Email drafting/composition | Thinking | MC | Requires voice, context, relationship awareness |
| Email sending | Action | Rover | Pre-composed by MC, sent via Gmail tool |
| Email thread monitoring | In-Between | Scanner | Watch for replies, flag important changes |
| Email-to-task conversion | Thinking | MC | "This email requires you to do X by Friday" |

### 4. Documents

| Function | Tier | Agent | Notes |
|----------|------|-------|-------|
| Document scanning/summarization | In-Between | Scanner | Extract key points, structure |
| Document relevance assessment | In-Between | Scanner | "Is this relevant to task X?" |
| Document creation/writing | Thinking | MC | Requires synthesis, voice, structure |
| Document editing/revision | Thinking | MC | Requires understanding of intent and quality |
| Document surfacing for tasks | Action | Rover | Open files, copy to accessible locations |
| Document search and retrieval | In-Between | Scanner / RAG MCP | Vector search + relevance filtering |

### 5. Slack / Organizational Monitoring

| Function | Tier | Agent | Notes |
|----------|------|-------|-------|
| Channel message scanning | In-Between | Scanner | Fetch recent messages, extract signals |
| Sentiment/attitude assessment | Thinking | MC | "The team seems frustrated about the timeline" |
| Issue identification | In-Between → Thinking | Scanner → MC | Scanner flags patterns; MC interprets significance |
| Organizational pulse synthesis | Thinking | MC | Periodic summary: "Here's what's happening across your org" |
| Mention/DM monitoring | In-Between | Scanner | Alert on direct mentions or important threads |
| Slack response drafting | Thinking | MC | Context-aware, relationship-aware |
| Slack message sending | Action | Rover | Pre-composed, via Slack API |

### 6. World Monitoring

| Function | Tier | Agent | Notes |
|----------|------|-------|-------|
| Article/news fetching | In-Between | Scanner | RSS, web search, curated sources |
| Relevance filtering | In-Between | Scanner | Match against interest criteria and current priorities |
| Article summarization | In-Between | Scanner | Key points, relevance assessment |
| Insight synthesis | Thinking | MC | "This article is relevant to your Q2 strategy because..." |
| Alert generation | In-Between → Thinking | Scanner → MC | Scanner detects; MC decides if it's worth surfacing |
| Resource bookmarking | Action | Rover | Save links, add to reference collections |

---

## Event Flows

### Morning Planning Flow
```
1. Scanner (In-Between): Fetch today's calendar, overdue tasks, recent emails,
   Slack highlights, pending timer data
2. Scanner: Compress into structured summary
3. MC (Thinking): Receive summary, synthesize with goals/priorities,
   generate ordered task queue with time estimates and resource links
4. MC → Rover (Action): "Load queue: [id1, id2, id3, ...]"
5. Rover: widget-queue.sh set id1 id2 id3
6. Widget (No-Model): Displays first task, user clicks Play
```

### Task Completion Flow
```
1. User completes task (Caps Lock / widget checkmark)
2. Timer Plugin (No-Model): Stops timer, logs to note, emits event
3. Host Bridge (No-Model): Relays event to MC
4. MC (Thinking): Receives "Task X complete, 15m actual vs 30m estimate"
   Updates internal model. Decides: advance queue? Reprioritize?
5. MC → Rover: "Queue is current, advance to next" (or new instructions)
6. Widget (No-Model): Auto-advances to next task
```

### Incoming Email Flow
```
1. Scanner (In-Between): Periodic Gmail scan, detects new important email
2. Scanner: Summarizes content, categorizes urgency
3. Scanner → MC: "Urgent email from VP: needs response about Q2 budget by EOD"
4. MC (Thinking): Evaluates against current priorities. Decides to:
   - Create a new task "Respond to VP re: Q2 budget"
   - Insert at position 1 in queue (urgent)
   - Draft a response
5. MC → Rover: "Create task [details], insert at queue position 1,
   draft ready in shared_context block"
6. Rover: omnifocus-cli task create ..., widget-queue.sh insert 0 <id>
```

### Calendar Conflict Flow
```
1. Scanner (In-Between): Detects meeting in 30 minutes, current task
   estimated at 45 minutes remaining
2. Scanner → MC: "Conflict: meeting at 2:00, current task needs ~45 more min"
3. MC (Thinking): Evaluates options — pause task? Reschedule meeting?
   Decides: "Pause current task, switch to meeting prep task"
4. MC → Rover: "Pause timer, insert meeting-prep task at queue position 0"
5. Rover: omnifocus-cli timer pause, widget-queue.sh insert 0 <prep-task-id>
```

---

## Memory Architecture

### Core Memory Blocks (consumed on every LLM call)

| Block | Agent | Content | Update Frequency | Size Target |
|-------|-------|---------|-----------------|-------------|
| **persona** | MC | Role, reasoning guidelines, agent coordination rules | Rare (architecture changes) | < 2KB |
| **human** | MC | User preferences, tendencies, communication style | Monthly | < 1KB |
| **priorities** | MC | Current goals, deadlines, active projects | Weekly or on change | < 2KB |
| **task-status** | MC | Compressed task queue state, recent completions, estimate accuracy | Daily or on batch completion | < 1.5KB |
| **org-context** | MC | Current org dynamics, key relationships, active issues | Weekly | < 1KB |
| **persona** | Rover | Tool instructions only, no reasoning guidance | Rare | < 1KB |

### Archival Memory (retrieved on-demand)

| Content Type | Agent | Retrieval Pattern | Notes |
|-------------|-------|-------------------|-------|
| Past task patterns | MC | Semantic search on task type/project | For estimation improvement |
| Meeting notes/summaries | MC | Search by meeting ID, topic, person | Via Granola MCP |
| Document summaries | MC | Semantic search on topic | Via RAG MCP |
| Email thread histories | MC | Search by sender, topic, thread | Via Gmail MCP |
| Historical decisions | MC | Semantic search on context | "Last time this happened, we..." |

### External State (queried live)

| Source | Queried By | Frequency | Method |
|--------|-----------|-----------|--------|
| OmniFocus tasks | Scanner / Rover | On-demand | omnifocus-cli |
| Calendar | Scanner | Periodic (15min) | Calendar MCP |
| Gmail | Scanner | Periodic (5min) | Gmail MCP |
| Slack | Scanner | Periodic (10min) | Slack MCP |
| Timer state | Widget (No-Model) | Every 2s | osascript poll |
| Queue file | Widget (No-Model) | File watcher | Direct file read |

---

## Memory Management Rules of Thumb

### What goes in Core Memory Blocks
- Information needed on EVERY reasoning turn: persona, user model, current priorities
- Compressed operational state: "3 tasks done today, 5 remaining, running 15% over estimates"
- Active relationship context: "VP is stressed about Q2, be careful with timeline commitments"
- Keep blocks LEAN — every byte is multiplied across every LLM call

### What goes in Archival Memory
- Historical data that's useful but not needed every turn
- Past decisions and their outcomes (for pattern matching)
- Meeting summaries older than 1 week
- Completed task details and timing data
- User feedback and preference history

### What NOT to put in memory at all
- Information derivable from tools (current task list — just query OmniFocus)
- Rapidly changing state (timer elapsed time — the widget handles this)
- Large documents (store references/summaries, not full content)

### Caching Implications
- **Stable blocks maximize cache hits.** OpenAI's prefix caching works when the system prompt + memory blocks are identical across calls. Every update to a core block invalidates the cache.
- **Update task-status block in batches, not per-event.** Rather than updating on every timer stop, batch updates at natural breakpoints (end of task batch, end of day, user-initiated check-in).
- **Archival retrieval doesn't break caching** — it's tool-call output, not part of the cached prefix.
- **Model switching across agents preserves per-agent caches.** MC's cache is independent of Rover's. This is another advantage of separate agents vs. model switching within one agent.

### Progressive Disclosure and File-Based Memory

Letta's emerging file-based memory system changes the calculus:

- **Current state:** Memory blocks are fixed-size text consumed as context. Archival memory is vector-searched. There's no middle ground.
- **With file-based memory:** Agents can reference files that are loaded on-demand, creating a "progressive disclosure" pattern where the agent sees summaries in core memory and can drill into files for detail.
- **Impact on architecture NOW:**
  - Design core memory blocks as *indexes* that point to deeper information
  - Keep summaries in blocks, details in archival or files
  - Structure archival entries with clear metadata for retrieval
  - This is already the right pattern — file-based memory just makes it more explicit
- **What to wait on:**
  - Don't over-invest in complex archival tagging schemes — file-based memory may provide better organization primitives
  - Don't build elaborate summarization pipelines — progressive disclosure may make raw-detail-on-demand more efficient than pre-summarized blocks
  - DO build clean data capture now (timer logs, completion events, meeting summaries) — the raw data is always valuable regardless of how it's later organized

---

## Implementation Priorities

### Phase 1: Agent Role Clarification (immediate)
- Switch Rover to 4.1-mini
- Strip Rover's persona to action-only instructions
- Route timer events to MC instead of Rover
- Update MC's persona with orchestration guidelines

### Phase 2: Scanner Functions (near-term)
- Implement periodic email/calendar/Slack scanning
- Build status summarization pipeline (OF → compressed block)
- These can start as MC's tool calls, graduating to a dedicated agent if needed

### Phase 3: Full Orchestration (medium-term)
- Morning planning workflow
- Calendar-priority conflict detection
- Queue management driven by MC decisions
- Estimation improvement from timer history

### Phase 4: World Monitoring (longer-term)
- Article/news monitoring against priorities
- Organizational pulse synthesis
- Proactive resource surfacing for upcoming tasks

---

## Current System Inventory

### Agents
| Agent | Model | Role | Location |
|-------|-------|------|----------|
| Mission Control | GPT-5.2 | Thinking orchestrator | Server (Letta) |
| Rover | GPT-5.2 → should be 4.1-mini | Action executor | Laptop (LettaBot) |

### Tools and Services
| Component | Location | Function | Tier |
|-----------|----------|----------|------|
| OmniFocus Timer Plugin | Laptop (OF) | Timer state, note logging | No-Model |
| Timer Widget | Laptop (Swift) | UI, queue display, user interaction | No-Model |
| Host Bridge | Server (Node.js) | Event relay, command routing | No-Model |
| Toggle Script | Laptop (bash) | Caps Lock integration | No-Model |
| omnifocus-cli | Laptop (Python) | OmniFocus command interface | No-Model |
| widget-queue.sh | Laptop (bash) | Queue file management | No-Model |
| Scheduler Service | Server (Python) | Cron jobs, scheduled actions | No-Model |
| Gmail MCP | Server (Node.js) | Email operations | No-Model |
| Slack MCP | Server (Node.js) | Slack operations | No-Model |
| Calendar MCP | Server (Node.js) | Calendar operations | No-Model |
| Graphiti MCP | Server (Python) | Knowledge graph | No-Model |
| RAG MCP | Server (Python) | Document vector search | No-Model |
| Granola MCP | Server (proxy) | Meeting notes | No-Model |
| Drive RAG | Server (Python) | Google Drive document indexing | No-Model |

### Network Topology
```
Server (100.99.171.119)          Laptop (100.95.213.46)
├── Letta (8283)                 ├── OmniFocus + Timer Plugin
├── Host Bridge (8889) ←──────→  ├── Timer Widget (Swift)
├── Docker services              ├── Rover / LettaBot (8080)
├── MCP servers                  ├── omnifocus-cli
└── Supabase, Neo4j, etc.       └── Karabiner + toggle script
         ↕ Tailscale ↕
```
