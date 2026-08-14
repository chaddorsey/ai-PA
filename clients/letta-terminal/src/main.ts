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
    onWarn: (msg) => process.stderr.write(`— ${msg}\n`),
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
    process.stderr.write(`\nCould not attach: ${(err as Error).message}\n`);
    detach();
    core.stop();
    return 1;
  }

  const runtime = core.getRuntime();
  write(
    `— attached to ${runtime.agent_id} · conversation ${runtime.conversation_id}
— type a message and press Enter; /exit to leave
`,
  );

  const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: color });
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
    process.stderr.write(`fatal: ${err instanceof Error ? err.stack : String(err)}\n`);
    process.exit(1);
  },
);
