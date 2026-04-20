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

# Pin the letta-code version that Phase 1 targets. Bumping this requires
# re-running Unit 1.1's smoke tests (test_subprocess_env.py) and the
# compatibility pass described in the migration plan.
ARG LETTA_CODE_VERSION=0.23.8

RUN npm install -g "@letta-ai/letta-code@${LETTA_CODE_VERSION}" \
    && npm cache clean --force


# ---------- Stage 2: Python app image ----------
FROM python:3.11-slim

WORKDIR /app

# Install curl (for healthchecks) + the Node runtime required by letta-code.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY . .

# Expose port.
EXPOSE 5200

# Create the crash-log directory (Unit 1.6 will write redacted stdout/stderr
# tails here; bind-mounted to the host in docker-compose.yml).
RUN mkdir -p /app/logs

# Run the service.
CMD ["python", "app.py"]
