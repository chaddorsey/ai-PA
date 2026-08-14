/**
 * cli.ts — argument/env resolution, kept separate from main.ts so it is testable.
 */

import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { assertLoopbackUrl as coreAssertLoopbackUrl } from "@ai-pa/letta-continuity-core";

export interface CliOptions {
  pointerPath: string;
  /** Explicit target, bypassing the pointer file entirely. Both must be given together. */
  agentId: string | undefined;
  conversationId: string | undefined;
  /** One-shot: send this, wait for the reply, exit. Non-TTY stdin fills it when unset. */
  message: string | undefined;
  /** Bound on a one-shot run, in seconds. */
  timeoutSeconds: number;
  /** Emit NDJSON events instead of a human transcript. */
  json: boolean;
  /** Non-interactive subcommand, if one was given. */
  command: "attach" | "conversations-list" | "conversations-create";
  /** conversations-create: optional title. */
  title: string | undefined;
  /** conversations-create: write the new {agent, conversation} to this pointer path. */
  writePointer: string | undefined;
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
/** Generous: local turns in this system run 51s-600s. */
const DEFAULT_TIMEOUT_SECONDS = 180;

export const DEFAULT_POINTER_PATH = join(homedir(), ".letta", "continuity-pointer.json");

export const USAGE = `letta-continuity — terminal client for the sole-owner Letta App Server

USAGE
  letta-continuity [options]                       attach and stream (default)
  letta-continuity conversations list [options]    list this agent's conversations
  letta-continuity conversations create [options]  create one (Unit 8's seed operation)

Attaches to the {agent, conversation} named by the continuity pointer file and streams the
conversation live. Turns typed here and turns from any other surface (e.g. the web client)
appear in the same transcript.

OPTIONS
  --pointer <path>   Pointer file to read (default: ${DEFAULT_POINTER_PATH},
                     or $LETTA_CONTINUITY_POINTER)
  --url <ws-url>     App Server WS URL (default: the core's ws://127.0.0.1:4577/ws,
                     or $LETTA_CONTINUITY_WS_URL)
  --agent <id>       Attach to this agent (with --conversation), instead of reading a pointer
  --conversation <id>
  --message <text>   Send one message, print the reply, exit. Also the default when stdin is
                     not a TTY, so \`echo "..." | letta-continuity\` works
  --timeout <sec>    Bound on a one-shot run (default: 180)
  --json             Emit NDJSON events on stdout instead of a human transcript
  --title <text>     conversations create: title for the new conversation
  --write-pointer <path>
                     conversations create: write the resulting pointer file, so the seed loop
                     closes without hand-rolling JSON
  --reasoning        Show the model's reasoning stream (hidden by default)
  --strict-version   Refuse to attach unless the server is a contract-verified version
  --allow-remote     Permit a non-loopback --url (loopback is the trust boundary; there is no
                     client authentication, so only do this if you understand the exposure)
  --no-color         Disable ANSI colour (also honours $NO_COLOR)
  -h, --help         Show this help

EXIT CODES
  0  clean detach, or a one-shot that completed
  1  could not attach, the session died, or a message was not delivered
  2  bad arguments

IN-SESSION
  Type a message and press Enter to send it. Ctrl-C (or /exit) leaves; the conversation and
  any running turn continue on the server — this client is only a viewer/injector, never the
  owner of the runtime.`;

/**
 * Loopback binding IS the trust boundary for this design — the App Server takes no client auth
 * because it only listens on 127.0.0.1 (R20).
 *
 * The rule itself now lives in the CORE, next to the code that opens the socket, so every surface
 * gets it rather than only the one whose argument parser remembers to ask. This wrapper exists to
 * keep the CLI's error type (and therefore its friendly exit path) unchanged.
 */
export function assertLoopbackUrl(raw: string, allowRemote: boolean): void {
  try {
    coreAssertLoopbackUrl(raw, allowRemote);
  } catch (err) {
    throw new CliError(err instanceof Error ? err.message : String(err));
  }
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
    agentId: undefined,
    conversationId: undefined,
    message: undefined,
    timeoutSeconds: DEFAULT_TIMEOUT_SECONDS,
    json: false,
    command: "attach",
    title: undefined,
    writePointer: undefined,
  };

  // Subcommands are positional and must come first, so they cannot be confused with a value.
  let args = argv;
  if (args[0] === "conversations") {
    const verb = args[1];
    if (verb === "list") opts.command = "conversations-list";
    else if (verb === "create") opts.command = "conversations-create";
    else throw new CliError(`unknown conversations subcommand: ${verb ?? "(none)"}`);
    args = args.slice(2);
  }

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
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
        const value = args[++i];
        if (!value) throw new CliError("--pointer requires a path");
        opts.pointerPath = value;
        break;
      }
      case "--title": {
        const value = args[++i];
        if (value === undefined) throw new CliError("--title requires text");
        opts.title = value;
        break;
      }
      case "--write-pointer": {
        const value = args[++i];
        if (!value) throw new CliError("--write-pointer requires a path");
        opts.writePointer = resolve(value);
        break;
      }
      case "--json":
        opts.json = true;
        break;
      case "--agent": {
        const value = args[++i];
        if (!value) throw new CliError("--agent requires an agent id");
        opts.agentId = value;
        break;
      }
      case "--conversation": {
        const value = args[++i];
        if (!value) throw new CliError("--conversation requires a conversation id");
        opts.conversationId = value;
        break;
      }
      case "--message":
      case "-m": {
        const value = args[++i];
        if (value === undefined) throw new CliError("--message requires text");
        opts.message = value;
        break;
      }
      case "--timeout": {
        const value = args[++i];
        const parsed = Number(value);
        if (!value || !Number.isFinite(parsed) || parsed <= 0) {
          throw new CliError("--timeout requires a positive number of seconds");
        }
        opts.timeoutSeconds = parsed;
        break;
      }
      case "--url": {
        const value = args[++i];
        if (!value) throw new CliError("--url requires a ws:// URL");
        opts.url = value;
        break;
      }
      default:
        throw new CliError(`unknown option: ${arg}\n\n${USAGE}`);
    }
  }
  if (opts.url) assertLoopbackUrl(opts.url, opts.allowRemote);
  if ((opts.agentId === undefined) !== (opts.conversationId === undefined)) {
    throw new CliError("--agent and --conversation must be given together");
  }
  // Resolve to an absolute path HERE. The bin wrapper cds to the launchpad directory before exec,
  // so a relative --pointer was being opened relative to a directory the caller never chose —
  // ENOENT at best, and at worst attaching to a different conversation that happened to match.
  opts.pointerPath = resolve(opts.pointerPath);
  return opts;
}
