#!/usr/bin/env python3
"""Create meeting-related memory blocks on the Granola agent.

Creates two blocks if they don't already exist:
1. queued_tasks_from_meetings — task queue (parallels queued_tasks_from_email)
2. meeting_processing_chain — step-by-step guidance for the post-meeting
   processing workflow (scan → review → draft email → extract tasks)
"""
import os
import sys

try:
    from letta_client import Letta
except ImportError:
    from letta import Letta

AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"

MEETING_PROCESSING_CHAIN = """\
## Post-Meeting Processing Chain

When you receive a message containing "New meeting archived" with a meeting_id:

### Step 1: Scan
Call scan_meeting_notes(meeting_id="<the meeting_id>").
This returns a scan package with marker_extractions and scannable_content.

### Step 2: Review & Merge
Review the scan package:
- marker_extractions.decisions: items marked D: or Decision: = explicit decisions (rare)
- marker_extractions.my_tasks: items marked [ ] or [] = personal tasks for Chad
- marker_extractions.their_tasks: items marked [;] = others action items
- marker_extractions.pointers: items marked > = expand using transcript excerpts
- scannable_content: private_notes, AI summary, transcript excerpts to scan semantically
- For linked_doc entries with text=null, call fetch_document_from_drive to get content

Semantic scan each scannable_content item for additional action items not captured by markers.
Merge: markers are authoritative anchors. Semantic discoveries augment or add new items.
Confidence: markers > user notes > AI summary > linked docs > transcript.

DECISIONS ARE RARE. Only include if explicitly marked with D: or Decision: in notes,
or if the meeting context makes a clear group decision (e.g. "we agreed to X").
Progress updates, status items, and observations are NOT decisions. Most meetings
will have zero decisions. When in doubt, omit.

### Step 2b: Attach Deadlines
Each action item may have a deadline_hint (from notes or transcript).
- If deadline_source is "notes": high confidence — include "by <date>" in the action text.
- If deadline_source is "transcript": medium confidence — include if context supports it.
- If no hint but you can infer a deadline from meeting context (e.g. "let's get this done
  this week"): include with medium+ confidence only.
- Format: "Chad to send message to Michelle W by Wednesday, 2/18"
- Resolve day names to actual dates using meeting_date as reference.
- When in doubt, omit the deadline — better to leave it off than guess wrong.

### Step 3: Draft Email
Call prepare_meeting_followup with ALL merged items:
- meeting_id, meeting_title, meeting_date: from scan package
- participants: comma-separated "Name <email>" entries (resolve emails from important_people)
- decisions: pipe-separated key decisions ONLY if high-confidence (D: markers or clear group agreement)
- my_actions: pipe-separated personal tasks with deadlines inline ([ ] markers + semantic)
- their_actions: pipe-separated "Name: action by date" entries ([;] markers + semantic)

CRITICAL: You MUST call prepare_meeting_followup after reviewing the scan.
Do NOT just summarize results as text. The user expects a Gmail draft.

### Step 4: Extract Tasks
For any my_actions items, also call add_extracted_tasks following the
task_extraction_process_docs_transcripts block rules."""

BLOCKS = [
    ("queued_tasks_from_meetings", "# Queued Tasks from Meetings\n(empty)\n"),
    ("meeting_processing_chain", MEETING_PROCESSING_CHAIN),
]


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    client = Letta(base_url=LETTA_BASE)

    agent = client.agents.retrieve(agent_id=AGENT_ID)
    existing_labels = {b.label for b in agent.memory.blocks}

    print(f"Letta: {LETTA_BASE}")
    print(f"Agent: {AGENT_ID}")
    print()

    for label, value in BLOCKS:
        if label in existing_labels:
            print(f"{label}: already exists, skipping")
            continue

        block = client.blocks.create(label=label, value=value)
        print(f"{label}: created {block.id}")

        client.agents.blocks.attach(agent_id=AGENT_ID, block_id=block.id)
        print(f"{label}: attached to agent")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
