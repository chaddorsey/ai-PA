#!/bin/bash
# Mount the fox-cam NFS share from the Synology DS220j to /Volumes/fox-cam.
#
# Run by launchd at boot (com.ai-pa.mount-fox-cam.plist).
# KeepAlive(SuccessfulExit=false) means launchd will retry if this exits non-zero,
# so we exit 1 on any failure to make the mount attempt resilient to NAS-not-yet-up.
#
# Idempotent: if already mounted, exits 0 immediately.

set -euo pipefail

NAS_HOST="192.168.7.81"
NAS_EXPORT="/volume1/frigate-foxcam"
MOUNT_POINT="/Volumes/fox-cam"
NFS_OPTS="vers=4,resvport,rw,hard,intr,rsize=131072,wsize=131072,noatime"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Already mounted? Done.
if mount | grep -q " on ${MOUNT_POINT} "; then
    log "Already mounted at ${MOUNT_POINT}"
    exit 0
fi

# Wait briefly for NAS to be reachable (handles boot ordering).
for i in 1 2 3 4 5 6; do
    if ping -c 1 -W 1000 "${NAS_HOST}" >/dev/null 2>&1; then
        break
    fi
    log "NAS ${NAS_HOST} not reachable yet, waiting (attempt ${i}/6)"
    sleep 5
done

if ! ping -c 1 -W 1000 "${NAS_HOST}" >/dev/null 2>&1; then
    log "NAS ${NAS_HOST} unreachable after 30s, will retry via launchd"
    exit 1
fi

mkdir -p "${MOUNT_POINT}"

log "Mounting ${NAS_HOST}:${NAS_EXPORT} at ${MOUNT_POINT}"
if mount -t nfs -o "${NFS_OPTS}" "${NAS_HOST}:${NAS_EXPORT}" "${MOUNT_POINT}"; then
    log "Mount OK"
    exit 0
else
    log "Mount FAILED, will retry via launchd"
    exit 1
fi
