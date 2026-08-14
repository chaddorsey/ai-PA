#!/usr/bin/env -S npx tsx
/**
 * main.ts — the terminal surface.
 *
 * A PURE CLIENT of the sole-owner App Server: it speaks `/ws` and never opens
 * `~/.letta/lc-local-backend`. That distinction is the whole point of Unit 5 — the legacy
 * `~/bin/letta-<slug>` wrappers run `letta --backend local`, which makes them *second writers*
 * on the backend the App Server sole-owns (R1/R4). This client cannot do that.
 */

import { createInterface } from "node:readline";
import { ContinuityCore, protocol, writePointer } from "@ai-pa/letta-continuity-core";
import { CliError, USAGE, parseArgs } from "./cli.js";
import { sanitize } from "./sanitize.js";
import { TerminalSession } from "./session.js";

/**
 * Read a single message from a non-TTY stdin, or undefined when stdin is interactive.
 *
 * Whole-stream, not line-by-line: `echo "..." | letta-continuity` is one message, and the
 * alternative (treating each line as a turn) would fire N turns at a conversation the caller
 * cannot see the replies from.
 */
async function readPipedMessage(): Promise<string | undefined> {
  if (process.stdin.isTTY) return undefined;
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
  const text = Buffer.concat(chunks).toString("utf-8").trim();
  return text === "" ? undefined : text;
}

/**
 * Send one message, wait for ITS run to finish, return an exit code.
 *
 * Keyed on the run this send produced — not on "the next turn_finished", which on a shared
 * conversation is frequently a peer's.
 */
async function runOneShot(
  core: ContinuityCore,
  session: TerminalSession,
  message: string,
  timeoutSeconds: number,
): Promise<number> {
  const outcome = session.handleInput(message);
  if (outcome !== "sent") {
    process.stderr.write("— message was not delivered\n");
    return 1;
  }

  return new Promise<number>((resolve) => {
    let settled = false;
    // Capture OUR run id at turn_start. Ownership is released at turn_finished, so asking there
    // always reads false and the wait never ends — the same trap that has now bitten this
    // codebase three times, in ownership tests, in a review assertion, and here.
    let sawOurTurn = false;
    const finish = (code: number): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(code);
    };
    const timer = setTimeout(() => {
      process.stderr.write(`— timed out after ${timeoutSeconds}s waiting for a reply\n`);
      finish(1);
    }, timeoutSeconds * 1000);
    core.onFatal(() => finish(1));
    core.onRender((e) => {
      if (e.type === "turn_start" && e.runId && core.ownsRun(e.runId)) {
        sawOurTurn = true;
        return;
      }
      // Terminate on the agent going IDLE, not on our run finishing.
      //
      // A multi-step agentic reply spans several runs, and the run our send started never emits
      // turn_finished at all — captured live: our `local-run-320` began, a tool ran, a NEW
      // `local-run-321` began and finished, and 320 was simply never closed. Waiting for our own
      // run to finish therefore hangs on every tool-using reply, which is most of them.
      //
      // `sawOurTurn` guards against resolving on the idle that PRECEDES our turn (or that ends a
      // peer's turn while ours is still queued).
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
 * NDJSON output for machine consumers.
 *
 * The human transcript is deliberately lossy — origin labels, `— ` notice prefixes, sanitizer
 * rewrites and continuation indents — so a wrapper parsing it has to reverse all of that, and an
 * agent reply containing a line starting with `— ` breaks the parse. The core already hands us a
 * structured event; this stops throwing it away. Text is NOT sanitized here: the consumer is not
 * a terminal, and it needs the real bytes.
 */
function attachJson(
  core: ContinuityCore,
  write: (t: string) => void,
  writeErr: (t: string) => void,
): () => void {
  const emit = (sink: (t: string) => void, obj: Record<string, unknown>): void => {
    sink(`${JSON.stringify(obj)}\n`);
  };
  // Origin is captured at turn_start and held for the run. Asking at turn_finished reads the
  // state AFTER ownership is released, which reported every completed turn of our own as
  // "unknown" — the same trap the human renderer already guards against.
  const originByRun = new Map<string, string>();
  const offs = [
    core.onRender((e) => {
      if (e.type === "turn_start" && e.runId) {
        originByRun.set(e.runId, core.ownsRun(e.runId) ? "self" : core.attributeRun(e.runId));
      }
      const origin = e.runId ? originByRun.get(e.runId) : undefined;
      if (e.type === "turn_finished" && e.runId) originByRun.delete(e.runId);
      emit(write, {
        kind: e.type,
        runId: e.runId,
        origin,
        messageId: e.messageId,
        messageType: e.messageType,
        text: e.text,
        stopReason: e.stopReason,
        eventSeq: e.eventSeq,
      });
    }),
    core.onConnectionState((state) => emit(writeErr, { kind: "connection_state", state })),
    core.onApproval((a) => emit(writeErr, { kind: "approval", ...a })),
    core.onError((err) => emit(writeErr, { kind: "error", message: err.message })),
  ];
  return () => {
    for (const off of offs) off();
  };
}

async function runConversationsCommand(
  core: ContinuityCore,
  options: ReturnType<typeof parseArgs>,
  write: (t: string) => void,
  writeErr: (t: string) => void,
): Promise<number> {
  if (options.command === "conversations-list") {
    const conversations = await core.conversationList();
    if (options.json) {
      for (const c of conversations) write(`${JSON.stringify(c)}\n`);
    } else {
      for (const c of conversations) {
        write(
          `${sanitize(c.id, { maxLength: 120 })}\t${c.archived ? "archived" : "active"}\t${sanitize(c.updated_at, { maxLength: 40 })}\n`,
        );
      }
    }
    return 0;
  }

  const created = await core.conversationCreate(options.title);
  if (!created) {
    writeErr("— conversation_create returned no conversation\n");
    return 1;
  }
  const runtime = core.getRuntime();
  if (options.writePointer) {
    await writePointer(options.writePointer, {
      agentId: runtime.agent_id,
      conversationId: created.id,
      label: options.title,
    });
    writeErr(`— pointer written to ${options.writePointer}\n`);
  }
  write(
    options.json
      ? `${JSON.stringify({ agent_id: runtime.agent_id, conversation_id: created.id })}\n`
      : `${sanitize(created.id, { maxLength: 120 })}\n`,
  );
  return 0;
}

async function main(): Promise<number> {
  let options: ReturnType<typeof parseArgs>;
  try {
    options = parseArgs(process.argv.slice(2), process.env);
  } catch (err) {
    process.stderr.write(`${err instanceof CliError ? err.message : String(err)}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(`${USAGE}\n`);
    return 0;
  }

  const color = options.color ?? Boolean(process.stdout.isTTY);
  const write = (text: string): void => {
    process.stdout.write(text);
  };
  const writeErr = (text: string): void => {
    process.stderr.write(text);
  };

  const core = new ContinuityCore({
    ...(options.agentId && options.conversationId
      ? { pointer: { agentId: options.agentId, conversationId: options.conversationId } }
      : { pointerPath: options.pointerPath }),
    ...(options.url ? { url: options.url } : {}),
    versionPolicy: options.strictVersion ? "refuse" : "warn",
    // onWarn payloads embed server strings (snapshot errors, reported versions, capability
    // names). They bypass the Renderer, so they are sanitized here rather than trusted.
    onWarn: (msg) => process.stderr.write(`— ${sanitize(msg, { maxLength: 512 })}\n`),
  });

  // A session-fatal condition must reach the EXIT CODE, not only the transcript.
  let exitCode = 0;
  core.onFatal(() => {
    exitCode = 1;
  });

  const session = new TerminalSession(core, {
    write,
    writeErr,
    color,
    showReasoning: options.showReasoning,
  });
  // Subcommands print one result; they must not also emit the live transcript, or their stdout
  // is unparseable (a stray "— subagents idle" landed in `conversations list` output).
  const detach =
    options.command !== "attach"
      ? (): void => {}
      : options.json
        ? attachJson(core, write, writeErr)
        : session.attach();

  try {
    await core.start();
  } catch (err) {
    // Pointer problems and version refusals both land here, and both are actionable.
    // Version-gate failures embed server-reported version and capability strings.
    process.stderr.write(
      `\nCould not attach: ${sanitize((err as Error).message, { maxLength: 512 })}\n`,
    );
    detach();
    core.stop();
    return 1;
  }

  // Non-interactive subcommands: connect, do one thing, print it, exit. These exist because the
  // core's conversation RPCs had no executable surface at all — the pointer error told operators
  // to seed a conversation via an RPC only reachable by writing TypeScript against an
  // unpublished package.
  if (options.command !== "attach") {
    const code = await runConversationsCommand(core, options, write, writeErr);
    detach();
    core.stop();
    return code;
  }

  // Read piped stdin only once we know we are attaching and were not given a message. Doing it
  // at startup blocked forever whenever stdin was a non-TTY that never closes — which is every
  // subcommand run from a supervisor, and is how `conversations list` hung.
  const oneShotMessage = options.message ?? (await readPipedMessage());
  const oneShot = oneShotMessage !== undefined;

  const runtime = core.getRuntime();
  if (oneShot) {
    const code = await runOneShot(core, session, oneShotMessage, options.timeoutSeconds);
    session.finish();
    detach();
    core.stop();
    return code === 0 ? exitCode : code;
  }

  // Pointer-derived, and the pointer decides which AGENT this attaches to — a swapped pointer
  // silently retargets the session, so show it and do not trust its contents.
  writeErr(
    `— attached to ${sanitize(runtime.agent_id, { maxLength: 120 })} · conversation ${sanitize(runtime.conversation_id, { maxLength: 120 })}
— type a message and press Enter; /exit to leave
`,
  );

  // Line-editing mode is a TTY question, not a colour question. Tying it to `color` meant that
  // NO_COLOR silently turned raw mode OFF, which is what lets pasted escape sequences reach the
  // echo path verbatim (render.renderLocalInput now sanitizes, but the coupling was still wrong).
  const rl = createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: Boolean(process.stdout.isTTY),
  });
  const done = new Promise<void>((resolve) => {
    rl.on("line", (line) => {
      const outcome = session.handleInput(line);
      if (outcome === "exit") rl.close();
      // A message the client could not deliver is a failure the caller must be able to see.
      if (outcome === "failed") exitCode = 1;
    });
    rl.on("close", () => resolve());
  });

  // Ctrl-C leaves the client only: the conversation and any running turn continue server-side.
  process.on("SIGINT", () => rl.close());

  await done;
  session.finish();
  detach();
  core.stop();
  writeErr("— detached (the conversation continues on the server)\n");
  return exitCode;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    const detail = err instanceof Error ? (err.stack ?? err.message) : String(err);
    process.stderr.write(`fatal: ${sanitize(detail, { maxLength: 4096 })}\n`);
    process.exit(1);
  },
);
