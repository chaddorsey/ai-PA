# Meeting Prep Coordination v2: Calendar-First with Iterative Refinement

## Problem

The current coordination system dispatches all specialist agents in parallel with a vague user string (e.g., "Becca / Concord check-in"). Agents guess at names, search with overly narrow terms, and have no shared context. Results from a recent run:

- Calendar: fuzzy-matched the wrong meeting entirely
- Email: guessed "Becca Ellis" (wrong person — it's Becca Novak)
- Pulse: used exact-phrase quoted search, got zero results
- Docs: found excellent Granola data but couldn't write it to its block (prompt used deprecated `memory_insert` syntax; agent has the canonical `memory` tool)

Root causes: no resolved meeting context before searching, no evaluation of search quality, no iteration on poor results, prompt templates targeting deprecated tool API.

## Design

### Architecture: Orchestrator as Framework, Main Agent as Brain

**Orchestrator** (pa-routing-handler Python code): Process runner and rule keeper.
- Executes phases in sequence (Round 0 → Round 1 → Evaluate → Round 2 → Synthesize)
- Manages parallel dispatch (specialist agents can't be fanned out from the main agent's serial multi-agent tools)
- Enforces timeouts and caps (max 2 rounds, per-agent timeouts)
- Manages memory block lifecycle (create, attach, detach, cleanup)
- Logs coordination events for analysis

**Main agent** (Letta main-assistant-agent-kinara): Intelligence and evaluation.
- Evaluates search quality from Round 1 ("Pulse searched too narrowly")
- Formulates follow-up prompts for Round 2 ("Search for 'Becca Novak' and 'Valhalla' separately")
- Decides which agents need re-dispatch
- Produces final synthesis
- Has long-term memory about the user's contacts, projects, relationships

**Specialist agents** (calendar, docs, email, pulse): Domain tool access.
- Execute searches using their domain-specific tools
- Report both findings AND search strategy (what terms, what tools, how many results)

### Phase Flow

```
Phase 0: RESOLVE (serial, ~10s)
  Orchestrator → Calendar Agent
  "Find today's next meeting matching '{identifier}'. Return structured data."
  Output: title, participants (names + emails), time, video link
  If NO_MATCH → return error to user asking for clarification

Phase 1: GATHER (parallel, ~30s)
  Orchestrator → Docs, Email, Pulse (parallel dispatch)
  Each agent gets resolved meeting details from Phase 0
  Each agent reports: search strategy used + findings
  Output: per-agent findings written to memory blocks

Phase 1.5: EVALUATE (serial, ~10s)
  Orchestrator → Main Agent
  "Here are Round 1 findings and search strategies. Evaluate search quality.
   For agents that should search again, call request_agent_followup(agent, prompt).
   If no follow-ups needed, say NO_FOLLOWUPS."
  Main agent uses tool calls to request specific follow-ups
  Orchestrator reads tool calls from Letta API response

Phase 2: REFINE (selective parallel, ~20s, may be skipped)
  Orchestrator → only agents the main agent requested
  Prompts come directly from main agent's follow-up instructions
  Output: additional findings in memory blocks

Phase 3: SYNTHESIZE (serial, ~10s)
  Orchestrator → Main Agent
  "Here are all findings from Round 1 + Round 2. Produce a meeting prep brief."
  Output: final prep document returned to user
```

Total estimated time: 60-80s (down from current ~90s with better results).

### Calendar Agent Prompt (Phase 0)

Constrained to return structured, parseable data:

```
MEETING PREP: Find today's next upcoming meeting matching '{meeting_identifier}'.

Get today's calendar events and find the NEXT event (soonest, not past) where
the title or description contains words from '{meeting_identifier}'.

Return EXACTLY this format:
TITLE: <exact calendar event title>
TIME: <e.g., "2:00 PM">
DATE: <e.g., "Feb 27, 2026">
PARTICIPANTS: <comma-separated full names>
EMAILS: <comma-separated email addresses>
LINK: <video conference URL or "none">
DESCRIPTION: <first 200 chars of event description or "none">

If NO upcoming meeting matches, return exactly: NO_MATCH

Write your response to your coordination block using:
memory("insert", path="/memories/{gathered_label}", insert_line=0,
  insert_text="[Calendar HH:MM] <your structured response>")
```

### Specialist Agent Prompts (Phase 1)

Each prompt includes resolved meeting details AND requires reporting search strategy.

Example for Docs agent:

```
MEETING PREP: Gather documents for '{resolved_title}' with {resolved_participants}
at {resolved_time} today.

Participant emails: {resolved_emails}

Search strategy — try ALL of these:
1. search_documents for participant names (e.g., "{participant_first_names}")
2. search_documents for meeting topic keywords
3. search_documents for "Briefing" + participant/org names
4. query_granola_meetings for past meetings with these participants
5. Look for recently modified docs mentioning participants

IMPORTANT: Report your search strategy. For each search you run, note:
- What tool you called and with what terms
- How many results you got

Write your findings AND strategy to your coordination block:
memory("insert", path="/memories/{gathered_label}", insert_line=0,
  insert_text="[Document HH:MM] STRATEGY: <what you searched for> | FINDINGS: <what you found>")
```

### Main Agent Evaluation Prompt (Phase 1.5)

```
MEETING PREP EVALUATION for '{resolved_title}' with {resolved_participants}.

Round 1 results from specialist agents:

CALENDAR: {calendar_findings}
DOCS: {docs_findings_and_strategy}
EMAIL: {email_findings_and_strategy}
PULSE: {pulse_findings_and_strategy}

Evaluate each agent's search strategy:
- Did they search with the right terms?
- Did they use participant names and emails effectively?
- Could a different search strategy yield better results?
- Are there leads from one agent's results that another agent should pursue?
  (e.g., an org name from Granola, a doc title from email, an email address from calendar)

For each agent that should search again, call:
  request_agent_followup(agent_name="<agent>", followup_prompt="<specific instructions>")

If all searches were adequate, respond with: NO_FOLLOWUPS
```

### Main Agent Synthesis Prompt (Phase 3)

```
MEETING PREP SYNTHESIS for '{resolved_title}' at {resolved_time}.

All gathered information:

{all_findings_round_1_and_round_2}

Produce a concise meeting prep brief covering:
- Meeting basics (time, participants, video link)
- Key context from past meetings and conversations
- Relevant documents and their significance
- Action items or open threads from prior interactions
- Suggested preparation priorities
- Questions to consider raising

Format for readability. Be concise — this is a prep brief, not a research paper.
```

### The `request_agent_followup` Tool

New custom Letta tool attached to the main agent. The orchestrator reads tool calls from the Letta API response to determine Round 2 dispatches.

```python
def request_agent_followup(agent_name: str, followup_prompt: str) -> Dict[str, Any]:
    """
    Request a follow-up search from a specialist agent during meeting prep.

    Call this when evaluating Round 1 results if an agent's search strategy
    was inadequate or if new leads emerged that warrant further searching.

    Args:
        agent_name: Which agent to re-dispatch ("document", "email", "pulse")
        followup_prompt: Specific search instructions for the agent

    Returns:
        Confirmation that the follow-up was registered.
    """
    return {"status": "ok", "agent": agent_name, "prompt": followup_prompt}
```

The tool itself does nothing — it's a structured communication channel. The orchestrator intercepts the tool call from the Letta response messages.

### Memory Block Strategy

Same per-agent block model as current (no race conditions):
- `coordination_gathered_{identity_id}_{agent_name}` — one per specialist agent
- All prompts use canonical `memory` tool syntax with `insert_line=0` workaround
- `memory_insert` references removed from all prompts

Orchestrator reads blocks to collect findings. If a block is empty after dispatch (tool call failed), orchestrator falls back to reading the assistant_message from the Letta API response.

### No Calendar Match

If Phase 0 returns NO_MATCH:
- Orchestrator returns immediately to the user: "I couldn't find a matching meeting on your calendar for '{identifier}'. Can you clarify the meeting name or participants?"
- No Phase 1/2/3 executed
- Logged as a "no_match" event for analysis

## Changes Required

| Component | Change |
|-----------|--------|
| `meeting_prep.yaml` | Rewrite all prompt templates: `memory` syntax, strategy reporting, resolved-context placeholders. Add Phase 1.5 and Phase 3 prompts. |
| `coordination_orchestrator.py` | Two-phase dispatch: calendar serial → others parallel. New evaluation phase (send to main agent, parse tool calls). New synthesis phase. Assistant-message fallback for empty blocks. |
| `coordination_handler.py` | Minor: assistant-message fallback method. Otherwise unchanged. |
| New Letta tool: `request_agent_followup` | Register tool, attach to main agent. Orchestrator reads tool calls from response. |
| `AGENT_IDS` in orchestrator | Add main agent to the mapping (already exists as `MAIN_AGENT_ID`). |

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Main agent evaluation adds latency | Cap at 2 rounds. Skip Round 2 if main agent says NO_FOLLOWUPS. |
| Calendar agent still fuzzy-matches wrong meeting | Constrained prompt with structured output. Orchestrator validates parsed fields before proceeding. |
| `memory("insert", insert_line=0)` workaround breaks in future Letta version | Monitor Letta releases. The bug is `insert_line` defaulting to None. Once fixed, remove the explicit `insert_line=0`. |
| Main agent's follow-up prompts are too vague | The evaluation prompt explicitly asks for specific search terms and tool instructions. Log follow-up prompts for refinement. |

## Success Criteria

1. Calendar agent resolves the correct meeting with correct participants
2. All specialist agents receive resolved participant names and emails
3. Docs agent successfully writes findings to its block using `memory` tool
4. Main agent identifies at least one search improvement in Round 1 evaluation
5. Final synthesis includes information from multiple agents
6. Total coordination time under 90 seconds
