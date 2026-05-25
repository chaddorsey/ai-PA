#!/usr/bin/env python3
"""Apply the letta-external-memfs memoryGit.ts patch to a bundled letta.js.

The upstream Fimeg patch (memoryGit.ts.patch) is calibrated against the
TypeScript source. Our installed letta-code ships only the bundled letta.js,
so we apply the equivalent behavioral changes via string replacement on the
bundle.

Three changes:
1. getGitRemoteUrl: check LETTA_MEMFS_GIT_URL env var first; if set, return
   the URL with {agentId} substituted. Otherwise fall through to existing
   getMemfsServerUrl()/v1/git/...state.git logic.
2. configureLocalCredentialHelper: skip entirely when LETTA_MEMFS_GIT_URL is
   set (external git hosts use embedded URL auth or their own credential flow).
3. maybeUpdateMemoryRemoteOrigin: when LETTA_MEMFS_GIT_URL is set, skip the
   isMemfsRemoteUrlForAgent guard so the origin is updated to point at the
   external git URL even though it doesn't match the /v1/git/ pattern.

Idempotent. Atomic write. Preserves file mode.

Usage: python3 apply_letta_code_memfs_external_git.py [path/to/letta.js]
Default path: ~/code/letta-code-memfs/...   OR
              /Volumes/main-drive/ai-PA/letta-code-patched/node_modules/@letta-ai/letta-code/letta.js

Verifies success by checking that '[PATCH-MEMFS-GIT]' marker appears at
least 3 times.
"""
import os
import sys

DEFAULT_PATH = "/Volumes/main-drive/ai-PA/letta-code-patched/node_modules/@letta-ai/letta-code/letta.js"

# Change 1 — getGitRemoteUrl: check env var first.
OLD_1 = """function getGitRemoteUrl(agentId, baseUrl) {
  const resolvedBaseUrl = (baseUrl ?? getMemfsServerUrl()).trim().replace(/\\/+$/, "");
  return `${resolvedBaseUrl}/v1/git/${agentId}/state.git`;
}"""

NEW_1 = """function getGitRemoteUrl(agentId, baseUrl) {
  // [PATCH-MEMFS-GIT] If LETTA_MEMFS_GIT_URL is set, route memfs git operations
  // to that URL (e.g. an external Gitea host) instead of the Letta server's
  // /v1/git/ proxy. Substitutes {agentId} placeholder.
  const _envUrl = process.env.LETTA_MEMFS_GIT_URL;
  if (_envUrl) {
    return _envUrl.replace("{agentId}", agentId);
  }
  const resolvedBaseUrl = (baseUrl ?? getMemfsServerUrl()).trim().replace(/\\/+$/, "");
  return `${resolvedBaseUrl}/v1/git/${agentId}/state.git`;
}"""

# Change 2 — configureLocalCredentialHelper: skip when env var set.
OLD_2 = """async function configureLocalCredentialHelper(dir, token) {
  const rawBaseUrl = getMemfsServerUrl();"""

NEW_2 = """async function configureLocalCredentialHelper(dir, token) {
  // [PATCH-MEMFS-GIT] Skip server-proxied credential helper when external git
  // host is configured — external URLs typically embed auth or use their own
  // credential flow.
  if (process.env.LETTA_MEMFS_GIT_URL) {
    debugLog("memfs-git", "Skipping credential helper (LETTA_MEMFS_GIT_URL is set)");
    return;
  }
  const rawBaseUrl = getMemfsServerUrl();"""

# Change 3 — maybeUpdateMemoryRemoteOrigin: when env var set, force-update
# the origin to the external URL even if it doesn't match /v1/git/ pattern.
#
# Bundle-shape note: in letta-code 0.24.x the guard called
# isMemfsRemoteUrlForAgent directly. Starting in 0.26.x upstream refactored
# the guard to use a new wrapper, isRepairableMemfsRemoteUrl, which matches
# both `.../v1/git/{id}/state.git` and `.../v1/git/{id}`. The behavioral
# bypass is the same — short-circuit when LETTA_MEMFS_GIT_URL is set.
OLD_3 = """  if (!currentOrigin) {
    return;
  }
  if (!isRepairableMemfsRemoteUrl(currentOrigin, agentId)) {
    return;
  }
  const expectedOrigin = normalizeRemoteUrl(getGitRemoteUrl(agentId));"""

NEW_3 = """  if (!currentOrigin) {
    return;
  }
  // [PATCH-MEMFS-GIT] When LETTA_MEMFS_GIT_URL is set, bypass the
  // isRepairableMemfsRemoteUrl guard so the origin gets updated to the
  // external git URL (which will not match the /v1/git/ pattern).
  const _envUrl3 = process.env.LETTA_MEMFS_GIT_URL;
  if (!_envUrl3 && !isRepairableMemfsRemoteUrl(currentOrigin, agentId)) {
    return;
  }
  const expectedOrigin = normalizeRemoteUrl(getGitRemoteUrl(agentId));"""


def main(path=None):
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    with open(path, "r") as f:
        content = f.read()

    if "[PATCH-MEMFS-GIT]" in content:
        n_markers = content.count("[PATCH-MEMFS-GIT]")
        print(f"Already patched ({n_markers} marker occurrences). No-op.")
        return 0

    replacements = [
        ("getGitRemoteUrl", OLD_1, NEW_1),
        ("configureLocalCredentialHelper", OLD_2, NEW_2),
        ("maybeUpdateMemoryRemoteOrigin", OLD_3, NEW_3),
    ]

    new_content = content
    for label, old, new in replacements:
        if old not in new_content:
            print(f"ERROR: anchor for change '{label}' not found in {path}.", file=sys.stderr)
            print("       The bundle's shape may have changed in this letta-code version.", file=sys.stderr)
            return 3
        before_count = new_content.count(old)
        new_content = new_content.replace(old, new, 1)
        after_count = new_content.count(old)
        if before_count - after_count != 1:
            print(f"ERROR: change '{label}' had unexpected occurrence count.", file=sys.stderr)
            return 4

    original_mode = os.stat(path).st_mode

    tmp_path = path + ".memfsgit.tmp"
    with open(tmp_path, "w") as f:
        f.write(new_content)
    os.chmod(tmp_path, original_mode)
    os.replace(tmp_path, path)

    n_markers = new_content.count("[PATCH-MEMFS-GIT]")
    print(f"Patched: 3 changes applied, {n_markers} [PATCH-MEMFS-GIT] markers in file.")
    print(f"Original size: {len(content)} bytes -> patched size: {len(new_content)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
