#!/usr/bin/env python3
"""Apply the empty-approvals subprocess-survival patch to a bundled letta.js.

Background
==========
letta-code 0.23.x and 0.24.x (verified up through 0.24.10 as of 2026-04-29)
contain this code path inside the headless-mode run loop:

  if (stopReason === "requires_approval") {
    if (approvals.length === 0) {
      console.error("Unexpected empty approvals array");
      await exitHeadless(1, "headless_requires_approval_empty");
    }
    const { autoAllowed, autoDenied, needsUserInput } =
      await classifyApprovals(approvals, {...});
    ...
  }

When the Letta server emits stop_reason=requires_approval but the streaming
response's approvals array comes back empty, letta-code panics and KILLS
the subprocess with exit code 1. The Letta server is then left holding a
dangling approval_request_message that nothing ever resolves; the run sits
"completed" with stop_reason=requires_approval; the agent appears stalled.

This is a real bug. It fires reliably on certain tool calls (Skill, Task,
sometimes Bash) when invoked via pa-web-ui's headless letta-code subprocess.
Documented at length in:
  - docs/diagnoses/letta-code-empty-approvals.md (this repo)
  - pa-web-ui/approval_responder.py (the workaround on our side)

Our pa-web-ui ships an `approval_responder.py` that detects
approval_request_message events and POSTs an `ApprovalCreate` directly to
the Letta API (`POST /v1/agents/{id}/messages` with `messages: [{type:
"approval", approvals: [...]}]`). The server resumes the run. BUT — if the
subprocess has already died from this bug by the time our POST lands, the
resumed stream output goes to a dead consumer and the user sees dead-air.

The fix here keeps the subprocess alive long enough for pa-web's responder
to do its job. Three behavioral changes:

1. Replace `exitHeadless(1, "headless_requires_approval_empty")` with a
   3-second wait + `continue` (outer-loop re-iterate). This gives pa-web's
   responder time to POST the approval before letta-code retries.
2. The next loop iteration calls `drainStreamWithResume` again, which can
   resume a run by ID. By then the Letta server has applied our POST and
   has fresh stream chunks (approved tool output) to send. The subprocess
   consumes them and continues.
3. We add a small ATTEMPTS counter so this can't loop forever. After 5
   retries, we fall through to a benign log+break instead of exitHeadless
   (which would have killed the subprocess) — pa-web sees a clean
   stop_reason and chat.js can render an "agent stopped" state instead of
   a crash.

Verification: marker `[PATCH-EMPTY-APPROVALS]` appears at least 2 times in
the patched bundle (once in the replaced code path, once in the comment).

Idempotent. Atomic write. Preserves file mode.

Usage:
    python3 apply_letta_code_empty_approvals_fix.py [path/to/letta.js]
Default path: /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js

Provenance / upstream report
============================
Filed against letta-code by Concord Consortium PA team, 2026-04-29.
The full diagnosis chain (race-loss vs subprocess-crash; pa-web responder;
this letta.js patch) is checked into:
  - pa-web-ui/approval_responder.py (the responder + classifier)
  - pa-web-ui/tests/test_approval_responder.py (unit tests for both)
  - docs/diagnoses/letta-code-empty-approvals.md (the full writeup)
A reproduction can be made by sending any user message to a self-hosted
Letta agent that triggers a tool with stop_reason=requires_approval and
where the streaming response returns empty approvals[]. Tool name doesn't
matter — Skill, Task, and Bash have all reproduced it for us.

The upstream-friendly fix would be: when approvals[] is empty,
letta-code should fetch the run's current state from the API to check
for approval_request_messages it can derive approvals from, OR wait for
a control_request to be issued from the server side, instead of treating
the empty array as a fatal client-side error.
"""
import os
import shutil
import stat
import sys

DEFAULT_PATH = "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js"

OLD_BLOCK = '''      if (stopReason === "requires_approval") {
        if (approvals.length === 0) {
          console.error("Unexpected empty approvals array");
          await exitHeadless(1, "headless_requires_approval_empty");
        }'''

NEW_BLOCK = '''      if (stopReason === "requires_approval") {
        if (approvals.length === 0) {
          // [PATCH-EMPTY-APPROVALS] Replaced upstream exitHeadless(1,...)
          // with a wait+continue so the subprocess survives long enough
          // for an external resolver (e.g., pa-web-ui/approval_responder.py)
          // to POST an ApprovalCreate to the Letta API. The next outer
          // loop iteration's drainStreamWithResume will pick up the
          // resumed run output. See:
          //   letta-memfs-patches/patches/apply_letta_code_empty_approvals_fix.py
          if (typeof globalThis.__pa_empty_approvals_attempts === "undefined") {
            globalThis.__pa_empty_approvals_attempts = 0;
          }
          globalThis.__pa_empty_approvals_attempts += 1;
          console.error(
            "[PATCH-EMPTY-APPROVALS] empty approvals[]; waiting 3s for external resolver (attempt " +
            globalThis.__pa_empty_approvals_attempts + "/5)"
          );
          if (globalThis.__pa_empty_approvals_attempts >= 5) {
            console.error("[PATCH-EMPTY-APPROVALS] giving up after 5 attempts; ending turn cleanly");
            globalThis.__pa_empty_approvals_attempts = 0;
            break;
          }
          await new Promise((r) => setTimeout(r, 3000));
          continue;
        } else {
          // Reset the counter on any successful approval cycle.
          globalThis.__pa_empty_approvals_attempts = 0;
        }'''


def main(path=None):
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        print(f"ERROR: bundle not found at {path}", file=sys.stderr)
        return 2

    src = open(path, "r", encoding="utf-8").read()

    # Idempotency check
    if "[PATCH-EMPTY-APPROVALS]" in src:
        print(f"already patched: {path}")
        return 0

    if OLD_BLOCK not in src:
        print(
            f"ERROR: anchor for empty-approvals block not found in {path}.\n"
            "       The bundle's shape may have changed in this letta-code version.",
            file=sys.stderr,
        )
        return 3

    out = src.replace(OLD_BLOCK, NEW_BLOCK)

    # Atomic write preserving file mode
    tmp_path = path + ".empty-approvals.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(out)
    src_mode = stat.S_IMODE(os.stat(path).st_mode)
    os.chmod(tmp_path, src_mode)
    shutil.move(tmp_path, path)

    # Verify marker appears
    n = open(path, "r", encoding="utf-8").read().count("[PATCH-EMPTY-APPROVALS]")
    if n < 2:
        print(
            f"WARN: marker found {n} times (expected >= 2). Patch may have applied but verification is loose.",
            file=sys.stderr,
        )
    print(f"patched: {path} ({n} markers)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
