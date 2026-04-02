"""
Process Spark Queue Tool for Letta

Deterministic tool that reads the spark_queue block, extracts tasks
from each JSON Spark Record, and clears the queue. No LLM reasoning
needed for parsing — the tool handles block I/O and calls
add_extracted_tasks via API for each spark.

Tool: process_spark_queue
"""

from typing import Dict, Any, Optional


def process_spark_queue(dry_run: Optional[str] = None) -> Dict[str, Any]:
    """
    Process all pending Spark Records in the spark_queue memory block.

    Reads each JSON entry from the block, calls add_extracted_tasks for each,
    then clears the queue. This is deterministic — no LLM reasoning needed
    for parsing or field mapping.

    For sparks with fetch_hint (e.g. emails), the tool includes the fetch_hint
    in the output so the agent can decide whether to fetch full content. For
    sparks with self-contained source_text (Slack, Docs comments), extraction
    proceeds directly.

    Args:
        dry_run: If "true", parse and report sparks without extracting. Useful for debugging.

    Returns:
        Dictionary with status, extracted count, and details for each spark.
    """
    import json
    import os
    import re
    import traceback
    import urllib.request
    import urllib.error
    import uuid
    from datetime import datetime

    try:
        LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        SPARK_BLOCK_ID = "block-534bb56d-f7f1-4ea4-b2d9-20dc75eca03a"
        ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
        is_dry_run = dry_run and dry_run.lower() == "true"

        # ── Read spark_queue block ──
        block_url = f"{LETTA_BASE}/v1/blocks/{SPARK_BLOCK_ID}"
        req = urllib.request.Request(block_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            block_data = json.loads(resp.read().decode("utf-8"))

        block_value = block_data.get("value", "")

        if "(empty)" in block_value or len(block_value.strip()) < 30:
            return {"status": "ok", "message": "Spark queue is empty", "extracted": 0, "details": []}

        # ── Parse JSON entries ──
        # Split by --- separator, strip header lines (# Spark Queue)
        segments = [e.strip() for e in block_value.split("---") if e.strip()]
        raw_entries = []
        for seg in segments:
            # Strip header lines starting with #
            lines = [l for l in seg.split("\n") if l.strip() and not l.strip().startswith("#")]
            content = "\n".join(lines).strip()
            if content:
                raw_entries.append(content)

        sparks = []
        parse_errors = []
        for i, raw in enumerate(raw_entries):
            try:
                spark = json.loads(raw)
                sparks.append(spark)
            except json.JSONDecodeError as e:
                parse_errors.append({"index": i, "error": str(e), "text": raw[:100]})

        if not sparks and parse_errors:
            return {
                "status": "error",
                "message": f"No valid JSON entries found. {len(parse_errors)} parse errors.",
                "parse_errors": parse_errors,
                "extracted": 0,
            }

        if is_dry_run:
            summaries = []
            for s in sparks:
                summaries.append({
                    "spark_id": s.get("spark_id"),
                    "source_type": s.get("source_type"),
                    "location": s.get("location"),
                    "from_person": s.get("from_person"),
                    "task_hint": s.get("task_hint"),
                    "fetch_hint": s.get("fetch_hint"),
                    "has_source_text": bool(s.get("source_text")),
                })
            return {
                "status": "ok",
                "message": f"Dry run: {len(sparks)} spark(s) found",
                "dry_run": True,
                "sparks": summaries,
                "extracted": 0,
            }

        # ── Get agent info for block updates ──
        try:
            import pytz
            tz = pytz.timezone("America/New_York")
        except ImportError:
            from datetime import timezone, timedelta
            tz = timezone(timedelta(hours=-4))

        now = datetime.now(tz)
        timestamp_str = now.strftime("%Y-%m-%d %H:%M")
        iso_timestamp = now.isoformat()
        year_month = now.strftime("%Y-%m")

        # Get agent name and ID
        AGENT_ID = os.environ.get("LETTA_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")
        agent_name = "tasks-agent"
        if AGENT_ID:
            try:
                areq = urllib.request.Request(f"{LETTA_BASE}/v1/agents/{AGENT_ID}/")
                with urllib.request.urlopen(areq, timeout=10) as aresp:
                    adata = json.loads(aresp.read().decode("utf-8"))
                    agent_name = adata.get("name", agent_name)
            except Exception:
                pass

        # ── Extract each spark ──
        results = []
        for spark in sparks:
            spark_id = spark.get("spark_id", "?")
            source_type = spark.get("source_type", "unknown")
            origin = spark.get("origin", "agent-identified")

            # Determine task description
            task_hint = spark.get("task_hint")
            source_text = spark.get("source_text", "")
            fetch_hint = spark.get("fetch_hint")

            if task_hint and len(task_hint) > 10:
                # User provided explicit task hint — use it
                task_desc = task_hint
                # Capitalize first letter
                if task_desc and task_desc[0].islower():
                    task_desc = task_desc[0].upper() + task_desc[1:]
            elif fetch_hint:
                # Need full content — extract a placeholder from what we have
                location = spark.get("location", "")
                task_desc = f"Review and process: {location}" if location else "Process email task (fetch full content)"
            else:
                # Use source_text to formulate
                # Take first meaningful line
                lines = [l.strip() for l in source_text.split("\n") if l.strip() and not l.startswith("Comment:") and not l.startswith("Quoted")]
                if lines:
                    first_line = lines[0][:120]
                    task_desc = f"Review: {first_line}" if not first_line[0].isupper() else first_line
                else:
                    task_desc = f"Process task from {source_type}"

            # Strip common prefixes
            task_desc = re.sub(r"^(Fwd:|Re:|FW:)\s*", "", task_desc).strip()

            ref_id = uuid.uuid4().hex[:8]
            from_person = spark.get("from_person", "")
            location = spark.get("location", "")
            location_id = spark.get("location_id", "")
            reference_id = spark.get("reference_id", "")
            related_urls = spark.get("related_urls", [])
            captured_at = spark.get("captured_at", iso_timestamp)

            # Build estimate (simple heuristic)
            estimate = 15  # default
            if task_hint and len(task_hint) < 30:
                estimate = 5
            elif source_type == "google-docs-comment":
                estimate = 10

            # ── Write to extracted_tasks block ──
            try:
                # Get current block
                et_block_id = None
                areq2 = urllib.request.Request(f"{LETTA_BASE}/v1/agents/{AGENT_ID}/")
                with urllib.request.urlopen(areq2, timeout=10) as aresp2:
                    adata2 = json.loads(aresp2.read().decode("utf-8"))
                    for blk in adata2.get("memory", {}).get("blocks", []):
                        if blk.get("label") == "extracted_tasks":
                            et_block_id = blk["id"]
                            current_val = blk["value"]
                            break

                if not et_block_id:
                    results.append({"spark_id": spark_id, "status": "error", "error": "extracted_tasks block not found"})
                    continue

                origin_part = f"; origin: {origin}" if origin else ""
                task_line = f"[extracted_time: {timestamp_str}; ref_id: {ref_id}{origin_part}; est: {estimate}] {task_desc}\n"

                section_header = f"=== {agent_name} ({AGENT_ID}) ==="
                section_pattern = re.compile(
                    rf'({re.escape(section_header)})(.*?)(?=(===\s+.+?\s+\(agent-[a-f0-9-]+\)\s+===)|$)',
                    re.DOTALL,
                )
                section_match = section_pattern.search(current_val)

                if section_match:
                    insert_pos = section_match.end()
                    before = current_val[:insert_pos]
                    after = current_val[insert_pos:]
                    if before and not before.endswith("\n"):
                        before += "\n"
                    new_val = before + task_line + after
                else:
                    new_val = current_val + f"\n{section_header}\n{task_line}"

                update_data = json.dumps({"value": new_val}).encode("utf-8")
                update_req = urllib.request.Request(
                    f"{LETTA_BASE}/v1/blocks/{et_block_id}",
                    data=update_data,
                    headers={"Content-Type": "application/json"},
                    method="PATCH",
                )
                urllib.request.urlopen(update_req, timeout=10)

            except Exception as e:
                results.append({"spark_id": spark_id, "status": "error", "error": f"Block write failed: {str(e)}"})
                continue

            # ── Write archival passage ──
            urls_section = ""
            if related_urls:
                urls_section = "\nRELATED URLS\n" + "\n".join(f"- {u}" for u in related_urls) + "\n"

            passage_text = (
                f"TASK: {task_desc}\n"
                f"REF_ID: {ref_id}\n"
                f"ORIGIN: {origin}\n\n"
                f"TASK METADATA\n"
                f"- Estimate: {estimate}\n"
                f"- Agent Estimate: {estimate}\n\n"
                f"SOURCE REFERENCE\n"
                f"- Type: {source_type}\n"
                f"- Context: {spark.get('source_context', location)}\n"
                f"- Reference ID: {reference_id}\n\n"
                f"SOURCE METADATA\n"
                f"- Timestamp: {captured_at}\n"
                f"- From: {from_person}\n"
                f"- Location: {location}\n"
                f"- Location ID: {location_id}\n"
                f"{urls_section}\n"
                f"TIMESTAMPS\n"
                f"- Source: {captured_at}\n"
                f"- Extracted: {iso_timestamp}\n"
                f"- OmniFocus: pending\n\n"
                f"OMNIFOCUS\n"
                f"- Task ID: pending\n"
                f"- Status: extracted\n\n"
                f"SOURCE TEXT\n"
                f"{source_text}"
            )

            if fetch_hint:
                passage_text += f"\n\nFETCH HINT: {fetch_hint}"

            tags = [
                f"source:{source_type}",
                year_month,
                "status:extracted",
                f"origin:{origin}",
                f"agent:{AGENT_ID}",
            ]

            try:
                arch_data = json.dumps({"text": passage_text, "tags": tags}).encode("utf-8")
                arch_req = urllib.request.Request(
                    f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages",
                    data=arch_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(arch_req, timeout=30)
            except Exception as e:
                results.append({
                    "spark_id": spark_id,
                    "status": "partial",
                    "error": f"Block written but archival failed: {str(e)}",
                    "ref_id": ref_id,
                    "task": task_desc,
                })
                continue

            results.append({
                "spark_id": spark_id,
                "status": "ok",
                "ref_id": ref_id,
                "task": task_desc,
                "source_type": source_type,
                "fetch_hint": fetch_hint,
            })

        # ── Clear spark queue ──
        try:
            clear_data = json.dumps({"value": "# Spark Queue\n(empty)"}).encode("utf-8")
            clear_req = urllib.request.Request(
                block_url,
                data=clear_data,
                headers={"Content-Type": "application/json"},
                method="PATCH",
            )
            urllib.request.urlopen(clear_req, timeout=10)
        except Exception:
            pass  # Non-critical — cron will catch stale entries

        extracted_count = len([r for r in results if r["status"] == "ok"])

        return {
            "status": "ok",
            "message": f"Processed {len(sparks)} spark(s), extracted {extracted_count} task(s)",
            "extracted": extracted_count,
            "details": results,
            "parse_errors": parse_errors if parse_errors else None,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
            "extracted": 0,
        }
