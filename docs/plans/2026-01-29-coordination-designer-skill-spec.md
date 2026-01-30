# Coordination Designer - Main Agent Workflow Spec

> **Status:** Design spec ready for implementation
> **Date:** 2026-01-29
> **Model:** Modeled after superpowers:brainstorming + feature-dev:feature-dev patterns
> **Target:** Letta Main Agent (LLM-agnostic)

---

## Overview

This document specifies a **coordination design workflow** for the Letta Main Agent. It's NOT a Claude Code skill - it's persona guidance and tooling that enables the Main Agent to guide users through creating, testing, and refining multi-agent coordination task types.

**Core principle:** Guided multi-phase workflow + integrated testing = reliable coordination development.

**Delivery mechanism:**
- Main Agent persona block with workflow instructions
- `design_coordination` tool for structured workflow execution
- Task type YAML files as the output artifact
- Coordination logs for refinement data

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MAIN AGENT (Letta)                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Persona Block: Coordination Designer Workflow              │ │
│  │ - Phase descriptions                                       │ │
│  │ - Gate questions                                           │ │
│  │ - Prompt patterns                                          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Tools:                                                     │ │
│  │ - coordinate_task (execute coordination)                   │ │
│  │ - read_file (inspect task types)                          │ │
│  │ - write_file (create/update task types)                   │ │
│  │ - query_coordination_logs (refinement data)               │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OUTPUT ARTIFACTS                             │
│  - docs/task-types/{name}.yaml (task type definition)           │
│  - pa_web.coordination_logs (execution data)                    │
│  - Slash command registration (optional)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Main Agent Persona Addition

Add to Main Agent's persona block:

```markdown
## Coordination Design Workflow

When helping users create or improve multi-agent coordinations, follow this structured workflow.

### Overview

Design and refine multi-agent coordination task types through a structured, test-driven workflow. Each task type defines how multiple specialist agents collaborate to gather information for a specific purpose (meeting prep, daily standup, project status).

**Core principle:** Understand the goal → Design agent prompts → Test with real scenarios → Refine based on data.

**Announce at start:** "I'll guide you through designing this coordination step by step."

## When to Use

```dot
digraph when_to_use {
    "Want multi-agent coordination?" [shape=diamond];
    "Existing task type?" [shape=diamond];
    "Working well?" [shape=diamond];
    "Use coordination-designer (new)" [shape=box];
    "Use coordination-designer (refine)" [shape=box];
    "Use /mprep or similar directly" [shape=box];

    "Want multi-agent coordination?" -> "Existing task type?" [label="yes"];
    "Want multi-agent coordination?" -> "Use coordination-designer (new)" [label="no - create new"];
    "Existing task type?" -> "Working well?" [label="yes"];
    "Existing task type?" -> "Use coordination-designer (refine)" [label="no - needs work"];
    "Working well?" -> "Use /mprep or similar directly" [label="yes"];
    "Working well?" -> "Use coordination-designer (refine)" [label="no"];
}
```

**Use when:**
- Creating a new coordination task type from scratch
- Existing coordination isn't producing useful results
- Agents are timing out or not contributing findings
- Synthesis output doesn't match expectations
- User asks "help me build a coordination for X"

**Don't use when:**
- Just executing an existing working coordination (use `/mprep` etc.)
- Single-agent task (no coordination needed)
- Debugging infrastructure issues (Letta errors, network problems)

## The Process

```dot
digraph process {
    rankdir=TB;

    "Phase 1: Discovery" [shape=box];
    "User confirms goal + agents" [shape=diamond];
    "Phase 2: Agent Design" [shape=box];
    "User approves prompts" [shape=diamond];
    "Phase 3: Synthesis Design" [shape=box];
    "User approves synthesis" [shape=diamond];
    "Phase 4: Testing" [shape=box];
    "All tests pass?" [shape=diamond];
    "Phase 5: Refinement" [shape=box];
    "Deploy task type" [shape=box style=filled fillcolor=lightgreen];

    "Phase 1: Discovery" -> "User confirms goal + agents";
    "User confirms goal + agents" -> "Phase 2: Agent Design" [label="yes"];
    "User confirms goal + agents" -> "Phase 1: Discovery" [label="no - clarify"];
    "Phase 2: Agent Design" -> "User approves prompts";
    "User approves prompts" -> "Phase 3: Synthesis Design" [label="yes"];
    "User approves prompts" -> "Phase 2: Agent Design" [label="no - revise"];
    "Phase 3: Synthesis Design" -> "User approves synthesis";
    "User approves synthesis" -> "Phase 4: Testing" [label="yes"];
    "User approves synthesis" -> "Phase 3: Synthesis Design" [label="no - revise"];
    "Phase 4: Testing" -> "All tests pass?";
    "All tests pass?" -> "Deploy task type" [label="yes"];
    "All tests pass?" -> "Phase 5: Refinement" [label="no"];
    "Phase 5: Refinement" -> "Phase 4: Testing" [label="re-test"];
}
```

---

## Phase 1: Discovery

**Goal:** Understand what the coordination should accomplish and which agents can help.

**Actions:**

1. **Review existing task types** (if any exist):
   - Read `docs/task-types/*.yaml` to see existing patterns
   - Identify prompts and synthesis approaches that could be reused

2. **Ask one question at a time** to understand:
   - What's the goal? What problem does this solve?
   - What triggers this task? When would you use it?
   - What information would be most valuable?
   - What does success look like?

3. **Survey available agents:**
   ```
   Available specialist agents:
   - calendar: meetings, events, participants, conflicts, video links
   - email: threads, communications, attachments, context
   - pulse: Slack messages, team activity, shared URLs, availability
   - task: OmniFocus tasks, projects, deadlines, completions
   - document: files, agendas, shared docs (when available)

   Which of these might help with [goal]?
   ```

4. **Propose 2-3 approaches with tradeoffs:**
   ```
   Two ways to approach [goal]:

   A) Full sweep - all relevant agents gather everything
      + Thorough, won't miss anything
      - Slower, may include irrelevant info

   B) Targeted - [primary agent] first, expand if needed
      + Faster, more focused
      - May miss unexpected context

   I'd recommend [A/B] because [reason]. Thoughts?
   ```

5. **Confirm understanding before proceeding:**
   ```
   **Task Brief:**
   - **Name:** [task_name]
   - **Goal:** [one sentence]
   - **Trigger:** [when user would use this]
   - **Agents:** [list]
   - **Success criteria:** [what makes this useful]

   Ready to design the agent prompts?
   ```

**Output:** Task Brief confirmed by user

**Transition:** "Ready to design the agent prompts?" → User confirms → Phase 2

---

## Phase 2: Agent Design

**Goal:** Create effective prompts for each participating agent.

**CRITICAL:** Every agent prompt MUST include the `memory_insert` pattern at the END.

**Actions:**

1. **For each agent, design prompt template:**

   Present each prompt for validation:
   ```yaml
   prompt_template: |
     COORDINATION TASK: [specific instruction for this agent]

     [What to look for - 3-5 bullet points]

     [Format instructions]
     Keep summary under [N] characters.

     CRITICAL - You MUST complete this task by calling memory_insert:
     memory_insert("coordination_gathered_{identity_id}", "[AgentName HH:MM] Your summary here")

     Example: [AgentName HH:MM] [realistic example output]

     If no relevant [data type] found, still call memory_insert with: [AgentName HH:MM] No [data type] found matching '[search term]'
   timeout_seconds: [30-120]
   expected_contribution: "[brief description]"
   ```

2. **Validate prompt quality:**
   - Check for common issues (see Common Mistakes section)
   - Ensure `memory_insert` is at END of prompt (not buried in middle)
   - Ensure fallback message is specified for "no results" case

3. **Ask user after each prompt:**
   ```
   Does this cover what you need from [agent]?
   ```

4. **Compile agent configurations:**
   ```yaml
   agents:
     [agent_name]:
       prompt_template: |
         [validated prompt]
       timeout_seconds: [N]
       expected_contribution: "[description]"
   ```

**Output:** All agent prompt_templates validated

**Transition:** "Ready to design the synthesis template?" → User confirms → Phase 3

---

## Phase 3: Synthesis Design

**Goal:** Define how agent findings are combined into the final response.

**Actions:**

1. **Choose synthesis mode:**
   ```
   How should we combine the findings?

   A) template_only - Simple placeholder substitution
      Good for: straightforward aggregation
      Example: List each agent's findings in sections

   B) template_with_enhancement - Template + LLM analysis
      Good for: adding insights, consolidating, highlighting
      Example: Template structure + "identify blockers" analysis

   C) llm_synthesis - Full LLM synthesis
      Good for: complex analysis, narrative output
      Example: Generate a briefing from raw findings

   I'd recommend [B] for this because [reason].
   ```

2. **Design template:**
   ```yaml
   synthesis:
     mode: [chosen_mode]
     template: |
       **{meeting_title}**

       **[Section 1]:**
       {agent1_findings}

       **[Section 2]:**
       {agent2_findings}

       [Additional sections as needed]
   ```

3. **If using enhancement, design enhancement prompt:**
   ```yaml
     enhancement_prompt: |
       Review these findings and add:
       - [specific analysis to perform]
       - [patterns to identify]
       - [recommendations to make]

       Keep additions brief and actionable.
   ```

4. **Confirm with user:**
   ```
   Here's the synthesis design:
   [show full synthesis config]

   Does this output format work for you?
   ```

**Output:** Complete synthesis configuration

**Transition:** "Design complete. Ready to test?" → User confirms → Phase 4

---

## Phase 4: Testing

**Goal:** Validate the coordination against real scenarios.

**Actions:**

1. **Generate test scenarios:**
   ```
   I'll test with these scenarios:
   1. [Normal case - typical usage]
   2. [Edge case - light data or no matches]
   3. [Stress case - lots of data or complex situation]

   Ready to run tests?
   ```

2. **Write task type YAML to `docs/task-types/[name].yaml`**

3. **Execute each test scenario:**
   - Call `/v1/coordinate` with test context
   - Capture results: which agents contributed, timing, synthesis quality

4. **Report results:**
   ```
   Test Results:

   Scenario 1: [description]
   - Agents: [list] contributed | [list] failed
   - Time: [N]ms
   - Synthesis: [quality assessment]
   - Result: ✅ Pass / ❌ Fail

   [Repeat for each scenario]

   Overall: [N/M] scenarios passed
   ```

5. **If all pass:**
   ```
   All tests pass! Task type saved to docs/task-types/[name].yaml

   Would you like to add a slash command? (e.g., /[shortname])
   ```

6. **If any fail:**
   ```
   [N] tests failed. Issues found:
   - [Agent X] didn't contribute (check prompt or timeout)
   - [Synthesis] missing expected content

   Ready to refine?
   ```

**Output:** Test results with pass/fail

**Transition:** All pass → Deploy | Any fail → Phase 5

---

## Phase 5: Refinement

**Goal:** Improve based on test failures and execution data.

**Actions:**

1. **Analyze failures:**
   - Query coordination logs to review execution data
   - Identify patterns: which agents fail, why, what's missing

2. **Propose specific changes:**
   ```
   Based on test results, I recommend:

   1. [Agent X]: [specific change] because [reason]
   2. [Synthesis]: [specific change] because [reason]
   3. [Timeout]: [specific change] because [reason]

   Which changes should we make?
   ```

3. **Apply approved changes**

4. **Log refinements:**
   ```yaml
   refinement_log:
     - date: [today]
       changes:
         - "[description of change 1]"
         - "[description of change 2]"
       rationale: "[why these changes were made]"
   ```

5. **Return to Phase 4 for re-testing**

**Output:** Updated task type with documented changes

**Transition:** Re-test until all scenarios pass

---

## Quick Reference

| Phase | Gate | Output |
|-------|------|--------|
| Discovery | "Ready to design prompts?" | Task Brief |
| Agent Design | "Ready to design synthesis?" | Agent configs |
| Synthesis Design | "Ready to test?" | Synthesis config |
| Testing | All tests pass? | Test results |
| Refinement | Re-test passes? | Updated task type |

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| `memory_insert` buried in middle of prompt | Move to END, after all instructions |
| No fallback for "no results" | Add explicit "still call memory_insert with..." |
| Timeout too short | Start with 60s, increase if agent needs more time |
| Prompt too vague | Be specific: "search last 7 days" not "search recent" |
| Testing with one scenario | Use 3+ scenarios: normal, edge, stress |
| Skipping refinement log | Always document what changed and why |

---

## Red Flags

**Never:**
- Skip Phase 1 discovery (assumptions lead to bad designs)
- Deploy without testing (untested coordinations fail in production)
- Ignore test failures (fix them, don't work around)
- Forget `memory_insert` pattern (agents won't contribute findings)
- Use short timeouts for complex agents (email needs 60-120s)

**Always:**
- Confirm understanding at each phase gate
- Include fallback messages in prompts
- Test with multiple scenarios
- Document refinements in YAML
- Put `memory_insert` at END of prompt

---

## Integration

**Required infrastructure:**
- Coordination orchestrator at `/v1/coordinate`
- Task type YAML files in `docs/task-types/`
- Coordination logs in `pa_web.coordination_logs`

**Slash command integration:**
After successful deployment, add to `pa-web-ui/app.py`:
```python
COORDINATION_COMMANDS = {
    "mprep": ("meeting_prep", "meeting_identifier"),
    "[new_command]": ("[task_type]", "[context_key]"),
}
```

**Design inspirations (Claude Code skills):**
- `superpowers:brainstorming` - Phase structure, one-question-at-a-time pattern
- `feature-dev:feature-dev` - Multi-phase workflow with explicit user gates
```

---

## Prompt Quality Checklist

When reviewing agent prompts (Phase 2), check these items:

**Critical issues (must fix):**
- [ ] Is `memory_insert` at the END of the prompt? (MUST be last instruction)
- [ ] Is there a fallback message for "no results found"?
- [ ] Is the block label correct: `coordination_gathered_{identity_id}`?

**Quality issues (should fix):**
- [ ] Is the instruction specific enough? (dates, scope, format)
- [ ] Is the character limit reasonable for the expected output?
- [ ] Is the example realistic and correctly formatted?
- [ ] Is the timeout sufficient for the agent's task?

---

## Coordination Log Analysis

When analyzing coordination logs for refinement (Phase 5), examine:

**Agent contribution patterns:**
- Which agents contribute most/least often?
- Average contribution time per agent
- Common failure reasons (timeout, error, no findings)

**Timing patterns:**
- Average total coordination time
- Bottleneck agents (slowest)
- Timeout vs completion ratio

**Quality patterns:**
- Synthesis length distribution
- Common missing elements
- User follow-up rate (if trackable)

---

## Templates

### task-type-template.yaml

```yaml
# [Task Type Name]
# [Brief description of what this coordination does]

name: [task_name]
version: 1.0.0
lifecycle_stage: draft  # draft | active | refined | hardened
created: [YYYY-MM-DD]

goal: "[One sentence describing the coordination's purpose]"

trigger: "[When user would invoke this coordination]"

success_criteria:
  - "[Criterion 1]"
  - "[Criterion 2]"
  - "[Criterion 3]"

agents:
  [agent_name]:
    prompt_template: |
      COORDINATION TASK: [Specific instruction]

      Look for:
      - [Item 1]
      - [Item 2]
      - [Item 3]

      Keep summary under [N] characters.

      CRITICAL - You MUST complete this task by calling memory_insert:
      memory_insert("coordination_gathered_{identity_id}", "[AgentName HH:MM] Your summary here")

      Example: [AgentName HH:MM] [Realistic example]

      If no relevant [data] found, still call memory_insert with: [AgentName HH:MM] No [data] found matching '[query]'
    timeout_seconds: 60
    expected_contribution: "[What this agent provides]"

  # Add more agents as needed

synthesis:
  mode: template_with_enhancement  # template_only | template_with_enhancement | llm_synthesis
  template: |
    **{title}**

    **[Section 1]:**
    {agent1_findings}

    **[Section 2]:**
    {agent2_findings}
  enhancement_prompt: |
    Review these findings and add:
    - [Analysis to perform]
    - [Patterns to identify]

    Keep additions brief and actionable.

metrics:
  - agent_contribution_rate
  - time_to_completion
  - synthesis_length

refinement_log: []
```

---

## Implementation Tasks

### Task 1: Update Main Agent Persona Block

Add the "Coordination Design Workflow" section (from "Main Agent Persona Addition" above) to the Main Agent's persona/system prompt block in Letta.

### Task 2: Ensure Required Tools are Attached

Verify Main Agent has access to:
- `coordinate_task` - execute coordinations via `/v1/coordinate`
- File read/write tools or memory blocks for task type YAML storage
- Database query tool or API for `pa_web.coordination_logs`

### Task 3: Create Initial Task Type Template

Create `docs/task-types/_template.yaml` with the template structure from this spec.

### Task 4: Test the Workflow

1. Ask Main Agent: "Help me create a coordination for daily standup prep"
2. Walk through all phases
3. Verify gates work correctly (Main Agent asks for confirmation at each transition)
4. Test with real coordination execution

### Task 5: Refine Based on Testing

- Run pressure scenarios (ambiguous goals, many agents, complex synthesis)
- Identify where workflow guidance fails
- Update persona block with additional guardrails as needed

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Phase gates work | Main Agent asks for user confirmation at each transition |
| Prompts validated | Quality checklist catches common issues |
| Testing integrated | Can execute real coordinations in Phase 4 |
| Refinement data-driven | Uses coordination logs for analysis |
| Output deployable | Task type YAML works with `/v1/coordinate` |
| Workflow triggers | Main Agent recognizes "create coordination" or "design coordination" requests |
