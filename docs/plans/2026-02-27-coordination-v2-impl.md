# Coordination V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor meeting prep coordination from a single parallel fan-out into a calendar-first, iterative refinement system where the main agent evaluates search quality and directs follow-ups.

**Architecture:** The orchestrator manages phase transitions (Resolve → Gather → Evaluate → Refine → Synthesize) and parallel dispatch. The main Letta agent evaluates Round 1 results and formulates follow-up prompts via a `request_agent_followup` tool call. Specialist agents report both search strategy and findings using the canonical `memory` tool.

**Tech Stack:** Python 3.11+, FastAPI, httpx, Letta API, pytest, pytest-asyncio

**Design doc:** `docs/plans/2026-02-27-coordination-v2-design.md`

---

## Task 1: Add Phase Config to Task Type Model

Extend the task type model to support phased agent execution (resolve agent runs first, then gather agents in parallel) and evaluation/synthesis prompts for the main agent.

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/task_type_loader.py`
- Test: `pa-routing-handler/tests/services/test_task_type_loader.py`

**Step 1: Write the failing test**

Add to `tests/services/test_task_type_loader.py`:

```python
class TestTaskTypePhaseConfig:
    """Tests for phase-aware task type configuration."""

    def test_parse_resolve_agent(self, tmp_path):
        """Task type with resolve_agent parses correctly."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        yaml_content = """
name: meeting_prep
version: "2.0.0"
lifecycle_stage: active
goal: Gather meeting context
resolve_agent: calendar
agents:
  calendar:
    prompt_template: "Find meeting {meeting_identifier}"
    timeout_seconds: 30
  document:
    prompt_template: "Find docs for {resolved_title}"
    timeout_seconds: 60
synthesis:
  mode: main_agent
  evaluation_prompt: "Evaluate these results: {findings}"
  synthesis_prompt: "Synthesize: {findings}"
"""
        (tmp_path / "meeting_prep.yaml").write_text(yaml_content)
        loader = TaskTypeLoader(str(tmp_path))
        task_type = loader.load("meeting_prep")

        assert task_type.resolve_agent == "calendar"

    def test_get_gather_agents_excludes_resolve(self, tmp_path):
        """get_gather_agents returns enabled agents minus the resolve agent."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        yaml_content = """
name: meeting_prep
version: "2.0.0"
lifecycle_stage: active
goal: Gather meeting context
resolve_agent: calendar
agents:
  calendar:
    prompt_template: "Find meeting"
    timeout_seconds: 30
  document:
    prompt_template: "Find docs"
    timeout_seconds: 60
  email:
    prompt_template: "Find emails"
    timeout_seconds: 120
synthesis:
  mode: main_agent
"""
        (tmp_path / "meeting_prep.yaml").write_text(yaml_content)
        loader = TaskTypeLoader(str(tmp_path))
        task_type = loader.load("meeting_prep")

        gather = task_type.get_gather_agents()
        assert "calendar" not in gather
        assert "document" in gather
        assert "email" in gather

    def test_parse_evaluation_and_synthesis_prompts(self, tmp_path):
        """Evaluation and synthesis prompts parse from synthesis config."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        yaml_content = """
name: test
version: "1.0.0"
lifecycle_stage: active
goal: Test
agents: {}
synthesis:
  mode: main_agent
  evaluation_prompt: "Evaluate: {findings}"
  synthesis_prompt: "Synthesize: {findings}"
"""
        (tmp_path / "test.yaml").write_text(yaml_content)
        loader = TaskTypeLoader(str(tmp_path))
        task_type = loader.load("test")

        assert task_type.synthesis.evaluation_prompt == "Evaluate: {findings}"
        assert task_type.synthesis.synthesis_prompt == "Synthesize: {findings}"

    def test_resolve_agent_defaults_to_none(self, tmp_path):
        """Task types without resolve_agent default to None (v1 compat)."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        yaml_content = """
name: simple
version: "1.0.0"
lifecycle_stage: active
goal: Simple task
agents:
  calendar:
    prompt_template: "Find meeting"
synthesis:
  mode: template_only
  template: "{findings}"
"""
        (tmp_path / "simple.yaml").write_text(yaml_content)
        loader = TaskTypeLoader(str(tmp_path))
        task_type = loader.load("simple")

        assert task_type.resolve_agent is None
        # get_gather_agents falls back to get_enabled_agents when no resolve
        assert "calendar" in task_type.get_gather_agents()
```

**Step 2: Run test to verify it fails**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_task_type_loader.py::TestTaskTypePhaseConfig -v`
Expected: FAIL — `TaskType` has no `resolve_agent` attribute, no `get_gather_agents` method, `SynthesisConfig` has no `evaluation_prompt`/`synthesis_prompt`

**Step 3: Implement the model changes**

In `pa-routing-handler/src/pa_routing/services/task_type_loader.py`:

Add `synthesis_prompt` and `evaluation_prompt` to `SynthesisConfig`:

```python
@dataclass
class SynthesisConfig:
    """Configuration for response synthesis."""

    mode: str  # template_only, template_with_enhancement, main_agent
    template: Optional[str] = None
    enhancement_prompt: Optional[str] = None
    evaluation_prompt: Optional[str] = None
    synthesis_prompt: Optional[str] = None
```

Add `resolve_agent` and `get_gather_agents` to `TaskType`:

```python
@dataclass
class TaskType:
    """A loaded task type definition."""

    name: str
    version: str
    lifecycle_stage: str
    goal: str
    agents: Dict[str, AgentConfig]
    synthesis: SynthesisConfig
    success_criteria: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    resolve_agent: Optional[str] = None

    def get_enabled_agents(self) -> Dict[str, AgentConfig]:
        """Get only enabled agents."""
        return {name: config for name, config in self.agents.items() if config.enabled}

    def get_gather_agents(self) -> Dict[str, AgentConfig]:
        """Get agents for the gather phase (enabled, minus resolve agent)."""
        enabled = self.get_enabled_agents()
        if self.resolve_agent:
            return {k: v for k, v in enabled.items() if k != self.resolve_agent}
        return enabled

    def is_executable(self) -> bool:
        """Check if task type can be executed (not draft)."""
        return self.lifecycle_stage != "draft"
```

In `_parse_task_type`, add parsing for `resolve_agent` and new synthesis fields:

```python
def _parse_task_type(self, data: Dict[str, Any], name: str) -> TaskType:
    # ... existing agent parsing ...

    synthesis_data = data.get("synthesis", {})
    synthesis = SynthesisConfig(
        mode=synthesis_data.get("mode", "template_only"),
        template=synthesis_data.get("template"),
        enhancement_prompt=synthesis_data.get("enhancement_prompt"),
        evaluation_prompt=synthesis_data.get("evaluation_prompt"),
        synthesis_prompt=synthesis_data.get("synthesis_prompt"),
    )

    return TaskType(
        name=data.get("name", name),
        version=data.get("version", "0.0.0"),
        lifecycle_stage=data.get("lifecycle_stage", "draft"),
        goal=data.get("goal", ""),
        agents=agents,
        synthesis=synthesis,
        success_criteria=data.get("success_criteria", []),
        metrics=data.get("metrics", []),
        resolve_agent=data.get("resolve_agent"),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_task_type_loader.py::TestTaskTypePhaseConfig -v`
Expected: PASS (4 tests)

**Step 5: Run all existing tests to check for regressions**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_task_type_loader.py -v`
Expected: All existing tests PASS (new fields have defaults, backwards compatible)

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/task_type_loader.py pa-routing-handler/tests/services/test_task_type_loader.py
git commit -m "feat(coordination): add resolve_agent and evaluation/synthesis prompts to task type model"
```

---

## Task 2: Create `request_agent_followup` Letta Tool

Create the tool the main agent calls during evaluation to request follow-up searches from specialist agents. The tool itself is a no-op — the orchestrator reads tool calls from the Letta API response.

**Files:**
- Create: `letta/tools/request_agent_followup.py`
- Create: `letta/register_followup_tool.py`

**Step 1: Write the tool function**

Create `letta/tools/request_agent_followup.py`:

```python
from typing import Dict, Any, Optional


def request_agent_followup(agent_name: str, followup_prompt: str) -> Dict[str, Any]:
    """
    Request a follow-up search from a specialist agent during meeting prep evaluation.

    Call this when evaluating Round 1 results if an agent's search was too narrow,
    used wrong terms, or if new leads emerged from other agents' findings.

    You may call this multiple times for different agents. Only call for agents
    that would benefit from a refined search — not agents whose results are already good.

    Valid agent names: "document", "email", "pulse"

    Args:
        agent_name: Which specialist agent to re-dispatch. Must be one of: document, email, pulse.
        followup_prompt: Specific search instructions for the agent. Be precise about what terms to search, what tools to use, and what to look for. Include any new context discovered in Round 1.

    Returns:
        Confirmation that the follow-up request was registered.
    """
    import traceback

    try:
        valid_agents = {"document", "email", "pulse", "calendar"}
        if agent_name not in valid_agents:
            return {
                "status": "error",
                "error_message": f"Invalid agent: {agent_name}. Must be one of: {', '.join(sorted(valid_agents))}"
            }

        return {
            "status": "ok",
            "message": f"Follow-up registered for {agent_name}. The orchestrator will dispatch this agent with your prompt.",
            "agent_name": agent_name,
            "prompt_preview": followup_prompt[:100]
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

**Step 2: Write the registration script**

Create `letta/register_followup_tool.py`:

```python
"""Register request_agent_followup tool with Letta and attach to main agent.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python letta/register_followup_tool.py
"""
import os
import inspect
import requests

LETTA_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"

from tools.request_agent_followup import request_agent_followup

def main():
    source = inspect.getsource(request_agent_followup)

    # Check if tool already exists
    resp = requests.get(f"{LETTA_URL}/v1/tools/")
    existing = {t["name"]: t["id"] for t in resp.json()}

    tool_name = "request_agent_followup"

    if tool_name in existing:
        tool_id = existing[tool_name]
        resp = requests.patch(
            f"{LETTA_URL}/v1/tools/{tool_id}",
            json={"source_code": source}
        )
        print(f"Updated tool: {tool_id} [{resp.status_code}]")
    else:
        resp = requests.post(
            f"{LETTA_URL}/v1/tools/",
            json={"source_code": source, "name": tool_name}
        )
        if resp.ok:
            tool_id = resp.json()["id"]
            print(f"Created tool: {tool_id}")
        else:
            print(f"Error creating tool: {resp.status_code} {resp.text}")
            return

    # Attach to main agent
    resp = requests.patch(
        f"{LETTA_URL}/v1/agents/{MAIN_AGENT_ID}/tools/attach/{tool_id}"
    )
    if resp.ok:
        print(f"Attached to main agent: {MAIN_AGENT_ID}")
    else:
        print(f"Attach error: {resp.status_code} {resp.text}")


if __name__ == "__main__":
    main()
```

**Step 3: Register and verify**

Run:
```bash
cd /Volumes/main-drive/ai-PA
LETTA_BASE_URL=http://localhost:8283 python letta/register_followup_tool.py
```
Expected: "Created tool: tool-xxx" + "Attached to main agent"

Verify:
```bash
curl -s 'http://localhost:8283/v1/agents/agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a/tools?limit=50' | python3 -c "import sys,json; print([t['name'] for t in json.load(sys.stdin) if 'followup' in t['name']])"
```
Expected: `['request_agent_followup']`

**Step 4: Commit**

```bash
git add letta/tools/request_agent_followup.py letta/register_followup_tool.py
git commit -m "feat(coordination): add request_agent_followup tool for main agent evaluation"
```

---

## Task 3: Rewrite meeting_prep.yaml Prompts

Rewrite all agent prompts: constrained calendar output for Phase 0, resolved-context placeholders + strategy reporting + `memory` tool syntax for Phase 1, evaluation and synthesis prompts for the main agent.

**Files:**
- Modify: `docs/task-types/meeting_prep.yaml`

**Step 1: Rewrite the YAML**

Replace `docs/task-types/meeting_prep.yaml` with:

```yaml
# Meeting Prep Task Type v2
# Calendar-first with iterative refinement via main agent evaluation

name: meeting_prep
version: 2.0.0
lifecycle_stage: active
created: 2026-01-29
updated: 2026-02-27

goal: "Gather relevant context before meetings using calendar-first resolution and iterative search refinement"

trigger: "User asks to prep for a specific meeting"

# Calendar runs first (serial) to resolve meeting details before other agents
resolve_agent: calendar

success_criteria:
  - "Calendar resolves the correct meeting with correct participants"
  - "All specialist agents receive resolved participant names and emails"
  - "Main agent identifies search improvements in evaluation"
  - "Final synthesis includes information from multiple agents"
  - "Total coordination time under 90 seconds"

agents:
  calendar:
    prompt_template: |
      MEETING PREP — RESOLVE: Find today's next upcoming meeting matching '{meeting_identifier}'.

      Get today's calendar events. Find the NEXT event (soonest upcoming, not past) where
      the title or description contains words from '{meeting_identifier}'.

      Return EXACTLY this format (one field per line):
      TITLE: <exact calendar event title>
      TIME: <e.g., "2:00 PM">
      DATE: <e.g., "Feb 27, 2026">
      PARTICIPANTS: <comma-separated full names>
      EMAILS: <comma-separated email addresses from attendees>
      LINK: <video conference URL or "none">
      DESCRIPTION: <first 200 chars of event description, or "none">

      If NO upcoming meeting matches, return exactly: NO_MATCH

      Write your response to your coordination block:
      memory("insert", path="/memories/{gathered_label}", insert_line=0,
        insert_text="[Calendar HH:MM] <your structured response above>")
    timeout_seconds: 30
    expected_contribution: "Structured meeting data: title, time, participants with emails"

  document:
    enabled: true
    prompt_template: |
      MEETING PREP — GATHER: Find documents and past meetings related to '{resolved_title}'
      with participants: {resolved_participants}
      Participant emails: {resolved_emails}
      Meeting time: {resolved_time} {resolved_date}

      Search strategy — try ALL of these and report what you did:
      1. search_documents for each participant name (e.g., search for "{participant_first_names}")
      2. search_documents for meeting topic keywords from the title
      3. search_documents for "Briefing" combined with participant or organization names
      4. query_granola_meetings for past meetings with these participants
      5. Look for recently modified documents mentioning any participant

      IMPORTANT: Report your search strategy. For EACH search, note what tool you used,
      what terms you searched, and how many results you got.

      Write findings AND strategy to your coordination block:
      memory("insert", path="/memories/{gathered_label}", insert_line=0,
        insert_text="[Document HH:MM] STRATEGY: <list each search: tool, terms, result count> | FINDINGS: <what you found>")

      If no results from any search, still write your strategy so it can be improved.
    timeout_seconds: 60
    expected_contribution: "Relevant docs, transcripts, agendas, action items, with search strategy report"

  email:
    prompt_template: |
      MEETING PREP — GATHER: Search for email threads related to '{resolved_title}'
      with participants: {resolved_participants}
      Participant emails: {resolved_emails}

      Search strategy — try these approaches:
      1. Search by participant email addresses: from:{resolved_emails} or to:{resolved_emails} in last 14 days
      2. Search by meeting title keywords
      3. Search by participant names
      4. Search by organization or topic keywords from the meeting title

      IMPORTANT: Report your search strategy. For EACH search, note what terms you used
      and how many results you got.

      Write findings AND strategy to your coordination block:
      memory("insert", path="/memories/{gathered_label}", insert_line=0,
        insert_text="[Email HH:MM] STRATEGY: <list each search: terms, result count> | FINDINGS: <what you found>")

      If no results, still write your strategy so it can be improved.
    timeout_seconds: 120
    expected_contribution: "Recent email threads with participants, with search strategy report"

  pulse:
    enabled: true
    prompt_template: |
      MEETING PREP — GATHER: Search Slack for context related to '{resolved_title}'
      with participants: {resolved_participants}

      Search strategy — try these approaches (use INDIVIDUAL TERMS, never exact phrases):
      1. Search for each participant's first name separately
      2. Search for each participant's last name separately
      3. Search for organization or topic keywords from the meeting title
      4. Search for project names or keywords that relate to the meeting

      DO NOT use quoted exact phrases like "John Smith meeting" — search for individual
      words: "John", "Smith", topic keywords.

      IMPORTANT: Report your search strategy. For EACH search, note what terms you used
      and how many results you got.

      Write findings AND strategy to your coordination block:
      memory("insert", path="/memories/{gathered_label}", insert_line=0,
        insert_text="[Pulse HH:MM] STRATEGY: <list each search: terms, result count> | FINDINGS: <what you found>")

      If no results, still write your strategy so it can be improved.
    timeout_seconds: 45
    expected_contribution: "Slack context with search strategy report"

synthesis:
  mode: main_agent
  evaluation_prompt: |
    MEETING PREP EVALUATION for '{resolved_title}' with {resolved_participants} at {resolved_time}.

    Round 1 results from specialist agents (each includes their search strategy):

    CALENDAR:
    {calendar_findings}

    DOCUMENTS:
    {document_findings}

    EMAIL:
    {email_findings}

    PULSE (Slack):
    {pulse_findings}

    Your job: evaluate each agent's search strategy and results.

    For each agent, consider:
    - Did they search with the right terms? Were searches too narrow or too broad?
    - Did they use participant names and email addresses effectively?
    - Are there leads from one agent's results that another should pursue?
      (e.g., an org name from a transcript, a doc title mentioned in email, a project name from Slack)
    - Would different search terms or a different tool yield better results?

    For each agent that should search again, call:
      request_agent_followup(agent_name="<agent>", followup_prompt="<specific instructions>")

    Be specific in your followup_prompt: what terms to search, what tools to use, what to look for.

    If all searches were adequate and you don't expect better results, respond with just:
    NO_FOLLOWUPS
  synthesis_prompt: |
    MEETING PREP SYNTHESIS for '{resolved_title}' at {resolved_time} {resolved_date}.
    Participants: {resolved_participants}

    All gathered information (Round 1 + Round 2 combined):

    {all_findings}

    Produce a concise meeting prep brief covering:
    - Meeting basics (time, participants, video link)
    - Key context from past meetings and conversations
    - Relevant documents and their significance
    - Action items or open threads from prior interactions
    - Suggested preparation priorities
    - Questions to consider raising

    Be concise — this is a prep brief, not a research paper. Use bullet points.

metrics:
  - agent_contribution_rate
  - follow_up_questions_needed
  - time_to_completion
  - synthesis_length
  - round_2_dispatches

refinement_log:
  - date: 2026-02-27
    changes:
      - "v2: Calendar-first serial resolution before other agents"
      - "v2: All prompts use canonical memory() tool syntax with insert_line=0"
      - "v2: Agents report search strategy alongside findings"
      - "v2: Main agent evaluates Round 1 and directs Round 2 follow-ups"
      - "v2: Synthesis via main agent instead of template"
      - "v2: Resolved context (title, participants, emails) injected into Phase 1 prompts"
    rationale: "v1 dispatched all agents in parallel from vague user input. Agents guessed at names, searched poorly, and had no feedback loop. v2 resolves the meeting first, then iterates."
```

**Step 2: Verify YAML parses correctly**

Run:
```bash
cd pa-routing-handler && poetry run python -c "
from pa_routing.services.task_type_loader import TaskTypeLoader
loader = TaskTypeLoader('../docs/task-types')
tt = loader.load('meeting_prep')
print(f'Name: {tt.name}, Version: {tt.version}')
print(f'Resolve agent: {tt.resolve_agent}')
print(f'Gather agents: {list(tt.get_gather_agents().keys())}')
print(f'Has evaluation prompt: {tt.synthesis.evaluation_prompt is not None}')
print(f'Has synthesis prompt: {tt.synthesis.synthesis_prompt is not None}')
"
```
Expected:
```
Name: meeting_prep, Version: 2.0.0
Resolve agent: calendar
Gather agents: ['document', 'email', 'pulse']
Has evaluation prompt: True
Has synthesis prompt: True
```

**Step 3: Commit**

```bash
git add docs/task-types/meeting_prep.yaml
git commit -m "feat(coordination): rewrite meeting_prep.yaml for v2 calendar-first with evaluation"
```

---

## Task 4: Refactor Orchestrator — Calendar-First Resolution (Phase 0)

Refactor the `coordinate` method to run the resolve agent (calendar) first as a serial step, parse the structured meeting data, and handle NO_MATCH.

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`
- Modify: `pa-routing-handler/tests/services/test_coordination_orchestrator.py`

**Step 1: Write tests for Phase 0 parsing**

Add to `tests/services/test_coordination_orchestrator.py`:

```python
class TestCalendarResolution:
    """Tests for Phase 0 calendar resolution parsing."""

    @pytest.fixture
    def orchestrator(self):
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator
        return CoordinationOrchestrator(
            task_type_loader=MagicMock(),
            coordination_handler=MagicMock(),
            coordination_logger=MagicMock(),
            letta_base_url="http://localhost:8283"
        )

    def test_parse_calendar_response_structured(self, orchestrator):
        """Parses structured calendar response into dict."""
        text = """[Calendar 14:30] TITLE: Becca / Concord check-in
TIME: 2:00 PM
DATE: Feb 27, 2026
PARTICIPANTS: Becca Novak, Chad Dorsey
EMAILS: bnovak@valhalla.org, chad@example.com
LINK: https://zoom.us/j/123
DESCRIPTION: Monthly stewardship check-in"""

        result = orchestrator._parse_calendar_response(text)

        assert result["title"] == "Becca / Concord check-in"
        assert result["time"] == "2:00 PM"
        assert result["date"] == "Feb 27, 2026"
        assert "Becca Novak" in result["participants"]
        assert "bnovak@valhalla.org" in result["emails"]
        assert result["link"] == "https://zoom.us/j/123"

    def test_parse_calendar_response_no_match(self, orchestrator):
        """Returns None for NO_MATCH response."""
        text = "[Calendar 14:30] NO_MATCH"
        result = orchestrator._parse_calendar_response(text)
        assert result is None

    def test_parse_calendar_response_empty(self, orchestrator):
        """Returns None for empty response."""
        result = orchestrator._parse_calendar_response("")
        assert result is None

    def test_parse_calendar_response_none_link(self, orchestrator):
        """Handles 'none' link value."""
        text = """[Calendar 14:30] TITLE: Team standup
TIME: 9:00 AM
DATE: Feb 27, 2026
PARTICIPANTS: Alice, Bob
EMAILS: alice@co.com, bob@co.com
LINK: none
DESCRIPTION: none"""

        result = orchestrator._parse_calendar_response(text)
        assert result["link"] is None
        assert result["description"] is None

    def test_extract_first_names(self, orchestrator):
        """Extracts first names from participant list."""
        participants = "Becca Novak, Chad Dorsey, John Smith III"
        result = orchestrator._extract_first_names(participants)
        assert result == "Becca, Chad, John"
```

**Step 2: Run test to verify it fails**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_coordination_orchestrator.py::TestCalendarResolution -v`
Expected: FAIL — `_parse_calendar_response` and `_extract_first_names` don't exist

**Step 3: Implement Phase 0 parsing methods**

Add to `CoordinationOrchestrator`:

```python
import re

def _parse_calendar_response(self, text: str) -> Optional[Dict[str, str]]:
    """Parse structured calendar response from Phase 0.

    Expected format (from calendar agent's block or assistant message):
    [Calendar HH:MM] TITLE: ...
    TIME: ...
    PARTICIPANTS: ...
    etc.

    Returns:
        Dict with keys: title, time, date, participants, emails, link, description.
        None if NO_MATCH or unparseable.
    """
    if not text or "NO_MATCH" in text:
        return None

    fields = {}
    field_pattern = re.compile(r"^(TITLE|TIME|DATE|PARTICIPANTS|EMAILS|LINK|DESCRIPTION):\s*(.+)$", re.MULTILINE)

    for match in field_pattern.finditer(text):
        key = match.group(1).lower()
        value = match.group(2).strip()
        if value.lower() == "none":
            value = None
        fields[key] = value

    if "title" not in fields:
        return None

    return fields

def _extract_first_names(self, participants: str) -> str:
    """Extract first names from comma-separated participant list.

    Args:
        participants: e.g., "Becca Novak, Chad Dorsey, John Smith III"

    Returns:
        Comma-separated first names: "Becca, Chad, John"
    """
    names = [name.strip().split()[0] for name in participants.split(",") if name.strip()]
    return ", ".join(names)
```

**Step 4: Run test to verify it passes**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_coordination_orchestrator.py::TestCalendarResolution -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py pa-routing-handler/tests/services/test_coordination_orchestrator.py
git commit -m "feat(coordination): add Phase 0 calendar response parser"
```

---

## Task 5: Refactor Orchestrator — Phased Coordinate Method

Replace the single-phase `coordinate` method with the full phased flow: Resolve → Gather → Evaluate → Refine → Synthesize.

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`
- Modify: `pa-routing-handler/tests/services/test_coordination_orchestrator.py`

**Step 1: Write integration-style test for the full phased flow**

Add to `tests/services/test_coordination_orchestrator.py`:

```python
class TestPhasedCoordination:
    """Tests for the full phased coordination flow."""

    @pytest.fixture
    def v2_task_type(self):
        """Create v2 task type with resolve_agent and evaluation prompts."""
        from pa_routing.services.task_type_loader import AgentConfig, SynthesisConfig, TaskType

        return TaskType(
            name="meeting_prep",
            version="2.0.0",
            lifecycle_stage="active",
            goal="Gather meeting context",
            resolve_agent="calendar",
            agents={
                "calendar": AgentConfig(
                    name="calendar",
                    prompt_template="Find meeting {meeting_identifier}",
                    timeout_seconds=30
                ),
                "document": AgentConfig(
                    name="document",
                    prompt_template="Find docs for {resolved_title} with {resolved_participants}",
                    timeout_seconds=60
                ),
                "email": AgentConfig(
                    name="email",
                    prompt_template="Find emails for {resolved_title}",
                    timeout_seconds=120
                ),
            },
            synthesis=SynthesisConfig(
                mode="main_agent",
                evaluation_prompt="Evaluate: {calendar_findings}\n{document_findings}\n{email_findings}",
                synthesis_prompt="Synthesize: {all_findings}",
            )
        )

    @pytest.fixture
    def mock_deps(self):
        handler = MagicMock()
        handler.start_coordinated_task = AsyncMock(return_value="task-123")
        handler.check_agent_contribution = AsyncMock(return_value=True)
        handler.get_gathered_findings = AsyncMock(return_value={
            "document": "STRATEGY: searched 'Becca' | FINDINGS: Found briefing doc",
            "email": "STRATEGY: searched from:bnovak | FINDINGS: 2 threads",
        })
        handler.complete_task = AsyncMock(return_value=True)
        return {
            "task_type_loader": MagicMock(),
            "coordination_handler": handler,
            "coordination_logger": MagicMock(),
            "letta_base_url": "http://localhost:8283"
        }

    @pytest.mark.asyncio
    async def test_phased_flow_runs_calendar_first(self, mock_deps, v2_task_type):
        """Phase 0 dispatches calendar before other agents."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_deps["task_type_loader"].load.return_value = v2_task_type
        orchestrator = CoordinationOrchestrator(**mock_deps)

        dispatch_order = []

        async def track_dispatch(agent_name, **kwargs):
            dispatch_order.append(agent_name)
            return {"status": "success"}

        # Mock calendar block to return structured data
        mock_deps["coordination_handler"].get_block_from_agent = AsyncMock(
            return_value={"value": "[Calendar 14:00] TITLE: Becca check-in\nTIME: 2:00 PM\nDATE: Feb 27\nPARTICIPANTS: Becca Novak\nEMAILS: b@v.org\nLINK: none\nDESCRIPTION: none"}
        )

        # Mock main agent synthesis response
        with patch.object(orchestrator, '_dispatch_to_agent', side_effect=track_dispatch):
            with patch.object(orchestrator, '_send_to_letta', new_callable=AsyncMock, return_value="Meeting prep complete"):
                request = CoordinateRequest(
                    identity_id="id-123",
                    task_type="meeting_prep",
                    context={"meeting_identifier": "Becca check-in"}
                )
                await orchestrator.coordinate(request)

        # Calendar should be dispatched before document and email
        assert dispatch_order[0] == "calendar"

    @pytest.mark.asyncio
    async def test_no_match_returns_error(self, mock_deps, v2_task_type):
        """NO_MATCH from calendar returns error to user."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_deps["task_type_loader"].load.return_value = v2_task_type
        orchestrator = CoordinationOrchestrator(**mock_deps)

        # Calendar block returns NO_MATCH
        mock_deps["coordination_handler"].get_block_from_agent = AsyncMock(
            return_value={"value": "[Calendar 14:00] NO_MATCH"}
        )

        with patch.object(orchestrator, '_dispatch_to_agent', new_callable=AsyncMock):
            request = CoordinateRequest(
                identity_id="id-123",
                task_type="meeting_prep",
                context={"meeting_identifier": "nonexistent meeting"}
            )
            response = await orchestrator.coordinate(request)

        assert response.status == "error"
        assert "no matching meeting" in response.error_message.lower() or "couldn't find" in response.error_message.lower()
```

**Step 2: Run to verify tests fail**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_coordination_orchestrator.py::TestPhasedCoordination -v`
Expected: FAIL — current `coordinate` doesn't have phased logic

**Step 3: Implement phased coordinate method**

This is the core refactor. Replace the body of `coordinate()` in `coordination_orchestrator.py`. The method should:

1. Load task type (existing)
2. Check if it has `resolve_agent` — if yes, run Phase 0
3. Phase 0: dispatch resolve agent, wait, read block, parse structured response
4. If NO_MATCH: return error immediately
5. Enrich context with resolved fields (`resolved_title`, `resolved_participants`, `resolved_emails`, `resolved_time`, `resolved_date`, `participant_first_names`)
6. Phase 1: dispatch gather agents in parallel (existing `_launch_agent_dispatches`, but only for gather agents)
7. Poll for contributions (existing `_wait_for_contributions`, but only gather agents)
8. Phase 1.5: if task type has `evaluation_prompt`, send findings to main agent, parse `request_agent_followup` tool calls
9. Phase 2: dispatch follow-ups if any
10. Phase 3: if task type synthesis mode is `main_agent`, send all findings to main agent for synthesis
11. Complete task (existing)

Key new methods needed:
- `_run_resolve_phase()` — dispatches resolve agent, waits, reads block, parses
- `_run_evaluation_phase()` — sends to main agent, reads tool calls
- `_run_synthesis_via_main_agent()` — sends to main agent, returns text
- `_parse_followup_tool_calls()` — extracts `request_agent_followup` calls from Letta response

The `_send_to_letta` method already exists and returns assistant_message text. For evaluation, we need to also capture tool calls. Add `_send_to_letta_full()` that returns the full message list.

```python
async def _send_to_letta_full(
    self,
    agent_id: str,
    message: str,
    identity_id: str,
    max_retries: int = 5,
) -> List[Dict[str, Any]]:
    """Send message to Letta agent and return full response messages.

    Unlike _send_to_letta which returns only assistant_message text,
    this returns all response messages including tool calls.
    """
    url = f"{self._letta_url}/v1/agents/{agent_id}/messages"
    payload = {"messages": [{"role": "user", "content": message}]}

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                response = await client.post(url, json=payload)

                if response.status_code == 502:
                    if attempt < max_retries:
                        backoff_seconds = 2 ** attempt
                        logger.warning("letta_502_retry", agent_id=agent_id, attempt=attempt + 1)
                        await asyncio.sleep(backoff_seconds)
                        continue
                    else:
                        raise httpx.HTTPStatusError(
                            f"502 Bad Gateway after {max_retries} retries",
                            request=response.request, response=response,
                        )

                response.raise_for_status()
                return response.json().get("messages", [])

        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code != 502:
                raise
        except Exception as e:
            last_error = e
            raise

    if last_error:
        raise last_error
    return []


def _parse_followup_tool_calls(
    self, messages: List[Dict[str, Any]]
) -> List[Dict[str, str]]:
    """Extract request_agent_followup tool calls from Letta response messages.

    Returns:
        List of dicts with 'agent_name' and 'followup_prompt' keys.
    """
    import json as json_module

    followups = []
    for msg in messages:
        if msg.get("message_type") == "tool_call_message":
            tool_call = msg.get("tool_call", {})
            if tool_call.get("name") == "request_agent_followup":
                try:
                    args = json_module.loads(tool_call.get("arguments", "{}"))
                    followups.append({
                        "agent_name": args.get("agent_name", ""),
                        "followup_prompt": args.get("followup_prompt", ""),
                    })
                except json_module.JSONDecodeError:
                    logger.warning("followup_parse_error", raw=tool_call.get("arguments"))
    return followups
```

For the `_run_resolve_phase` method:

```python
async def _run_resolve_phase(
    self,
    task_type: TaskType,
    task_id: str,
    identity_id: str,
    context: Dict[str, Any],
    agent_ids: Dict[str, str],
) -> Optional[Dict[str, str]]:
    """Phase 0: Dispatch resolve agent, wait, parse structured response.

    Returns:
        Parsed meeting data dict, or None if NO_MATCH or failure.
    """
    resolve_name = task_type.resolve_agent
    resolve_config = task_type.agents.get(resolve_name)
    if not resolve_config or resolve_name not in agent_ids:
        logger.warning("resolve_agent_not_found", agent=resolve_name)
        return None

    agent_id = agent_ids[resolve_name]

    # Build prompt with gathered_label for this agent's block
    resolve_context = {
        **context,
        "identity_id": identity_id,
        "gathered_label": f"coordination_gathered_{identity_id}_{resolve_name}",
    }
    if "meeting_title" not in resolve_context:
        resolve_context["meeting_title"] = resolve_context.get("meeting_identifier", "")
    prompt = self._build_agent_prompt(resolve_config, resolve_context)

    # Dispatch and wait
    self._logger.log_event(
        event_type="phase0_dispatch",
        task_id=task_id,
        identity_id=identity_id,
        task_type=task_type.name,
        data={"agent": resolve_name},
    )

    try:
        assistant_msg = await asyncio.wait_for(
            self._send_to_letta(agent_id, prompt, identity_id),
            timeout=resolve_config.timeout_seconds,
        )
    except (asyncio.TimeoutError, Exception) as e:
        logger.error("resolve_phase_error", agent=resolve_name, error=str(e))
        return None

    # Read from the resolve agent's block
    block_label = f"coordination_gathered_{identity_id}_{resolve_name}"
    block = await self._handler.get_block_from_agent(agent_id, block_label)
    block_text = block.get("value", "") if block else ""

    # Fallback to assistant message if block is empty
    if not block_text.strip() and assistant_msg:
        block_text = assistant_msg

    return self._parse_calendar_response(block_text)
```

For the full phased `coordinate` method, the structure becomes:

```python
async def coordinate(self, request: CoordinateRequest) -> CoordinateResponse:
    # ... existing: load task type, verify executable, get enabled agents, build agent_ids ...
    # ... existing: start_coordinated_task ...

    # --- PHASE 0: RESOLVE (if task type has resolve_agent) ---
    resolved_context = {}
    if task_type.resolve_agent:
        meeting_data = await self._run_resolve_phase(
            task_type, task_id, request.identity_id, enriched_context, agent_ids
        )
        if meeting_data is None:
            # NO_MATCH or parse failure
            await self._handler.complete_task(...)
            return CoordinateResponse(
                status="error", task_id=task_id,
                error_message=f"Couldn't find a matching meeting on your calendar for '{request.context.get('meeting_identifier', '')}'. Can you clarify the meeting name or participants?",
            )

        # Enrich context with resolved data for Phase 1 agents
        resolved_context = {
            "resolved_title": meeting_data.get("title", ""),
            "resolved_time": meeting_data.get("time", ""),
            "resolved_date": meeting_data.get("date", ""),
            "resolved_participants": meeting_data.get("participants", ""),
            "resolved_emails": meeting_data.get("emails", ""),
            "resolved_link": meeting_data.get("link", ""),
            "resolved_description": meeting_data.get("description", ""),
            "participant_first_names": self._extract_first_names(meeting_data.get("participants", "")),
        }

    # --- PHASE 1: GATHER (parallel, gather agents only) ---
    gather_context = {**enriched_context, **resolved_context}
    gather_agents = task_type.get_gather_agents() if task_type.resolve_agent else task_type.get_enabled_agents()

    # Launch gather dispatches (same parallel mechanism, but only gather agents)
    dispatch_tasks = self._launch_agent_dispatches(
        task_id=task_id, identity_id=request.identity_id,
        task_type=task_type, context=gather_context,
        agents_override=gather_agents,
    )

    # Poll for contributions from gather agents only
    findings = await self._wait_for_contributions(
        identity_id=request.identity_id, task_type=task_type,
        task_id=task_id, agent_ids=agent_ids,
        agents_override=gather_agents,
    )

    # Cancel still-running dispatches
    for task in dispatch_tasks:
        if not task.done():
            task.cancel()

    # Include calendar findings from Phase 0
    if task_type.resolve_agent:
        resolve_name = task_type.resolve_agent
        resolve_id = agent_ids.get(resolve_name)
        if resolve_id:
            block_label = f"coordination_gathered_{request.identity_id}_{resolve_name}"
            block = await self._handler.get_block_from_agent(resolve_id, block_label)
            if block and block.get("value", "").strip():
                findings[resolve_name] = block.get("value", "").strip()

    # --- PHASE 1.5: EVALUATE (if main_agent synthesis mode) ---
    followups = []
    if task_type.synthesis.mode == "main_agent" and task_type.synthesis.evaluation_prompt:
        followups = await self._run_evaluation_phase(
            task_type, task_id, request.identity_id,
            findings, {**gather_context, **resolved_context},
        )

    # --- PHASE 2: REFINE (selective, if main agent requested follow-ups) ---
    if followups:
        round2_findings = await self._run_refinement_phase(
            task_type, task_id, request.identity_id,
            followups, agent_ids, gather_context,
        )
        # Merge Round 2 findings (append to Round 1)
        for agent_name, new_finding in round2_findings.items():
            if agent_name in findings:
                findings[agent_name] += "\n\n[Round 2] " + new_finding
            else:
                findings[agent_name] = "[Round 2] " + new_finding

    # --- PHASE 3: SYNTHESIZE ---
    if task_type.synthesis.mode == "main_agent" and task_type.synthesis.synthesis_prompt:
        synthesis = await self._run_synthesis_phase(
            task_type, findings, {**gather_context, **resolved_context},
        )
    else:
        synthesis = await self._synthesize(task_type, findings, gather_context)

    # ... existing: complete_task, log, return response ...
```

**Implementation note:** `_launch_agent_dispatches` and `_wait_for_contributions` need an `agents_override` parameter to dispatch only gather agents instead of all enabled agents.

**Step 4: Run all orchestrator tests**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_coordination_orchestrator.py -v`
Expected: All tests PASS (existing tests may need minor fixture updates for the new `resolve_agent` field default)

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py pa-routing-handler/tests/services/test_coordination_orchestrator.py
git commit -m "feat(coordination): implement phased coordination — resolve, gather, evaluate, refine, synthesize"
```

---

## Task 6: Add Evaluation and Synthesis Phases

Implement `_run_evaluation_phase` and `_run_synthesis_phase` methods that send findings to the main agent.

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`
- Modify: `pa-routing-handler/tests/services/test_coordination_orchestrator.py`

**Step 1: Write tests**

```python
class TestEvaluationPhase:
    """Tests for Phase 1.5 evaluation."""

    @pytest.fixture
    def orchestrator(self):
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator
        return CoordinationOrchestrator(
            task_type_loader=MagicMock(),
            coordination_handler=MagicMock(),
            coordination_logger=MagicMock(),
            letta_base_url="http://localhost:8283"
        )

    def test_parse_followup_tool_calls(self, orchestrator):
        """Extracts followup requests from Letta response messages."""
        messages = [
            {"message_type": "tool_call_message", "tool_call": {
                "name": "request_agent_followup",
                "arguments": '{"agent_name": "pulse", "followup_prompt": "Search for Becca Novak separately"}'
            }},
            {"message_type": "tool_return_message", "tool_return": "ok"},
            {"message_type": "tool_call_message", "tool_call": {
                "name": "request_agent_followup",
                "arguments": '{"agent_name": "email", "followup_prompt": "Search from:bnovak@valhalla.org"}'
            }},
            {"message_type": "tool_return_message", "tool_return": "ok"},
            {"message_type": "assistant_message", "content": "Follow-ups dispatched"},
        ]

        followups = orchestrator._parse_followup_tool_calls(messages)
        assert len(followups) == 2
        assert followups[0]["agent_name"] == "pulse"
        assert "Becca Novak" in followups[0]["followup_prompt"]
        assert followups[1]["agent_name"] == "email"

    def test_parse_no_followups(self, orchestrator):
        """Returns empty list when main agent says NO_FOLLOWUPS."""
        messages = [
            {"message_type": "assistant_message", "content": "NO_FOLLOWUPS"},
        ]
        followups = orchestrator._parse_followup_tool_calls(messages)
        assert len(followups) == 0

    def test_parse_ignores_non_followup_tool_calls(self, orchestrator):
        """Ignores tool calls that aren't request_agent_followup."""
        messages = [
            {"message_type": "tool_call_message", "tool_call": {
                "name": "memory",
                "arguments": '{"command": "insert"}'
            }},
            {"message_type": "assistant_message", "content": "Done"},
        ]
        followups = orchestrator._parse_followup_tool_calls(messages)
        assert len(followups) == 0
```

**Step 2: Run, verify fails**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_coordination_orchestrator.py::TestEvaluationPhase -v`

**Step 3: Implement evaluation and synthesis methods**

```python
async def _run_evaluation_phase(
    self,
    task_type: TaskType,
    task_id: str,
    identity_id: str,
    findings: Dict[str, str],
    context: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Phase 1.5: Send findings to main agent for evaluation.

    Main agent evaluates search strategies and calls request_agent_followup
    for agents that should search again.

    Returns:
        List of followup dicts: [{"agent_name": ..., "followup_prompt": ...}]
    """
    prompt_template = task_type.synthesis.evaluation_prompt
    if not prompt_template:
        return []

    # Build evaluation prompt with findings
    prompt = prompt_template
    for key, value in context.items():
        prompt = prompt.replace("{" + key + "}", str(value))
    for agent_name, finding in findings.items():
        prompt = prompt.replace("{" + agent_name + "_findings}", finding)
    # Replace any remaining {xxx_findings} with "No data collected"
    prompt = re.sub(r"\{(\w+)_findings\}", "No data collected", prompt)

    self._logger.log_event(
        event_type="phase_evaluate",
        task_id=task_id,
        identity_id=identity_id,
        task_type=task_type.name,
        data={"findings_agents": list(findings.keys())},
    )

    try:
        messages = await asyncio.wait_for(
            self._send_to_letta_full(MAIN_AGENT_ID, prompt, identity_id),
            timeout=60,
        )
        followups = self._parse_followup_tool_calls(messages)

        self._logger.log_event(
            event_type="phase_evaluate_complete",
            task_id=task_id,
            identity_id=identity_id,
            task_type=task_type.name,
            data={"followup_count": len(followups), "followup_agents": [f["agent_name"] for f in followups]},
        )

        return followups

    except Exception as e:
        logger.error("evaluation_phase_error", error=str(e))
        return []


async def _run_refinement_phase(
    self,
    task_type: TaskType,
    task_id: str,
    identity_id: str,
    followups: List[Dict[str, str]],
    agent_ids: Dict[str, str],
    context: Dict[str, Any],
) -> Dict[str, str]:
    """Phase 2: Dispatch follow-up searches directed by main agent.

    Returns:
        Dict mapping agent_name to their Round 2 findings.
    """
    self._logger.log_event(
        event_type="phase_refine",
        task_id=task_id,
        identity_id=identity_id,
        task_type=task_type.name,
        data={"followups": [f["agent_name"] for f in followups]},
    )

    round2_findings = {}

    async def dispatch_followup(agent_name: str, prompt: str):
        agent_id = agent_ids.get(agent_name)
        if not agent_id:
            return

        # Prepend gathered_label context so agent can write to its block
        gathered_label = f"coordination_gathered_{identity_id}_{agent_name}"
        full_prompt = f"""MEETING PREP — FOLLOW-UP SEARCH (Round 2)

{prompt}

Write your additional findings to your coordination block:
memory("insert", path="/memories/{gathered_label}", insert_line=0,
  insert_text="[{agent_name.title()} HH:MM] ROUND 2: <your findings>")
"""
        try:
            assistant_msg = await asyncio.wait_for(
                self._send_to_letta(agent_id, full_prompt, identity_id),
                timeout=45,
            )
            # Read from block
            block = await self._handler.get_block_from_agent(agent_id, gathered_label)
            block_text = block.get("value", "") if block else ""
            # Look for Round 2 content
            if "ROUND 2:" in block_text:
                round2_findings[agent_name] = block_text.split("ROUND 2:", 1)[1].strip()
            elif assistant_msg:
                round2_findings[agent_name] = assistant_msg
        except Exception as e:
            logger.warning("followup_dispatch_error", agent=agent_name, error=str(e))

    # Dispatch all follow-ups in parallel
    tasks = [
        asyncio.create_task(dispatch_followup(f["agent_name"], f["followup_prompt"]))
        for f in followups
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    return round2_findings


async def _run_synthesis_phase(
    self,
    task_type: TaskType,
    findings: Dict[str, str],
    context: Dict[str, Any],
) -> str:
    """Phase 3: Send all findings to main agent for synthesis.

    Returns:
        Synthesized meeting prep brief.
    """
    prompt_template = task_type.synthesis.synthesis_prompt
    if not prompt_template:
        return "\n\n".join(findings.values())

    # Build all_findings block
    all_findings_parts = []
    for agent_name, finding in findings.items():
        all_findings_parts.append(f"--- {agent_name.upper()} ---\n{finding}")
    all_findings = "\n\n".join(all_findings_parts)

    prompt = prompt_template.replace("{all_findings}", all_findings)
    for key, value in context.items():
        prompt = prompt.replace("{" + key + "}", str(value))

    try:
        result = await asyncio.wait_for(
            self._send_to_letta(MAIN_AGENT_ID, prompt, ""),
            timeout=60,
        )
        return result or "\n\n".join(findings.values())
    except Exception as e:
        logger.error("synthesis_phase_error", error=str(e))
        return "\n\n".join(findings.values())
```

**Step 4: Run tests**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_coordination_orchestrator.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py pa-routing-handler/tests/services/test_coordination_orchestrator.py
git commit -m "feat(coordination): add evaluation, refinement, and synthesis phases"
```

---

## Task 7: Update _launch_agent_dispatches and _wait_for_contributions for agents_override

Add `agents_override` parameter so these methods can target only gather agents.

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

**Step 1: Add agents_override parameter**

In `_launch_agent_dispatches`, add `agents_override: Optional[Dict[str, AgentConfig]] = None` parameter. If provided, use it instead of `task_type.get_enabled_agents()`.

In `_wait_for_contributions`, add `agents_override: Optional[Dict[str, AgentConfig]] = None` parameter. If provided, use it instead of `task_type.get_enabled_agents()`.

This is a minimal change — just replace the `enabled_agents` variable source at the top of each method.

**Step 2: Run existing tests to verify no regressions**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_coordination_orchestrator.py -v`
Expected: All PASS (default None means existing behavior unchanged)

**Step 3: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py
git commit -m "refactor(coordination): add agents_override param to dispatch and polling methods"
```

---

## Task 8: Add Assistant-Message Fallback to Block Reading

If an agent's block is empty after dispatch (tool call failed), capture findings from the Letta assistant_message response instead.

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

**Step 1: Capture assistant message from dispatch**

In `_dispatch_to_agent`, capture and return the assistant_message text from `_send_to_letta`:

```python
async def _dispatch_to_agent(self, agent_name, prompt, identity_id, task_id, task_type, timeout):
    # ... existing code ...
    try:
        assistant_msg = await asyncio.wait_for(
            self._send_to_letta(agent_id, prompt, identity_id),
            timeout=timeout,
        )
        return {"status": "success", "assistant_message": assistant_msg}
    # ... existing error handling ...
```

In the gather phase of `coordinate`, after collecting block-based findings, check for agents with empty blocks and fill from assistant_message responses stored during dispatch.

Store dispatch results in a dict keyed by agent name, then after `get_gathered_findings`, for any agent not in findings, check if the dispatch result has an `assistant_message`.

**Step 2: Run tests**

Run: `cd pa-routing-handler && poetry run pytest tests/services/test_coordination_orchestrator.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py
git commit -m "feat(coordination): add assistant-message fallback when agent block is empty"
```

---

## Task 9: Build, Deploy, and Smoke Test

Rebuild the pa-routing-handler container and run an end-to-end test.

**Step 1: Register the followup tool**

```bash
cd /Volumes/main-drive/ai-PA
LETTA_BASE_URL=http://localhost:8283 python letta/register_followup_tool.py
```

**Step 2: Rebuild and restart pa-routing-handler**

```bash
docker-compose up -d --build pa-routing-handler
docker-compose logs -f pa-routing-handler --tail=20
```

Wait for healthy startup.

**Step 3: Smoke test via pa-web-ui**

Navigate to web UI. Type:
```
/mprep Becca / Concord check-in
```

Expected flow:
1. Calendar resolves the meeting → structured data with "Becca Novak", emails
2. Docs/Email/Pulse receive resolved context in parallel
3. Main agent evaluates Round 1, may request follow-ups
4. Synthesis includes real participant names and multi-source information

**Step 4: Check coordination logs**

```bash
docker-compose logs pa-routing-handler --tail=100 | grep -E "phase|dispatch|evaluate|synthesis|resolve"
```

Verify the phase sequence: phase0_dispatch → phase_evaluate → phase_refine (maybe) → synthesis

**Step 5: Commit any fixes**

If smoke test reveals issues, fix and commit incrementally.

**Step 6: Final commit with all uncommitted coordination changes**

```bash
git add -A
git status  # Verify only expected files
git commit -m "feat(coordination): v2 calendar-first with iterative refinement — complete"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `pa-routing-handler/src/pa_routing/services/task_type_loader.py` | Add `resolve_agent`, `get_gather_agents()`, `evaluation_prompt`, `synthesis_prompt` |
| `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py` | Phased coordinate: resolve → gather → evaluate → refine → synthesize. Calendar parsing. Followup tool call extraction. Assistant-message fallback. |
| `pa-routing-handler/tests/services/test_coordination_orchestrator.py` | Tests for calendar parsing, phased flow, evaluation parsing |
| `pa-routing-handler/tests/services/test_task_type_loader.py` | Tests for resolve_agent, gather_agents, new synthesis fields |
| `docs/task-types/meeting_prep.yaml` | v2 prompts: constrained calendar, strategy reporting, memory() syntax, evaluation + synthesis prompts |
| `letta/tools/request_agent_followup.py` | New tool for main agent evaluation |
| `letta/register_followup_tool.py` | Registration script |
