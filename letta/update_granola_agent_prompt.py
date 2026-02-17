#!/usr/bin/env python3
"""Update Granola agent system prompt with meeting processing protocol."""
import os
import sys
import json
import urllib.request

AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"
PROTOCOL_TAG = "<meeting_processing_protocol>"

PROTOCOL_SECTION = """
<meeting_processing_protocol>
When you receive a "New meeting archived" notification:

1. Call scan_meeting_notes(meeting_id) to get the scan package.

2. Review the scan package:
   a. marker_extractions contains high-confidence items parsed from user notes.
   b. scannable_content contains labeled text for you to scan semantically.
   c. For linked_doc items with text=null, call fetch_document_from_drive to get content.

3. Semantic scan — review each scannable_content item for:
   - Action items not captured by markers (especially from AI summary and transcript)
   - Additional context for marker items (deadlines, specifics from discussion)
   - Tasks from linked document content

4. Merge results:
   - Markers are authoritative anchors
   - Semantic discoveries augment markers or add new items
   - Deduplicate: if a semantic hit overlaps a marker, enrich the marker item
   - Confidence weighting: markers > user notes > AI summary > linked docs > transcript

5. Expand pointers (> items): use the provided transcript excerpts to identify what
   was discussed and formulate the action item or talking point.

6. Call prepare_meeting_followup with ALL merged items:
   - meeting_id, meeting_title, meeting_date from scan package
   - participants as comma-separated "Name <email>" entries
   - decisions: pipe-separated key decisions from AI summary
   - my_actions: pipe-separated personal action items (from [ ] markers + semantic)
   - their_actions: pipe-separated "Name: action" entries (from [;] markers + semantic)

Marker convention:
- [ ] or [] = my task (queued for extraction + included in D/NA email)
- [;] = someone else's task (D/NA email only, not queued)
- > = pointer needing expansion from transcript context
- D/NA = section header (informational, not required for routing)
</meeting_processing_protocol>
"""


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta: {LETTA_BASE}")
    print(f"Agent: {AGENT_ID}")

    # Get current agent
    url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        agent_data = json.loads(resp.read().decode("utf-8"))

    current_prompt = agent_data.get("system", "")

    if PROTOCOL_TAG in current_prompt:
        print("\nProtocol already present in system prompt. No update needed.")
        return 0

    # Append protocol
    updated_prompt = current_prompt.rstrip() + "\n" + PROTOCOL_SECTION.strip() + "\n"

    # Update agent
    update_data = json.dumps({"system": updated_prompt}).encode("utf-8")
    update_req = urllib.request.Request(
        url,
        data=update_data,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(update_req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    new_prompt = result.get("system", "")
    if PROTOCOL_TAG in new_prompt:
        print("\nSuccess: meeting_processing_protocol added to agent prompt.")
        print(f"Prompt length: {len(new_prompt)} chars")
    else:
        print("\nWarning: protocol tag not found in updated prompt.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
