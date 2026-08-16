#!/usr/bin/env -S npx tsx
/**
 * main.ts — the terminal surface.
 *
 * A PURE CLIENT of the sole-owner App Server: it speaks `/ws` and never opens
 * `~/.letta/lc-local-backend`. That distinction is the whole point of Unit 5 — the legacy
 * `~/bin/letta-<slug>` wrappers run `letta --backend local`, which makes them *second writers*
 * on the backend the App Server sole-owns (R1/R4). This client cannot do that.
 *
 * The whole program is `run(argv, env, io)`, which returns an exit code and touches no global.
 * It used to be a top-level `main()` that read `process.argv`, wrote to `process.stdout`, built
 * its own readline and called `process.exit` — so nothing in it could be tested, and it held
 * three defects nobody could have caught: a one-shot that hung on tool-using replies, `--json`
 * output that was not parseable because the human echo shared the stream, and `process.exit()`
 * truncating piped stdout mid-flush (122 of 20,000 lines delivered, at exit 0).
 */

import { copyFile } from "node:fs/promises";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import {
  ContinuityCore,
  type ContinuityCoreConfig,
  type RenderEvent,
  evictOldest,
  protocol,
  writePointer,
} from "@ai-pa/letta-continuity-core";
import { CliError, USAGE, parseArgs } from "./cli.js";
import { ControllerCore } from "./controller-core.js";
import { MAX_TRACKED_ORIGINS } from "./render.js";
import { sanitize } from "./sanitize.js";
import { TerminalSession, classifyInput } from "./session.js";

/** What a line typed (or piped) into the session did. */
export type InputOutcome = "sent" | "ignored" | "failed" | "exit";

/**
 * Everything `run` touches outside itself.
 *
 * Injected rather than reached for, so the program can be driven end-to-end against a real core
 * and a mock App Server without a TTY, a pipe, or a process exit.
 */
export interface TerminalIO {
  stdout: (text: string) => void;
  stderr: (text: string) => void;
  /** The whole of a non-TTY stdin as one message, or undefined when stdin is interactive. */
  readPipedMessage: () => Promise<string | undefined>;
  /** Drive the interactive loop. Resolves when the user leaves. */
  interactive: (onLine: (line: string) => InputOutcome) => Promise<void>;
  /** Whether stdout is a terminal — decides colour and line editing, nothing else. */
  isStdoutTTY: boolean;
  /** Build the core. Overridable so a test can inject a transport or a fault. */
  createCore?: (config: ContinuityCoreConfig) => ContinuityCore;
}

/**
 * NDJSON line.
 *
 * `JSON.stringify` escapes C0 but leaves U+007F and the C1 block (U+0080-U+009F) as raw bytes —
 * and U+009B is an 8-bit CSI, so a `--json` stream piped into a terminal carried live escape
 * sequences straight through the one output path that had deliberately skipped sanitization. The
 * consumer still gets the real characters: they arrive as the two characters \\u009b, which is what a JSON parser
 * hands back, rather than as something the pipe's other end acts on.
 */
export function ndjson(value: unknown): string {
  return `${JSON.stringify(value).replace(
    /[\u007f-\u009f]/g,
    (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`,
  )}\n`;
}

/**
 * Send one message, wait for the runtime to go idle, return an exit code.
 *
 * NOT keyed on "our run finished". A multi-step agentic reply spans several runs and the run our
 * send started is never closed — captured live: `local-run-320` began, a tool ran, a NEW
 * `local-run-321` began and finished, and 320 was simply never closed. Waiting for our own run to
 * finish therefore hangs on every tool-using reply, which is most of them.
 */
async function runOneShot(
  core: ContinuityCore,
  send: () => InputOutcome,
  io: TerminalIO,
  timeoutSeconds: number,
): Promise<number> {
  if (send() !== "sent") {
    io.stderr("— message was not delivered\n");
    return 1;
  }

  return new Promise<number>((resolve) => {
    let settled = false;
    // Capture OUR turn at turn_start. Ownership is released at turn_finished (and at the idle
    // that precedes it), so asking later always reads false and the wait never ends.
    let sawOurTurn = false;
    // A reconnect between the send and the reply demotes attribution to `unknown` by design: an
    // unknown number of runs may have begun and ended across the gap. Waiting for a run we can
    // still prove is ours therefore hangs FOREVER after a mid-turn reconnect — observed rendering
    // the full reply and then exiting 1 on the timeout. After a seam, a turn we cannot positively
    // attribute to a peer counts.
    let attributionLost = false;
    const finish = (code: number): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(code);
    };
    const timer = setTimeout(() => {
      io.stderr(`— timed out after ${timeoutSeconds}s waiting for a reply\n`);
      finish(1);
    }, timeoutSeconds * 1000);
    core.onConnectionState((state) => {
      if (state === "reconnecting") attributionLost = true;
    });
    core.onFatal(() => finish(1));
    core.onRender((e) => {
      if (e.type === "turn_start" && e.runId) {
        const ours =
          core.ownsRun(e.runId) || (attributionLost && core.attributeRun(e.runId) !== "foreign");
        if (ours) sawOurTurn = true;
        return;
      }
      // A turn that ENDED IN ERROR is over, and on this server path no idle follows it — so a wait
      // keyed only on the shared idle had nothing to wake it and sat out the whole `--timeout`
      // (measured: 20.32s at `--timeout 20`, 180s by default) before reporting a timeout and
      // blaming a server that had answered immediately.
      //
      // ADDITIVE, on purpose. This is a PER-RUN signal read from the frame itself; it does not
      // change how idle terminates a turn and does not change how a run is attributed. It reuses
      // the existing `sawOurTurn` guard rather than inventing a second rule, so a peer's failed
      // turn ends our one-shot exactly as often as a peer's idle already does — no more, no less.
      if (sawOurTurn && e.type === "turn_finished" && e.stopReason === protocol.StopReasons.error) {
        finish(1);
        return;
      }
      // Terminate on the agent going IDLE. `sawOurTurn` guards against resolving on the idle that
      // PRECEDES our turn, or that ends a peer's while ours is still queued.
      if (
        sawOurTurn &&
        e.type === "loop_status" &&
        e.status === protocol.LoopStatuses.waitingOnInput
      ) {
        finish(0);
      }
    });
  });
}

/**
 * The slice of the core the `--json` bridge uses.
 *
 * Structural rather than the concrete `ContinuityCore` so the bridge's own bounds and origin
 * handling can be driven frame-by-frame by a stub — the same seam reasoning as `SessionCore`.
 * Without it, the only way to reach this code is a real socket and a real server, which is why
 * the unbounded map here went unnoticed while both caches on the human path were bounded AND
 * asserted.
 */
export interface JsonBridgeCore {
  onRender: (cb: (e: RenderEvent) => void) => () => void;
  onConnectionState: (cb: (state: string) => void) => () => void;
  onApproval: (cb: (a: { requestId: string; outcome: string }) => void) => () => void;
  onFatal: (
    cb: (err: { reason: string; requestId?: string; origin?: string; message: string }) => void,
  ) => () => void;
  onError: (cb: (err: Error) => void) => () => void;
  ownsRun: (runId: string | undefined) => boolean;
  attributeRun: (runId: string | undefined) => string;
}

/**
 * NDJSON output for machine consumers.
 *
 * The human transcript is deliberately lossy — origin labels, `— ` notice prefixes, sanitizer
 * rewrites and continuation indents — so a wrapper parsing it has to reverse all of that, and an
 * agent reply containing a line starting with `— ` breaks the parse. The core already hands us a
 * structured event; this stops throwing it away. Text is NOT sanitized: the consumer is not a
 * terminal and needs the real characters, which is why they are ESCAPED rather than stripped.
 */
export function attachJson(
  core: JsonBridgeCore,
  io: TerminalIO,
  // Injected so the BOUND is assertable rather than merely intended — the same reason
  // `Renderer.trackedOriginCount` exists. A caller that does not care omits it.
  originByRun: Map<string, string> = new Map<string, string>(),
): () => void {
  // Origin is captured at turn_start and held for the run. Asking at turn_finished reads the
  // state AFTER ownership is released, which reported every completed turn of our own as
  // "unknown" — the same trap the human renderer already guards against.
  const offs = [
    core.onRender((e: RenderEvent) => {
      if (e.type === "turn_start" && e.runId) {
        originByRun.set(e.runId, core.ownsRun(e.runId) ? "self" : core.attributeRun(e.runId));
      }
      const origin = e.runId ? originByRun.get(e.runId) : undefined;
      if (e.type === "turn_finished" && e.runId) originByRun.delete(e.runId);
      // Entries normally leave at turn_finished — but a tool-using reply's FIRST run is never
      // closed (captured live), so on the `--json` bridge path this map gained one entry per
      // tool-using turn and never gave it back. Both origin caches on the human path are bounded;
      // this one was not, on the path a long-lived bridge actually uses.
      evictOldest(originByRun, MAX_TRACKED_ORIGINS);
      io.stdout(
        ndjson({
          kind: e.type,
          runId: e.runId,
          origin,
          messageId: e.messageId,
          messageType: e.messageType,
          text: e.text,
          // The loop status was dropped, which is the one field a machine consumer needs to know
          // the turn is over — this client's own one-shot terminates on it.
          status: e.status,
          stopReason: e.stopReason,
          eventSeq: e.eventSeq,
        }),
      );
    }),
    core.onConnectionState((state) => io.stderr(ndjson({ kind: "connection_state", state }))),
    core.onApproval((a) => io.stderr(ndjson({ kind: "approval", ...a }))),
    core.onFatal((err) =>
      io.stderr(
        ndjson({
          kind: "fatal",
          reason: err.reason,
          requestId: err.requestId,
          origin: err.origin,
          message: err.message,
        }),
      ),
    ),
    core.onError((err) => io.stderr(ndjson({ kind: "error", message: err.message }))),
  ];
  return () => {
    for (const off of offs) off();
  };
}

/**
 * One field of the `conversations list` TSV.
 *
 * `sanitize` deliberately PRESERVES `\t` and `\n` — they are legitimate content in a transcript.
 * In a tab-separated, newline-delimited record they are the delimiters, and the fields here are
 * server-supplied and validated only as `typeof === "string"`. A conversation id containing a
 * newline therefore injects whole extra records into whatever parses this — Unit 8's cutover
 * script among them. The two escapes that are safe everywhere else are exactly the two that are
 * not safe here, which is why this cannot be left to the sanitizer.
 */
function tsvField(value: string, maxLength: number): string {
  return sanitize(value, { maxLength }).replace(/[\t\n]+/g, " ");
}

async function runConversationsCommand(
  core: ContinuityCore,
  options: ReturnType<typeof parseArgs>,
  io: TerminalIO,
): Promise<number> {
  if (options.command === "conversations-list") {
    const conversations = await core.conversationList();
    for (const c of conversations) {
      io.stdout(
        options.json
          ? ndjson(c)
          : `${tsvField(c.id, 120)}\t${c.archived ? "archived" : "active"}\t${tsvField(c.updated_at, 40)}\n`,
      );
    }
    return 0;
  }

  const created = await core.conversationCreate(options.title);
  if (!created) {
    io.stderr("— conversation_create returned no conversation\n");
    return 1;
  }
  const runtime = core.getRuntime();
  if (options.writePointer) {
    // Keep a copy of whatever was there. This path is how the cutover seeds the pointer every
    // surface reads, so overwriting it silently retargets every attached client — and the file it
    // replaces may be the only record of the conversation now orphaned.
    try {
      await copyFile(options.writePointer, `${options.writePointer}.bak`);
      // The PATH is argv, so it echoes back whatever was passed — sanitized like every other
      // string this process did not author.
      io.stderr(
        `— previous pointer saved to ${sanitize(options.writePointer, { maxLength: 512 })}.bak\n`,
      );
    } catch {
      // Nothing there to preserve: the ordinary first-run case.
    }
    await writePointer(options.writePointer, {
      agentId: runtime.agent_id,
      conversationId: created.id,
      label: options.title,
    });
    io.stderr(`— pointer written to ${sanitize(options.writePointer, { maxLength: 512 })}\n`);
  }
  io.stdout(
    options.json
      ? ndjson({ agent_id: runtime.agent_id, conversation_id: created.id })
      : `${sanitize(created.id, { maxLength: 120 })}\n`,
  );
  return 0;
}

/**
 * The controller-transport session (C6): the terminal as a SURFACE. Reuses the reviewed,
 * mutation-bound render/sanitize/NDJSON machinery through the same seams the raw path uses —
 * only the transport under them changed. Session commands beyond plain text: `/abort`
 * (operator turn kill), `/approve` · `/deny` (approval arbitration). An `@specialist` address
 * is NOT parsed here — the controller owns routing; the terminal passes the line through.
 */
async function runController(
  options: ReturnType<typeof parseArgs>,
  io: TerminalIO,
): Promise<number> {
  if (options.command !== "attach") {
    io.stderr(
      "— conversation management over the controller arrives with the web-surface unit (C9); use --direct (break-glass) for now\n",
    );
    return 2;
  }
  let runtime: { agent_id: string; conversation_id: string };
  if (options.agentId && options.conversationId) {
    runtime = { agent_id: options.agentId, conversation_id: options.conversationId };
  } else {
    const { readPointer } = await import("@ai-pa/letta-continuity-core");
    try {
      const pointer = await readPointer(options.pointerPath);
      runtime = { agent_id: pointer.agentId, conversation_id: pointer.conversationId };
    } catch (err) {
      io.stderr(`\nCould not attach: ${sanitize((err as Error).message, { maxLength: 512 })}\n`);
      return 1;
    }
  }

  const core = new ControllerCore({
    url: options.controllerUrl,
    tokenFile: options.tokenFile,
    runtime,
    onWarn: (msg) => io.stderr(`— ${sanitize(msg, { maxLength: 512 })}\n`),
  });

  let exitCode = 0;
  core.onFatal(() => {
    exitCode = 1;
  });

  const session = new TerminalSession(core, {
    write: io.stdout,
    writeErr: io.stderr,
    color: options.color ?? io.isStdoutTTY,
    showReasoning: options.showReasoning,
  });
  const detach = options.json ? attachJson(core, io) : session.attach();
  // A LIVE failed turn fails an interactive session's exit — the same rule as the raw path's
  // ERROR_DELTA_TYPES hook. Attached BEFORE start() so the attach replay itself exercises the
  // live/replayed distinction: REPLAYED history must not poison this run's exit code. The
  // one-shot path detaches this hook — its exit belongs to its own receipt's outcome alone.
  const offLiveFailures = core.onTurnOutcome(
    (_cm: string | null, outcome: string, live: boolean) => {
      if (live && (outcome.startsWith("FAILED") || outcome.startsWith("failed"))) exitCode = 1;
    },
  );

  try {
    await core.start();
  } catch (err) {
    io.stderr(`\nCould not attach: ${sanitize((err as Error).message, { maxLength: 512 })}\n`);
    detach();
    core.stop();
    return 1;
  }

  const oneShotMessage = options.message ?? (await io.readPipedMessage());
  if (oneShotMessage !== undefined) offLiveFailures();
  if (oneShotMessage !== undefined) {
    const code = await new Promise<number>((resolve) => {
      let settled = false;
      let myCm: string | null = null;
      const finish = (c: number): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(c);
      };
      const timer = setTimeout(() => {
        io.stderr(`— timed out after ${options.timeoutSeconds}s waiting for a reply\n`);
        finish(1);
      }, options.timeoutSeconds * 1000);
      core.onReceipt((cm) => {
        myCm = cm;
        if (options.json) io.stdout(ndjson({ kind: "sent", clientMessageId: cm }));
      });
      // Controller data ends the wait: the outcome row for EXACTLY our receipt's turn.
      core.onTurnOutcome((cm, outcome) => {
        if (cm !== null && cm === myCm) {
          finish(outcome.startsWith("FAILED") || outcome.startsWith("failed") ? 1 : 0);
        }
      });
      core.onFatal(() => finish(1));
      const intent = classifyInput(oneShotMessage);
      if (intent.kind !== "send") return finish(0);
      const outcome = options.json
        ? ((): InputOutcome => {
            try {
              core.send(intent.text);
              return "sent";
            } catch (err) {
              io.stderr(ndjson({ kind: "error", message: (err as Error).message }));
              return "failed";
            }
          })()
        : session.handleInput(oneShotMessage);
      if (outcome !== "sent") {
        io.stderr("— message was not delivered\n");
        finish(1);
      }
    });
    session.finish();
    detach();
    core.stop();
    return code === 0 ? exitCode : code;
  }

  io.stderr(
    `— attached via controller to ${sanitize(runtime.agent_id, { maxLength: 120 })} · conversation ${sanitize(runtime.conversation_id, { maxLength: 120 })}
— type a message and press Enter; /exit leaves, /abort kills the running turn, /approve · /deny answer approvals
`,
  );

  await io.interactive((line) => {
    const trimmed = line.trim();
    if (trimmed === "/abort") {
      try {
        core.abort();
        io.stderr("— abort requested\n");
      } catch (err) {
        io.stderr(`— abort failed: ${sanitize((err as Error).message, { maxLength: 256 })}\n`);
      }
      return "ignored";
    }
    if (trimmed === "/approve" || trimmed === "/deny") {
      const answered = core.answerApproval(trimmed === "/approve" ? "allow" : "deny");
      io.stderr(answered ? `— ${trimmed.slice(1)} sent\n` : "— no approval is pending\n");
      return "ignored";
    }
    const outcome = session.handleInput(line);
    if (outcome === "failed") exitCode = 1;
    return outcome;
  });

  session.finish();
  detach();
  core.stop();
  // The INVERSE of the raw-WS detach caveat, by architecture: the controller's anchor+worker
  // hold the runtime's subscriptions, so a running turn continues without this terminal.
  io.stderr("— detached (the controller keeps the turn running; re-attach to catch up)\n");
  return exitCode;
}

/** The whole program. Returns the exit code; writes nothing except through `io`. */
export async function run(
  argv: readonly string[],
  env: NodeJS.ProcessEnv,
  io: TerminalIO,
): Promise<number> {
  let options: ReturnType<typeof parseArgs>;
  try {
    options = parseArgs(argv, env);
  } catch (err) {
    // Sanitized like every sibling diagnostic — this one was the exception, and it is the FIRST
    // thing the program can print, before any socket opens.
    //
    // The message embeds argv and env verbatim: `letta-continuity $'\x1b]52;c;…\x07'` comes back
    // as `unknown option: <ESC>]52;…`, which is an OSC-52 clipboard write executed by the
    // operator's terminal, and `--url $'\x1b]0;…\x07'` spoofs the window title through
    // TrustBoundaryError. Agents write this repo's env and invoke this binary, so "the input is
    // the operator's own" does not hold here.
    io.stderr(
      `${sanitize(err instanceof CliError ? err.message : String(err), { maxLength: 512 })}\n`,
    );
    return 2;
  }
  if (options.help) {
    io.stdout(`${USAGE}\n`);
    return 0;
  }

  // C6: the controller transport is the DEFAULT. The raw-WS path below survives as the
  // break-glass client (operator decision 2026-08-15) and announces its suspended guarantees.
  if (options.transport === "controller") return runController(options, io);
  io.stderr(
    "— DIRECT (break-glass) transport: single-submitter ownership and attribution guarantees are suspended; detaching mid-turn may cancel the turn\n",
  );

  const color = options.color ?? io.isStdoutTTY;
  const config: ContinuityCoreConfig = {
    ...(options.agentId && options.conversationId
      ? { pointer: { agentId: options.agentId, conversationId: options.conversationId } }
      : { pointerPath: options.pointerPath }),
    ...(options.url ? { url: options.url } : {}),
    versionPolicy: options.strictVersion ? "refuse" : "warn",
    // The CLI validated the URL, but the CORE is what opens the socket and it applies the same
    // rule — so without forwarding the opt-in, `--allow-remote` passed the argument parser and
    // was then refused by the layer it was meant to unlock. The flag simply did not work.
    allowRemote: options.allowRemote,
    // onWarn payloads embed server strings (snapshot errors, reported versions, capability
    // names). They bypass the Renderer, so they are sanitized here rather than trusted.
    onWarn: (msg) => io.stderr(`— ${sanitize(msg, { maxLength: 512 })}\n`),
  };
  const core = (io.createCore ?? ((c) => new ContinuityCore(c)))(config);

  // A session-fatal condition must reach the EXIT CODE, not only the transcript.
  let exitCode = 0;
  core.onFatal(() => {
    exitCode = 1;
  });
  // So must a FAILED TURN. This is deliberately here rather than in the renderer: the exit code
  // has to be the same whether the run is rendering a human transcript or NDJSON, and `--json`
  // does not go through the renderer at all. A turn that errored is not a successful run, and
  // reporting 0 for one is what let a provider outage look like an agent with nothing to say.
  core.onRender((e) => {
    if (e.type === "delta" && e.messageType && protocol.ERROR_DELTA_TYPES.has(e.messageType)) {
      exitCode = 1;
    }
  });

  const session = new TerminalSession(core, {
    write: io.stdout,
    writeErr: io.stderr,
    color,
    showReasoning: options.showReasoning,
  });
  // Subcommands print one result; they must not also emit the live transcript, or their stdout
  // is unparseable (a stray "— subagents idle" landed in `conversations list` output).
  const detach =
    options.command !== "attach"
      ? (): void => {}
      : options.json
        ? attachJson(core, io)
        : session.attach();

  try {
    await core.start();
  } catch (err) {
    // Pointer problems and version refusals both land here, and both are actionable.
    // Version-gate failures embed server-reported version and capability strings.
    io.stderr(`\nCould not attach: ${sanitize((err as Error).message, { maxLength: 512 })}\n`);
    detach();
    core.stop();
    return 1;
  }

  // Non-interactive subcommands: connect, do one thing, print it, exit. These exist because the
  // core's conversation RPCs had no executable surface at all — the pointer error told operators
  // to seed a conversation via an RPC only reachable by writing TypeScript against an
  // unpublished package.
  if (options.command !== "attach") {
    try {
      const code = await runConversationsCommand(core, options, io);
      return code;
    } catch (err) {
      io.stderr(`— ${sanitize((err as Error).message, { maxLength: 512 })}\n`);
      return 1;
    } finally {
      detach();
      core.stop();
    }
  }

  // Read piped stdin only once we know we are attaching and were not given a message. Doing it
  // at startup blocked forever whenever stdin was a non-TTY that never closes — which is every
  // subcommand run from a supervisor, and is how `conversations list` hung.
  const oneShotMessage = options.message ?? (await io.readPipedMessage());

  const runtime = core.getRuntime();
  if (oneShotMessage !== undefined) {
    // In `--json` mode the send must NOT go through the session: its local echo (`you › …`) is
    // human text on the stdout that is supposed to be nothing but NDJSON, so one line of every
    // one-shot failed to parse.
    // What the line MEANS is decided in one place (`classifyInput`) for both paths; only the ECHO
    // differs. This path used to re-implement the whole thing and had already diverged: `--json`
    // sent a blank message as a turn, and sent the literal text `/exit` to the agent instead of
    // leaving.
    const send = (): InputOutcome => {
      if (!options.json) return session.handleInput(oneShotMessage);
      const intent = classifyInput(oneShotMessage);
      if (intent.kind !== "send") return intent.kind;
      try {
        const handle = core.send(intent.text);
        io.stdout(ndjson({ kind: "sent", requestId: handle.requestId, text: intent.text }));
        return "sent";
      } catch (err) {
        io.stderr(ndjson({ kind: "error", message: (err as Error).message }));
        return "failed";
      }
    };
    const code = await runOneShot(core, send, io, options.timeoutSeconds);
    session.finish();
    detach();
    core.stop();
    return code === 0 ? exitCode : code;
  }

  // Pointer-derived, and the pointer decides which AGENT this attaches to — a swapped pointer
  // silently retargets the session, so show it and do not trust its contents.
  io.stderr(
    `— attached to ${sanitize(runtime.agent_id, { maxLength: 120 })} · conversation ${sanitize(runtime.conversation_id, { maxLength: 120 })}
— type a message and press Enter; /exit to leave
`,
  );

  await io.interactive((line) => {
    const outcome = session.handleInput(line);
    // A message the client could not deliver is a failure the caller must be able to see.
    if (outcome === "failed") exitCode = 1;
    return outcome;
  });

  session.finish();
  detach();
  core.stop();
  // NOT "the conversation continues on the server". The conversation persists, but the App
  // Server "requests cancellation of its active turn" when no other subscribed client can take
  // over — and in ordinary terminal use this IS the only client. Verified live: a turn executing
  // a 25s tool was dead within 6s of detaching, runtime back to WAITING_ON_INPUT with no output.
  // The old message told the operator the opposite of what happens at the moment it printed.
  io.stderr(
    "— detached (a turn still running may have been cancelled; the conversation remains)\n",
  );
  return exitCode;
}

// ── the process-facing shell ────────────────────────────────────────────────

/**
 * A writer that survives its consumer going away.
 *
 * `letta-continuity --json | head -3` killed the client with an unhandled `EPIPE`. The
 * listener-isolation fix does not cover it and could not: a failed write to a pipe is reported
 * ASYNCHRONOUSLY, as an `error` event on the socket, long after the `write()` call returned — so
 * no try/catch around the write can see it, and Node's default policy turns it into an exit with
 * a stack trace on stderr. Offline tests cannot see it either, because they capture into arrays
 * and an array never closes. It took a real pipe to find.
 *
 * A downstream `head` or `less` closing is the consumer saying "enough", not a failure, so the
 * response is to stop writing and leave quietly.
 */
export function guardedWriter(
  stream: Pick<NodeJS.WriteStream, "on" | "write">,
  onGone: (err: NodeJS.ErrnoException) => void,
): (text: string) => void {
  let gone = false;
  stream.on("error", (err: NodeJS.ErrnoException) => {
    // NEVER rethrow. This runs inside an EventEmitter `error` listener, so a throw here becomes an
    // uncaughtException and kills the process — including on stderr, whose whole contract is that
    // losing it is survivable. The old code rethrew everything that was not EPIPE, which turned a
    // recoverable IO fault (EIO on a detached tty, ECONNRESET, ENOSPC) into a crash with a stack
    // trace, on the stream the crash report itself would have to be written to.
    //
    // Either way the stream is GONE: nothing more can be written to it. What differs is what the
    // caller does about it, which is why the error is handed on rather than classified here.
    gone = true;
    onGone(err);
  });
  return (text: string) => {
    if (gone) return;
    stream.write(text);
  };
}

function nodeIO(): TerminalIO {
  return {
    // Losing STDOUT ends the session: the transcript had one reader and it has gone. Exiting
    // outright is safe here in a way it is not on the normal path — there is nothing left to
    // flush, because the stream that would have been flushed is the one that closed.
    //
    // `process.exitCode ?? 0`, NOT a literal 0. A run that had already FAILED reported success the
    // moment its consumer went away, on all three channels at once: the exit code was overwritten,
    // stdout was closed, and the stderr notice never got written. Measured on one run: CODE=1
    // unpiped, CODE=0 through `| head`. A consumer choosing to stop reading does not retroactively
    // make a failed session succeed.
    stdout: guardedWriter(process.stdout, (err) => {
      // EPIPE is `head`/`less` saying "enough" — not a failure, so it does not create one. Any
      // other error means the transcript genuinely could not be written, which does.
      if (err.code !== "EPIPE") process.exitCode = 1;
      process.exit(process.exitCode ?? 0);
    }),
    // Losing STDERR is survivable: the conversation is on stdout, so keep going quietly. This
    // holds for a non-EPIPE fault too — there is simply nowhere left to report it.
    stderr: guardedWriter(process.stderr, () => {}),
    isStdoutTTY: Boolean(process.stdout.isTTY),
    /**
     * Whole-stream, not line-by-line: `echo "..." | letta-continuity` is one message, and the
     * alternative (a turn per line) would fire N turns at a conversation the caller cannot see
     * the replies from.
     */
    readPipedMessage: async () => {
      if (process.stdin.isTTY) return undefined;
      const chunks: Buffer[] = [];
      for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
      const text = Buffer.concat(chunks).toString("utf-8").trim();
      return text === "" ? undefined : text;
    },
    interactive: (onLine) =>
      new Promise<void>((resolve) => {
        // STDIN IS ALREADY OVER — resolve rather than wait for input that cannot arrive.
        //
        // `letta-continuity --json < /dev/null` is the canonical headless invocation and it hung
        // FOREVER (killed at budget; an earlier run sat three minutes). The path: stdin is not a
        // TTY, so `readPipedMessage` drains it to EOF and finds nothing, so there is no one-shot
        // message and this interactive loop runs — over a stream whose `end` already fired. A
        // readline built on an ended stream never emits `close`, so this promise never settled.
        // Nothing in-process could see it: `run()`'s promise simply never resolving is
        // indistinguishable from a slow test, which is why it took spawning the binary to find.
        if (process.stdin.readableEnded) return resolve();
        // Line-editing mode is a TTY question, not a colour question. Tying it to `color` meant
        // NO_COLOR silently turned raw mode OFF, which is what lets pasted escape sequences reach
        // the echo path verbatim.
        const rl = createInterface({
          input: process.stdin,
          output: process.stdout,
          terminal: Boolean(process.stdout.isTTY),
        });
        rl.on("line", (line) => {
          if (onLine(line) === "exit") rl.close();
        });
        rl.on("close", () => resolve());
        // Ctrl-C leaves the CLIENT. The conversation persists, but a running turn may not: the
        // App Server cancels the active turn when the last subscribed client detaches, and in
        // ordinary terminal use this is the only one. See the detach notice below.
        process.on("SIGINT", () => rl.close());
      }),
  };
}

/**
 * True when this module was started as the program, false when a test imported it.
 *
 * Without this, `main.ts` could not be imported at all — so the one-shot wait, the timeout, the
 * exit codes and the NDJSON stream had no tests, and three of this file's defects were found by
 * reading rather than by running.
 */
function isEntrypoint(): boolean {
  const invoked = process.argv[1];
  if (!invoked) return false;
  try {
    return fileURLToPath(import.meta.url) === invoked;
  } catch {
    return false;
  }
}

if (isEntrypoint()) {
  run(process.argv.slice(2), process.env, nodeIO()).then(
    (code) => {
      // `process.exitCode`, NOT `process.exit()`. Exiting outright discards whatever is still
      // buffered for a PIPE: measured at 122 of 20,000 lines delivered, and at exit 0, so a
      // consumer had no way to tell a truncated stream from a complete one. Letting the process
      // end on its own flushes first. The bail-out is only for a handle that leaks — a hung
      // client is a worse failure than a truncated one, but neither should be the normal path.
      process.exitCode = code;
      const bail = setTimeout(() => process.exit(code), 2000);
      bail.unref();
    },
    (err) => {
      const detail = err instanceof Error ? (err.stack ?? err.message) : String(err);
      process.stderr.write(`fatal: ${sanitize(detail, { maxLength: 4096 })}\n`);
      process.exitCode = 1;
    },
  );
}
