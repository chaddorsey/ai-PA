# Quick follow-up to Issue 4 — workaround question

Confirmed your diagnosis. Ran a series of isolation tests; every variable
checks out as ruled out:

- Memfs tag presence/absence: same failure
- Memfs env vars present/absent: same failure
- Parent model (kimi-k2p6, gpt-5.4, gpt-4.1-mini): same failure
- Parent agent identity (test agent + this morning's successful subagent
  reused as a parent): both fail identically
- `composeSubagentChildEnv` correctly inherits parent env via spread

So it's system-wide on this stack, exactly as you described — same bug class
as naturlich's filing.

**One question before we pivot to investigating ourselves:**

Earlier today (06:43 UTC) Task subagents *worked* on this same self-hosted
0.16.7 stack — `task_4.log` and `task_5.log` show clean
`subagent_status=success` runs that produced real persistent subagent agents
(still in the DB tagged `role:subagent, type:general-purpose`,
`agent-8f885655-...` and `agent-6bd40f17-...`). The Letta server restarted
at ~16:58 with our v2 patched image (only added a refinement to Fimeg
patch 02), and subagents have been broken in every test since.

The fact that subagents worked at 06:43 and broke after a restart suggests
the bug isn't fully deterministic — possibly state-dependent, possibly
something the v1 server image had that v2 doesn't (or that the restart
itself cleared). If you have any signal on:

- A specific server version that's known to have working subagents on
  self-hosted (we could downgrade temporarily)
- A server config flag that affects approval IPC behavior
- Anything state-dependent that the v1 image accumulated and v2 didn't
  re-create

…that would be enormously helpful. If not, no worries — we'll start packet-
capturing the subagent's first client_tool API exchange to figure out
whether we're crashing on issuance side or consumption side.

Run IDs and per-test repro details are in the isolation note (committed
locally; happy to send the file if useful).
