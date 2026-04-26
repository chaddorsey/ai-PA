# Memfs migration follow-up — Issue 2 reframed, Issue 4 surfaced

Quick follow-up to my Apr 25 defects note (the one with run IDs for the
calendar-agent /doctor loop and the Letta Code agent's TaskOutput
hallucinations). Ran the model-comparison test you suggested — partially
inverts what we thought, and surfaces a new defect that's more important than
Issue 2.

## Method

Single throwaway test agent (Letta Code, `letta_v1_agent`,
`origin:letta-code` tag, currently `gpt-5.2`). PATCHed `llm_config.model`
and `.handle` between three models, all routed via litellm to match MC's
invocation pattern. For each: headless `letta -p "..." --yolo` with a clean
Task→TaskOutput exchange. Restored `gpt-5.2` after.

| Pass | Model | Task chain | Subagent execution |
|---|---|---|---|
| 1 | claude-sonnet-4-6 | (Anthropic credit exhausted upstream — couldn't test) | n/a |
| 2 | **kimi-k2p6 (MC's actual model)** | **Clean. Real Task call, real subagent ID returned, TaskOutput chained correctly. No hallucination.** | "Failed to parse subagent output: Unexpected end of JSON input" |
| 3 | gpt-5.4 | Clean. Real ID `subagent-1777164606213-1`. | Same subagent failure. |

## Issue 2 reframe (good news for the model question)

**Task→TaskOutput hallucination is not a kimi-k2p6 problem.** MC's actual
model handles the Task contract correctly. The earlier hallucinations on
gpt-5.2 were either model-specific or TUI-specific — both kimi-k2p6 and
gpt-5.4 consistently produced real Task calls with real subagent IDs in
headless `--yolo`.

So MC migration does NOT need a model swap as a prerequisite. Thank you —
this saves a substantial chunk of work.

## Issue 4 — subagent runtime failure on self-hosted (the real blocker)

Both successful Task chains hit the same subagent failure: subagent process
spawns, parent receives a real subagent ID back from Task, then TaskOutput
returns `Failed to parse subagent output: Unexpected end of JSON input`.
Located at `letta.js:72562` in `parseResultFromStdout` — parent expects
the subagent's stdout last line to be `{type: "result", ...}`; getting
empty/malformed output means the subagent crashed early.

This is the same mechanism `/doctor`'s `context_doctor` skill depends on —
it spawns analyzer subagents via Task. So `/doctor` is still broken
end-to-end on our setup, just for a different reason than I diagnosed
earlier (not persona, not model — subagent runtime).

Reproducible across two different models (kimi-k2p6 + gpt-5.4) on the same
agent in the same session. Consistent with subagent process startup failing
before it can produce a `result` line.

**Questions:**
- Is subagent runtime supposed to work on self-hosted (Letta 0.16.7
  patched + letta-code 0.24.4 host install)? Specifically: does the child
  letta-code process spawned by Task inherit the parent's env vars
  (`LETTA_BASE_URL`, `LETTA_MEMFS_LOCAL`, `LETTA_MEMFS_GIT_URL`)? If not,
  the subagent can't reach Letta and would crash on first API call.
- Is there known incompatibility between the Task subagent runtime and
  Fimeg's external-memfs setup (e.g., the subagent expects to talk to
  Letta's `/v1/git/...` endpoints which we route to Gitea instead)?
- What does a successful subagent execution look like in your test
  environment? Any specific config or env we might be missing?

I'm going to capture the subagent's stderr/stdout directly next to narrow
down the cause, but if there's a known answer, that'd save the dig.

## Quick acknowledgments

- Issue 1 (persona Skill awareness) — drafted Option A snippet, will apply
  to MC pre-migration. **Confirmed by direct inspection that MC's
  `assistant_role_playbook` has 0 mentions of "skill"/"doctor"/
  "context_doctor"** despite the `origin:letta-code` tag — so the snippet
  is mandatory, not optional.
- Issue 3 (sync-from-git on-demand) — built a small Gitea-webhook→sync
  relay per your recommended pattern. Single-file Python service, HMAC
  verification, runs on the `pa-internal` network. Will deploy once Issue 4
  is sorted (no point routing webhooks to a server whose sync pathway
  hasn't been validated end-to-end).

## What I'd love from you

Whether Issue 4 is known, self-hosted-specific, fixable on my end via env
propagation, or genuinely upstream. If you have a known-good subagent test
recipe (model + agent type + env config) that runs end-to-end on a Letta
self-hosted instance, that'd be the most useful single piece of guidance —
gives me a target to converge on.

Run IDs for forensic review (still on disk if you want them):

- `run-9dad9a9d-...` and adjacent — kimi-k2p6 Task test passes (subagent
  failure, see /tmp/task-test-kimi-k2p6.json captured)
- `run-3d02af86-...` and adjacent — gpt-5.4 Task test passes (subagent
  failure with subagent ID `subagent-1777164606213-1`)
