#!/bin/bash
# Update gws CLI to latest release from GitHub.
# Works on both macOS (host) and Linux (Letta container).
# Keeps previous binary as gws.bak for rollback.

set -euo pipefail

INSTALL_DIR="${GWS_INSTALL_DIR:-/usr/local/bin}"
REPO="googleworkspace/cli"
BINARY_NAME="gws"

# Detect platform
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "${OS}" in
    darwin) PLATFORM_OS="apple-darwin" ;;
    linux)  PLATFORM_OS="unknown-linux-gnu" ;;
    *)      echo "[update-gws] Unsupported OS: ${OS}"; exit 1 ;;
esac

case "${ARCH}" in
    arm64|aarch64) PLATFORM_ARCH="aarch64" ;;
    x86_64)        PLATFORM_ARCH="x86_64" ;;
    *)             echo "[update-gws] Unsupported arch: ${ARCH}"; exit 1 ;;
esac

TARGET="${PLATFORM_ARCH}-${PLATFORM_OS}"

# Get latest version from GitHub API
LATEST=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')

if [ -z "${LATEST}" ]; then
    echo "[update-gws] ERROR: Could not fetch latest version"
    exit 1
fi

# Get current version (if installed)
CURRENT="none"
if command -v "${BINARY_NAME}" &>/dev/null; then
    CURRENT=$("${BINARY_NAME}" --version 2>/dev/null | head -1 | awk '{print $2}' || echo "none")
fi

if [ "${CURRENT}" = "${LATEST}" ]; then
    echo "[update-gws] Already at v${LATEST}"
    exit 0
fi

echo "[update-gws] Upgrading from v${CURRENT} to v${LATEST}..."

# Download
ASSET="google-workspace-cli-${TARGET}.tar.gz"
URL="https://github.com/${REPO}/releases/download/v${LATEST}/${ASSET}"
TMPDIR=$(mktemp -d)
trap 'rm -rf "${TMPDIR}"' EXIT

curl -fsSL "${URL}" -o "${TMPDIR}/${ASSET}"
tar -xzf "${TMPDIR}/${ASSET}" -C "${TMPDIR}"

# Find the binary in the extracted contents (may be in a subdirectory)
# Avoid -perm +111 vs /111 portability issues — just search by name, then verify executable
EXTRACTED_BIN=$(find "${TMPDIR}" -name "gws" -type f 2>/dev/null | head -1)

if [ ! -f "${EXTRACTED_BIN}" ]; then
    echo "[update-gws] ERROR: Could not find gws binary in downloaded archive"
    ls -la "${TMPDIR}"
    exit 1
fi

# Backup current binary
if [ -f "${INSTALL_DIR}/${BINARY_NAME}" ]; then
    cp "${INSTALL_DIR}/${BINARY_NAME}" "${INSTALL_DIR}/${BINARY_NAME}.bak"
fi

# Install
cp "${EXTRACTED_BIN}" "${INSTALL_DIR}/${BINARY_NAME}"
chmod +x "${INSTALL_DIR}/${BINARY_NAME}"

echo "[update-gws] Updated gws: v${CURRENT} -> v${LATEST}"
