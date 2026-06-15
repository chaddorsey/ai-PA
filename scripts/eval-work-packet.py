#!/usr/bin/env python3
"""Evaluate OmniFocus work-packet note fidelity for one or more tasks (READ-ONLY).

For each ref_id it pulls:
  - the task detail + packet_info from pa-web-ui (GET /api/tasks/<ref_id>)
  - the LIVE OmniFocus note via the host bridge (getTask)
and reports fidelity flags:
  - encoding corruption (U+FFFD / mojibake)
  - literal "\\n" in the note (unrendered newlines)
  - doubled list bullets ("• •")
  - RICHNESS: which non-empty packet_info fields actually made it into the note

Usage:
  python3 scripts/eval-work-packet.py [ref_id ...]
  (no args = the 3 standing evaluation tasks)

Env: PA_WEB_BASE (default http://localhost:5200), OF_BRIDGE (default http://127.0.0.1:8889)
"""
import json
import os
import re
import sys
import urllib.request

PA_WEB = os.environ.get("PA_WEB_BASE", "http://localhost:5200")
BRIDGE = os.environ.get("OF_BRIDGE", "http://127.0.0.1:8889")
EVAL_SET = ["19e93fe4", "3d69358e-a", "meeting-not_jlLav4yZFqNMBh-chad-3"]

PACKET_FIELDS = [
    "direct_action", "artifact_provenance", "intent_genesis", "context_brief",
    "knowns", "unknowns", "resources", "related_tasks", "suggested_subtasks",
    "agent_notes", "mismatch_warning",
]


def _get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def _bridge_get_note(of_id):
    body = json.dumps({"command": "getTask", "args": {"taskId": of_id}}).encode()
    req = urllib.request.Request(BRIDGE + "/execute", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    res = data.get("result", data)
    if isinstance(res, str):
        res = json.loads(res)
    res = res.get("result", res)
    return res.get("note", "") if isinstance(res, dict) else ""


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _field_probe(v):
    """A representative text chunk for a packet_info field, for note-presence matching."""
    if v is None:
        return None
    if isinstance(v, list):
        if not v:
            return None
        first = v[0]
        return first if isinstance(first, str) else json.dumps(first)
    if isinstance(v, dict):
        return json.dumps(v) if v else None
    s = str(v).strip()
    return s or None


def evaluate(ref_id):
    out = [f"\n{'='*72}\nref_id: {ref_id}"]
    try:
        detail = _get_json(f"{PA_WEB}/api/tasks/{ref_id}")
    except Exception as e:
        out.append(f"  ERROR fetching detail: {e}")
        return "\n".join(out)
    if "error" in detail:
        out.append(f"  ERROR: {detail['error']}")
        return "\n".join(out)

    of = detail.get("omnifocus") or {}
    of_id = of.get("task_id")
    pi = detail.get("packet_info") or {}
    out.append(f"  task   : {(detail.get('task') or '')[:78]}")
    out.append(f"  status : {detail.get('status')}   of_id: {of_id}")

    note = ""
    if of_id and of_id != "pending":
        try:
            note = _bridge_get_note(of_id)
        except Exception as e:
            out.append(f"  ERROR fetching OF note: {e}")
    else:
        out.append("  (not promoted to OmniFocus — no note)")

    # --- Fidelity flags on the note ---
    out.append("  --- note fidelity ---")
    ffffd = note.count("�")
    moji = len(re.findall(r"[âÃ][\x80-\xbf�]", note))
    out.append(f"  encoding   : {'FAIL' if (ffffd or moji) else 'ok'}  (U+FFFD={ffffd}, mojibake-pairs={moji})")
    lit_nl = note.count("\\n")
    out.append(f"  literal \\n : {'FAIL' if lit_nl else 'ok'}  (count={lit_nl})")
    dbl = len(re.findall(r"[•\-]\s*[•\-]\s", note))
    out.append(f"  dbl bullets: {'FAIL' if dbl else 'ok'}  (count={dbl})")
    out.append(f"  note length: {len(note)} chars")

    # --- Richness: which populated packet_info fields reached the note? ---
    out.append("  --- richness (packet_info field -> in note?) ---")
    nnote = _norm(note)
    present = missing = empty = 0
    for f in PACKET_FIELDS:
        probe = _field_probe(pi.get(f))
        if not probe:
            out.append(f"    {f:20s}: (empty)")
            empty += 1
            continue
        chunk = _norm(probe)[:24]
        if chunk and chunk in nnote:
            out.append(f"    {f:20s}: IN NOTE")
            present += 1
        else:
            out.append(f"    {f:20s}: *** MISSING FROM NOTE ***   probe={probe[:50]!r}")
            missing += 1
    out.append(f"  richness summary: {present} in-note, {missing} missing, {empty} empty")
    return "\n".join(out)


def main():
    ids = sys.argv[1:] or EVAL_SET
    print(f"Work-packet note fidelity eval  (PA_WEB={PA_WEB}, BRIDGE={BRIDGE})")
    for rid in ids:
        print(evaluate(rid))


if __name__ == "__main__":
    main()
