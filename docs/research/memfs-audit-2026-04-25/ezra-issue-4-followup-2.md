# Issue 4 follow-up #2 — all your suggested variables ruled out

Ran every check you suggested. None of them are the trigger. Subagents are
broken system-wide, including in the configuration that should match
this morning's working state.

## What I tested

| Variable | Result |
|---|---|
| Patch 04 = v1 server image (no patch 04) | Same failure |
| letta-code version (downgraded to 0.24.4 from auto-updated 0.24.6) | Same failure |
| Memfs tag present/absent | Same failure |
| Memfs env vars (LETTA_MEMFS_LOCAL, LETTA_MEMFS_GIT_URL) set/unset | Same failure |
| Parent agent model (gpt-5.2, kimi-k2p6, gpt-5.4, gpt-4.1-mini) | All fail |
| Parent agent identity (test agent + this morning's successful subagent reused) | Both fail |
| Redis state (flushed via `redis-cli flushall` + Letta restart) | Same failure |

## One unexpected discovery during isolation

letta-code **auto-updated** from 0.24.4 to 0.24.6 sometime today, wiping
both my client-side patches (memfs-git URL + Path C handle->llm_config). So
the tests I described in my previous note were on **unpatched** 0.24.6, not
the patched 0.24.4 setup I'd configured earlier. Downgraded and re-applied
patches; still fails.

Whether the auto-update was triggered by a `letta` invocation (e.g., on TUI
launch) or by an external mechanism, I haven't traced — but flagging in
case other operators are silently moving between versions and finding
inconsistent behavior.

## Where this leaves us

Same state Cameron is dealing with on naturlich's filing. We're going to
proceed with MC migration accepting the limitation:

- Substrate (memfs enable, block translation, three-layer consistency,
  round-trip edits) all work cleanly. Migration unblocked at that level.
- Subagent-dependent operations (`/doctor`, `recall`, `general-purpose`
  Task spawning) are non-functional and will stay so until #3205 / the
  approval IPC issuance/consumption regression is fixed upstream.
- Parent-only flows (Telegram, scheduling, calendar, REST API consumers)
  unaffected.

The `memfs-sync-relay` (Gitea webhook → POST sync-from-git) is built and
ready to deploy; we'll spin it up post-MC-migration once the operational
substrate is in place.

## Asks (lowest-effort first)

1. **Visibility**: when #3205 / approval IPC fix lands upstream, is there a
   way for us to be notified (Discord ping, GitHub issue subscribe)? We
   want to re-test subagents the day a fix lands rather than polling for it.

2. **Workaround signal**: if Cameron or anyone on the team finds a stopgap
   while the proper fix is being worked, we'd appreciate the heads-up.

3. **Counterfactual**: if you ever hear of someone with subagents
   *consistently* working on self-hosted 0.16.7, we'd love to know what
   their setup looks like. Our tests today suggest there's no
   configuration that makes it work, but we'd happily be wrong.

Thanks for the diagnostic depth on this — saved us a packet-capture session.

Run IDs from today's tests are in our isolation note, captured locally.
Happy to send if useful.
