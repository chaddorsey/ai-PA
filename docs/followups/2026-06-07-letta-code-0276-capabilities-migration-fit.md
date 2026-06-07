---
date: 2026-06-07
status: exploration (no build yet — migration still on HOLD)
letta_code_version: 0.27.6 (already latest on npm; capabilities already installed)
related:
  - docs/followups/2026-06-07-letta-server-tools-migration-stock.md
  - docs/plans/2026-06-07-analytics-briefing-local-completion-charter.md
letta_bug: LET-9147
---

# Letta Code 0.27.6 capabilities — migration-fit notes

## Upgrade status: already current
- Installed `0.27.6` == npm `latest` (only other tag is stale `0.18.5-next`).
- All five new capability skills already ship in the installed package
  (`/opt/homebrew/lib/node_modules/@letta-ai/letta-code/skills/`).
- **No upgrade action needed.** Rollback is trivial: `npm i -g
  @letta-ai/letta-code@0.27.6`. `~/.letta/settings.json` backed up
  (`settings.json.pre-upgrade-*`). (Newer than 0.27.6 only exists on GitHub
  `main`, unreleased — would require a from-source build; not recommended.)

## The five capabilities (installed skills)

1. **creating-extensions** — trusted local apps in `~/.letta/extensions/`
   that add **tools** (agent-callable), **commands** (slash), **local model
   providers**, **events** (lifecycle/turn/tool), **permission overlays**,
   **panels/status**. Run in letta-code's Node runtime. Load on start /
   `/reload`; recover via `letta --no-extensions`.
2. **customizing-commands** — `/foo` slash commands (prompt | output |
   handled). Pattern: durable workflow → **skill + thin launcher command**.
3. **modifying-the-harness** — deterministic config: **permissions**,
   **hooks** (PreToolUse/PostToolUse/Stop…), per-agent `toolset`, and
   model/context via `PATCH /v1/agents`. Clear **memory-vs-harness** rule.
4. **customizing-statusline** — `~/.letta/extensions/statusline.tsx` idle row.
5. **acquiring-skills** — `letta skills install <source>` from Hermes /
   ClawHub / GitHub into an agent's memfs.

## Migration fit (where these land in our scheme)

### A. Extension tools = the likely answer to LET-9147 (highest value)
The pulse saga's root pain: server-registered **Python** tools run under a
**non-deterministic interpreter** (venv 3.13 / CLT 3.9 / `/root` sandbox).
Extension tools run in **Node** and `execFile` external commands directly
(confirmed in `creating-extensions/references/tools.md` — recipes shell out
via `node:child_process`). So an extension tool can:

```ts
execFile("/Users/dorseyhomeserver/.local/pipx/venvs/pulse-cli/bin/python",
         [scriptPath, ...args], { env: {...} })
```

→ **we pin the interpreter and env deterministically.** Two re-home shapes:
- **Thin wrapper (low effort):** keep the existing Python logic, expose it as
  a local extension tool that `execFile`s a pinned venv. Kills the
  non-determinism without rewriting the analytics code.
- **Native port (higher effort):** rewrite tool logic in TS. Only worth it
  for simple tools.

This reframes the "server-harden vs. re-home-local" decision: **re-home as
local extension tools** is now concrete and aligns with the no-Docker,
local-mode direction (eliminates the `/root` server-sandbox path entirely).

### B. Provider extensions = the model/quota lever
"Custom model/API provider for **local agents**." Lets us add Kimi 2.6 /
5.4-mini-API as first-class local providers — addresses the ChatGPT
team-plan quota that bit us, and supports cross-provider flexibility.

### C. Commands + skills = the briefing/schedule UX
Daily briefing, schedule, analytics rundown → proper `/commands` backed by
skills (the documented "durable workflow = skill + thin launcher command"
pattern, which matches our existing skill-first approach).

### D. Hooks/permissions = harness hardening
PreToolUse/PostToolUse/Stop hooks + permission rules for deterministic
guardrails (auto-approve safe CLIs, notify-on-done, block risky ops) —
relevant to the fleet broadly, not just pulse.

### E. acquiring-skills + statusline = lower-priority polish
Skill acquisition for capability expansion; statusline for TUI ergonomics.

## Open questions for the migration plan (do NOT build yet)
1. **Tool execution model**: do we re-home the 202 server tools as local
   extension tools (Node wrappers around a pinned Python venv), or keep them
   server-side and harden the sandbox? Extension tools now make re-homing the
   stronger option, but it's a large surface — sequence it (pulse cluster as
   the pilot).
2. **Python packaging**: a pinned venv (the pulse-cli venv, or a dedicated
   `pa-tools` venv) with all deps + the helper modules, that extension tools
   `execFile`. Decide one canonical venv.
3. **Desktop app**: now local-mode compatible — evaluate as an additional
   surface alongside the TUI (the user flagged this; not yet examined here).
4. **Scope**: this is the "new path." Per Chad, plan it explicitly before
   executing any significant-scope migration.

## Suggested pilot (when migration resumes)
Re-home ONE pulse tool (`collect_analytics_snapshot`) as a local extension
tool that `execFile`s the pinned venv, prove deterministic execution end to
end, then template the rest.
