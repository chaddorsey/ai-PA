#!/usr/bin/env bash
#
# Generate a fresh VAPID keypair (ECDSA P-256) for Web Push.
#
# Output: prints the three env vars you need to set in BOTH the
# curator and fox-cam-public .env files. Generation is one-time —
# rotating the key invalidates every existing client subscription, so
# don't run this casually in production.
#
# Requires: openssl + python3 with cryptography. Most macOS dev boxes
# have both already; on the home-server box we run inside the curator's
# venv since cryptography is already a transitive dep there.
#
# Usage:
#   ./scripts/generate-vapid-keys.sh
#   # then paste the three exported lines into:
#   #   .env                                  (top-level / fox-cam-public)
#   #   ~/Library/LaunchAgents/com.ai-pa.frigate-curator.plist  (or its env file)
#
set -euo pipefail

python3 - <<'PY'
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

# Generate P-256 keypair — required by the VAPID spec (RFC 8292) and
# the only curve supported by all browsers + Apple Push.
priv = ec.generate_private_key(ec.SECP256R1())
pub = priv.public_key()

# VAPID/Web Push uses raw 32-byte private scalars + 65-byte
# uncompressed public points, base64url-encoded, no padding.
priv_int = priv.private_numbers().private_value.to_bytes(32, "big")
pub_pts  = pub.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)

def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

print("# === Web Push VAPID keypair ===")
print("# Paste these three lines into BOTH .env files (curator + fox-cam-public).")
print("# Rotating the keypair invalidates every existing client subscription.")
print()
print(f"VAPID_PRIVATE_KEY={b64u(priv_int)}")
print(f"VAPID_PUBLIC_KEY={b64u(pub_pts)}")
print(f"VAPID_SUBJECT=mailto:cdorsey@concord.org")
PY
