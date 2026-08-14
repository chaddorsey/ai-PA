/**
 * cli.ts — argument/env resolution, kept separate from main.ts so it is testable.
 */

import { homedir } from "node:os";
import { join } from "node:path";

export interface CliOptions {
  pointerPath: string;
  url: string | undefined;
  showReasoning: boolean;
  color: boolean | undefined;
  help: boolean;
  /** Refuse to attach to a server whose version is not contract-verified. */
  strictVersion: boolean;
  /** Permit a non-loopback App Server URL. Off by default — loopback is the trust boundary. */
  allowRemote: boolean;
}

export class CliError extends Error {
  override name = "CliError";
}

/**
 * The durable `{agent, conversation}` pointer both M1 surfaces read at startup. Targeting is
 * pointer-driven ON PURPOSE: not by recency (enrichment turns pollute it) and not the literal
 * `"default"` (the legacy `~/bin/letta-*` wrapper target → cross-talk).
 */
export const DEFAULT_POINTER_PATH = join(homedir(), ".letta", "continuity-pointer.json");

export const USAGE = `letta-continuity — terminal client for the sole-owner Letta App Server

USAGE
  letta-continuity [options]

Attaches to the {agent, conversation} named by the continuity pointer file and streams the
conversation live. Turns typed here and turns from any other surface (e.g. the web client)
appear in the same transcript.

OPTIONS
  --pointer <path>   Pointer file to read (default: ${DEFAULT_POINTER_PATH},
                     or $LETTA_CONTINUITY_POINTER)
  --url <ws-url>     App Server WS URL (default: the core's ws://127.0.0.1:4577/ws,
                     or $LETTA_CONTINUITY_WS_URL)
  --reasoning        Show the model's reasoning stream (hidden by default)
  --strict-version   Refuse to attach unless the server is a contract-verified version
  --allow-remote     Permit a non-loopback --url (loopback is the trust boundary; there is no
                     client authentication, so only do this if you understand the exposure)
  --no-color         Disable ANSI colour (also honours $NO_COLOR)
  -h, --help         Show this help

IN-SESSION
  Type a message and press Enter to send it. Ctrl-C (or /exit) leaves; the conversation and
  any running turn continue on the server — this client is only a viewer/injector, never the
  owner of the runtime.`;

/**
 * Loopback binding IS the trust boundary for this design — the App Server takes no client auth
 * because it only listens on 127.0.0.1 (R20). A client that will dial anywhere and then treat the
 * peer as the trusted App Server inverts that: everything typed, and the whole conversation
 * history via conversation_messages_list, goes to the remote host in cleartext, and whatever it
 * streams back renders under the agent's own label. `ws.ts` already ASSERTS this invariant in a
 * comment; this enforces it.
 */
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

export function assertLoopbackUrl(raw: string, allowRemote: boolean): void {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new CliError(`--url is not a valid URL: ${raw}`);
  }
  if (parsed.protocol !== "ws:" && parsed.protocol !== "wss:") {
    throw new CliError(`--url must be ws:// or wss:// (got ${parsed.protocol})`);
  }
  if (allowRemote || LOOPBACK_HOSTS.has(parsed.hostname)) return;
  throw new CliError(
    `refusing a non-loopback App Server at ${parsed.hostname}: loopback is this design's trust boundary and there is no client authentication. Pass --allow-remote if you genuinely mean it.`,
  );
}

export function parseArgs(argv: readonly string[], env: NodeJS.ProcessEnv = {}): CliOptions {
  const opts: CliOptions = {
    pointerPath: env.LETTA_CONTINUITY_POINTER || DEFAULT_POINTER_PATH,
    url: env.LETTA_CONTINUITY_WS_URL || undefined,
    showReasoning: false,
    color: env.NO_COLOR ? false : undefined,
    help: false,
    strictVersion: false,
    allowRemote: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case "-h":
      case "--help":
        opts.help = true;
        break;
      case "--reasoning":
        opts.showReasoning = true;
        break;
      case "--strict-version":
        opts.strictVersion = true;
        break;
      case "--no-color":
        opts.color = false;
        break;
      case "--allow-remote":
        opts.allowRemote = true;
        break;
      case "--pointer": {
        const value = argv[++i];
        if (!value) throw new CliError("--pointer requires a path");
        opts.pointerPath = value;
        break;
      }
      case "--url": {
        const value = argv[++i];
        if (!value) throw new CliError("--url requires a ws:// URL");
        opts.url = value;
        break;
      }
      default:
        throw new CliError(`unknown option: ${arg}\n\n${USAGE}`);
    }
  }
  if (opts.url) assertLoopbackUrl(opts.url, opts.allowRemote);
  return opts;
}
