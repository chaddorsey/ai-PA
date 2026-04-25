# Memfs migration rehearsal defects — paste-ready for Ezra

Hey — running through migration rehearsal on self-hosted Letta 0.16.7 + patched
letta-code 0.24.4. Substrate-level mechanics work, but enough surface-area
defects came up that I'm pausing migration of real agents until we can confirm
behavior. Three concrete issues, asking for your read on whether they're known,
specific to my stack, or fixable by changes on my side.

## Setup

- Letta server: 0.16.7 with Fimeg patches 1-3 + a local refinement to scope
  patch-02 delete propagation per-agent (avoids global hard-delete of shared
  blocks in multi-agent ecosystems — happy to share separately if useful)
- letta-code: 0.24.4, host-installed via npm, with the bundled `memoryGit.ts`
  patch applied (`apply_letta_code_memfs_external_git.py`) so it routes git ops
  to my self-hosted Gitea via `LETTA_MEMFS_GIT_URL`
- Env to invoke: `LETTA_MEMFS_LOCAL=1` + `LETTA_BASE_URL=http://localhost:8283`
  + `LETTA_MEMFS_GIT_URL='http://USER:TOKEN@127.0.0.1:3030/agents/{agentId}.git'`
- Test agents: two — calendar-agent (`memgpt_v2_agent`, gpt-4.1-mini via
  litellm, domain-specific persona) and a "Letta Code" agent
  (`letta_v1_agent` + `origin:letta-code` tag, gpt-5.2 via litellm,
  letta-code-paradigm persona)

## Issue 1 — `/doctor` fails on personas without explicit Skill awareness

**Repro**: open `memgpt_v2_agent` with a domain-specific persona in TUI,
`/memfs enable` (works), `/doctor`.

`buildDoctorMessage` injection (line 83960 in 0.24.4) fires correctly — agent
receives the standard "Use the Skill tool with skill: 'context_doctor'"
template. **Agent doesn't invoke Skill** — falls back to web_search and loops
to max_steps (151 messages, run-33531d33-...).

I read the bundled `context_doctor` skill. The doctor template tells the agent
to invoke Skill, but the agent's persona has zero language about Skill tool
existence — it's a calendar/scheduling persona. With no priming, the agent
treats `/doctor` as a vague task and reaches for the only general-purpose tool
it knows: web_search.

**Question**: is there a recommended persona snippet you ship for "any agent
should know how to handle /doctor"? Or is the assumption that all agents that
get migrated to memfs already have letta-code-paradigm personas with Skill
awareness baked in? If the latter, MC migration needs a persona update *before*
`/memfs enable` for `/doctor` to be usable post-migration. Happy to add Option
A (persona language directing Skill invocation) but want to confirm that's the
intended approach versus something I'm missing.

## Issue 2 — `/doctor` fails again on a letta-code-native persona via Task→TaskOutput hallucination

This is the more concerning one because it failed on the agent type we'd
expect to work cleanly.

**Repro**: open `letta_v1_agent` + `origin:letta-code` tag, `/memfs enable`
(works), `/doctor`.

- Doctor template injected ✓
- Agent invokes `Skill(skill: "context_doctor")` ✓ (exactly what should happen)
- `context_doctor` skill loads and instructs the agent to spawn analyzer
  subagents via Task and read their output via TaskOutput
- **Agent calls `TaskOutput(non-blocking)` with hallucinated IDs** — `task_1`,
  `task_2`, `task_1.log`, `subagent-persona-first5` — instead of real
  Task-returned IDs
- These IDs look like Claude-Code-style training-data patterns; they're not
  the runtime IDs Task actually returns

In one earlier `/doctor` run I did see real-looking IDs come through
(`subagent-1776661684849-1` and `-2` with unix timestamps), so Task DOES spawn
subagents at least sometimes. But the agent's polling loop intermittently
skips Task entirely and just makes up IDs that look plausible.

I isolated this with a direct prompt outside `/doctor`:

> Use the Task tool to spawn a general-purpose subagent with the prompt:
> "Read system/persona.md and reply with just the first 5 words of the file."
> Wait for it to finish and show me its output.

The agent's reasoning trace explicitly said "I'll call Task and wait for the
output," but it never called Task — went straight to three TaskOutput calls
with invented IDs (subagent-persona-first5, task_persona_first5, task_1) and
then gave up.

**Speculation**: tool-definition ordering in the agent's context, or a system
prompt that lets the agent confuse "predict an ID" with "use the returned ID
from a prior Task call." Possibly model-specific — gpt-5.2 might be more prone
to this than the models you typically test against.

**Questions**:
- Is this a known issue in 0.24.4? You mentioned working on `/doctor` a lot
  recently — what does success normally look like?
- Is there a Task→TaskOutput protocol contract I could check (e.g. is the
  returned task_id supposed to be in a structured field, or in prose, that
  some models might miss)?
- Is there a recommended way to test Task in isolation against self-hosted
  before depending on it for `/doctor`? My headless `letta -p` test showed
  Task is at least *registered* (it returned a "Tool requires approval
  (headless mode)" denial when called), but I haven't been able to validate
  end-to-end Task subagent execution in either TUI or headless yet on my
  setup.

## Issue 3 — write path requires manual `sync-from-git`

**Repro**: in TUI, edit a `system/*.md` file via the Edit tool. Verify
propagation to all four layers.

What I see:
- ✓ Local working tree (`~/.letta/agents/<id>/memory/`) updated
- ✓ Gitea remote receives the push
- ✗ Server bare repo at `/root/.letta/memfs/repository/<org>/<id>/repo.git`
  stays at the prior commit
- ✗ Postgres block cache (queried via REST `GET /v1/agents/<id>/core-memory/blocks`)
  returns stale content

To get the bare repo and Postgres caught up, I have to explicitly POST
`/v1/agents/<id>/memory/sync-from-git`. Then everything converges.

Implication: any non-letta-code consumer of the agent's memory (in my case
pa-routing-handler, slackbot, pa-web-ui's task review sidebar — all hit REST
directly) sees stale content until something triggers sync-from-git.

**Questions**:
- Does letta-code 0.24.4 trigger `sync-from-git` automatically on session
  exit, or is the post-edit sync intentionally on-demand?
- If on-demand, what's the recommended cadence for production deployments?
  Cron-style every-N-minutes, post-edit hook in letta-code, agent-side trigger,
  or something else?
- Is there a way to subscribe to Gitea push notifications and trigger
  sync-from-git server-side automatically? I'd rather not have my agents
  silently reading stale memory between sync cycles.

## What I'd love from you

1. **Confirmation or correction** on each of issues 1, 2, 3 — known,
   self-hosted-specific, version-specific, or my-stack-specific
2. **Concrete repro guidance for issue 2** — what does a successful `/doctor`
   look like end-to-end? If you have a recipe (model + persona + tool config
   that's known to work), I can use that as a target.
3. **A workable validation test for MC migration readiness** — what would you
   want to see green before migrating the most critical agent in a 44-agent
   ecosystem? My current bar is "successfully run `/doctor` end-to-end on a
   throwaway agent and have it produce useful cleanup proposals" + "verify a
   round-trip edit reaches all REST consumers without manual intervention." I'm
   not at that bar yet.

I'm not on a deadline; I'd rather pause migration than ship something where
the post-migration operational layer is unreliable.

---

Run IDs for forensic review (all on my self-hosted instance, won't survive
container restart but happy to capture before restart if useful):

- run-33531d33-1419-45ff-9cde-32ec08bc044b — calendar-agent /doctor (web_search loop)
- run-7b191bb6-7a01-4b52-af28-8dd31885331d and adjacent ~16 runs at ~22:20 UTC
  on 2026-04-25 — Letta Code agent /doctor (Task hallucination loop)
