/**
 * The C6 transport swap, end to end: `run()` over the CONTROLLER surface protocol against a
 * REAL worker + mock App Server stack. The terminal UX contract (stream split, sanitizer on
 * every controller-derived string, exit codes, NDJSON) must hold through the swap — and the
 * headline inversion must too: detaching mid-turn no longer kills the turn, and a re-attach
 * replays it.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Registry } from "@ai-pa/continuity-controller/registry";
import { openStateDb } from "@ai-pa/continuity-controller/state/db";
import { Journal } from "@ai-pa/continuity-controller/state/journal";
import { WorkerDaemon } from "@ai-pa/continuity-controller/worker";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { afterEach, describe, expect, it } from "vitest";
import { type InputOutcome, type TerminalIO, run } from "../src/main.js";

const AGENT = "ag-1";
const CONV = "local-conv-1";
const RUNTIME = { agent_id: AGENT, conversation_id: CONV };
const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };

interface Stack {
  server: MockAppServer;
  worker: WorkerDaemon;
  dir: string;
  argvTarget: string[];
}

interface Harness {
  io: TerminalIO;
  out: string[];
  err: string[];
}

function harness(over: Partial<TerminalIO> = {}): Harness {
  const out: string[] = [];
  const err: string[] = [];
  const io: TerminalIO = {
    stdout: (t) => out.push(t),
    stderr: (t) => err.push(t),
    isStdoutTTY: false,
    readPipedMessage: async () => undefined,
    interactive: async () => {},
    ...over,
  };
  return { io, out, err };
}

describe("run() over the controller transport", () => {
  let stack: Stack | null = null;

  afterEach(async () => {
    stack?.worker.stop();
    await stack?.server.stop();
    stack = null;
  });

  async function startStack(
    serverOptions: ConstructorParameters<typeof MockAppServer>[0] = {},
    workerOverrides: Record<string, unknown> = {},
  ): Promise<Stack> {
    const server = new MockAppServer(serverOptions);
    const url = await server.start();
    const dir = mkdtempSync(join(tmpdir(), "terminal-controller-"));
    const { db } = openStateDb(dir);
    new Registry(db).upsert(RUNTIME);
    const worker = new WorkerDaemon({
      url,
      db,
      registry: new Registry(db),
      journal: new Journal(db),
      livenessFile: join(dir, "liveness.json"),
      livenessIntervalMs: 60_000,
      livenessDeadlineMs: 2_000,
      hotsetPollMs: 50,
      queuePollMs: 40,
      turnTimeoutMs: 60_000,
      abortConfirmMs: 1_000,
      degraded: null,
      surfacePort: 0,
      stateDir: dir,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
      ...workerOverrides,
    });
    await worker.start();
    const port = worker.surfaceBoundPort;
    if (port === null) throw new Error("no surface port");
    stack = {
      server,
      worker,
      dir,
      argvTarget: [
        "--agent",
        AGENT,
        "--conversation",
        CONV,
        "--controller-url",
        `ws://127.0.0.1:${port}/surface`,
        "--token-file",
        join(dir, "surface-token"),
      ],
    };
    return stack;
  }

  it("one-shot completes through the controller: reply rendered, exit 0", async () => {
    const s = await startStack();
    const h = harness();
    const code = await run([...s.argvTarget, "--message", "hello"], {}, h.io);
    expect(code).toBe(0);
    // The mock's canned reply ("OK…") reached stdout through journal → surface → renderer.
    expect(h.out.join("")).toContain("OK");
    // The stream split held: connection chatter went to stderr, never stdout.
    expect(h.err.join("")).toContain("connected");
    expect(h.out.join("")).not.toContain("connected");
  });

  it("one-shot --json emits NOTHING but parseable NDJSON on stdout", async () => {
    const s = await startStack();
    const h = harness();
    const code = await run([...s.argvTarget, "--json", "--message", "hello"], {}, h.io);
    expect(code).toBe(0);
    const lines = h.out.join("").trim().split("\n");
    expect(lines.length).toBeGreaterThan(0);
    for (const line of lines) expect(() => JSON.parse(line)).not.toThrow();
    const kinds = lines.map((l) => (JSON.parse(l) as { kind: string }).kind);
    expect(kinds).toContain("turn_finished");
  });

  it("a FAILED-VISIBLE turn renders as failure and exits nonzero", async () => {
    const s = await startStack({ autoTurnOnInput: false }, { turnTimeoutMs: 300 });
    const h = harness();
    const code = await run(
      [...s.argvTarget, "--message", "will wedge", "--timeout", "20"],
      {},
      h.io,
    );
    expect(code).toBe(1);
    expect(h.err.join("")).toContain("FAILED-VISIBLE");
  });

  it("SANITIZES controller-derived strings: an escape-bearing failure reason cannot reach the TTY raw", async () => {
    const s = await startStack();
    const h = harness();
    // Inject a hostile journal row directly — the worst case: controller data (which C8's
    // Kinara-authored labels also are) carrying a live escape sequence.
    const hostile = "]0;pwned[2Jboom";
    const code = await run(
      [...s.argvTarget, "--message", "hello"],
      {},
      harness({
        interactive: async () => {},
      }).io,
    );
    void code;
    // Now render a failed-visible with the hostile reason through a fresh attach.
    s.worker.pipeline.accept(RUNTIME, "second turn"); // ensure journal continuity
    const journalDb = s.worker;
    void journalDb;
    // Direct path: emit a turn_failed_visible row and re-run a one-shot that replays it.
    const { db } = openStateDb(s.dir);
    db.prepare(
      `INSERT INTO turn_events (agent_id, conversation_id, client_message_id, kind, payload, at)
       VALUES (?, ?, 'cm-hostile', 'turn_failed_visible', ?, ?)`,
    ).run(AGENT, CONV, JSON.stringify({ reason: hostile }), new Date().toISOString());

    const code2 = await run([...s.argvTarget, "--message", "trigger replay"], {}, h.io);
    void code2;
    const everything = h.out.join("") + h.err.join("");
    expect(everything).not.toContain("");
    expect(everything).not.toContain("");
  });

  it("detach mid-turn: the turn COMPLETES without the terminal, and a re-attach replays it", async () => {
    const s = await startStack({ autoTurnOnInput: false });
    // Interactive session: type one line, see it ACCEPTED by the controller, then leave with
    // the turn still in flight — the q5 shape, inverted.
    const h1 = harness({
      interactive: async (onLine: (line: string) => InputOutcome) => {
        onLine("long running turn");
        await new Promise<void>((resolve, reject) => {
          const deadline = setTimeout(() => reject(new Error("send never accepted")), 4000);
          const timer = setInterval(() => {
            if (s.worker.pipeline.rows(["queued", "submitting", "submitted"]).length === 1) {
              clearInterval(timer);
              clearTimeout(deadline);
              resolve();
            }
          }, 25);
        });
      },
    });
    const code1 = await run(s.argvTarget, {}, h1.io);
    expect(code1).toBe(0);
    expect(h1.err.join("")).toContain("the controller keeps the turn running");
    // The turn is genuinely IN FLIGHT after the terminal left — not completed, not lost.
    expect(s.worker.pipeline.rows(["queued", "submitting", "submitted"])).toHaveLength(1);

    // With NO terminal attached, the server completes the turn; the controller journals it.
    s.server.broadcastTurn(RUNTIME, "run-after-detach", [
      { id: "m-detach-1", messageType: "assistant_message", text: "finished after you left" },
    ]);
    await new Promise<void>((resolve, reject) => {
      const deadline = setTimeout(() => reject(new Error("turn never completed")), 5000);
      const timer = setInterval(() => {
        if (s.worker.pipeline.rows(["queued", "submitting", "submitted"]).length === 0) {
          clearInterval(timer);
          clearTimeout(deadline);
          resolve();
        }
      }, 50);
    });

    // Re-attach: the turn that completed in absence is PRESENT via replay. (The probe message
    // itself needs a live reply, so the mock resumes auto-turning.)
    s.server.options.autoTurnOnInput = true;
    const h2 = harness();
    const code2 = await run([...s.argvTarget, "--message", "and now?"], {}, h2.io);
    expect(code2).toBe(0);
    expect(h2.out.join("")).toContain("finished after you left");
  }, 20_000);

  it("one-shot settles ONLY on its own receipt's outcome — a replayed outcome cannot end it", async () => {
    const s = await startStack();
    // A completed prior turn sits in the journal…
    const h0 = harness();
    await run([...s.argvTarget, "--message", "first"], {}, h0.io);
    // …and the NEXT one-shot replays it at attach. The replayed outcome must not settle the
    // wait: with the server wedged, the only honest exit is the timeout.
    s.server.options.autoTurnOnInput = false;
    const h = harness();
    const code = await run([...s.argvTarget, "--message", "second", "--timeout", "1"], {}, h.io);
    expect(code).toBe(1);
    expect(h.err.join("")).toContain("timed out");
  }, 20_000);

  it("/deny answers a pending approval with DENY (the decision is the operator's, verbatim)", async () => {
    const s = await startStack({ approvalMode: true });
    const h = harness({
      interactive: async (onLine: (line: string) => InputOutcome) => {
        onLine("do something gated");
        await new Promise<void>((resolve, reject) => {
          const deadline = setTimeout(() => reject(new Error("no approval notice")), 5000);
          const timer = setInterval(() => {
            if (h.err.join("").includes("approval requested")) {
              clearInterval(timer);
              clearTimeout(deadline);
              resolve();
            }
          }, 25);
        });
        onLine("/deny");
        await new Promise((r) => setTimeout(r, 200));
      },
    });
    await run(s.argvTarget, {}, h.io);
    const answers = s.server.received.filter(
      (f) => f.type === "input" && (f.payload as { kind?: string })?.kind === "approval_response",
    );
    expect(answers).toHaveLength(1);
    expect(
      (answers[0]?.payload as { decision?: { behavior?: string } })?.decision?.behavior ?? "",
    ).toBe("deny");
  }, 20_000);

  it("conversations subcommands refuse on the controller transport and point at --direct", async () => {
    const s = await startStack();
    const h = harness();
    const code = await run(["conversations", "list", ...s.argvTarget], {}, h.io);
    expect(code).toBe(2);
    expect(h.err.join("")).toContain("--direct");
  });
});
