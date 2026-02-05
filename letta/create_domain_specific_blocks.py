#!/usr/bin/env python3
"""
Create Domain-Specific Memory Blocks for Specialist Agents

Creates and attaches domain-specific blocks based on Letta v1 best practices:
- Email Agent: email_patterns
- Documents Agent: document_organization
- Calendar Agent: calendar_preferences
- Tasks Agent: task_organization
- Pulse Monitor: monitoring_priorities

Each block contains tailored content for the agent's specialty area.
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
# DOMAIN-SPECIFIC BLOCK CONTENT
# =============================================================================

DOMAIN_BLOCKS = {}

# -----------------------------------------------------------------------------
# EMAIL AGENT: email_patterns
# -----------------------------------------------------------------------------
DOMAIN_BLOCKS["Email Agent"] = {
    "label": "email_patterns",
    "description": "Email organization, search patterns, and drafting guidelines",
    "value": """Email Drafting Guidelines:
- When instructed to draft an email, compose it fully but DO NOT SEND
- Present drafts for review before sending
- Only send when explicitly directed with "send" or "go ahead"
- Confirm recipient and subject before sending

Watch Labels & Thread Monitoring:
- Watch labels: [To be configured - labels that trigger monitoring]
- Monitored threads: Track threads with watch labels for replies
- Reply timeframe alerts: [To be configured - e.g., alert if no reply within 48h]
- Escalation patterns: [When to surface unreplied threads]

Urgent/Actionable Monitoring:
- Surface urgent messages on request (not proactively unless configured)
- Urgent indicators: Time-sensitive language, escalation markers, key senders
- Actionable indicators: Requests for decisions, approvals, responses needed
- Key sender priorities: [Board members, funders, direct reports - to be populated]

Search Patterns:
- Frequently searched senders: [To be populated as patterns emerge]
- Important email types: Grant correspondence, Board communications, Team updates
- Project-related searches: Cross-reference with current priorities from [human] block

Organization Patterns:
- Label system: [To be learned - how labels are used]
- Archive vs delete: [To be learned]
- Processing times: Morning block (9-11am) includes email processing
"""
}

# -----------------------------------------------------------------------------
# DOCUMENTS AGENT: document_organization
# -----------------------------------------------------------------------------
DOMAIN_BLOCKS["Documents Agent"] = {
    "label": "document_organization",
    "description": "Document search, retrieval, and meeting transcript patterns",
    "value": """Core Functions:
- Document search and retrieval across Google Drive
- Document summarization on request
- Semantic RAG searches across indexed documents
- Meeting transcript search via Granola

Document Search Strategy:
- Search before retrieving (efficiency)
- Use semantic search for conceptual queries
- Use metadata search for known documents
- Cross-reference related documents automatically

Meeting Transcript Handling:
- Tag structures: [To be configured - how transcripts are tagged]
- Retrieval patterns: Search by date, participants, topics, action items
- Action item extraction: On request, extract action items as suggested tasks
- Format: Present action items in task-ready format for Tasks Agent

Meeting Summary Functions:
- Summarize meeting goals and outcomes on request
- Identify key decisions and commitments
- Suggest next-meeting targets based on current transcript
- Surface unresolved topics for follow-up
- Connect to related documents and prior meetings

Document Organization:
- Project folder patterns: [To be learned]
- Active project locations: [Key folders for current work]
- Shared drive patterns: [Concord Consortium team drives]

Cross-Reference Priorities:
- Connect transcripts to related documents
- Link meeting discussions to project documentation
- Surface relevant prior meetings when searching topics
"""
}

# -----------------------------------------------------------------------------
# CALENDAR AGENT: calendar_preferences
# -----------------------------------------------------------------------------
DOMAIN_BLOCKS["Calendar Agent"] = {
    "label": "calendar_preferences",
    "description": "Scheduling preferences, patterns, and meeting type handling",
    "value": """Protected Time:
- Morning block: 9-11am reserved for Email & Tasks (NO meetings)
- [Other protected times to be configured]

Scheduling Preferences:
- Preferred meeting times: [To be learned beyond morning protection]
- Buffer between meetings: [To be learned - default to 15 min when possible]
- Default lengths: [To be learned - internal vs external]
- End-of-day buffer: [Avoid scheduling too late]

Meeting Type Handling:
- 1-on-1s: [Preferred day/time/duration patterns]
- Team meetings: [Recurring patterns]
- Board/Executive meetings: [Special handling, prep time]
- External calls (funders, partners): [Preferences, prep requirements]
- Focus/deep work blocks: [When to suggest blocking time]

Calendly Integration:
- When to offer Calendly links: External scheduling, new contacts
- Availability windows for external booking: [Settings]
- Link types: [Different links for different meeting types]

Colleague Coordination:
- Use lookup_staff for internal scheduling
- Check colleague availability before proposing times
- Key collaborators: Danielle Kehoe (development), [others]

Travel/Location:
- Base location: Concord, MA (Concord Consortium office)
- Cross-location meeting buffer: [Time needs for travel]
- Virtual vs in-person defaults: [Preferences by meeting type]

NOTE: See [orchestrate_scheduling_tool_use_guidelines] for detailed tool usage.
"""
}

# -----------------------------------------------------------------------------
# TASKS AGENT: task_organization
# -----------------------------------------------------------------------------
DOMAIN_BLOCKS["Tasks Agent"] = {
    "label": "task_organization",
    "description": "OmniFocus structure, patterns, and cross-agent task handling",
    "value": """OmniFocus Structure:
- Project hierarchy: [To be learned - how projects are organized]
- Context usage: [What contexts exist and their meanings]
- Flag system: [What flags indicate - urgent, waiting, etc.]
- Review frequency: [Daily/weekly review patterns]

Priority Indicators:
- Current focus (from [human] block): Q1 2026 priorities
- Recurring responsibilities: [CEO standing items]
- Delegation markers: [Tasks involving others]

Task Entry Patterns:
- Default entry: Inbox (unless project specified)
- Quick capture from agents: Add to inbox with source context
- Defer patterns: [How defer dates are used]
- Due date conventions: [Hard vs soft deadlines]

Cross-Agent Task Handling:
- Tasks from Email Agent: Email follow-ups, response reminders
- Tasks from Documents Agent: Action items from meeting transcripts
- Tasks from Calendar Agent: Meeting prep tasks, follow-up tasks
- Tasks from Pulse Agent: Slack/Jira items needing action
- Format: Include source context when creating tasks from other agents

Completion Patterns:
- Confirm before marking complete (unless explicit)
- Batch completion: [Preferences for reviewing and completing]
- Recurring task handling: [Auto-complete patterns]

Task Suggestions:
- When extracting action items, present as suggestions first
- Group related tasks when presenting
- Include context (source meeting, email, conversation)
"""
}

# -----------------------------------------------------------------------------
# PULSE MONITOR: monitoring_priorities
# -----------------------------------------------------------------------------
DOMAIN_BLOCKS["Pulse Monitor"] = {
    "label": "monitoring_priorities",
    "description": "Slack/Jira/Confluence monitoring priorities and analytics patterns",
    "value": """@Mention & Request Scanning:
- Scan @mentions across Slack for direct requests
- Scan Jira comments/assignments for action items
- Collate requests for review and potential conversion to tasks
- Surface actionable items distinctly from FYI information

Channel Priorities:
- Critical (immediate attention): [To be configured]
- Daily digest: [Regular monitoring channels]
- Weekly rollup: [Lower frequency channels]
- Muted but searchable: [Archived reference channels]

People Tracking:
- NOTE: Detailed people mapping in separate [slack_people_mapping] block
- Key relationships to monitor: Leadership, direct reports, external partners
- Development team tracking: Danielle Kehoe and related threads

Topic Tracking:
- Always alert: [Urgent topics - incidents, deadlines, critical decisions]
- Daily digest: [Project updates, team news]
- Weekly rollup: [Metrics, retrospectives]

Jira Monitoring:
- Assigned issues: Track status changes
- Mentioned in comments: Surface requests and questions
- Key projects: [Project keys to watch]
- Sprint/release tracking: [Patterns]

Confluence Monitoring:
- Important spaces: [Spaces to watch]
- Page updates: [Key documents to track]
- Comment mentions: [Surface discussions]

Analytics & Rollups:
- Use analytics tools for regular pattern reports
- Communication volume trends: [Frequency of rollups]
- Channel activity summaries: [What to include]
- Response time patterns: [Metrics to track]

Task Conversion:
- When scanning finds actionable items, format for Tasks Agent
- Include source context (channel, person, timestamp)
- Distinguish between requests TO Chad vs. requests ABOUT Chad's projects
"""
}


# =============================================================================
# HTTP HELPERS
# =============================================================================

def http_request(url, method='GET', data=None):
    """Make HTTP request with redirect handling."""
    if data:
        payload = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method=method
        )
    else:
        req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 307:
            redirect_url = e.headers.get('Location')
            if redirect_url:
                return http_request(redirect_url, method, data)
        error_body = e.read().decode('utf-8')
        print(f"  HTTP Error {e.code}: {error_body[:300]}")
        return None
    except Exception as e:
        print(f"  Request Error: {e}")
        return None


def get_agent_blocks(agent_id):
    """Get agent's memory blocks."""
    agent = http_request(f"{LETTA_BASE}/v1/agents/{agent_id}")
    if agent:
        return agent.get('memory', {}).get('blocks', [])
    return []


def create_block(label, value, limit=5000, description=""):
    """Create a new memory block."""
    data = {
        "label": label,
        "value": value,
        "limit": limit,
    }
    if description:
        data["description"] = description
    return http_request(f"{LETTA_BASE}/v1/blocks", method='POST', data=data)


def attach_block_to_agent(agent_id, block_id):
    """Attach a block to an agent."""
    return http_request(
        f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}",
        method='PATCH'
    )


def check_existing_block(agent_id, label):
    """Check if agent already has a block with this label."""
    blocks = get_agent_blocks(agent_id)
    for block in blocks:
        if block.get('label') == label:
            return block
    return None


# =============================================================================
# BACKUP
# =============================================================================

def backup_current_state():
    """Backup current agent blocks before changes."""
    backup_dir = "/Volumes/main-drive/ai-PA/letta/backups"
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/domain_blocks_backup_{timestamp}.json"

    all_data = {}
    for agent_name, agent_id in AGENTS.items():
        blocks = get_agent_blocks(agent_id)
        all_data[agent_name] = {
            "agent_id": agent_id,
            "blocks": blocks
        }

    with open(backup_file, 'w') as f:
        json.dump(all_data, f, indent=2)

    print(f"  Backed up to: {backup_file}")
    return backup_file


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("Create Domain-Specific Memory Blocks")
    print("=" * 70)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print()

    # Step 1: Show what will be created
    print("Domain blocks to create:")
    print()
    for agent_name, block_info in DOMAIN_BLOCKS.items():
        print(f"  {agent_name}:")
        print(f"    Label: [{block_info['label']}]")
        print(f"    Size: {len(block_info['value'])} chars")
        print()

    # Step 2: Check for existing blocks
    print("Checking for existing blocks...")
    print()
    conflicts = []
    for agent_name, block_info in DOMAIN_BLOCKS.items():
        agent_id = AGENTS[agent_name]
        existing = check_existing_block(agent_id, block_info['label'])
        if existing:
            conflicts.append({
                'agent': agent_name,
                'label': block_info['label'],
                'existing_id': existing.get('id'),
                'existing_chars': len(existing.get('value', ''))
            })
            print(f"  WARNING: {agent_name} already has [{block_info['label']}]")
            print(f"           Block ID: {existing.get('id')}")
            print(f"           Size: {len(existing.get('value', ''))} chars")
        else:
            print(f"  OK: {agent_name} does not have [{block_info['label']}]")
    print()

    if conflicts:
        print("=" * 70)
        print("CONFLICTS DETECTED")
        print("=" * 70)
        print()
        print("The following agents already have blocks with the target labels.")
        print("Options:")
        print("  1. Skip these agents (keep existing blocks)")
        print("  2. Replace existing blocks with new content")
        print()
        response = input("How to handle conflicts? [skip/replace/cancel]: ").lower()
        if response == 'cancel':
            print("Cancelled.")
            return 0
        replace_conflicts = (response == 'replace')
    else:
        replace_conflicts = False

    # Step 3: Backup
    print()
    print("Creating backup...")
    backup_file = backup_current_state()
    print()

    # Step 4: Confirm
    print("=" * 70)
    print("READY TO CREATE DOMAIN BLOCKS")
    print("=" * 70)
    print()
    response = input("Proceed with creation? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    # Step 5: Create and attach blocks
    print()
    print("=" * 70)
    print("CREATING DOMAIN BLOCKS")
    print("=" * 70)

    results = {"created": [], "skipped": [], "replaced": [], "failed": []}

    for agent_name, block_info in DOMAIN_BLOCKS.items():
        print()
        print(f"[{agent_name}]")
        agent_id = AGENTS[agent_name]

        # Check if already exists
        existing = check_existing_block(agent_id, block_info['label'])
        if existing:
            if not replace_conflicts:
                print(f"  Skipping - [{block_info['label']}] already exists")
                results["skipped"].append(agent_name)
                continue
            else:
                # Update existing block
                print(f"  Replacing existing [{block_info['label']}]...")
                update_result = http_request(
                    f"{LETTA_BASE}/v1/blocks/{existing.get('id')}",
                    method='PATCH',
                    data={"value": block_info['value']}
                )
                if update_result:
                    print(f"  ✓ Replaced [{block_info['label']}]")
                    results["replaced"].append(agent_name)
                else:
                    print(f"  ✗ Failed to replace")
                    results["failed"].append(agent_name)
                continue

        # Create new block
        print(f"  Creating [{block_info['label']}]...")
        new_block = create_block(
            label=block_info['label'],
            value=block_info['value'],
            limit=5000,
            description=block_info['description']
        )

        if not new_block:
            print(f"  ✗ Failed to create block")
            results["failed"].append(agent_name)
            continue

        block_id = new_block.get('id')
        print(f"  Created: {block_id}")

        # Attach to agent
        print(f"  Attaching to {agent_name}...")
        attach_result = attach_block_to_agent(agent_id, block_id)

        if attach_result:
            print(f"  ✓ Attached [{block_info['label']}] to {agent_name}")
            results["created"].append(agent_name)
        else:
            print(f"  ✗ Failed to attach (block created but not attached)")
            results["failed"].append(agent_name)

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    if results["created"]:
        print(f"Created and attached ({len(results['created'])}):")
        for name in results["created"]:
            print(f"  ✓ {name}: [{DOMAIN_BLOCKS[name]['label']}]")

    if results["replaced"]:
        print(f"Replaced existing ({len(results['replaced'])}):")
        for name in results["replaced"]:
            print(f"  ✓ {name}: [{DOMAIN_BLOCKS[name]['label']}]")

    if results["skipped"]:
        print(f"Skipped (already exists) ({len(results['skipped'])}):")
        for name in results["skipped"]:
            print(f"  - {name}: [{DOMAIN_BLOCKS[name]['label']}]")

    if results["failed"]:
        print(f"Failed ({len(results['failed'])}):")
        for name in results["failed"]:
            print(f"  ✗ {name}")

    print()
    print(f"Backup saved to: {backup_file}")
    print()

    # Note about slack_people_mapping
    print("=" * 70)
    print("NOTES")
    print("=" * 70)
    print()
    print("- [slack_people_mapping] kept as separate block for Pulse Monitor")
    print("- [orchestrate_scheduling_tool_use_guidelines] kept for Calendar Agent")
    print("- Domain blocks contain [To be configured] placeholders for learning")
    print()
    print("Next steps:")
    print("  1. Test each agent to verify domain blocks are accessible")
    print("  2. Populate [To be configured] sections as patterns emerge")
    print("  3. Review existing OmniFocus blocks for Tasks Agent overlap")

    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
