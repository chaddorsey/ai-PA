# Runner migration — retire com.ai-pa.letta-local-runner for good

Origin: cutover Tier-3 operator decision (a) (2026-08-16): runner booted out at cutover,
its riders paused; "memfs-sync/extension-tools migration = first post-cutover unit". This
is that unit. The runner (`letta-local-runner`, :8920) did three things per `/invoke`:
fork `letta --backend local` (a direct backend writer — the reason it had to die), wrap
the fork in memfs Gitea pull-rebase/push, and hand its child a credential env.

## Inventory (verified 2026-08-17)

- **Callers of :8920**: `scripts/run-analytics-stage.sh` (vibe + mentions agent stages);
  scheduler-service `route=local` default (both jobs already PATCHed to `route=letta` at
  cutover — inactive). Nothing else (repo grep + launchd sweep).
- **memfs sync**: runner-side pull-rebase-before/push-after per invocation
  (`invoker.py`), remote `gitea`, branch `main`, repos at
  `~/.letta/lc-local-backend/memfs/<agent>/memory` (remote URLs carry the token).
  letta-code commits memfs changes locally on its own; sync only moves them.
- **Tool env**: App Server child already gets `build_runtime_env()` (warm_pool.py) —
  PATH, GITEA/SLACK_MCP/GITHUB/GRANOLA/POSTGRES creds, GWS creds file. The runner env +
  `~/.letta/pa-tools.env` additionally carried SUPABASE_REST_URL/SERVICE_KEY,
  PA_WEB_POSTGRES_URL, SLACK_ANALYTICS_EXPORT_URL, TWITTER_CONFIG_PATH, LETTA_BASE_URL,
  MY_EMAIL, MC/LETTA_AGENT_ID, ADMIN_REPORTS_CREDENTIALS_FILE — extension tools that
  shell to host CLIs expect these.

## Migrations

1. **memfs Gitea sync → periodic daemon** (`scripts/memfs-gitea-sync.sh` +
   `com.ai-pa.memfs-gitea-sync`, StartInterval 300). Per-invocation wrapping is
   impossible now (turns originate from controller, ingress, enrichment, web); a periodic
   sweep covers ALL sources uniformly. Logic mirrors invoker.py: pull --rebase
   --autostash (abort → clean tree on conflict), push, on reject rebase+push once.
   Worst case is one interval of staleness vs the old immediate push — accepted.
   Logs under ~/Library/Logs (EX_CONFIG/78 trap). Tracked plist: scripts/launchd/.
2. **Analytics agent stages → App Server `/v1/responses`**: `invoke_agent()` in
   run-analytics-stage.sh POSTs :4577 `{"model": "pulse-monitor-agent-local", "input":
   msg}` (friendly-name targeting, same as enrichment). Fresh conversation per call ==
   the runner's `--new`; memfs stays the durable memory. Preserves the uncommitted
   mentions replace-not-append prompt fix (committed with this unit).
3. **Tool env parity**: `build_runtime_env()` additionally sources
   `~/.letta/pa-tools.env` (additive only — the pinned safety keys PATH/HOME/
   LETTA_LOCAL_BACKEND_DIR/TERM are never overridden). pipx reinstall + kickstart
   letta-app-server (+push-receiver) to land it.

## Retirement posture

Runner stays booted out; its plist stays ON DISK until the cutover soak ends (§3b full
switch-back needs it). After soak: delete plist + .bak siblings; the package remains in
the repo as history. scheduler-service's `route=local` code path is left intact but
unused.

## Tasks

- [x] 1. memfs-gitea-sync.sh + plist; manual + launchd-driven sweeps green (synced=6).
        Gotchas hit: launchd refuses direct exec of tool-written scripts
        (com.apple.provenance xattr → EX 126) — plist uses the `/bin/bash <script>`
        ProgramArguments form like letta-code-verify.
- [x] 2. run-analytics-stage.sh re-pointed; mentions stage live-green via /v1/responses
        (31.6s, real Slack search + memfs write; also committed the pre-existing
        replace-not-append prompt fix). NOTE: Edit had dropped the exec bit — restored;
        the analytics plists use /bin/bash form so scheduled runs were never exposed.
- [x] 3. build_runtime_env sources ~/.letta/pa-tools.env additively; pipx reinstalled;
        app-server + push-receiver kickstarted; child env verified (SUPABASE/PA_WEB_
        POSTGRES/TWITTER/SLACK_ANALYTICS keys present); controller liveness green.
- [x] 4. Committed; memory updated.

## Found-and-fixed along the way: pulse memfs auto-commit stalled since 08-14

letta-code's per-turn memfs auto-commit (author `<agent>@letta.com`) works under the App
Server (proof: the cutover scratch agent auto-committed 2026-08-17 09:04). But pulse's
repo has a pre-commit FRONTMATTER hook, and the agent's 08-14 rewrite dropped the
frontmatter — every auto-commit since was silently rejected, stranding 3 days of writes
uncommitted. Repaired: frontmatter restored, stranded content committed + pushed
(`db1d5ce`). The sweep now logs `WARN <agent>: N uncommitted tracked change(s)` when a
tree stays dirty, so a recurring hook rejection is visible instead of silent.
LETTA_MEMFS_LOCAL=1 (runner-era env) proved unnecessary — not carried forward.
Leftover untracked agent scratch in pulse memfs (slack_mentions_raw.json etc.) left for
the agent/operator to clean.
