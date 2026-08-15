/**
 * The program itself, driven end-to-end against a mock App Server.
 *
 * `main.ts` had ZERO tests and held three S1 defects, because everything in it reached for a
 * global: `process.argv`, `process.stdout`, its own readline, and `process.exit`. Nothing about a
 * one-shot's termination, its timeout, its exit code, or the shape of its `--json` stream could be
 * asserted, so all four were verified by hand once and then trusted.
 *
 * These use a REAL ContinuityCore over a REAL socket. The one thing stubbed is the write fault,
 * which no server-side action can produce on cue.
 */

import { spawn } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ContinuityCoreConfig } from "@ai-pa/letta-continuity-core";
import { ContinuityCore } from "@ai-pa/letta-continuity-core";
import { FaultyWsConnection, MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { afterEach, describe, expect, it } from "vitest";
import { type InputOutcome, type TerminalIO, run } from "../src/main.js";

const AGENT = "agent-local-3898b33a";
const CONV = "local-conv-continuity-uuid";

interface Harness {
  io: TerminalIO;
  out: string[];
  err: string[];
  configs: ContinuityCoreConfig[];
}

function harness(over: Partial<TerminalIO> = {}): Harness {
  const out: string[] = [];
  const err: string[] = [];
  const configs: ContinuityCoreConfig[] = [];
  const io: TerminalIO = {
    stdout: (t) => out.push(t),
    stderr: (t) => err.push(t),
    isStdoutTTY: false,
    readPipedMessage: async () => undefined,
    interactive: async () => {},
    createCore: (config) => {
      configs.push(config);
      return new ContinuityCore({
        openTimeoutMs: 2000,
        helloTimeoutMs: 2000,
        rpcTimeoutMs: 2000,
        reconnectDelayMs: 20,
        ...config,
      });
    },
    ...over,
  };
  return { io, out, err, configs };
}

function target(url: string): string[] {
  return ["--agent", AGENT, "--conversation", CONV, "--url", url];
}

describe("run()", () => {
  let server: MockAppServer;

  afterEach(async () => {
    FaultyWsConnection.reset();
    await server?.stop();
  });

  describe("one-shot", () => {
    it("terminates on a TOOL-USING reply, whose run is never closed", async () => {
      // The captured shape: our send starts local-run-320, a tool suspends it, a NEW run carries
      // the answer, and 320 never emits turn_finished at all. A wait keyed on "our run finished"
      // hangs here — on most real replies, since most of them use a tool.
      server = new MockAppServer({ toolUse: true });
      const url = await server.start();
      const h = harness();

      const code = await run([...target(url), "--message", "use a tool"], {}, h.io);

      expect(code).toBe(0);
      expect(h.out.join("")).toContain("OK");
    }, 20_000);

    it("gives up with exit 1 when no reply arrives inside the timeout", async () => {
      server = new MockAppServer({ autoTurnOnInput: false });
      const url = await server.start();
      const h = harness();

      const code = await run([...target(url), "--message", "hello", "--timeout", "0.3"], {}, h.io);

      expect(code).toBe(1);
      expect(h.err.join("")).toContain("timed out after 0.3s");
    }, 20_000);

    it("exits 1 when the session dies under it", async () => {
      // A supervisor cannot tell a clean detach from a dead session unless this is true; the exit
      // code used to be 0 even after the reconnect budget was exhausted.
      server = new MockAppServer({ autoTurnOnInput: false });
      const url = await server.start();
      const h = harness();

      const pending = run([...target(url), "--message", "hello", "--timeout", "20"], {}, h.io);
      await new Promise((r) => setTimeout(r, 150));
      await server.stop();

      expect(await pending).toBe(1);
    }, 20_000);

    it("exits 1 when the message could not be delivered at all", async () => {
      server = new MockAppServer({ autoTurnOnInput: false });
      const url = await server.start();
      const h = harness({
        createCore: (config) =>
          new ContinuityCore({
            openTimeoutMs: 2000,
            helloTimeoutMs: 2000,
            ...config,
            createConnection: FaultyWsConnection.factory,
          }),
      });
      FaultyWsConnection.failSendsWith = "cannot send `input`: socket not open";

      const code = await run([...target(url), "--message", "hello", "--timeout", "5"], {}, h.io);

      expect(code).toBe(1);
      expect(h.err.join("")).toContain("was not delivered");
    }, 20_000);

    it("still terminates when a reconnect lands in the middle of the turn", async () => {
      // A reconnect demotes attribution to `unknown` BY DESIGN — across the gap an unknown number
      // of runs may have begun and ended. A wait that insists on a run it can still prove is ours
      // therefore never ends: observed rendering the whole reply and then exiting 1 on the
      // timeout, blaming a server that had answered.
      server = new MockAppServer({ autoTurnOnInput: false });
      const url = await server.start();
      const h = harness();

      const pending = run([...target(url), "--message", "hello", "--timeout", "10"], {}, h.io);
      await new Promise((r) => setTimeout(r, 200));
      server.dropAllConnections();
      await new Promise((r) => setTimeout(r, 400));
      // The reply arrives on the NEW connection, on a run no claim of ours can bind.
      server.injectForeignTurn({ agent_id: AGENT, conversation_id: CONV }, "local-run-after-gap", [
        { id: "letta-msg-1", messageType: "assistant_message", text: "answered anyway" },
      ]);

      expect(await pending).toBe(0);
      expect(h.out.join("")).toContain("answered anyway");
    }, 30_000);
  });

  describe("--json", () => {
    it("puts NOTHING but parseable NDJSON on stdout", async () => {
      // The local echo (`you › …`) shared the stream, so exactly one line of every one-shot failed
      // to parse — and it was the first, which is where a consumer looks.
      server = new MockAppServer({ toolUse: true });
      const url = await server.start();
      const h = harness();

      const code = await run([...target(url), "--json", "--message", "hi"], {}, h.io);

      expect(code).toBe(0);
      const lines = h.out.join("").split("\n").filter(Boolean);
      expect(lines.length).toBeGreaterThan(3);
      for (const line of lines) expect(() => JSON.parse(line)).not.toThrow();
    }, 20_000);

    it("reports the loop status a machine consumer needs to see the turn end", async () => {
      server = new MockAppServer();
      const url = await server.start();
      const h = harness();

      await run([...target(url), "--json", "--message", "hi"], {}, h.io);

      const events = h.out
        .join("")
        .split("\n")
        .filter(Boolean)
        .map((l) => JSON.parse(l) as { kind: string; status?: string });
      expect(events.some((e) => e.kind === "loop_status" && e.status === "WAITING_ON_INPUT")).toBe(
        true,
      );
    }, 20_000);

    it("escapes C1 and DEL so the stream cannot drive the terminal it is piped into", async () => {
      // JSON.stringify escapes C0 and stops there. U+009B is an 8-bit CSI: raw, it is a live
      // escape sequence on the one output path that deliberately skips sanitization.
      server = new MockAppServer({ autoTurnOnInput: false });
      const url = await server.start();
      const h = harness();

      const pending = run(
        [...target(url), "--json", "--message", "hi", "--timeout", "5"],
        {},
        h.io,
      );
      await new Promise((r) => setTimeout(r, 200));
      server.injectForeignTurn({ agent_id: AGENT, conversation_id: CONV }, "run-hostile", [
        {
          id: "letta-msg-1",
          messageType: "assistant_message",
          text: "before\u009b2Kafter\u007fdel",
        },
      ]);
      await pending;

      const raw = h.out.join("");
      expect(raw).not.toContain("\u009b");
      expect(raw).not.toContain("\u007f");
      // The consumer still receives the real characters — escaped, not stripped.
      const texts = raw
        .split("\n")
        .filter(Boolean)
        .map((l) => JSON.parse(l) as { text?: string })
        .map((e) => e.text ?? "")
        .join("");
      expect(texts).toContain("\u009b2K");
    }, 20_000);
  });

  describe("conversations", () => {
    it("create --write-pointer writes the pointer and preserves what it replaced", async () => {
      // This is how the cutover seeds the pointer every surface reads, so overwriting silently
      // retargets every attached client — and the file replaced may be the only record of the
      // conversation now orphaned.
      server = new MockAppServer();
      const url = await server.start();
      const dir = await mkdtemp(join(tmpdir(), "letta-terminal-"));
      const path = join(dir, "pointer.json");
      await writeFile(
        path,
        JSON.stringify({ agent_id: "agent-old", conversation_id: "conv-old" }),
        "utf-8",
      );
      const h = harness();

      const code = await run(
        ["conversations", "create", ...target(url), "--title", "seed", "--write-pointer", path],
        {},
        h.io,
      );

      expect(code).toBe(0);
      const written = JSON.parse(await readFile(path, "utf-8")) as { conversation_id: string };
      expect(written.conversation_id).toMatch(/^local-conv-new-/);
      const backup = JSON.parse(await readFile(`${path}.bak`, "utf-8")) as {
        conversation_id: string;
      };
      expect(backup.conversation_id).toBe("conv-old");
    }, 20_000);

    it("list prints one line per conversation and no transcript chatter", async () => {
      server = new MockAppServer({
        conversations: [
          {
            id: "c-1",
            agent_id: AGENT,
            archived: false,
            archived_at: null,
            created_at: "x",
            updated_at: "y",
          },
        ],
      });
      const url = await server.start();
      const h = harness();

      const code = await run(["conversations", "list", ...target(url)], {}, h.io);

      expect(code).toBe(0);
      expect(h.out.join("")).toBe("c-1\tactive\ty\n");
    }, 20_000);
  });

  describe("as a real process, through a real pipe", () => {
    // These spawn the CLI so its output crosses an actual pipe. Everything else here captures
    // into arrays, and an array never closes, never fills, and never reports a write error — so
    // the two defects below were invisible to the whole suite by construction. Both were found by
    // running the thing.
    function spawnPipeline(shellCommand: string): Promise<{
      code: number | null;
      stdout: string;
      stderr: string;
    }> {
      return new Promise((resolve) => {
        const child = spawn("sh", ["-c", shellCommand], { cwd: process.cwd() });
        let stdout = "";
        let stderr = "";
        child.stdout.on("data", (d) => {
          stdout += d.toString();
        });
        child.stderr.on("data", (d) => {
          stderr += d.toString();
        });
        child.on("close", (code) => resolve({ code, stdout, stderr }));
      });
    }

    it("survives its consumer closing the pipe, instead of dying on an unhandled EPIPE", async () => {
      server = new MockAppServer();
      const url = await server.start();
      const cli = `npx tsx src/main.ts --agent ${AGENT} --conversation ${CONV} --url ${url} --json --message hi --timeout 20`;

      const { code, stderr } = await spawnPipeline(`${cli} | head -1`);

      expect(stderr).not.toContain("EPIPE");
      expect(stderr).not.toContain("Unhandled");
      expect(code).toBe(0);
    }, 60_000);

    it("delivers ALL of a large stdout to a pipe rather than truncating at exit", async () => {
      // `process.exit()` discards whatever is still buffered for a pipe — measured at 122 of
      // 20,000 lines, and at exit 0, so a consumer could not tell a truncated stream from a
      // complete one. The entry point sets `process.exitCode` instead and lets Node flush.
      // The `input` ack is suppressed, so our claim never arms and none of the injected turns is
      // mistaken for the reply — the client keeps streaming until its own timeout, which is what
      // gives it a large stdout to lose.
      server = new MockAppServer({ autoTurnOnInput: false, suppressResponsesFor: ["input"] });
      const url = await server.start();
      const cli = `npx tsx src/main.ts --agent ${AGENT} --conversation ${CONV} --url ${url} --json --message hi --timeout 4`;
      // The reader is deliberately SLOW to start. A consumer that drains as fast as the client
      // writes never leaves anything buffered at exit, so the test would pass against a truncating
      // exit — which is exactly what it did until this sleep was added. Here the 64KB pipe buffer
      // fills, the rest queues inside Node, and the client reaches its exit with data still owed.
      const pending = spawnPipeline(`${cli} | (sleep 6; cat)`);

      // Enough frames that the total comfortably exceeds a pipe buffer.
      await new Promise((r) => setTimeout(r, 1500));
      for (let i = 0; i < 400; i += 1) {
        server.injectForeignTurn({ agent_id: AGENT, conversation_id: CONV }, `run-${i}`, [
          { id: `letta-msg-${i}`, messageType: "assistant_message", text: "x".repeat(400) },
        ]);
      }

      const { stdout } = await pending;
      const lines = stdout.split("\n").filter(Boolean);
      const deltas = lines
        .map((l) => JSON.parse(l) as { kind: string; runId?: string })
        .filter((e) => e.kind === "delta");
      // Every injected turn is represented: nothing was lost to a truncated flush.
      expect(new Set(deltas.map((d) => d.runId)).size).toBe(400);
      expect(stdout.length).toBeGreaterThan(64 * 1024);
    }, 90_000);
  });

  describe("argument plumbing", () => {
    it("--allow-remote reaches the CORE, which is what applies the rule", async () => {
      // The flag passed the argument parser and was then refused by the layer it was meant to
      // unlock, because the option was never forwarded. It simply did not work.
      server = new MockAppServer();
      const url = await server.start();
      const h = harness();
      await run([...target(url), "--message", "hi", "--allow-remote", "--timeout", "5"], {}, h.io);
      expect(h.configs[0]?.allowRemote).toBe(true);

      const plain = harness();
      await run([...target(url), "--message", "hi", "--timeout", "5"], {}, plain.io);
      expect(plain.configs[0]?.allowRemote).toBe(false);
    }, 20_000);

    it("a bad argument exits 2 without opening a socket", async () => {
      server = new MockAppServer();
      const url = await server.start();
      const h = harness();
      const code = await run([...target(url), "--nonsense"], {}, h.io);
      expect(code).toBe(2);
      expect(server.connectionCount).toBe(0);
    });
  });

  describe("interactive", () => {
    it("sends what the user types and leaves on /exit", async () => {
      server = new MockAppServer();
      const url = await server.start();
      const lines = ["hello there", "/exit"];
      const outcomes: InputOutcome[] = [];
      const h = harness({
        interactive: async (onLine) => {
          for (const line of lines) {
            const outcome = onLine(line);
            outcomes.push(outcome);
            if (outcome === "exit") return;
            await new Promise((r) => setTimeout(r, 100));
          }
        },
      });

      const code = await run(target(url), {}, h.io);

      expect(code).toBe(0);
      expect(outcomes).toEqual(["sent", "exit"]);
      expect(h.out.join("")).toContain("you › hello there");
      expect(
        server.received.some(
          (m) => m.type === "input" && JSON.stringify(m).includes("hello there"),
        ),
      ).toBe(true);
    }, 20_000);

    it("exits 1 if any typed line was never delivered", async () => {
      server = new MockAppServer();
      const url = await server.start();
      const h = harness({
        createCore: (config) =>
          new ContinuityCore({
            openTimeoutMs: 2000,
            helloTimeoutMs: 2000,
            ...config,
            createConnection: FaultyWsConnection.factory,
          }),
        interactive: async (onLine) => {
          FaultyWsConnection.failSendsWith = "cannot send `input`: socket not open";
          onLine("this one is lost");
          onLine("/exit");
        },
      });

      const code = await run(target(url), {}, h.io);
      expect(code).toBe(1);
    }, 20_000);
  });
});
