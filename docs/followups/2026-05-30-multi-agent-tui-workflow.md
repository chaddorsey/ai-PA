---
date: 2026-05-30
status: design-in-progress
related:
  - docs/runbooks/letta-local-mode-per-agent-migration.md
  - docs/followups/2026-05-30-letta-code-tui-latency.md
  - docs/followups/2026-05-30-ai-pa-directory-bloat-audit.md
---

# Multi-agent TUI workflow — design notes

Once the fleet (Docs, Calendar, Tasks, Email, Pulse, MC) is migrated to
local mode, you'll want to interact with multiple agents fluently from the
TUI. This doc captures the implications of that workflow and what to set
up for it.

## The shape of a multi-agent TUI workflow

What you've described:
- Use ALL agents together as one coherent system
- Swap across them via the TUI at various points
- Same machine, same shell session, same workflow

That breaks down into a few practical questions:

1. How do I switch from "talking to Docs" to "talking to Calendar"
   quickly, without paying cold-start every time?
2. How do agents talk to each other (Docs hands off a task to Tasks
   agent, MC dispatches to specialist)?
3. How do I keep state coherent across agents (preferences, who's who,
   project context) without each agent having its own siloed copy?
4. How much does running 6 agents simultaneously cost on each provider?

## Architecture implications

### 1. Each `letta` invocation is a fresh Node process

The 32 MB letta-code bundle loads, V8 boots, skill discovery runs, provider
config loads, agent record loads, memfs git repo opens. That's the
~2-3 second floor BEFORE any model call.

**Implication**: spawning a new letta process per agent-switch is wasteful
if you'll swap back. Keeping processes alive in tmux panes or some other
long-lived container is the better pattern.

### 2. Provider prompt-cache cold-start is per-agent, per-process

OpenAI / Fireworks / Anthropic prompt caches are keyed by the prefix of
your request. Each agent has its own system prompt + memfs files, so
**Agent A's cache doesn't warm Agent B**. With ~5min cache TTL on most
providers (1hr on Anthropic), an idle agent goes cold quickly.

**Implication**: cold-start hits scale linearly with number of agents you
swap between. If you've got 6 agents and rotate among all of them in a
30-min span, you pay 6 cold starts.

### 3. Cross-agent dispatch via the `Agent` tool

letta-code exposes an `Agent` tool that lets the current agent spawn a
subagent (another agent_id) to delegate. In local mode this works against
the same `~/.letta/lc-local-backend/agents/` registry — so MC can
delegate to Calendar even without going through a separate process.

**But**: subagents inherit memory guard (default ON) — they can't peek at
the parent's memfs. The contract is "parent reads what it needs, passes
content as the subagent's prompt." That's the same caveat documented in
the runbook (W6).

**Implication**: cross-agent workflows need to be redesigned around
explicit handoff payloads rather than "child reads parent's plate." Most
won't, because most existing tools were Docker-era and didn't share memfs
either — but worth auditing.

### 4. Canonical store is the single source of truth across agents

`agents-canonical/` in Gitea (signals/, digests/, tasks/, preferences/,
identity/) is how agents share durable state across the fleet. Each agent
reads/writes there via `Bash + curl` (or eventually a `canonical` CLI
when we ship one).

**Implication**: this layer needs to be solid before multi-agent fluency
is real. Item A in the alignment doc (preferences/identity canonical
consolidation) is on the critical path here. Item I-quater (migrate
operational knowledge out of archival → memfs/canonical) too.

### 5. Cost concentration

Six agents × Kimi K2.6 at Fireworks pricing is roughly cost-neutral with
the previous Docker setup. But if MC ends up on a heavier model (likely —
user-facing dispatch wants good tool-calling and reasoning) and gets
called the most, MC will dominate the bill.

**Implication**: per-agent model choice matters. Kimi K2.6 / GPT-5.4-mini
for the bulk of the fleet; reserve heavier models for MC. Watch the
litellm `/spend` endpoint after a few days of real use.

## Recommended setup

### Phase 1 (now, while we have one agent migrated)

1. **Wrapper scripts in `~/bin`** — one per agent:

   ```bash
   # ~/bin/letta-docs
   #!/usr/bin/env bash
   exec env LETTA_LOCAL_BACKEND_DIR="$HOME/.letta/lc-local-backend" \
     letta --backend local \
     --agent agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a \
     --conversation default "$@"
   ```

   Run from `~/letta-cwd` (or any small dir). The wrapper sets the
   working dir implicitly by being launched from wherever you `cd` to —
   so add a `cd "$HOME/letta-cwd"` line if you want to force it.

2. **Headless one-shots** for quick queries:

   ```bash
   letta-docs -p "what meetings did I have this week about Mapping Time?"
   ```

   Headless is 5-10s for warm calls, no TUI ceremony.

3. **Keep tmux panes warm** for agents you'll swap to often. A pane per
   agent, each running `letta-<agent>` in TUI mode. Cache stays warm
   because of intra-session activity.

### Phase 2 (as more agents migrate)

4. **Per-agent model handle in litellm aliases** — already in place:
   `gpt-4.1-mini/docs`, `gpt-4.1-mini/calendar`, etc. So you can tune
   per-agent without touching code, and litellm tracks spend per-alias.

5. **A switcher wrapper** for fast manual swap:

   ```bash
   # ~/bin/letta
   #!/usr/bin/env bash
   case "$1" in
     docs|d)    shift; exec letta-docs "$@" ;;
     calendar|c) shift; exec letta-calendar "$@" ;;
     tasks|t)   shift; exec letta-tasks "$@" ;;
     email|e)   shift; exec letta-email "$@" ;;
     pulse|p)   shift; exec letta-pulse "$@" ;;
     mc|m|"")   shift; exec letta-mc "$@" ;;
     *) command letta "$@" ;;
   esac
   ```

   (Aliased so `letta` itself routes; rename original if conflict.)

### Phase 3 (after all migrate, before production multi-agent)

6. **Stand up a "fleet manager" tmux session** that auto-launches all 6
   agents in their respective panes on login. Keeps everyone warm,
   visible at a glance, swap-by-pane.

7. **MC routing** decision (item G in alignment doc): does MC dispatch to
   specialist agents via the Agent tool, or do you talk to specialists
   directly? In a TUI-primary workflow, direct-to-specialist is fast
   (no extra hop). MC remains for orchestration where you need it.

8. **Canonical store CLIs**: ship `signal`, `task-write`, `pref-read`,
   `digest-emit` as primitives. Agents compose workflows from them via
   Bash. Replaces 30+ custom Letta tools.

## Anti-patterns to avoid

- **Don't spawn fresh `letta` per question.** Each fresh process is a
  cold cache + 2-3s startup. Use long-lived TUI panes for things you
  swap to often, headless `-p` for genuine one-shots.

- **Don't `cd` into ai-PA before launching letta** (until the bloat
  audit ships). The 243K-file project skill discovery is the typing-lag
  culprit. Use a small launch dir; the agent's tools take absolute paths.

- **Don't rely on cross-agent memfs reads.** Subagent memory guard is
  on by default and aligns with the right design (information passes by
  explicit handoff, not by shared workspace peeking).

- **Don't migrate MC last as a "leave the riskiest for last" tactic
  without a model-choice plan.** MC's user-impact and tool-diversity
  mean it deserves the most thought, not the least.

## Open decisions

These need a call from you, not from me:

1. **Per-agent models**: keep all 6 on Kimi K2.6, or differentiate?
   - Recommended: Kimi for Docs, Tasks, Email, Pulse (bulk). GPT-5.4-mini
     for Calendar (precise time math). Heavier model for MC if it's the
     user-facing dispatcher.

2. **Conversation hygiene**: do conversations grow unbounded per agent,
   or do you want a "new conv per day" / "weekly archive" pattern?
   - Recommended: leave `--conversation default` indefinite for the
     pilot; revisit if context bloats or letta-code's summarization
     starts producing weird artifacts.

3. **TUI as primary surface vs pa-web-ui**: with TUI working,
   pa-web-ui local-mode routing (deferred Option A from earlier) becomes
   less urgent. But pa-web is the only mobile-accessible surface.
   - Recommended: defer pa-web-ui local-mode routing until 2-3 agents
     are working well in TUI, then revisit. The Fix C subprocess-pool
     extension is still the right long-term answer.

4. **Skill / canonical CLI wave 2**: what's the next batch of CLIs to
   ship to replace remaining custom Letta tools?
   - Best candidates: `signal` (already exists; verify on PATH and add
     missing subcommands), `task-write` (needed for Tasks migration),
     `pref-read` / `pref-write` (canonical preferences layer).
