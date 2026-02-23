"""
Task Lifecycle Tools for Letta

Tools for managing the lifecycle of extracted tasks and their archival
source reference passages:
- update_extracted_task: Content updates to existing tasks
- transition_extracted_task: Status changes (confirm, reject, complete)
- merge_extracted_tasks: Combine multiple tasks into one
"""

from typing import Dict, Any, Optional


def update_extracted_task(
    ref_id: str,
    task_description: Optional[str] = None,
    source_context: Optional[str] = None,
    source_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update the content of an existing extracted task and its archival passage.

    Use this when new information emerges about an existing task — corrections,
    additional context, or updated source text. Only the provided fields are
    changed; all others are preserved. An Updated timestamp is added automatically.

    Passages are stored in the shared extracted_tasks_archive, so any agent
    with the archive attached can update any task regardless of which agent
    originally extracted it.

    Args:
        ref_id: The 8-character hex reference ID of the task to update.
        task_description: Updated concise verb-led task title. Only provide if
            the title needs changing.
        source_context: Updated human-readable origin description.
        source_text: Additional or corrected verbatim source text. This REPLACES
            the existing source text entirely.

    Returns:
        Dictionary with status, ref_id, and update confirmation.
    """
    import os
    import re
    import traceback
    from datetime import datetime
    import pytz
    import urllib.request
    import urllib.error
    import json

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        ARCHIVE_ID = "archive-3f0530eb-82db-463a-a28b-f4752a95d7d5"
        calling_agent = os.getenv("LETTA_AGENT_ID")

        if not any([task_description, source_context, source_text]):
            return {"status": "error", "ref_id": ref_id, "error_message": "At least one of task_description, source_context, or source_text must be provided"}

        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)
        iso_timestamp = now.isoformat()

        # ── Find archival passage by ref_id in shared archive ──
        search_url = f"{LETTA_BASE}/v1/passages/search"
        search_data = json.dumps({"query": f"REF_ID: {ref_id}", "archive_id": ARCHIVE_ID, "limit": 10}).encode('utf-8')
        search_req = urllib.request.Request(search_url, data=search_data, headers={"Content-Type": "application/json"}, method='POST')
        with urllib.request.urlopen(search_req, timeout=30) as resp:
            search_results = json.loads(resp.read().decode('utf-8'))

        target_passage = None
        for result in search_results:
            p = result.get('passage', {})
            if f"REF_ID: {ref_id}" in p.get('text', ''):
                target_passage = p
                break

        if not target_passage:
            return {"status": "error", "ref_id": ref_id, "error_message": f"No archival passage found with REF_ID: {ref_id}"}

        old_text = target_passage['text']
        old_tags = target_passage.get('tags', [])
        passage_id = target_passage['id']

        # ── Apply updates to passage text ──
        new_text = old_text

        if task_description:
            new_text = re.sub(r'^TASK: .*$', f'TASK: {task_description}', new_text, count=1, flags=re.MULTILINE)

        if source_context:
            new_text = re.sub(r'^- Context: .*$', f'- Context: {source_context}', new_text, count=1, flags=re.MULTILINE)

        if source_text:
            new_text = re.sub(r'(?s)(SOURCE TEXT\n).*$', f'\\1{source_text}', new_text)

        # Add Updated timestamp to TIMESTAMPS section
        new_text = re.sub(
            r'(TIMESTAMPS\n(?:- .+\n)*)',
            lambda m: m.group(0) + f'- Updated: {iso_timestamp}\n',
            new_text,
            count=1
        )

        # ── Delete old passage, insert updated one ──
        del_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{passage_id}"
        del_req = urllib.request.Request(del_url, method='DELETE')
        urllib.request.urlopen(del_req, timeout=10)

        ins_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages"
        ins_data = json.dumps({"text": new_text, "tags": old_tags}).encode('utf-8')
        ins_req = urllib.request.Request(ins_url, data=ins_data, headers={"Content-Type": "application/json"}, method='POST')
        with urllib.request.urlopen(ins_req, timeout=30) as resp:
            ins_resp = json.loads(resp.read().decode('utf-8'))
            new_passage_id = ins_resp.get('id', '')

        # ── Update extracted_tasks block if task_description changed ──
        if task_description and calling_agent:
            agent_url = f"{LETTA_BASE}/v1/agents/{calling_agent}"
            with urllib.request.urlopen(agent_url, timeout=10) as resp:
                agent_data = json.loads(resp.read().decode('utf-8'))
            blocks = agent_data.get('memory', {}).get('blocks', [])
            et_block = None
            for b in blocks:
                if b.get('label') == 'extracted_tasks':
                    et_block = b
                    break
            if et_block:
                val = et_block.get('value', '')
                new_val = re.sub(
                    rf'(\[extracted_time: [^;]+; ref_id: {re.escape(ref_id)}\]) .+',
                    f'\\1 {task_description}',
                    val
                )
                if new_val != val:
                    patch_url = f"{LETTA_BASE}/v1/blocks/{et_block['id']}"
                    patch_data = json.dumps({"value": new_val}).encode('utf-8')
                    patch_req = urllib.request.Request(patch_url, data=patch_data, headers={"Content-Type": "application/json"}, method='PATCH')
                    urllib.request.urlopen(patch_req, timeout=10)

        fields_updated = []
        if task_description is not None:
            fields_updated.append('task_description')
        if source_context is not None:
            fields_updated.append('source_context')
        if source_text is not None:
            fields_updated.append('source_text')
        return {
            "status": "ok",
            "ref_id": ref_id,
            "message": f"Updated {', '.join(fields_updated)}. Added Updated timestamp.",
            "passage_id": new_passage_id,
            "timestamp": iso_timestamp
        }

    except Exception as e:
        return {"status": "error", "ref_id": ref_id, "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def transition_extracted_task(
    ref_id: str,
    action: str,
    omnifocus_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Change the status of an extracted task: confirm, reject, or complete.

    This updates the archival source reference passage in the shared
    extracted_tasks_archive and removes the task from the extracted_tasks
    memory block (since it is no longer pending review).

    Actions:
    - confirm: Task accepted, OmniFocus task created. Requires omnifocus_task_id.
    - reject: Task rejected during review.
    - complete: OmniFocus task completed or removed from consideration.

    Args:
        ref_id: The 8-character hex reference ID of the task.
        action: One of "confirm", "reject", or "complete".
        omnifocus_task_id: The OmniFocus task ID. Required when action is "confirm".

    Returns:
        Dictionary with status, ref_id, action taken, and updated passage ID.
    """
    import os
    import re
    import traceback
    from datetime import datetime
    import pytz
    import urllib.request
    import urllib.error
    import json

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        ARCHIVE_ID = "archive-3f0530eb-82db-463a-a28b-f4752a95d7d5"
        calling_agent = os.getenv("LETTA_AGENT_ID")

        valid_actions = {"confirm", "reject", "complete"}
        if action not in valid_actions:
            return {"status": "error", "ref_id": ref_id, "action": action, "error_message": f"Invalid action '{action}'. Must be one of: {', '.join(sorted(valid_actions))}"}

        if action == "confirm" and not omnifocus_task_id:
            return {"status": "error", "ref_id": ref_id, "action": action, "error_message": "omnifocus_task_id is required when action is 'confirm'"}

        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)
        iso_timestamp = now.isoformat()

        # ── Find archival passage by ref_id in shared archive ──
        search_url = f"{LETTA_BASE}/v1/passages/search"
        search_data = json.dumps({"query": f"REF_ID: {ref_id}", "archive_id": ARCHIVE_ID, "limit": 10}).encode('utf-8')
        search_req = urllib.request.Request(search_url, data=search_data, headers={"Content-Type": "application/json"}, method='POST')
        with urllib.request.urlopen(search_req, timeout=30) as resp:
            search_results = json.loads(resp.read().decode('utf-8'))

        target_passage = None
        for result in search_results:
            p = result.get('passage', {})
            if f"REF_ID: {ref_id}" in p.get('text', ''):
                target_passage = p
                break

        if not target_passage:
            return {"status": "error", "ref_id": ref_id, "action": action, "error_message": f"No archival passage found with REF_ID: {ref_id}"}

        old_text = target_passage['text']
        old_tags = list(target_passage.get('tags', []))
        passage_id = target_passage['id']
        new_text = old_text

        # ── Apply action-specific modifications ──

        if action == "confirm":
            # Add OmniFocus created timestamp
            new_text = re.sub(
                r'(- OmniFocus: )pending',
                f'- OmniFocus created: {iso_timestamp}',
                new_text
            )
            # Update OMNIFOCUS section
            new_text = re.sub(r'- Task ID: pending', f'- Task ID: {omnifocus_task_id}', new_text)
            new_text = re.sub(r'- Status: extracted', '- Status: confirmed', new_text)
            # Update tags
            old_tags = [t for t in old_tags if not t.startswith('status:')]
            old_tags.append('status:confirmed')

        elif action == "reject":
            # Prefix TASK line with [REJECTED]
            task_match = re.search(r'^TASK: (.+)$', new_text, re.MULTILINE)
            if task_match:
                desc = task_match.group(1)
                if not desc.startswith('[REJECTED]'):
                    new_text = re.sub(r'^TASK: .+$', f'TASK: [REJECTED] {desc}', new_text, count=1, flags=re.MULTILINE)
            # Remove OmniFocus line from TIMESTAMPS, add Rejected timestamp
            new_text = re.sub(r'- OmniFocus: pending\n', '', new_text)
            new_text = re.sub(
                r'(TIMESTAMPS\n(?:- .+\n)*)',
                lambda m: m.group(0) + f'- Rejected: {iso_timestamp}\n',
                new_text,
                count=1
            )
            # Remove OMNIFOCUS section entirely
            new_text = re.sub(r'\nOMNIFOCUS\n- Task ID: .+\n- Status: .+\n?', '', new_text)
            # Update tags
            old_tags = [t for t in old_tags if not t.startswith('status:')]
            old_tags.append('status:rejected')

        elif action == "complete":
            # Prefix TASK line with [COMPLETED]
            task_match = re.search(r'^TASK: (.+)$', new_text, re.MULTILINE)
            if task_match:
                desc = task_match.group(1)
                if not desc.startswith('[COMPLETED]'):
                    new_text = re.sub(r'^TASK: .+$', f'TASK: [COMPLETED] {desc}', new_text, count=1, flags=re.MULTILINE)
            # Add Completed timestamp
            new_text = re.sub(
                r'(TIMESTAMPS\n(?:- .+\n)*)',
                lambda m: m.group(0) + f'- Completed: {iso_timestamp}\n',
                new_text,
                count=1
            )
            # Update OMNIFOCUS status
            new_text = re.sub(r'- Status: (extracted|confirmed)', '- Status: completed', new_text)
            # Update tags
            old_tags = [t for t in old_tags if not t.startswith('status:')]
            old_tags.append('status:completed')

        # ── Delete old passage, insert updated one ──
        del_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{passage_id}"
        del_req = urllib.request.Request(del_url, method='DELETE')
        urllib.request.urlopen(del_req, timeout=10)

        ins_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages"
        ins_data = json.dumps({"text": new_text, "tags": old_tags}).encode('utf-8')
        ins_req = urllib.request.Request(ins_url, data=ins_data, headers={"Content-Type": "application/json"}, method='POST')
        with urllib.request.urlopen(ins_req, timeout=30) as resp:
            ins_resp = json.loads(resp.read().decode('utf-8'))
            new_passage_id = ins_resp.get('id', '')

        # ── Remove from extracted_tasks block ──
        if calling_agent:
            agent_url = f"{LETTA_BASE}/v1/agents/{calling_agent}"
            try:
                with urllib.request.urlopen(agent_url, timeout=10) as resp:
                    agent_data = json.loads(resp.read().decode('utf-8'))
                blocks = agent_data.get('memory', {}).get('blocks', [])
                et_block = None
                for b in blocks:
                    if b.get('label') == 'extracted_tasks':
                        et_block = b
                        break
                if et_block:
                    val = et_block.get('value', '')
                    new_val = re.sub(rf'[^\n]*ref_id: {re.escape(ref_id)}[^\n]*\n*', '', val)
                    while '\n\n\n' in new_val:
                        new_val = new_val.replace('\n\n\n', '\n\n')
                    if new_val != val:
                        patch_url = f"{LETTA_BASE}/v1/blocks/{et_block['id']}"
                        patch_data = json.dumps({"value": new_val}).encode('utf-8')
                        patch_req = urllib.request.Request(patch_url, data=patch_data, headers={"Content-Type": "application/json"}, method='PATCH')
                        urllib.request.urlopen(patch_req, timeout=10)
            except Exception:
                pass  # Block cleanup is best-effort

        return {
            "status": "ok",
            "ref_id": ref_id,
            "action": action,
            "message": f"Task {action}d successfully." if action.endswith('e') else f"Task {action}ed successfully.",
            "passage_id": new_passage_id,
            "timestamp": iso_timestamp
        }

    except Exception as e:
        return {"status": "error", "ref_id": ref_id, "action": action, "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def merge_extracted_tasks(
    ref_ids: str,
    merged_task_description: str,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Merge multiple extracted tasks into a single new task.

    Creates a new merged archival passage linking to the originals, and marks
    each original passage as [MERGED] with a pointer to the new merged task.
    All passages are in the shared extracted_tasks_archive.

    The merged task becomes the active record for subsequent confirm/complete
    transitions. Original passages retain their full source data, reachable
    via MERGED_IDS.

    Args:
        ref_ids: Comma-separated 8-char hex reference IDs of tasks to merge
            (e.g., "a1b2c3d4,e5f6g7h8").
        merged_task_description: Concise verb-led title for the new merged task.
        project: Optional project name for tagging the merged record.

    Returns:
        Dictionary with status, new ref_id, merged passage ID, and count of
        original tasks merged.
    """
    import os
    import re
    import uuid
    import traceback
    from datetime import datetime
    import pytz
    import urllib.request
    import urllib.error
    import json

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        ARCHIVE_ID = "archive-3f0530eb-82db-463a-a28b-f4752a95d7d5"
        calling_agent = os.getenv("LETTA_AGENT_ID")

        # Parse ref_ids
        id_list = [rid.strip() for rid in ref_ids.split(',') if rid.strip()]
        if len(id_list) < 2:
            return {"status": "error", "ref_ids": ref_ids, "error_message": "At least 2 ref_ids are required for merging"}

        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)
        iso_timestamp = now.isoformat()
        year_month = now.strftime("%Y-%m")
        new_ref_id = uuid.uuid4().hex[:8]

        # ── Search shared archive for each ref_id ──
        found = {}
        for rid in id_list:
            search_url = f"{LETTA_BASE}/v1/passages/search"
            search_data = json.dumps({"query": f"REF_ID: {rid}", "archive_id": ARCHIVE_ID, "limit": 5}).encode('utf-8')
            search_req = urllib.request.Request(search_url, data=search_data, headers={"Content-Type": "application/json"}, method='POST')
            with urllib.request.urlopen(search_req, timeout=30) as resp:
                search_results = json.loads(resp.read().decode('utf-8'))
            for result in search_results:
                p = result.get('passage', {})
                if f"REF_ID: {rid}" in p.get('text', ''):
                    found[rid] = p
                    break

        missing = [rid for rid in id_list if rid not in found]
        if missing:
            return {"status": "error", "ref_ids": ref_ids, "error_message": f"Passages not found for ref_ids: {', '.join(missing)}"}

        # ── Mark each original passage as [MERGED] ──
        for rid, passage in found.items():
            old_text = passage['text']
            old_tags = list(passage.get('tags', []))
            pid = passage['id']

            new_text = old_text

            # Prefix TASK with [MERGED]
            task_match = re.search(r'^TASK: (.+)$', new_text, re.MULTILINE)
            if task_match:
                desc = task_match.group(1)
                if not desc.startswith('[MERGED]'):
                    new_text = re.sub(r'^TASK: .+$', f'TASK: [MERGED] {desc}', new_text, count=1, flags=re.MULTILINE)

            # Add MERGE_PARENT_ID below REF_ID
            new_text = re.sub(
                rf'(REF_ID: {re.escape(rid)})',
                f'\\1\nMERGE_PARENT_ID: {new_ref_id}',
                new_text,
                count=1
            )

            # Add Merged timestamp
            new_text = re.sub(
                r'(TIMESTAMPS\n(?:- .+\n)*)',
                lambda m: m.group(0) + f'- Merged: {iso_timestamp}\n',
                new_text,
                count=1
            )

            # Update tags
            new_tags = [t for t in old_tags if not t.startswith('status:')]
            new_tags.append('status:merged')

            # Delete old, insert updated
            del_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{pid}"
            del_req = urllib.request.Request(del_url, method='DELETE')
            urllib.request.urlopen(del_req, timeout=10)

            ins_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages"
            ins_data = json.dumps({"text": new_text, "tags": new_tags}).encode('utf-8')
            ins_req = urllib.request.Request(ins_url, data=ins_data, headers={"Content-Type": "application/json"}, method='POST')
            urllib.request.urlopen(ins_req, timeout=30)

        # ── Create new merged passage ──
        merged_ids_str = ", ".join(id_list)
        merged_text = (
            f"TASK: {merged_task_description}\n"
            f"REF_ID: {new_ref_id}\n"
            f"MERGED_IDS: {merged_ids_str}\n"
            f"\n"
            f"TIMESTAMPS\n"
            f"- Merged: {iso_timestamp}\n"
            f"- OmniFocus: pending\n"
            f"\n"
            f"OMNIFOCUS\n"
            f"- Task ID: pending\n"
            f"- Status: extracted\n"
        )

        merged_tags = [year_month, "status:extracted"]
        if project:
            merged_tags.append(f"project:{project}")

        ins_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages"
        ins_data = json.dumps({"text": merged_text, "tags": merged_tags}).encode('utf-8')
        ins_req = urllib.request.Request(ins_url, data=ins_data, headers={"Content-Type": "application/json"}, method='POST')
        with urllib.request.urlopen(ins_req, timeout=30) as resp:
            ins_resp = json.loads(resp.read().decode('utf-8'))
            merged_passage_id = ins_resp.get('id', '')

        # ── Remove merged entries from extracted_tasks block ──
        if calling_agent:
            agent_url = f"{LETTA_BASE}/v1/agents/{calling_agent}"
            try:
                with urllib.request.urlopen(agent_url, timeout=10) as resp:
                    agent_data = json.loads(resp.read().decode('utf-8'))
                blocks = agent_data.get('memory', {}).get('blocks', [])
                et_block = None
                for b in blocks:
                    if b.get('label') == 'extracted_tasks':
                        et_block = b
                        break
                if et_block:
                    val = et_block.get('value', '')
                    for rid in id_list:
                        val = re.sub(rf'[^\n]*ref_id: {re.escape(rid)}[^\n]*\n*', '', val)
                    while '\n\n\n' in val:
                        val = val.replace('\n\n\n', '\n\n')
                    patch_url = f"{LETTA_BASE}/v1/blocks/{et_block['id']}"
                    patch_data = json.dumps({"value": val}).encode('utf-8')
                    patch_req = urllib.request.Request(patch_url, data=patch_data, headers={"Content-Type": "application/json"}, method='PATCH')
                    urllib.request.urlopen(patch_req, timeout=10)
            except Exception:
                pass  # Block cleanup is best-effort

        return {
            "status": "ok",
            "ref_id": new_ref_id,
            "merged_ids": id_list,
            "message": f"Merged {len(id_list)} tasks into new task.",
            "passage_id": merged_passage_id,
            "timestamp": iso_timestamp
        }

    except Exception as e:
        return {"status": "error", "ref_ids": ref_ids, "error_message": f"{str(e)}\n{traceback.format_exc()}"}
