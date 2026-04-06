#!/usr/local/bin/python3
"""
Enrichment Conversation Reset

Weekly maintenance job: deletes the enrichment conversation and
creates a fresh one with the same label. This prevents token cost
growth from context summarization as the conversation accumulates
messages.

The scanner looks up the conversation by label at runtime, so no
env var update is needed after reset.

Registered as a weekly scheduler job (Sunday 3am).
"""

import json
import logging
import os
import sys
import urllib.request
import urllib.error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [enrichment-reset] %(levelname)s %(message)s",
)
log = logging.getLogger("enrichment-reset")

LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.environ.get("TASKS_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")
CONV_LABEL = "enrichment-pipeline"


def letta_request(method, path, data=None, timeout=15):
    """HTTP request to Letta API with redirect handling."""
    url = f"{LETTA_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            loc = e.headers.get("Location", "")
            req2 = urllib.request.Request(
                loc, data=body,
                headers={"Content-Type": "application/json"} if body else {},
                method=method,
            )
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                return json.loads(resp2.read().decode("utf-8"))
        raise


def main():
    log.info("Starting enrichment conversation reset")

    # Find existing conversation(s) by listing all for this agent
    old_conv_ids = []
    try:
        convs = letta_request("GET", f"/v1/conversations/?agent_id={AGENT_ID}")
        if isinstance(convs, list):
            for c in convs:
                cid = c.get("id", "")
                # Check by label if available, otherwise by env fallback
                if c.get("label") == CONV_LABEL:
                    old_conv_ids.append(cid)
            # Also check env var as fallback
            env_id = os.environ.get("ENRICHMENT_CONV_ID", "")
            if env_id and env_id not in old_conv_ids:
                old_conv_ids.append(env_id)
    except Exception as e:
        log.warning(f"Failed to list conversations: {e}")
        # Try env var
        env_id = os.environ.get("ENRICHMENT_CONV_ID", "")
        if env_id:
            old_conv_ids.append(env_id)

    # Delete old conversation(s)
    for cid in old_conv_ids:
        try:
            letta_request("DELETE", f"/v1/conversations/{cid}")
            log.info(f"Deleted conversation {cid}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log.info(f"Conversation {cid} already deleted")
            else:
                log.warning(f"Failed to delete conversation {cid}: {e.code}")
        except Exception as e:
            log.warning(f"Failed to delete conversation {cid}: {e}")

    # Create new conversation with same label
    try:
        new_conv = letta_request("POST", f"/v1/conversations/?agent_id={AGENT_ID}", {"label": CONV_LABEL})
        new_id = new_conv.get("id", "?")
        log.info(f"Created new conversation: {new_id}")
    except Exception as e:
        log.error(f"Failed to create new conversation: {e}")
        sys.exit(1)

    # Update the enrichment scanner job with the new conversation ID.
    # Letta doesn't persist labels, so the scanner relies on the env var.
    SCHEDULER_BASE = os.environ.get("SCHEDULER_URL", "http://localhost:8087/v1")
    SCANNER_JOB_ID = os.environ.get("SCANNER_JOB_ID", "3f93c9a4-2fbf-4547-8325-8b66e241e92e")

    try:
        # Read current job to get existing env vars
        job_url = f"{SCHEDULER_BASE}/jobs/{SCANNER_JOB_ID}"
        job_req = urllib.request.Request(job_url)
        with urllib.request.urlopen(job_req, timeout=15) as resp:
            job = json.loads(resp.read())

        actions = job.get("actions", [])
        if actions:
            env = actions[0].get("config", {}).get("env", {})
            env["ENRICHMENT_CONV_ID"] = new_id
            actions[0]["config"]["env"] = env

            update_data = json.dumps({"actions": actions}).encode()
            update_req = urllib.request.Request(
                job_url,
                data=update_data,
                headers={"Content-Type": "application/json"},
                method="PATCH",
            )
            urllib.request.urlopen(update_req, timeout=15)
            log.info(f"Updated scanner job {SCANNER_JOB_ID} with new ENRICHMENT_CONV_ID={new_id}")
    except Exception as e:
        log.error(f"Failed to update scanner job with new conversation ID: {e}")
        log.error("Scanner will use stale conversation ID until manually updated!")

    log.info("Enrichment conversation reset complete")


if __name__ == "__main__":
    main()
