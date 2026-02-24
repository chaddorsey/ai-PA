"""
OmniFocus Completion Sync Tool for Letta

Polls OmniFocus for completed tasks that have Letta archival records
(status:confirmed) and transitions them to status:completed in the
shared archive. Designed to run on a scheduler cron job.

Tool: sync_omnifocus_completions
"""

from typing import Dict, Any


def sync_omnifocus_completions() -> Dict[str, Any]:
    """
    Check OmniFocus for completed tasks and update their Letta archival records.

    Searches the shared extracted_tasks_archive for passages with
    status:confirmed, extracts their OmniFocus task IDs, batch-checks
    OmniFocus for completion status via the host bridge service, and
    transitions any completed tasks to status:completed.

    This tool is deterministic — no LLM reasoning is needed. It should
    be called periodically (e.g., every 15-30 minutes) via a scheduler
    cron job to keep Letta's task records in sync with OmniFocus.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - checked: Number of confirmed tasks checked
        - completed: Number of tasks transitioned to completed
        - dropped: Number of tasks found dropped in OmniFocus
        - not_found: Number of tasks not found in OmniFocus
        - details: List of dicts with ref_id, omnifocus_id, and action taken
        - error_message: Error details if status is "error"
    """
    import os
    import re
    import json
    import traceback
    from datetime import datetime
    import pytz
    import urllib.request
    import urllib.error

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
        BRIDGE_URL = "http://host.docker.internal:8889"
        # Use agent archival-memory substring search for reliable text matching.
        AGENT_ID = os.getenv("LETTA_AGENT_ID", "agent-62edcfac-2cc7-41a5-a3c2-d417da393397")

        tz = pytz.timezone("America/New_York")
        iso_timestamp = datetime.now(tz).isoformat()

        # ── Step 1: Find confirmed passages via agent archival memory ──
        # Uses substring search which is reliable for text matching.
        search_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory?search=Status%3A%20confirmed&limit=200"
        search_req = urllib.request.Request(search_url, method="GET")
        with urllib.request.urlopen(search_req, timeout=30) as resp:
            search_results = json.loads(resp.read().decode("utf-8"))

        # Filter to actual confirmed passages (substring search may return others)
        confirmed_passages = []
        for p in search_results:
            text = p.get("text", "")
            tags = p.get("tags", [])
            if "- Status: confirmed" in text and "status:confirmed" in tags:
                confirmed_passages.append(p)

        if not confirmed_passages:
            return {
                "status": "ok",
                "checked": 0, "completed": 0, "dropped": 0, "not_found": 0,
                "details": [],
                "error_message": "",
            }

        # ── Step 2: Extract OmniFocus task IDs and ref_ids from passages ──
        USER_NAME = "Chad Dorsey"  # Used to detect external origins
        task_map = {}
        for p in confirmed_passages:
            text = p.get("text", "")
            ref_match = re.search(r"REF_ID: (\S+)", text)
            task_id_match = re.search(r"- Task ID: (\S+)", text)
            if ref_match and task_id_match:
                of_id = task_id_match.group(1)
                ref_id = ref_match.group(1)
                if of_id != "pending":
                    # Extract source metadata for feedback routing
                    source_type_match = re.search(r"- Type: (.+)$", text, re.MULTILINE)
                    from_person_match = re.search(r"- From: (.+)$", text, re.MULTILINE)
                    source_type = source_type_match.group(1).strip() if source_type_match else ""
                    from_person = from_person_match.group(1).strip() if from_person_match else ""

                    task_map[of_id] = {
                        "ref_id": ref_id,
                        "passage_id": p.get("id", ""),
                        "text": text,
                        "tags": p.get("tags", []),
                        "source_type": source_type,
                        "from_person": from_person,
                        "has_external_origin": bool(from_person and USER_NAME not in from_person),
                    }

        if not task_map:
            return {
                "status": "ok",
                "checked": 0, "completed": 0, "dropped": 0, "not_found": 0,
                "details": [],
                "error_message": "",
            }

        # ── Step 3: Batch-check OmniFocus completion status ──
        bridge_payload = json.dumps({
            "command": "checkTaskCompletionStatus",
            "args": {"taskIds": list(task_map.keys())},
        }).encode("utf-8")
        bridge_req = urllib.request.Request(
            f"{BRIDGE_URL}/execute", data=bridge_payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(bridge_req, timeout=30) as resp:
            bridge_resp = json.loads(resp.read().decode("utf-8"))

        if not bridge_resp.get("success"):
            return {
                "status": "error",
                "checked": len(task_map), "completed": 0, "dropped": 0, "not_found": 0,
                "details": [],
                "error_message": f"Bridge call failed: {bridge_resp.get('error', 'unknown')}",
            }

        # Bridge result is double-encoded: the AppleScript evaluate
        # javascript returns a JSON string, which the bridge wraps in
        # {"success": true, "result": "<json-string>"}.
        raw_result = bridge_resp.get("result", {})
        if isinstance(raw_result, str):
            parsed = json.loads(raw_result)
            completion_statuses = parsed.get("result", parsed)
        elif isinstance(raw_result, dict):
            completion_statuses = raw_result.get("result", raw_result)
        else:
            completion_statuses = {}

        # ── Step 4: Transition completed/dropped tasks ──
        completed_count = 0
        dropped_count = 0
        not_found_count = 0
        details = []

        for of_id, status in completion_statuses.items():
            info = task_map.get(of_id)
            if not info:
                continue

            is_completed = status.get("completed", False)
            is_dropped = status.get("dropped", False)
            is_not_found = status.get("notFound", False)

            if not (is_completed or is_dropped or is_not_found):
                continue

            # Determine the action label
            if is_not_found:
                action = "not_found_in_omnifocus"
                not_found_count += 1
            elif is_dropped:
                action = "dropped"
                dropped_count += 1
            else:
                action = "completed"
                completed_count += 1

            # Apply completion transition to the passage
            old_text = info["text"]
            old_tags = list(info["tags"])
            passage_id = info["passage_id"]
            ref_id = info["ref_id"]
            new_text = old_text

            # Prefix TASK line with [COMPLETED] or [DROPPED]
            prefix = "[COMPLETED]" if (is_completed or is_not_found) else "[DROPPED]"
            task_line_match = re.search(r"^TASK: (.+)$", new_text, re.MULTILINE)
            if task_line_match:
                desc = task_line_match.group(1)
                if not desc.startswith("[COMPLETED]") and not desc.startswith("[DROPPED]"):
                    new_text = re.sub(
                        r"^TASK: .+$",
                        f"TASK: {prefix} {desc}",
                        new_text, count=1, flags=re.MULTILINE,
                    )

            # Add timestamp
            timestamp_label = "Completed" if (is_completed or is_not_found) else "Dropped"
            completion_date = status.get("completionDate") or iso_timestamp
            new_text = re.sub(
                r"(TIMESTAMPS\n(?:- .+\n)*)",
                lambda m: m.group(0) + f"- {timestamp_label}: {completion_date}\n",
                new_text, count=1,
            )

            # Update OMNIFOCUS status
            new_status = "completed" if (is_completed or is_not_found) else "dropped"
            new_text = re.sub(
                r"- Status: (extracted|confirmed)",
                f"- Status: {new_status}",
                new_text,
            )

            # Update tags
            new_tags = [t for t in old_tags if not t.startswith("status:")]
            new_tags.append(f"status:{new_status}")

            # Insert new passage first, then delete old (safer order)
            ins_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages"
            ins_data = json.dumps({"text": new_text, "tags": new_tags}).encode("utf-8")
            ins_req = urllib.request.Request(
                ins_url, data=ins_data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(ins_req, timeout=30) as resp:
                ins_resp = json.loads(resp.read().decode("utf-8"))
                new_passage_id = ins_resp.get("id", "")

            del_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{passage_id}"
            del_req = urllib.request.Request(del_url, method="DELETE")
            urllib.request.urlopen(del_req, timeout=10)

            details.append({
                "ref_id": ref_id,
                "omnifocus_id": of_id,
                "action": action,
                "task_name": status.get("name", ""),
                "new_passage_id": new_passage_id,
                "source_type": info.get("source_type", ""),
                "from_person": info.get("from_person", ""),
                "has_external_origin": info.get("has_external_origin", False),
            })

        return {
            "status": "ok",
            "checked": len(task_map),
            "completed": completed_count,
            "dropped": dropped_count,
            "not_found": not_found_count,
            "details": details,
            "error_message": "",
        }

    except Exception as e:
        return {
            "status": "error",
            "checked": 0, "completed": 0, "dropped": 0, "not_found": 0,
            "details": [],
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
