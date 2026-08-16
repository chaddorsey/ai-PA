/**
 * surface/auth.ts — the loopback trust boundary (plan Auth decision, G8/R20).
 *
 * Terminal-class surfaces authenticate with a FILE-PERMISSION token: generated at first boot
 * under the controller's state dir, mode 0600 — which makes *user-level code* the explicit
 * trust boundary, and approval-answering authority rides on it. Rotation = delete the file,
 * restart (or call ensureSurfaceToken again).
 *
 * Browser tickets (single-use, seconds-TTL, first-frame auth — NEVER in the WS URL) are C9;
 * `mintTicket` is deliberately a stub that refuses, so nothing can quietly ship a browser
 * path before the ticket design lands.
 */

import { randomBytes, timingSafeEqual } from "node:crypto";
import { chmodSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const SURFACE_TOKEN_FILENAME = "surface-token";

export function ensureSurfaceToken(stateDir: string): string {
  const path = join(stateDir, SURFACE_TOKEN_FILENAME);
  if (existsSync(path)) {
    return readFileSync(path, "utf8").trim();
  }
  const token = randomBytes(32).toString("hex");
  writeFileSync(path, `${token}\n`, { mode: 0o600 });
  chmodSync(path, 0o600);
  return token;
}

/** Constant-time comparison — a token check must not leak prefix length. */
export function verifySurfaceToken(expected: string, presented: string): boolean {
  const a = Buffer.from(expected);
  const b = Buffer.from(presented);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export function mintTicket(): never {
  throw new Error(
    "browser tickets are a C9 deliverable — the mint endpoint is deliberately absent",
  );
}
