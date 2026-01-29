# Multi-Agent Coordination Orchestration Design

> **Status:** Design complete, ready for implementation
> **Date:** 2026-01-29
> **Related:** [Multi-Agent Coordination Design](./2026-01-28-multi-agent-coordination-design.md)
> **Philosophy:** Superpowers-inspired task lifecycle with guided meta-refinement

## Overview

This design enables the Main Agent to **develop, execute, and refine multi-agent coordination tasks** through a structured lifecycle, analogous to how superpowers guides software development from brainstorming through implementation to refinement.

**Key Principles:**
- **Task Types are Projects**: Each coordination task type goes through its own development lifecycle
- **Intentional Entry + Self-Guided Progression**: User or agent recognizes the need, then agent drives through phases with user confirmation at gates
- **Documents for Designs, Database for Logs**: Task designs in Git-versioned YAML, execution logs in queryable database
- **Guided Meta-Refinement**: Agent structures reviews AND questions whether evaluation criteria are right
- **Lean/MVP**: Start conversational, discover patterns, graduate to structure

---

## Task Type Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    TASK TYPE LIFECYCLE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │ BRAIN-   │   │ DESIGN   │   │ CREATE   │   │ EXECUTE  │    │
│  │ STORM    │──▶│          │──▶│          │──▶│          │──┐ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘  │ │
│       │                                             │        │ │
│       │              ┌──────────┐                   │        │ │
│       │              │ REFINE   │◀──────────────────┘        │ │
│       │              │          │                            │ │
│       │              └────┬─────┘                            │ │
│       │                   │                                  │ │
│       │                   ▼                                  │ │
│       │         [hardened, reusable process]                 │ │
│       │                   │                                  │ │
│       └───────────────────┴──────────────────────────────────┘ │
│                    (new task type idea)                        │
└─────────────────────────────────────────────────────────────────┘

Lifecycle Stages:
  draft     → Being designed (phases 1-2)
  active    → Deployable, in use (phases 3-4)
  refined   → Improved based on execution data (phase 5)
  hardened  → Stable, potentially with UI shortcuts
```

---

## Phase 1: Task Brainstorming

**Purpose:** Explore what the user wants to accomplish and which agents could help.

**Entry:** Intentional - user says "I want help with X" or "Let's develop a task for Y", or Main Agent recognizes the need.

**Main Agent Behavior:**

1. **Survey capabilities:**
   ```
   "Here are the specialist agents available:
    - Calendar: events, conflicts, participants, scheduling
    - Document: files, agendas, shared docs, action items
    - Email: threads, communications, attachments
    - Pulse: availability, OOO status, working hours
    - Task: OmniFocus tasks, projects, deadlines

   Which of these might help with what you're trying to do?"
   ```

2. **One question at a time** (superpowers pattern):
   - "What triggers this task? When would you want this?"
   - "What's the goal? What does success look like?"
   - "What information would be most valuable?"
   - "How detailed should the output be?"

3. **Explore 2-3 approaches with tradeoffs:**
   ```
   "Two ways we could approach meeting prep:

   A) Full sweep - all 4 agents gather everything
      + Thorough, won't miss anything
      - Slower, may include irrelevant info

   B) Targeted - Calendar first, expand based on meeting type
      + Faster, more focused
      - May miss unexpected context

   I'd recommend A for important meetings, B for routine ones.
   Or we could make it configurable. Thoughts?"
   ```

4. **Confirm understanding before proceeding:**
   ```
   "Here's what I understand:

   Task: meeting_prep
   Goal: Gather relevant context before meetings
   Trigger: User asks to prep for a specific meeting
   Agents: Calendar, Document, Email, Pulse
   Success: Know participants, have docs, understand recent context

   Does this capture it? Ready to design the specifics?"
   ```

**Output:** Task Brief (stored in agent's working memory, used for Phase 2)

**Transition:** Agent proposes "Ready to design?" → User confirms → Phase 2

---

## Phase 2: Task Design

**Purpose:** Create concrete artifacts: templates, prompts, memory structures, metrics.

**Main Agent Behavior:**

1. **Resolve remaining ambiguities** (don't skip this):
   - "How far back should email search go? 7 days? Since last meeting?"
   - "Include tentative attendees or only confirmed?"
   - "What format works best for the synthesis output?"

2. **Design each component, present in sections, validate each:**

   **Agent prompts:**
   ```
   "For Calendar, I'm thinking:

   'Find the meeting matching {meeting_identifier}. Return:
    - Title, date/time, location
    - All participants with response status
    - Any conflicts in the 30 min before/after
    - Link to calendar event'

   Does this cover what you need from Calendar?"
   ```

   **Synthesis template:**
   ```
   "Here's a template for the output:

   **{meeting_title}** - {meeting_time}

   **Participants:**
   {participant_details}

   **Prep Materials:**
   {document_findings}

   **Recent Context:**
   {email_findings}

   **Availability Notes:**
   {pulse_findings}

   Does this format work?"
   ```

   **Success criteria:**
   ```
   "How should we measure if this task type is working well?

   I'm thinking:
   - Did you proceed to the meeting without follow-up questions?
   - Were the participants accurate?
   - Was relevant context surfaced?

   Any other criteria we should track?"
   ```

3. **Compile into Task Design Document:**
   - Agent prompts for each specialist
   - Synthesis template and mode
   - Memory block structure
   - Metrics to capture
   - Success criteria

**Output:** Task Design Document (YAML file ready for creation)

**Transition:** Agent proposes "Design complete. Create the artifacts?" → User confirms → Phase 3

---

## Phase 3: Task Creation

**Purpose:** Deploy the designed artifacts so the task type is executable.

**Main Agent Behavior:**

Once user confirms, agent **takes the wheel** and creates all artifacts without asking per-item:

1. Write task design file to `docs/task-types/{task_name}.yaml`
2. Register task type with coordination handler
3. Create/update any needed memory blocks
4. Set up logging for new metrics (if any)
5. Optionally update specialist agent personas with task-specific guidance

**Reports back when complete:**
```
"Task type 'meeting_prep' is now active.

Created:
- docs/task-types/meeting_prep.yaml (design document)
- Registered with coordination handler
- Logging configured for: agent_contribution_rate, synthesis_quality, time_to_completion

You can now use this by asking me to prep for a meeting.
Want to try it?"
```

**Output:** Deployable task type (lifecycle_stage: active)

**Transition:** Automatic on completion → Ready for Phase 4

---

## Phase 4: Task Execution

**Purpose:** Run the multi-agent coordination with gathered context.

**Trigger:** User requests something that matches an active task type.

**Main Agent Behavior:**

1. **Recognize task type:**
   ```
   User: "Prep me for my meeting tomorrow"
   Agent: (recognizes this as meeting_prep task type)
   ```

2. **Gather scenario-specific context conversationally:**
   ```
   "Which meeting? I see:
    - Board Meeting (tomorrow 2pm)
    - 1:1 with Sarah (tomorrow 4pm)
    - Team standup (tomorrow 9am)"

   User: "Board meeting"

   "Any specific focus, or should I gather everything?"

   User: "Everything, but especially participant context"
   ```

3. **Execute coordination** (takes the wheel):
   - Call `/v1/coordinate` with gathered context
   - Orchestrator dispatches agents, collects findings, synthesizes
   - All events logged per design

4. **Deliver result:**
   ```
   "**Board Meeting** - Tomorrow 2:00 PM

   **Participants:**
   - Alice Chen (confirmed, attending remotely) - flagged timeline concerns Thursday
   - Bob Smith (confirmed) - his section is ready
   - Carol Wu (pending response) - OOO Friday

   **Prep Materials:**
   - Q4 Budget Review deck (updated yesterday by Alice)
   - Board Deck v3 (shared Monday, 2 action items pending)

   **Recent Context:**
   - Alice's Thursday email raised concerns about Q1 timeline
   - Bob confirmed his deliverables in Monday's thread

   Anything else you'd like to know about this meeting?"
   ```

**Output:** Synthesized response + execution logged

**Transition:** After N executions → Phase 5 becomes relevant

---

## Phase 5: Task Refinement (Guided Meta-Refinement)

**Purpose:** Analyze execution patterns and improve the task type.

**Trigger:** After sufficient executions (e.g., 5+), or user asks "How is meeting_prep working?"

**Main Agent Behavior:**

Structures the review with high-level evaluation aims, then questions the aims themselves:

```
"We've run meeting_prep 5 times. Let me guide us through evaluation:

**1. Goal Achievement**
Did you get useful prep info?
- 4/5 times you proceeded without follow-up questions ✓
- 1 time you asked for more email context

**2. Agent Contribution Quality**
- Calendar: Useful every time (5/5) ✓
- Document: Useful 3/5 (2 meetings had no related docs)
- Email: Useful 4/5 (once pulled irrelevant threads)
- Pulse: Useful 1/5 - mostly redundant with Calendar info

**3. Process Efficiency**
- Average 2 clarifying questions before execution
- Most common: "which meeting?" (5/5) and "what focus?" (3/5)

**4. What I'd Propose Changing**
- Auto-detect "next meeting" if not specified
- Remove Pulse from default agents (add only for important meetings)
- Adjust Email prompt to focus on participants, not just meeting title
- Make "all focus areas" the default

**5. Meta Question: Are These the Right Criteria?**
I'm measuring:
- Contribution rate per agent
- Follow-up questions needed
- Time to completion

Should we also track:
- Synthesis length (too long? too short?)
- Whether you edited the output before using it?
- Which parts you actually referenced in the meeting?

What resonates? What should we refine - the process, the metrics, or both?"
```

**After user input:**
- Update task design document with approved changes
- Commit changes to Git (version history preserved)
- If patterns are very stable: propose UI hardening (Slack buttons, etc.)

**Output:** Refined task design (lifecycle_stage: refined → hardened)

---

## Storage Architecture

### Task Designs: Documents (Git-Versioned)

**Location:** `docs/task-types/{task_name}.yaml`

**Schema:**
```yaml
# docs/task-types/meeting_prep.yaml
name: meeting_prep
version: 1.2.0
lifecycle_stage: refined  # draft | active | refined | hardened
created: 2026-01-29
last_refined: 2026-02-15

# From brainstorming
goal: "Gather relevant context before meetings"
trigger: "User asks to prep for a specific meeting"
success_criteria:
  - "User proceeds to meeting without follow-up questions"
  - "Participants and their context are accurate"
  - "Relevant documents are surfaced"

# Agent configuration
agents:
  calendar:
    prompt_template: |
      Find the meeting matching '{meeting_identifier}'. Return:
      - Title, date/time, location
      - All participants with response status
      - Any conflicts in the 30 min before/after
      - Link to calendar event
    expected_contribution: "Event details, participant list, conflicts"
    timeout_seconds: 10

  document:
    prompt_template: |
      Search for documents related to '{meeting_title}' or
      shared by/with participants: {participants}.
      Return: title, last modified, key content summary.
    expected_contribution: "Relevant docs, agendas, action items"
    timeout_seconds: 15

  email:
    prompt_template: |
      Find email threads from the last {lookback_days} days
      involving participants: {participants}.
      Focus on threads mentioning '{meeting_title}' or related topics.
    expected_contribution: "Recent communications, concerns raised"
    timeout_seconds: 15
    default_lookback_days: 7

  pulse:
    enabled: false  # Disabled after refinement - redundant with calendar
    prompt_template: "..."

# Synthesis configuration
synthesis:
  mode: template_with_enhancement
  template: |
    **{meeting_title}** - {meeting_time}

    **Participants:**
    {participant_details}

    **Prep Materials:**
    {document_findings}

    **Recent Context:**
    {email_findings}
  enhancement_prompt: |
    Review these findings and highlight:
    - Any concerns or blockers raised
    - Action items that may come up
    - Preparation priorities

# Observability
metrics:
  - agent_contribution_rate
  - follow_up_questions_needed
  - time_to_completion
  - synthesis_length

# Refinement history
refinement_log:
  - date: 2026-02-01
    change: "Removed Pulse agent - redundant with Calendar"
    reason: "Only contributed useful info 1/5 executions"
  - date: 2026-02-15
    change: "Added auto-detect for 'next meeting'"
    reason: "Users asked 'which meeting?' 100% of the time"
```

**Why documents:**
- Human-readable, manually editable
- Git versioning (diffs, blame, history, branches)
- No infrastructure dependency
- Proven pattern (superpowers, CLAUDE.md)

### Execution Logs: Database (Queryable)

**Location:** `pa_web.coordination_logs` (Supabase)

**Schema:**
```sql
CREATE TABLE pa_web.coordination_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    event_type TEXT NOT NULL,
    task_id TEXT NOT NULL,
    identity_id TEXT NOT NULL,
    task_type TEXT NOT NULL,  -- References docs/task-types/{task_type}.yaml
    task_version TEXT,        -- Version from YAML at execution time
    data JSONB DEFAULT '{}'::jsonb,
    elapsed_ms INT
);

CREATE INDEX idx_coordination_logs_task ON pa_web.coordination_logs(task_id);
CREATE INDEX idx_coordination_logs_type ON pa_web.coordination_logs(task_type);
CREATE INDEX idx_coordination_logs_time ON pa_web.coordination_logs(timestamp);
```

**Events logged:**

| Event | Data Captured |
|-------|---------------|
| `start` | task_type, task_version, context_provided, questions_asked |
| `agent_dispatch` | agent, prompt_used |
| `agent_contributed` | agent, contribution_length, contribution_summary |
| `agent_timeout` | agent, elapsed_ms |
| `agent_error` | agent, error_message |
| `synthesis` | mode, input_length, output_length |
| `complete` | total_time_ms, agents_completed, agents_failed |
| `user_feedback` | follow_up_requested, edits_made (if trackable) |

**Refinement queries:**
```sql
-- Agent contribution rate by task type
SELECT
    task_type,
    data->>'agent' as agent,
    COUNT(*) FILTER (WHERE event_type = 'agent_contributed') as contributions,
    COUNT(*) FILTER (WHERE event_type = 'agent_dispatch') as dispatches,
    ROUND(100.0 * COUNT(*) FILTER (WHERE event_type = 'agent_contributed') /
          NULLIF(COUNT(*) FILTER (WHERE event_type = 'agent_dispatch'), 0), 1) as contribution_rate
FROM pa_web.coordination_logs
WHERE task_type = 'meeting_prep'
GROUP BY task_type, data->>'agent';

-- Questions asked before execution
SELECT
    data->>'questions_asked' as questions,
    COUNT(*) as frequency
FROM pa_web.coordination_logs
WHERE event_type = 'start' AND task_type = 'meeting_prep'
GROUP BY data->>'questions_asked'
ORDER BY frequency DESC;

-- Time to completion distribution
SELECT
    task_type,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY elapsed_ms) as p50_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY elapsed_ms) as p95_ms,
    AVG(elapsed_ms) as avg_ms
FROM pa_web.coordination_logs
WHERE event_type = 'complete'
GROUP BY task_type;
```

---

## Control Flow: Transitions

### When Agent Takes the Wheel

| Situation | Agent Behavior |
|-----------|----------------|
| Within brainstorming | Asks questions, doesn't pause between each |
| End of brainstorming | "Task brief complete. Ready to design?" → **waits** |
| Within design | Presents components, doesn't pause between each |
| End of design | "Design complete. Create artifacts?" → **waits** |
| User approved creation | Creates all artifacts, reports when done |
| User triggers execution | Gathers context, executes, delivers result |
| Ambiguity encountered | Pauses, asks clarifying question, then proceeds |
| Refinement review | Presents structured analysis → **waits for input** |

### Phase Transition Gates

```
Brainstorm → Design:  "Ready to design the specifics?"
Design → Create:      "Design complete. Create the artifacts?"
Create → Execute:     Automatic (task type now active)
Execute → Refine:     After N executions, or user asks
Refine → Hardened:    "This seems stable. Create a Slack shortcut?"
```

---

## API Design

### Endpoint: `POST /v1/coordinate`

Called by Main Agent after gathering context.

**Request:**
```json
{
    "identity_id": "identity-123",
    "task_type": "meeting_prep",
    "task_version": "1.2.0",
    "context": {
        "meeting_identifier": "Board Meeting tomorrow 2pm",
        "event_id": "event-abc123",
        "focus_areas": ["participants", "prep_materials", "recent_context"],
        "participants": ["alice@company.com", "bob@company.com"],
        "lookback_days": 7
    },
    "questions_asked": ["which_meeting", "focus_areas"],
    "conversation_id": "conv-456"
}
```

**Response:**
```json
{
    "status": "complete",
    "task_id": "task-meeting-prep-20260129-143000",
    "synthesis": "**Board Meeting** - Tomorrow 2:00 PM\n\n...",
    "findings": {
        "calendar": "[Calendar 14:30] Board Meeting, 2pm Jan 30, 3 participants",
        "document": "[Document 14:31] Q4 Budget deck updated yesterday",
        "email": "[Email 14:31] Alice flagged timeline concerns Thursday"
    },
    "agents_completed": ["calendar", "document", "email"],
    "agents_skipped": ["pulse"],
    "coordination_time_ms": 4500
}
```

---

## Main Agent Integration

### Task Development Skill

The Main Agent needs guidance for managing the task lifecycle. Add to persona:

```
## Multi-Agent Task Development

You can develop, execute, and refine multi-agent coordination tasks.

### Lifecycle Phases

**1. Brainstorming** - When user wants help with something that could benefit from multiple specialists:
- Survey which agents might help
- Ask one question at a time to understand the goal
- Explore 2-3 approaches with tradeoffs
- Confirm understanding before designing
- Transition: "Ready to design the specifics?"

**2. Design** - Create the concrete artifacts:
- Resolve remaining ambiguities (don't skip this!)
- Design agent prompts, synthesis template, success criteria
- Present each component, validate with user
- Transition: "Design complete. Create the artifacts?"

**3. Creation** - Deploy the task type:
- Write task design to docs/task-types/{name}.yaml
- Register with coordination handler
- Take the wheel - create all artifacts, report when done

**4. Execution** - Run coordination:
- Recognize when user wants an active task type
- Gather scenario-specific context conversationally
- Call coordinate_task() with full context
- Deliver synthesized result

**5. Refinement** - Improve based on execution data:
- After 5+ executions, offer to review
- Structure the analysis with evaluation aims
- Propose specific changes
- Question whether the evaluation criteria are right
- Update task design with approved changes

### Key Behaviors
- One question at a time during brainstorming
- Don't skip clarifying questions in design
- Take the wheel within phases once direction is set
- Pause at phase boundaries for user confirmation
- Structure refinement reviews, don't just dump data
```

### coordinate_task Tool

```python
def coordinate_task(
    task_type: str,
    context: str,
    questions_asked: str = "[]"
) -> Dict[str, Any]:
    """
    Execute multi-agent coordination for a defined task type.

    Args:
        task_type: Name of the task type (e.g., "meeting_prep")
        context: JSON string with task-specific context gathered from conversation
        questions_asked: JSON array of question IDs asked before execution

    Returns:
        Dictionary with synthesis, findings, and execution metadata.
    """
    import json
    import requests
    import traceback

    try:
        context_dict = json.loads(context)
        questions = json.loads(questions_asked)

        response = requests.post(
            "http://pa-routing-handler:5201/v1/coordinate",
            json={
                "identity_id": get_current_identity_id(),
                "task_type": task_type,
                "context": context_dict,
                "questions_asked": questions
            },
            timeout=60
        )

        return response.json()

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}"
        }
```

---

## Error Handling

| Failure | Handling |
|---------|----------|
| Agent times out | Mark as "timeout", continue with others, note in synthesis |
| Agent errors | Mark as "error", continue with others, note in synthesis |
| Agent disabled in config | Skip, don't dispatch |
| All agents fail | Return partial error, log for analysis |
| Task type not found | Error response, suggest available types |
| Design file invalid | Error on creation, report validation issues |
| Synthesis fails | Fall back to template-only or raw findings |

---

## Implementation Tasks

### Phase 1: Infrastructure
1. Create `docs/task-types/` directory
2. Create coordination_logs table in Supabase
3. Create logging utility functions

### Phase 2: Coordination Endpoint
4. Create `/v1/coordinate` endpoint
5. Implement task type loading from YAML files
6. Implement orchestration flow (dispatch, collect, synthesize)

### Phase 3: Main Agent Integration
7. Create `coordinate_task` tool
8. Update Main Agent persona with task development skill
9. Test brainstorm → execute flow manually

### Phase 4: Observability
10. Implement comprehensive logging
11. Create refinement query helpers
12. Test refinement analysis flow

### Phase 5: First Task Type
13. Develop `meeting_prep` through full lifecycle
14. Execute 5+ times, run refinement
15. Document learnings

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Lifecycle phases work | Can go from brainstorm → design → create → execute |
| Task designs persist | YAML files created, loadable, Git-trackable |
| Execution works | Agents dispatched, findings gathered, synthesis delivered |
| Logging captures data | Events queryable for refinement analysis |
| Refinement is guided | Agent structures review, proposes changes, questions criteria |
| Semi-automatic flow | Agent drives within phases, pauses at gates |

---

## Future Evolution

As task types mature through the lifecycle:

1. **Pattern Discovery** → Stable patterns emerge from execution logs
2. **UI Hardening** → Slack buttons, web forms for common task types
3. **Auto-Detection** → Infer context without asking (e.g., "next meeting")
4. **Cross-Task Learning** → Patterns from one task type inform others
5. **User-Defined Tasks** → Users create task types through conversation
