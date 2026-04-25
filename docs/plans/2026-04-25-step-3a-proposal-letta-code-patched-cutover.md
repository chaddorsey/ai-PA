---
date: 2026-04-25
status: proposal — awaiting user review before any production touching
parent-plan: ./2026-04-24-001-feat-letta-memfs-upgrade-plan.md
phase: -1, sub-step C1.6 (Step 3a only — binary swap with Task still disallowed)
---

# Step 3a Proposal — Patched letta-code Production Binary Swap

## Goal

Switch pa-web-ui and LettaBot to use the Path C patched letta-code, **with Task and other INTERACTIVE_APPROVAL_TOOLS still in their disallowed lists**. Pure binary swap; zero behavioral change because the patch's logic is gated by `if (!isCloud && isSubagent)` — and `isSubagent` requires the `LETTA_CODE_AGENT_ROLE === "subagent"` env var, which is set only when the parent letta-code spawns a subagent. With Task still disallowed, no subagents spawn, the patched code path is dead code.

This step exists to give us soak time on the patched binary in production before flipping Step 3b (re-enabling Task), so any regression in non-subagent paths surfaces early.

## What Step 3a does NOT do

- Does NOT remove Task / TodoWrite / EnterPlanMode / AskUserQuestion from `disallowedTools`
- Does NOT change any agent's behavior
- Does NOT touch Letta server, Gitea, or memfs infrastructure
- Does NOT modify the Homebrew-installed letta-code on the host
- Does NOT rename agent handles or insert SQL stopgap rows

## Surface area: where letta-code currently lives

Two consumers:

### Consumer 1: pa-web-ui (Docker container)

- Dockerfile installs letta-code globally inside the container at build time
- Pinned: `LETTA_CODE_VERSION=0.23.8` (in Dockerfile ARG)
- Binary location inside container: `/usr/local/bin/letta` → symlink to `/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js`
- Spawned via Python's `subprocess.Popen` from `pa-web-ui/subprocess_pool.py`

### Consumer 2: LettaBot (host process, NOT containerized)

- Runs from `/Volumes/main-drive/ai-PA/lettabot/` directly via `node src/main.ts` (PID 945, started Apr 11)
- Spawns letta-code subprocesses as: `node /Volumes/main-drive/ai-PA/lettabot/node_modules/@letta-ai/letta-code/letta.js …`
- Current spawn flags (verified via `ps`): `--disallowedTools TodoWrite,Task --no-memfs`
- Letta-code installed locally via `lettabot/package.json`'s `@letta-ai/letta-code-sdk` dependency

## Important version asymmetry

| Consumer | Currently pinned | Path C patched binary in repo |
|---|---|---|
| Host dev / canary tests | 0.24.2 (Homebrew via npm auto-update) | 0.24.2 |
| pa-web-ui container | **0.23.8** | not yet built |
| LettaBot host | **whatever's in lettabot/node_modules** (need to check) | not yet built |

Path C patch verified to apply cleanly to BOTH 0.23.8 and 0.24.2 — same `createAgentRequestBase` byte-block in both. So we have two paths:

**Option V1 — Keep pa-web-ui on 0.23.8, just patch it.** Lowest risk: no version bump on a known-good production runtime. Same letta-code surface as before, just with the Path C patch added.

**Option V2 — Bump pa-web-ui to 0.24.2 + patch.** Aligns pa-web-ui with our canary/dev binary. But introduces a letta-code minor version bump that hasn't been tested in pa-web-ui's specific subprocess-pool / event-translation paths. The pa-web-ui plan (`docs/plans/2026-04-20-001-feat-pa-web-ui-letta-code-migration-plan.md`) explicitly calls out: bumping `LETTA_CODE_VERSION` requires re-running Unit 1.1 smoke tests + the compatibility pass.

**Recommendation: Option V1 for Step 3a.** Smaller change, tighter scope. The Path C patch is the variable; everything else stays pinned. We can bump versions later in a separate, dedicated step.

For LettaBot, similarly: keep its currently-installed version, just patch.

## Proposed changes

### Change 1 — pa-web-ui Dockerfile: apply Path C patch at image build

Modify `pa-web-ui/Dockerfile` Stage 1 to apply the patch after `npm install -g`.

```diff
 RUN npm install -g "@letta-ai/letta-code@${LETTA_CODE_VERSION}" \
     && npm cache clean --force
+
+# Apply Path C self-hosted handle-fix patch to the installed letta-code.
+# The patch is idempotent and version-tolerant (works on 0.23.8 + 0.24.2);
+# safe to keep applied across LETTA_CODE_VERSION bumps as long as the
+# createAgentRequestBase byte-block matches.
+# See: /docs/research/2026-04-24-letta-issue-3205-final-diagnosis.md
+#      /letta-memfs-patches/patches/letta_code_self_hosted_handle_fix.md
+COPY --from=letta-build /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js /tmp/letta.js.unpatched
+# (apply.py needs the file in-place, not a temp copy)
```

Actually, simpler: put the patch script in the build context and apply it at the same RUN step as the npm install. New approach:

```diff
+# Copy the patch script into the build context so it's available at image build.
+COPY --from=context /workspace/letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py /tmp/apply-patch.py
+# Hmm — can't do that in a multi-stage build trivially.
```

**Cleanest pattern — copy the patch script into the build context via a Dockerfile COPY of the repo path**, then apply it after install:

```diff
 ARG LETTA_CODE_VERSION=0.23.8
 
 RUN npm install -g "@letta-ai/letta-code@${LETTA_CODE_VERSION}" \
     && npm cache clean --force

+# Apply Path C self-hosted handle-fix patch (see docs/research/2026-04-24-letta-issue-3205-final-diagnosis.md).
+# Idempotent: re-running has no effect once applied.
+# Compatible with letta-code 0.23.8 + 0.24.2; revisit if upgrading further.
+COPY ../letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py /tmp/apply-3205.py
+RUN python3 /tmp/apply-3205.py /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js \
+    && grep -c PATCH-3205 /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js
```

**Wait — `COPY ../`-relative paths don't work in standard Dockerfile.** Two options:

**Option B1.1**: Move build context one level up. In `docker-compose.yml`:

```diff
 pa-web-ui:
   build:
-    context: ./pa-web-ui
+    context: .
+    dockerfile: pa-web-ui/Dockerfile
```

Then `COPY letta-memfs-patches/patches/...` becomes a valid path.

**Option B1.2**: Copy the patch script into pa-web-ui/ before build, gitignore it as a build artifact. Less elegant.

**Option B1.3**: Bake the patch logic directly into the Dockerfile as inline Python via `RUN python3 -c "$(cat <<'PYEOF' ...)"`. Avoids the cross-directory COPY entirely. Cost: patch logic duplicated between repo and Dockerfile, maintained in two places.

**Recommendation: Option B1.1.** Bump build context to repo root. Single-line change in docker-compose.yml. Allows Dockerfile to access any other repo-level resource cleanly. Modern best practice.

Also adds a `RUN python3 ...` step. python3 is already in the build image (it's a build-tools install dep on line 17), so no new package install needed in Stage 1.

### Change 2 — pa-web-ui docker-compose: build context + LETTA_CODE_BIN env

```diff
 pa-web-ui:
   build:
-    context: ./pa-web-ui
+    context: .
     dockerfile: pa-web-ui/Dockerfile
   container_name: pa-web-ui
   restart: unless-stopped
   networks: [pa-internal]
   …
   environment:
     …
+    # Path C patched letta-code is at /usr/local/bin/letta (patched in
+    # Dockerfile build). Setting LETTA_CODE_BIN here makes letta-code's
+    # subagent shim mechanism propagate to spawned subagents — though with
+    # Task still in --disallowedTools, this is a no-op until Step 3b.
+    - LETTA_CODE_BIN=/usr/local/bin/letta
```

`LETTA_CODE_BIN` could be omitted in Step 3a since pa-web-ui already invokes `/usr/local/bin/letta` as its spawn target — the in-container patched binary is already what runs. But setting it explicitly makes the contract clear and handles the eventual subagent-spawning path that Step 3b will exercise.

### Change 3 — LettaBot host install: re-install letta-code patched

LettaBot runs on the host, so we just point its `node_modules/@letta-ai/letta-code/letta.js` at our patched copy. Two approaches:

**Option L1 — Symlink LettaBot's letta.js to the repo's patched copy.**

```bash
cd /Volumes/main-drive/ai-PA/lettabot/node_modules/@letta-ai/letta-code/
mv letta.js letta.js.original-pre-3205
ln -s /Volumes/main-drive/ai-PA/letta-code-patched/node_modules/@letta-ai/letta-code/letta.js letta.js
```

Pros: trivial, no rebuild, immediately reversible.
Cons: tightly couples LettaBot's letta-code version to whatever's in `letta-code-patched/`. If the latter bumps to 0.25, LettaBot picks it up unintentionally.

**Option L2 — Run apply.py directly against LettaBot's installed letta.js.**

```bash
python3 /Volumes/main-drive/ai-PA/letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py \
  /Volumes/main-drive/ai-PA/lettabot/node_modules/@letta-ai/letta-code/letta.js
```

Pros: keeps LettaBot's pinned version. Independent from `letta-code-patched/`.
Cons: future `npm install` in lettabot/ would overwrite the patch. Need a postinstall hook or re-apply discipline.

**Recommendation: Option L2 + a simple wrapper script.** Apply the patch directly. Add a `lettabot/scripts/apply-3205-patch.sh` that's a one-liner wrapper around `apply.py` so it's easy to re-run after any `npm ci` or `npm install`. Document in lettabot's README or our migration plan.

For Step 3a's actual invocation of LettaBot, no env var change needed — the spawn target is the same path, just with the patch applied to the file.

### Change 4 — LettaBot: backup-friendly re-apply on next `npm ci`

Optional safety: add to `lettabot/package.json` a `postinstall` script that auto-re-applies the patch:

```diff
 "scripts": {
+  "postinstall": "if [ -f node_modules/@letta-ai/letta-code/letta.js ]; then python3 ../letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py node_modules/@letta-ai/letta-code/letta.js || true; fi",
   ...
 }
```

Pros: future `npm ci` automatically re-patches, no manual step.
Cons: postinstall in production npm runs is sometimes considered fragile. The `|| true` makes it non-fatal but silent on failure.

**Recommendation: Skip postinstall for Step 3a.** Manual re-apply is OK for now since LettaBot doesn't rebuild often. Add the postinstall later if it becomes a maintenance pain.

## Verification plan (before declaring Step 3a stable)

### Pre-flight (before any production change)

1. **Backup verification**: confirm latest backup includes letta-code-patched/, lettabot/node_modules/@letta-ai/letta-code/, and pa-web-ui/Dockerfile. The ones from `c8c0ab8` + `a301486` commits are git-tracked so they're inherently recoverable.

### Activation steps

2. **pa-web-ui rebuild + cutover**:
   ```bash
   docker compose build pa-web-ui  # applies Path C patch at build time
   docker compose up -d pa-web-ui  # recreates container with new image
   ```
   Expected restart time: ~30 sec (multi-stage build with npm install caches).

3. **pa-web-ui in-container verification**:
   ```bash
   docker exec pa-web-ui letta --version  # should print 0.23.8 (Letta Code)
   docker exec pa-web-ui grep -c PATCH-3205 /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js  # should print 8
   docker exec pa-web-ui printenv LETTA_CODE_BIN  # should print /usr/local/bin/letta
   ```

4. **LettaBot patch + restart**:
   ```bash
   python3 /Volumes/main-drive/ai-PA/letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py \
     /Volumes/main-drive/ai-PA/lettabot/node_modules/@letta-ai/letta-code/letta.js
   # then restart LettaBot — depends on how it's launched (PM2? launchd? raw nohup?)
   ```

   **Open question**: how is LettaBot supervised? Need to confirm before restart procedure. Looking at `ps aux` output, PID 945 has been running since Apr 11; it's not under launchd I can see. Will need user input on how to safely restart.

5. **LettaBot post-restart verification**:
   ```bash
   ps aux | grep letta.js | grep lettabot  # confirm new PID, new process
   # Send a test Telegram message to MC and verify response
   ```

### Live regression test (24-72h soak window)

6. **pa-web-ui smoke**: open `localhost:5200`, send a few normal chat messages to MC. Verify:
   - Bash, Read, Edit, Write tool calls all work (these are non-subagent client_tools that the patch is gated against — should be unaffected)
   - No new errors in `docker logs pa-web-ui`
   - Response latency comparable to pre-cutover

7. **LettaBot smoke**: send a few Telegram messages to MC. Verify:
   - Responses arrive at expected latency
   - Tool calls execute normally
   - No regressions in `lettabot.log`

8. **Watch period (24h minimum, 72h preferred)**:
   - `docker logs pa-web-ui --follow` for any error class we don't recognize
   - LettaBot logs similarly
   - User experience: any noticeable behavior change in agent responses?

### Rollback (if regression observed)

**pa-web-ui rollback**:
```bash
# Revert Dockerfile changes via git
git checkout HEAD~1 -- pa-web-ui/Dockerfile docker-compose.yml
docker compose build pa-web-ui
docker compose up -d pa-web-ui
```

**LettaBot rollback**:
```bash
# Restore original letta.js
cd /Volumes/main-drive/ai-PA/lettabot/node_modules/@letta-ai/letta-code/
# If we kept a .original backup
mv letta.js letta.js.patched-3205
mv letta.js.original-pre-3205 letta.js  # if Option L1 — but we chose L2
# For Option L2, re-install:
cd /Volumes/main-drive/ai-PA/lettabot
npm install @letta-ai/letta-code-sdk@<pinned-version> --force
# Then restart LettaBot
```

**Recommendation**: keep a `.pre-3205-backup` copy of LettaBot's `letta.js` before patching, parallel to the `.original` we maintain in `letta-code-patched/`. One-line backup before apply.

## Decision points awaiting user input

Before any execution:

1. **pa-web-ui letta-code version**: keep at 0.23.8 (Option V1, recommended) or bump to 0.24.2 (Option V2)?

2. **pa-web-ui Dockerfile build context**: bump to repo root so it can COPY from `letta-memfs-patches/` (Option B1.1, recommended)? This is a small but real architectural change to pa-web-ui's build setup.

3. **LettaBot patch approach**: in-place apply (Option L2, recommended) or symlink to `letta-code-patched/` (Option L1)?

4. **LettaBot restart procedure**: how is PID 945 supervised? Need to confirm before triggering restart.

5. **Cutover ordering**: pa-web-ui first or LettaBot first? Recommend pa-web-ui first — it's our most active interactive surface, regressions are immediately visible. LettaBot a few hours later once pa-web-ui is clean.

6. **Soak duration**: 24h, 48h, or 72h before declaring Step 3a stable and proceeding to Phase 0 (Gitea) prep work in parallel?

## Estimated total time

- Pre-flight + decisions: 15 min (this discussion)
- pa-web-ui rebuild + cutover + verification: 15 min
- LettaBot patch + restart + verification: 10 min
- Initial smoke tests: 15 min
- Soak period: 24-72h (passive, can do other work)

Active work: ~1 hour. Calendar time to "Step 3a stable": 1-3 days.

## Files that would change

- `pa-web-ui/Dockerfile` — add patch-application RUN step
- `docker-compose.yml` — change pa-web-ui's build context + add LETTA_CODE_BIN env
- `lettabot/node_modules/@letta-ai/letta-code/letta.js` — patched in place (gitignored anyway)
- (optional) `lettabot/scripts/apply-3205-patch.sh` — convenience re-apply script
- `docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md` — mark C1.6's Step 3a portion done

No agent state, no Letta server image, no Gitea, no SQL changes.
