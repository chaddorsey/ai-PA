# letta-code-patched

Pinned and patched copy of `@letta-ai/letta-code` for self-hosted Letta. Applies two independent patches to the bundled `letta.js`:

1. **Path C handle-fix (`PATCH-3205`)** — fixes `POST /v1/agents/` failing with `HandleNotFoundError` during subagent spawn when the `provider_models` registry doesn't contain the parent agent's handle. Makes letta-code send `llm_config: <object>` instead of `model: <handle-string>` when creating subagents, bypassing server-side handle resolution per `server.py:540` guard. Source: `../letta-memfs-patches/patches/letta_code_self_hosted_handle_fix.md`.

2. **memfs-external-git (`PATCH-MEMFS-GIT`)** — translates `Fimeg/letta-external-memfs/patches/memoryGit.ts.patch` to the bundle. Makes letta-code's memfs git operations route to `LETTA_MEMFS_GIT_URL` (e.g. our self-hosted Gitea) instead of the Letta server's `/v1/git/` proxy. Three changes: env-var-aware `getGitRemoteUrl`, skip-credential-helper-when-external, and a remote-origin-update path that handles non-`/v1/git/` URLs. Source: `../letta-memfs-patches/patches/apply_letta_code_memfs_external_git.py`.

## Why this lives in the repo

The patched `letta.js` itself is large (~6 MB) and we keep it gitignored — instead we commit the `build.sh` recipe that installs the pinned npm package and applies the patch idempotently. Anyone who clones the repo can run `./build.sh` and get a byte-identical patched copy.

This shape is a deliberate inversion of `~/code/letta-code-memfs/` (the prior dev-time location): everything here is under `/Volumes/main-drive/ai-PA/`, covered by version control, backups, and the docker-compose lifecycle.

## Build

```bash
cd letta-code-patched
./build.sh
```

Idempotent. Safe to re-run after:
- Upstream auto-update overwrites `letta.js`
- New letta-code version bump in `package.json`
- The patch script being re-applied for whatever reason

The script:
1. Runs `npm install` (uses pinned `@letta-ai/letta-code@0.24.2`)
2. Backs up `letta.js` → `letta.js.original` (only on first run, only if pristine)
3. Applies `letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py` (Path C, `PATCH-3205`)
4. Applies `letta-memfs-patches/patches/apply_letta_code_memfs_external_git.py` (memfs-external-git, `PATCH-MEMFS-GIT`)
5. Verifies ≥6 `[PATCH-3205]` markers, ≥3 `[PATCH-MEMFS-GIT]` markers, parses cleanly, `--version` returns 0.24.2

Patches 3 and 4 are independent and additive. Both can apply alone or together. Both are idempotent at the apply.py level (detect existing markers, skip).

Output: `node_modules/@letta-ai/letta-code/letta.js` (patched, gitignored).

## Use from the host

For dev-time testing, point `LETTA_CODE_BIN` at the wrapper script and invoke `letta` normally:

```bash
export LETTA_CODE_BIN=/Volumes/main-drive/ai-PA/letta-memfs-patches/letta-patched-wrapper.sh
"$LETTA_CODE_BIN" --agent <agent-id> -p "your prompt"
```

The wrapper resolves to the patched `letta.js` here. Subagent spawns automatically inherit `LETTA_CODE_BIN` via letta-code's built-in shim mechanism.

## Use from Docker (production cutover)

For pa-web-ui and LettaBot, the patched `letta.js` needs to be available inside their containers. Two options:

**Option A — bind-mount (simpler, depends on host filesystem layout)**: Add a volume mount to the container's `docker-compose.yml` service definition:

```yaml
volumes:
  - /Volumes/main-drive/ai-PA/letta-code-patched/node_modules/@letta-ai/letta-code:/opt/letta-code-patched:ro
environment:
  LETTA_CODE_BIN: /opt/letta-code-patched/letta.js
```

**Option B — build into the image (more reproducible)**: Add a build step to the consuming service's Dockerfile:

```dockerfile
RUN mkdir -p /opt/letta-code-patched && \
    cd /opt/letta-code-patched && \
    npm install @letta-ai/letta-code@0.24.2 --silent --no-audit --no-fund

COPY letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py /tmp/
RUN python3 /tmp/apply.py /opt/letta-code-patched/node_modules/@letta-ai/letta-code/letta.js

ENV LETTA_CODE_BIN=/opt/letta-code-patched/node_modules/@letta-ai/letta-code/letta.js
```

We're using Option A initially (during Step 3a soak) and will graduate to Option B as we harden each consuming service.

## Reverting / rollback

To revert the patched copy back to stock:

```bash
LETTA_JS=node_modules/@letta-ai/letta-code/letta.js
cp "$LETTA_JS.original" "$LETTA_JS"
```

To stop production from using the patched copy: unset / remove `LETTA_CODE_BIN` from the consuming service's environment and recreate the container. The Homebrew-installed `letta` binary stays untouched as the always-available stock fallback.

## Upgrade path

When letta-code 0.24.x → 0.25.x ships:

1. Update `package.json` to the new pinned version
2. Run `./build.sh` — if the patch's text anchors still match, it applies cleanly
3. If text anchors changed (likely on minor bumps), update `apply_letta_code_self_hosted_handle_fix.py`'s `OLD_BLOCK` constant to match the new shape, then re-run
4. Validate via the C1.1-C1.5 test plan in `docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md`

When upstream lands a server-side fix (`sync_base_providers` extension or a client-side `llm_config` patch), this whole directory becomes obsolete. Track via the GitHub issue Letta team is filing.
