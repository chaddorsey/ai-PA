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
import { ContinuityCore } from "@ai-pa/letta-continuity-core";
import { CliError, USAGE, parseArgs } from "./cli.js";
import { sanitize } from "./sanitize.js";
import { TerminalSession } from "./session.js";

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

  const core = new ContinuityCore({
    pointerPath: options.pointerPath,
    ...(options.url ? { url: options.url } : {}),
    versionPolicy: options.strictVersion ? "refuse" : "warn",
    // onWarn payloads embed server strings (snapshot errors, reported versions, capability
    // names). They bypass the Renderer, so they are sanitized here rather than trusted.
    onWarn: (msg) => process.stderr.write(`— ${sanitize(msg, { maxLength: 512 })}\n`),
  });

  const session = new TerminalSession(core, {
    write,
    color,
    showReasoning: options.showReasoning,
  });
  const detach = session.attach();

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

  const runtime = core.getRuntime();
  // Pointer-derived, and the pointer decides which AGENT this attaches to — a swapped pointer
  // silently retargets the session, so show it and do not trust its contents.
  write(
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
      if (session.handleInput(line) === "exit") rl.close();
    });
    rl.on("close", () => resolve());
  });

  // Ctrl-C leaves the client only: the conversation and any running turn continue server-side.
  process.on("SIGINT", () => rl.close());

  await done;
  session.finish();
  detach();
  core.stop();
  write("— detached (the conversation continues on the server)\n");
  return 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    const detail = err instanceof Error ? (err.stack ?? err.message) : String(err);
    process.stderr.write(`fatal: ${sanitize(detail, { maxLength: 4096 })}\n`);
    process.exit(1);
  },
);
