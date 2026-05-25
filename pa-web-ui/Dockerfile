# pa-web-ui — Flask web UI + embedded letta-code runtime (Phase 1).
#
# Stage 1: fetch Node 20 runtime and globally install letta-code at the
# version pinned by the Phase-1 plan. Multi-stage keeps the final image
# lean — we copy only node + the installed package over.
#
# Stage 2: Python base with the Node runtime + letta-code copied in.

# ---------- Stage 1: Node / letta-code install ----------
FROM node:20-bookworm-slim AS letta-build

# letta-code pulls in node-pty (native module) which needs a C++ toolchain
# + Python during npm install. Install build deps, compile, then leave the
# binaries behind — the final image only copies the built artifacts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned letta-code version. Bumped 2026-04-29 from 0.23.8 → 0.24.10 to
# align with the host's letta-code-patched and to enable memfs-via-Gitea
# (the memfs-external-git patch was developed against 0.24.x). All three
# bundle patches (#3205, memfs-external-git, empty-approvals) were
# verified to apply against 0.24.10's bundle anchors before this bump.
# Bumping again requires re-verifying anchors AND re-running pa-web-ui
# Phase 1 smoke tests (tests/test_subprocess_pool.py + live smoke).
ARG LETTA_CODE_VERSION=0.26.1

RUN npm install -g "@letta-ai/letta-code@${LETTA_CODE_VERSION}" \
    && npm cache clean --force

# Apply the Path C self-hosted handle-fix patch to the installed letta-code.
# This makes subagent agent-creation send `llm_config: <object>` instead of
# `model: <handle-string>`, bypassing the server-side handle resolution that
# fails on self-hosted Letta when the parent's handle isn't in provider_models.
# Idempotent + version-tolerant (works on 0.23.8 and 0.24.2). Safe to keep
# applied across LETTA_CODE_VERSION bumps as long as the createAgentRequestBase
# byte-block matches; if a future bump changes the block, update apply.py.
# See: docs/research/2026-04-24-letta-issue-3205-final-diagnosis.md
COPY letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py /tmp/apply-3205.py
RUN python3 /tmp/apply-3205.py /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js \
    && grep -c PATCH-3205 /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js \
    && rm /tmp/apply-3205.py

# Apply the empty-approvals subprocess-survival patch. letta-code 0.23.x
# and 0.24.x panic-exit (returncode=1) when the server emits
# stop_reason=requires_approval with approvals=[]. This patch replaces
# the fatal exit with a wait+continue so an external resolver
# (pa-web-ui/approval_responder.py) has time to POST an ApprovalCreate
# and unblock the run. Full diagnosis: docs/diagnoses/letta-code-empty-approvals.md
COPY letta-memfs-patches/patches/apply_letta_code_empty_approvals_fix.py /tmp/apply-empty-approvals.py
RUN python3 /tmp/apply-empty-approvals.py /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js \
    && [ "$(grep -c '\[PATCH-EMPTY-APPROVALS\]' /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js)" -ge 2 ] \
    && rm /tmp/apply-empty-approvals.py

# Apply the memfs-external-git patch so letta-code can run with --memfs
# pointed at our self-hosted Gitea (instead of the cloud-only memfs server).
# Three string-replacement edits in the bundle:
#   1. getGitRemoteUrl → respect LETTA_MEMFS_GIT_URL env var (with {agentId})
#   2. configureLocalCredentialHelper → skip when LETTA_MEMFS_GIT_URL is set
#   3. maybeUpdateMemoryRemoteOrigin → bypass MemfsRemoteUrlForAgent guard
# Without this, --memfs against self-hosted Letta exits returncode=1 with
# "memfs is only available on Letta Cloud (api.letta.com)".
# Patch was developed against 0.24.2; verified to apply on 0.24.10 anchors.
COPY letta-memfs-patches/patches/apply_letta_code_memfs_external_git.py /tmp/apply-memfs-git.py
RUN python3 /tmp/apply-memfs-git.py /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js \
    && [ "$(grep -c 'PATCH-MEMFS-GIT' /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js)" -ge 3 ] \
    && rm /tmp/apply-memfs-git.py


# ---------- Stage 2: Python app image ----------
FROM python:3.11-slim

WORKDIR /app

# Install curl (for healthchecks + gws install) + the Node runtime required
# by letta-code.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install gws CLI (Google Workspace) so MC + letta-code subagents can issue
# direct Calendar/Gmail/Drive operations via Bash. Mirrors the letta
# container's pattern (see letta/entrypoint-wrapper.sh + scripts/update-gws.sh).
# Credentials are mounted at /root/.gws/credentials.json by docker-compose.
COPY scripts/update-gws.sh /tmp/update-gws.sh
RUN GWS_INSTALL_DIR=/usr/local/bin bash /tmp/update-gws.sh \
    && rm /tmp/update-gws.sh \
    && gws --version

# Copy the Node runtime + global letta-code install from the build stage.
# /usr/local/lib/node_modules holds the globally-installed letta-code
# package (with its dependencies bundled). /usr/local/bin/node is the
# interpreter.
#
# We intentionally do NOT copy the shim symlinks from /usr/local/bin
# (letta, npm, npx). Docker COPY dereferences them at copy time, so the
# resulting file sits outside any node_modules tree and Node's ESM
# resolver fails to find package imports like 'ws'. Instead, we recreate
# the `letta` shim as a symlink pointing into the preserved
# node_modules/.bin directory, which keeps ESM resolution working.
COPY --from=letta-build /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=letta-build /usr/local/bin/node /usr/local/bin/node

# Recreate the letta shim symlink. In the source image it's
#   /usr/local/bin/letta -> ../lib/node_modules/@letta-ai/letta-code/letta.js
# We can't COPY the symlink directly (Docker dereferences), so we re-create
# the same relative symlink here so the CLI resolves its ESM imports
# (e.g., `ws`) from the bundled node_modules at the expected depth.
RUN ln -sf ../lib/node_modules/@letta-ai/letta-code/letta.js /usr/local/bin/letta \
    && letta --version

# Python dependencies.
# NOTE: build context is now repo root (set in docker-compose.yml), so
# pa-web-ui sources are under pa-web-ui/.
COPY pa-web-ui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY pa-web-ui/. .

# Expose port.
EXPOSE 5200

# Create the crash-log directory (Unit 1.6 will write redacted stdout/stderr
# tails here; bind-mounted to the host in docker-compose.yml).
RUN mkdir -p /app/logs

# Run the service.
CMD ["python", "app.py"]
