# letta-memfs-build/Dockerfile
#
# Patched Letta server image for self-hosted memfs-external support.
# Overlays the three Fimeg/letta-external-memfs server patches on stock
# letta/letta:0.16.7. Vendored patch source: letta-memfs-patches/upstream-fimeg/
# pinned to commit 1156a55fa81bc71891a1f1ccac7351d98c713a47 (2026-04-24).
#
# See:
#   docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md Phase 1
#   docs/research/2026-04-24-letta-issue-3205-final-diagnosis.md
#
# Build via the wrapper at letta-memfs-build/build.sh OR directly via:
#   docker build --build-context root=. -f letta-memfs-build/Dockerfile -t letta-local:0.16.7-memfs-v1 letta-memfs-build/
#
# Note: the build context here is letta-memfs-build/ but we use --build-context
# to also pull from the repo root for letta-memfs-patches/.

FROM letta/letta:0.16.7

# Install build/runtime tools required for memfs operations:
# - patch: needed to apply the three server patches at build time
# - git: needed at runtime by memfs_client_base.py (RuntimeError otherwise)
RUN apt-get update && \
    apt-get install -y --no-install-recommends patch git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Pull patches from the named build context "root" (passed via --build-context root=..)
COPY --from=root letta-memfs-patches/upstream-fimeg/server_memory_sync_endpoint.patch /tmp/patches/01-sync-endpoint.patch
COPY --from=root letta-memfs-patches/upstream-fimeg/server_sync_delete_propagation.patch /tmp/patches/02-delete-propagation.patch
COPY --from=root letta-memfs-patches/upstream-fimeg/server_system_only_blocks.patch /tmp/patches/03-system-only-blocks.patch

# Pre-flight: dry-run all patches before any real apply, so failures surface
# before we modify the image.
RUN cd /app && \
    for p in /tmp/patches/*.patch; do \
        echo "[verify] $p" && \
        patch -p1 --dry-run < "$p" >/dev/null && \
        echo "[verify] OK $p"; \
    done

# Apply patches in numeric order
RUN cd /app && \
    for p in /tmp/patches/*.patch; do \
        echo "[apply] $p" && \
        patch -p1 < "$p" && \
        echo "[apply] OK $p"; \
    done

# Verify the resulting Python still imports cleanly (catches syntax-level errors
# from a botched patch).
RUN python -c "from letta.server.rest_api.routers.v1 import agents; print('agents OK')" && \
    python -c "from letta.services import block_manager_git; print('block_manager_git OK')" && \
    python -c "from letta.services.memory_repo import path_mapping; print('path_mapping OK')" && \
    python -c "import letta; print('letta', letta.__version__)"

# Cleanup patches dir
RUN rm -rf /tmp/patches
