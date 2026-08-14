/**
 * trust.ts — the loopback trust boundary, enforced where the socket is actually opened.
 *
 * The App Server takes no client authentication. It is safe only because it binds 127.0.0.1, so
 * "the peer is loopback" IS the authentication. A client that will dial anywhere and then treat
 * whatever answers as the trusted App Server inverts that: everything the user types, and the
 * entire conversation history pulled by the catch-up snapshot, goes to that host in cleartext,
 * and whatever it streams back renders under the agent's own label.
 *
 * This check used to live in the terminal's CLI — one package away from the socket, and
 * unreachable from the core. The core is the published seam and the web client is its next
 * consumer, so a check the consumer must remember to re-implement is a check that will be
 * missed. It belongs here.
 */

export class TrustBoundaryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TrustBoundaryError";
  }
}

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

/**
 * Throw unless `raw` names a loopback App Server.
 *
 * Host matching is on `URL.hostname`, which is already normalised by the WHATWG parser — so the
 * decimal (`2130706433`), hex (`0x7f.0.0.1`), short (`127.1`) and IDNA spellings all resolve to a
 * loopback hostname, while `ws://127.0.0.1@evil.example/` correctly resolves to `evil.example`.
 */
export function assertLoopbackUrl(raw: string, allowRemote = false): void {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new TrustBoundaryError(`not a valid URL: ${raw}`);
  }
  if (parsed.protocol !== "ws:" && parsed.protocol !== "wss:") {
    throw new TrustBoundaryError(`URL must be ws:// or wss:// (got ${parsed.protocol})`);
  }
  if (allowRemote || LOOPBACK_HOSTS.has(parsed.hostname)) return;
  throw new TrustBoundaryError(
    `refusing a non-loopback App Server at ${parsed.hostname}: loopback is this design's trust boundary and there is no client authentication. Pass --allow-remote if you genuinely mean it.`,
  );
}
