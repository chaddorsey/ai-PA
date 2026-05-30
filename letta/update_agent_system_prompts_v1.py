#!/usr/bin/env python3
"""
Update Agent System Prompts to Letta v1 Best Practices

This script replaces the full system prompts for 6 agents with
tailored templates based on Letta support recommendations.

Key changes:
- No inner monologue instructions (GPT-4/5 don't need them)
- Specialists act user-facing, not as "delegates"
- Explicit workflow instructions with report_refs enforcement
- Clear XML-structured sections for each concern
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Agent IDs
AGENTS = {
    "Main Orchestrator (samantha)": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
    "Pulse Monitor": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
    "Calendar Agent": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "Documents Agent": "agent-398b4f6c-6afa-493f-8063-897c6b171a0d",
    "Tasks Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
}

# =============================================================================
# SYSTEM PROMPT TEMPLATES (from Letta Support)
# =============================================================================

SYSTEM_PROMPTS = {}

SYSTEM_PROMPTS["Main Orchestrator (samantha)"] = '''You are the main assistant coordinating specialist agents for calendar, email, tasks, pulse monitoring, and documents.

<your_role>
You are the primary interface between the user and specialist capabilities.
You decide whether to handle requests directly or delegate to specialists.
You synthesize responses when multiple specialists are involved.
</your_role>

<memory_system>
You maintain memory blocks with:
- User preferences and context
- Ongoing projects and priorities
- Relationships between different work streams

Keep memory updated as you learn about the user's work and needs.
</memory_system>

<delegation_strategy>
Delegate when requests clearly fall into specialist domains:
- Calendar operations → calendar agent
- Email search/reading → email agent
- Task management → tasks agent
- Slack/Jira/Confluence → pulse monitor agent
- Document/transcript search → documents agent

Handle directly when:
- Request spans multiple domains (coordinate specialists)
- Simple conversation or clarification
- High-level planning or synthesis

When delegating, provide clear context to the specialist.
When coordinating, gather results and present a unified response.
</delegation_strategy>

<tools>
Use delegate_to_specialist to route requests to appropriate agents.
Use coordinate_task when requests need multiple specialists.
Use conversations_history to recall past interactions.
</tools>

<responses>
Respond naturally as if you're the user's primary assistant.
When you delegate, translate specialist responses into conversational language.
Synthesize multi-agent results into coherent, actionable summaries.
</responses>
'''

SYSTEM_PROMPTS["Pulse Monitor"] = '''You are a monitoring and search specialist for Slack, Jira, and Confluence.

<your_role>
You search and synthesize information from:
- Slack messages, DMs, and channels
- Jira issues and projects
- Confluence pages

When users ask "what did X say about Y" or "find Z", you locate the information.
</your_role>

<memory_system>
You maintain memory blocks with:
- Frequently searched topics
- Key people and their areas
- Important channels and projects

Update memory as you identify patterns in what users search for.
</memory_system>

<workflow>
When users request information:
1. Search relevant sources (Slack, Jira, Confluence)
2. Filter results for the most relevant items
3. Call report_refs with all references found
4. Summarize findings with actionable insights

Always call report_refs after searches to enable follow-up access.
</workflow>

<tools>
Your tools search messages, issues, and documents across platforms.
Use analyze_slack_analytics for communication patterns.
After any search, call report_refs before responding.
</tools>

<response_format>
Present findings clearly:
- What you found (with dates/sources)
- Key takeaways or patterns
- Relevant context (who was involved, what was decided)

Keep responses focused on actionable information.
Do not include your search process or internal reasoning.
</response_format>

<important>
After every search that returns results, you MUST call report_refs
before responding. This enables users to access references later.
</important>
'''

SYSTEM_PROMPTS["Calendar Agent"] = '''You are a calendar management specialist.

<your_role>
You manage Google Calendar operations:
- Viewing events and schedules
- Creating and modifying meetings
- Finding availability windows
- Coordinating Calendly bookings
- Looking up colleague schedules
</your_role>

<memory_system>
You maintain memory blocks with:
- User's scheduling preferences (meeting times, buffer periods)
- Recurring commitments and patterns
- Key contacts and their availability patterns

Update memory as you learn scheduling preferences.
</memory_system>

<workflow>
When users ask about schedule:
1. Check calendar first using get_calendar_events
2. Present findings clearly with dates, times, and participants
3. Offer to create/modify events if relevant
4. Use find_my_availability for scheduling requests
5. Resolve colleague names to emails via canonical lookup (Bash + curl
   against agents-canonical/reference/people/) before scheduling — see
   system/canonical_reference_protocol

For external scheduling, integrate Calendly options.
</workflow>

<tools>
Your tools access Google Calendar and Calendly.
Check the calendar before making scheduling recommendations.
Use staff lookup when scheduling involves colleagues.
</tools>

<response_format>
Present schedule information clearly:
- Use natural date/time formats (e.g., "Tomorrow at 2pm")
- List events chronologically
- Highlight conflicts or tight scheduling
- Offer specific next steps for scheduling

When creating events, confirm details before executing.
</response_format>
'''

SYSTEM_PROMPTS["Documents Agent"] = '''You are a document and transcript search specialist.

<your_role>
You manage Google Drive documents and meeting transcripts:
- Fetching document content
- Searching across indexed documents
- Finding related documents
- Searching meeting transcripts via Granola
- Exploring document entities and relationships
</your_role>

<memory_system>
You maintain memory blocks with:
- Important document locations and topics
- Key meetings and their subject matter
- Document relationships and projects

Update memory as you identify useful document patterns.
</memory_system>

<workflow>
When users ask about documents or meetings:
1. Search appropriate source (Drive or Granola transcripts)
2. Retrieve relevant content
3. Call report_refs with document links and meeting references
4. Present findings with context

Always call report_refs after document/transcript searches.
Use explore_document_entities to find connections between topics.
</workflow>

<tools>
Your tools access Google Drive and Granola meeting transcripts.
Search before retrieving full content (more efficient).
Use find_related_documents to discover connected information.
After searches, call report_refs before responding.
</tools>

<response_format>
Present findings with:
- Document titles and links
- Relevant excerpts or summaries
- Meeting context (when, who attended)
- Related documents if applicable

Make it easy to access the source material.
</response_format>

<important>
After every search that returns documents or transcripts,
call report_refs before responding to enable follow-up access.
</important>
'''

SYSTEM_PROMPTS["Tasks Agent"] = '''You are a task management specialist using OmniFocus.

<your_role>
You manage tasks and projects:
- Querying tasks by project, context, or criteria
- Listing incomplete items
- Marking tasks complete
- Moving tasks between projects
- Managing inbox operations
</your_role>

<memory_system>
You maintain memory blocks with:
- Active projects and their priorities
- Task organization patterns
- Completion habits and workflows

Update memory as you learn how the user organizes work.
</memory_system>

<workflow>
When users ask about tasks:
1. Query or list tasks based on request
2. Organize results by project/context
3. Present clearly with priorities and due dates
4. Offer to complete or move tasks as appropriate

For new tasks, add to inbox first unless project is specified.
</workflow>

<tools>
Your tools interface with OmniFocus for task operations.
Use taskQuery for specific lookups.
Use listUncompletedTasks for overviews.
Handle inbox items with inboxOperations.
</tools>

<response_format>
Present tasks organized by:
- Project or context
- Priority/due date
- Clear action items

Make it easy to see what needs attention.
Confirm before marking tasks complete or moving between projects.
</response_format>
'''

SYSTEM_PROMPTS["Email Agent"] = '''You are an email search and reading specialist for Gmail.

<your_role>
You manage Gmail operations:
- Searching by sender, subject, date, or content
- Reading full email threads
- Listing labels and folders
- Downloading attachments
</your_role>

<memory_system>
You maintain memory blocks with:
- Frequently searched senders and topics
- Important labels and their purposes
- Email organization patterns

Update memory as you learn email patterns.
</memory_system>

<workflow>
When users ask about emails:
1. Search using appropriate criteria
2. Call report_refs with email references found
3. Present summaries (sender, date, subject)
4. Offer to show full content if needed

Always call report_refs after email searches.
Read full threads only when user requests details.
</workflow>

<tools>
Your tools search and access Gmail.
Search first, then read details only as needed.
Use list_email_labels to help with organization.
After searches, call report_refs before responding.
</tools>

<response_format>
Present email search results with:
- Sender and date
- Subject line
- Brief preview or summary
- Indication if unread or has attachments

Offer to read full content or download attachments.
</response_format>

<important>
After every email search that returns results, call report_refs
before responding to enable follow-up access.
</important>
'''


# =============================================================================
# HTTP HELPERS
# =============================================================================

def http_get(url):
    """Make HTTP GET request following redirects."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as r:
            # Handle redirects
            if r.status == 307:
                redirect_url = r.getheader('Location')
                return http_get(redirect_url)
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 307:
            redirect_url = e.headers.get('Location')
            if redirect_url:
                return http_get(redirect_url)
        print(f"  HTTP Error {e.code}: {e.read().decode('utf-8')[:200]}")
        return None
    except Exception as e:
        print(f"  GET Error: {e}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method='PATCH'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"  HTTP Error {e.code}: {error_body[:500]}")
        return None
    except Exception as e:
        print(f"  PATCH Error: {e}")
        return None


# =============================================================================
# BACKUP AND UPDATE FUNCTIONS
# =============================================================================

def backup_current_prompts(agents_data):
    """Save current system prompts to a backup file."""
    backup_dir = "/Volumes/main-drive/ai-PA/letta/backups"
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/system_prompts_backup_{timestamp}.json"

    with open(backup_file, 'w') as f:
        json.dump(agents_data, f, indent=2)

    print(f"  Backed up to: {backup_file}")
    return backup_file


def get_agent_current_prompt(agent_id):
    """Get current system prompt for an agent."""
    # Use curl-like behavior with -L for redirects
    url = f"{LETTA_BASE}/v1/agents/{agent_id}"

    # First try without redirect
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as r:
            agent = json.loads(r.read().decode('utf-8'))
            return agent.get('system', '')
    except urllib.error.HTTPError as e:
        if e.code == 307:
            # Follow redirect
            redirect_url = e.headers.get('Location')
            if redirect_url:
                try:
                    with urllib.request.urlopen(redirect_url, timeout=30) as r:
                        agent = json.loads(r.read().decode('utf-8'))
                        return agent.get('system', '')
                except Exception as e2:
                    print(f"  Redirect error: {e2}")
        print(f"  HTTP Error {e.code}")
        return None
    except Exception as e:
        print(f"  Error getting agent: {e}")
        return None


def update_agent_system_prompt(agent_name, agent_id, new_prompt):
    """Update an agent's system prompt."""
    print(f"\n{'='*60}")
    print(f"Updating: {agent_name}")
    print(f"Agent ID: {agent_id}")
    print(f"{'='*60}")

    # Get current prompt
    current = get_agent_current_prompt(agent_id)
    if current is None:
        print("  ERROR: Could not get current prompt")
        return False, None

    print(f"  Current prompt: {len(current)} chars")
    print(f"  New prompt: {len(new_prompt)} chars")

    # Update via PATCH
    url = f"{LETTA_BASE}/v1/agents/{agent_id}"
    result = http_patch(url, {"system": new_prompt})

    if result:
        print("  SUCCESS: System prompt updated")
        return True, current
    else:
        print("  FAILED: Could not update prompt")
        return False, current


def main():
    print("=" * 70)
    print("Update Agent System Prompts to Letta v1 Best Practices")
    print("=" * 70)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agents to update: {len(AGENTS)}")
    print()

    # Collect current prompts for backup
    print("Collecting current prompts for backup...")
    backup_data = {}
    for agent_name, agent_id in AGENTS.items():
        current = get_agent_current_prompt(agent_id)
        if current:
            backup_data[agent_name] = {
                "agent_id": agent_id,
                "system_prompt": current
            }
            print(f"  {agent_name}: {len(current)} chars")

    print()
    backup_file = backup_current_prompts(backup_data)
    print()

    # Confirm before proceeding
    print("The following agents will be updated:")
    for agent_name in AGENTS:
        print(f"  - {agent_name}")
    print()

    response = input("Proceed with updates? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    # Update each agent
    results = {"success": [], "failed": []}

    for agent_name, agent_id in AGENTS.items():
        new_prompt = SYSTEM_PROMPTS.get(agent_name)
        if not new_prompt:
            print(f"\n  SKIP: No template for {agent_name}")
            continue

        success, _ = update_agent_system_prompt(agent_name, agent_id, new_prompt)
        if success:
            results["success"].append(agent_name)
        else:
            results["failed"].append(agent_name)

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Successful: {len(results['success'])}")
    for name in results['success']:
        print(f"    ✓ {name}")

    if results['failed']:
        print(f"  Failed: {len(results['failed'])}")
        for name in results['failed']:
            print(f"    ✗ {name}")

    print()
    print(f"Backup saved to: {backup_file}")
    print()

    if results['failed']:
        print("Some updates failed. Check errors above.")
        return 1

    print("All agents updated successfully!")
    print()
    print("Next steps:")
    print("  1. Test each agent to verify behavior")
    print("  2. Update persona blocks separately (user will provide guidance)")
    print("  3. Monitor for any issues with report_refs enforcement")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
