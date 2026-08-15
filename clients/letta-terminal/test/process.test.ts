/**
 * The CLI as a real process.
 *
 * Everything in `main.test.ts` drives `run()` with array sinks. This file drives the BINARY, and
 * exists because four of round 4's confirmed defects were invisible to 287 in-process tests and
 * were all found by someone typing the command. The properties asserted here — "it exits", "the
 * exit code survives a closed pipe", "stdout carried only NDJSON" — are not expressible against an
 * array, which never closes, never fills and never ends a process.
 *
 * These are slow (a real tsx startup each). That is the price of testing the thing that ships.
 */

import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { afterEach, describe, expect, it } from "vitest";
import { runCli, runCliOnPty } from "./helpers/spawnCli.js";

const AGENT = "agent-local-3898b33a";
const CONV = "local-conv-continuity-uuid";

/** Bounded generously: a tsx cold start is ~1.5s and CI is slower than a laptop. */
const RUN_TIMEOUT_MS = 25_000;
const TEST_TIMEOUT_MS = 60_000;

function target(url: string): string[] {
  return ["--agent", AGENT, "--conversation", CONV, "--url", url];
}

describe("the CLI as a real process", () => {
  let server: MockAppServer | undefined;

  afterEach(async () => {
    await server?.stop();
    server = undefined;
  });

  describe("the harness itself", () => {
    // If these do not hold, every assertion below is decoration. The harness is load-bearing, so
    // it is tested like anything else that is.
    it("reports a clean exit, keeps stdout and stderr apart, and returns promptly", async () => {
      const r = await runCli(["--help"], { timeoutMs: RUN_TIMEOUT_MS });

      expect(r.timedOut).toBe(false);
      expect(r.cliExitCode).toBe(0);
      expect(r.stdout).toContain("letta-continuity");
      // The usage text is stdout's alone. A merged capture could not tell the difference.
      expect(r.stderr).toBe("");
    }, TEST_TIMEOUT_MS);

    it("reports the CLI's own status, not the last pipeline stage's", async () => {
      // The distinction B3 turns on. `false | head -1` exits 0 as a pipeline under most shells;
      // PIPESTATUS[0] still reports the failure, and `pipefail` makes the pipeline agree.
      const r = await runCli(["--nonsense"], { pipeThrough: "head -1", timeoutMs: RUN_TIMEOUT_MS });

      expect(r.timedOut).toBe(false);
      // A bad argument is exit 2, and piping it to `head` must not launder that into 0.
      expect(r.cliExitCode).toBe(2);
      expect(r.pipelineExitCode).toBe(2);
    }, TEST_TIMEOUT_MS);

    it("treats a process that will not exit as a FAILURE, with the evidence attached", async () => {
      // Proves the hang detector detects hangs. Without this, `timedOut === false` in the tests
      // below would be a claim about a mechanism nobody had checked.
      const r = await runCli(["--help"], {
        timeoutMs: 1200,
        // `--help` returns immediately, so make the SHELL hang instead: same observable.
        pipeThrough: "cat - >/dev/null; sleep 30",
      });

      expect(r.timedOut).toBe(true);
    }, TEST_TIMEOUT_MS);
  });

  describe("headless attach", () => {
    it("exits instead of hanging when stdin is /dev/null", async () => {
      // B2. `letta-continuity --json < /dev/null` is THE canonical headless invocation, and it
      // attached, streamed, and hung forever: `readPipedMessage` drains stdin to EOF and then
      // `interactive` builds a readline over an already-ended stream, which resolves never.
      // An in-process test cannot see this — `run()`'s promise simply never settles, which is
      // indistinguishable from a slow test.
      server = new MockAppServer();
      const url = await server.start();

      const r = await runCli([...target(url), "--json"], {
        stdin: "< /dev/null",
        timeoutMs: RUN_TIMEOUT_MS,
      });

      expect(r.timedOut).toBe(false);
      expect(r.cliExitCode).toBe(0);
    }, TEST_TIMEOUT_MS);
  });

  describe("a closed stdout", () => {
    it("does not launder a failing run into exit 0", async () => {
      // B3. `guardedWriter`'s onGone called `process.exit(0)` unconditionally, so a session that
      // had already failed reported success the moment its consumer went away — on all three
      // channels at once (exit code, stdout, and the stderr notice that never got written).
      // Measured live: CODE=1 unpiped vs CODE=0 piped, same run.
      //
      // THE TIMING IS THE TEST. `onGone` has to fire AFTER the run has earned its nonzero code,
      // because that is the only window in which there is a code to destroy — a naive
      // `failing-run | head -1` passes against the UNFIXED client, since `head` closes long
      // before the timeout and there is nothing yet to launder. So:
      //
      //   t=0   the client attaches and starts streaming injected turns (never its own reply:
      //         the `input` ack is suppressed, so its claim never arms and it waits)
      //   t=3   the one-shot times out → exit code 1 earned, stdout still owed (the reader has
      //         not read a byte, so the 64KB pipe buffer is full and Node is holding the rest)
      //   t=4   `head -1` finally reads one line and exits → the pipe closes under a client that
      //         is mid-flush → EPIPE → onGone
      //   t=5   the entry point's unref'd bail timer would fire; the assertion lands before it,
      //         so a pass cannot be the bail timer's doing
      server = new MockAppServer({ autoTurnOnInput: false, suppressResponsesFor: ["input"] });
      const url = await server.start();

      const pending = runCli([...target(url), "--json", "--message", "hi", "--timeout", "3"], {
        // A reader that does not read. See the timeline above.
        pipeThrough: "(sleep 4; head -1)",
        timeoutMs: RUN_TIMEOUT_MS,
      });

      // Fill the pipe once the client is actually attached, so there is something in flight to
      // lose. Polling beats a fixed sleep: a cold tsx start is not a constant.
      const deadline = Date.now() + 15_000;
      while (server.connectionCount === 0 && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 50));
      }
      expect(server.connectionCount).toBeGreaterThan(0);
      for (let i = 0; i < 400; i += 1) {
        server.injectForeignTurn({ agent_id: AGENT, conversation_id: CONV }, `run-${i}`, [
          { id: `letta-msg-${i}`, messageType: "assistant_message", text: "x".repeat(400) },
        ]);
      }

      const r = await pending;

      expect(r.timedOut).toBe(false);
      expect(r.cliExitCode).not.toBe(0);
    }, TEST_TIMEOUT_MS);

    it("still leaves quietly when the consumer goes away on a SUCCEEDING run", async () => {
      // The other half of the same rule: a downstream `head` closing is the consumer saying
      // "enough", not a failure, so a healthy run must not be turned into one.
      server = new MockAppServer();
      const url = await server.start();

      const r = await runCli([...target(url), "--json", "--message", "hi", "--timeout", "20"], {
        pipeThrough: "head -1",
        timeoutMs: RUN_TIMEOUT_MS,
      });

      expect(r.timedOut).toBe(false);
      expect(r.cliExitCode).toBe(0);
      expect(r.stderr).not.toContain("EPIPE");
      expect(r.stderr).not.toContain("Unhandled");
    }, TEST_TIMEOUT_MS);
  });

  describe("on a pty", () => {
    it("runs a one-shot to completion on a real terminal", async () => {
      // The `isStdoutTTY` branches — colour, and readline's terminal mode — are unreachable from a
      // pipe or a file, so no other test in either package executes them. `main.ts` records that
      // tying line-editing to the colour setting is what let pasted escapes reach the echo path
      // verbatim; that path only exists on a terminal.
      server = new MockAppServer();
      const url = await server.start();

      const r = await runCliOnPty([...target(url), "--message", "hi", "--timeout", "20"], {
        timeoutMs: RUN_TIMEOUT_MS,
      });

      expect(r.timedOut).toBe(false);
      expect(r.cliExitCode).toBe(0);
      expect(r.stdout).toContain("OK");
      // Colour is ON here and off everywhere else, which is the proof this really was a terminal.
      expect(r.stdout).toContain("\x1b[");
    }, TEST_TIMEOUT_MS);
  });
});
