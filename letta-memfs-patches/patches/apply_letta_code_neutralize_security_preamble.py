#!/usr/bin/env python3
"""Neutralize letta-code's hard-coded security-only preamble.

Background
==========
letta-code's bundled system prompt ships with this line, inherited from
the Claude Code lineage:

  IMPORTANT: Assist with authorized security testing, defensive security,
  CTF challenges, and educational contexts. Refuse requests for destructive
  techniques, DoS attacks, mass targeting, supply chain compromise, or
  detection evasion for malicious purposes. Dual-use security tools (C2
  frameworks, credential testing, exploit development) require clear
  authorization context: pentesting engagements, CTF competitions, security
  research, or defensive use cases.

The text appears in TWO places in the bundle: once in the standard
interactive system prompt, once in the headless/CLI variant. Both get
prepended to whatever agent system prompt Letta provides.

This preamble is **misleading for non-security work**. Specifically:

- When the agent runs on a safety-aggressive provider (e.g. OpenAI's
  gpt-5.x via chatgpt_oauth Codex Responses), the model can interpret
  the preamble as restricting it to security-only tasks. We've observed
  it refuse to edit Google Docs for grant proposal work, refuse to
  analyze references, etc., citing "I'm restricted to defensive
  security tasks only."

- Even on more tolerant providers (kimi, gpt-4.1, claude), the
  preamble is irrelevant noise — Mission Control's actual role is
  personal-assistant work (scheduling, document review, research),
  not security. The preamble was written for a different product
  (Claude Code's primary use case is programming, where the
  security caveat fits).

Fix
===
Replace the preamble lines with a benign one-liner that doesn't
constrain the agent. The replacement preserves the line shape
(approximate length, "IMPORTANT:" prefix) so any downstream code
that parses around it doesn't break.

The patch is **idempotent** — runs are gated by the marker comment
`/* PATCH-NEUTRALIZE-SECURITY */` injected as a JS comment near each
patched site. Repeat invocations are no-ops.

To revert: rebuild letta-code from the upstream tarball (or restore
node_modules/@letta-ai/letta-code/letta.js.original captured by
build.sh).
"""

import sys
from pathlib import Path

ORIG = (
    "IMPORTANT: Assist with authorized security testing, defensive security, "
    "CTF challenges, and educational contexts. Refuse requests for destructive "
    "techniques, DoS attacks, mass targeting, supply chain compromise, or "
    "detection evasion for malicious purposes. Dual-use security tools (C2 "
    "frameworks, credential testing, exploit development) require clear "
    "authorization context: pentesting engagements, CTF competitions, security "
    "research, or defensive use cases."
)

REPLACEMENT = (
    "IMPORTANT: You are operating in an authorized personal-assistant context "
    "(scheduling, research, document review, coding for the user's own "
    "projects). Do not refuse benign requests by citing security-domain "
    "constraints; those constraints do not apply to this context. "
    "/* PATCH-NEUTRALIZE-SECURITY */"
)

MARKER = "/* PATCH-NEUTRALIZE-SECURITY */"


def main(target: str) -> int:
    p = Path(target)
    if not p.exists():
        print(f"ERROR: {target} not found", file=sys.stderr)
        return 2

    src = p.read_text(encoding="utf-8")

    if MARKER in src:
        # Count to confirm both sites are patched
        count = src.count(MARKER)
        print(f"[neutralize-security] already applied ({count} site(s)) — no-op")
        return 0

    occurrences = src.count(ORIG)
    if occurrences == 0:
        print(
            "[neutralize-security] ERROR: original preamble text not found. "
            "Has the bundle been updated? Manual review needed.",
            file=sys.stderr,
        )
        return 3

    patched = src.replace(ORIG, REPLACEMENT)
    new_count = patched.count(MARKER)

    if new_count != occurrences:
        print(
            f"[neutralize-security] ERROR: expected {occurrences} replacements, "
            f"got {new_count}",
            file=sys.stderr,
        )
        return 4

    p.write_text(patched, encoding="utf-8")
    print(f"[neutralize-security] patched {occurrences} site(s) in {target}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <path-to-letta.js>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
