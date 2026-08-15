/**
 * spawnCli.ts — run the CLI as a REAL PROCESS and observe what a shell observes.
 *
 * WHY THIS EXISTS. Every other test in these packages drives `run()` in-process with array-backed
 * sinks. An array never closes, never fills, never reports a write error, and never ends the
 * process — so an entire class of defect is invisible to the suite BY CONSTRUCTION:
 *
 *   - a client that never terminates (`--json < /dev/null` hung forever; nothing in-process can
 *     tell "resolved with exit 0" from "never resolved");
 *   - an exit code destroyed by a closed stdout (`| head` reported 0 for a failing run, and the
 *     suite's own pipe test read `head`'s status, not the client's);
 *   - stdout and stderr interleaving, which only exists once they are two real file descriptors.
 *
 * Four of round 4's confirmed defects were found by a reviewer spawning the binary and none by the
 * 287 in-process tests. This module is that reviewer, made repeatable.
 *
 * THREE THINGS IT DOES THAT `spawn("sh", ["-c", …])` DOES NOT:
 *
 * 1. **Reports the CLI's own exit status, not the pipeline's.** In `cli | head`, the shell's status
 *    is `head`'s. The client's status lives in `${PIPESTATUS[0]}`, which requires bash (not `sh`)
 *    and is captured here into its own file. `set -o pipefail` is set as well, so `pipelineExitCode`
 *    is the strictest reading of the whole pipeline. Asserting on `code` from `child.on("close")`
 *    is what let B3 ship: the assertion was true of `head` and said nothing about the client.
 * 2. **Keeps stdout and stderr apart.** Each is redirected to its own file, so a test can assert
 *    "stdout carried nothing but NDJSON" — which is meaningless when the two are merged.
 * 3. **Bounds the run in time.** A hang is a FAILURE here, not a timeout of the test runner: the
 *    process group is killed and `timedOut` is set, so `expect(r.timedOut).toBe(false)` is a real
 *    assertion about termination rather than a test that mysteriously takes 90s.
 */

import { type ChildProcess, spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
/** The real bin entry from package.json — run the thing users run, not a copy of it. */
const CLI_ENTRY = join(PACKAGE_ROOT, "src", "main.ts");
const TSX = join(PACKAGE_ROOT, "node_modules", ".bin", "tsx");

/**
 * bash, NOT sh. `PIPESTATUS` is a bash array and the whole point of this harness is reading
 * element 0 of it; under `sh` it expands to nothing and every exit-code assertion silently
 * degrades to "the pipeline's last command succeeded".
 */
const SHELL = "/bin/bash";

/** Default ceiling on a run. Generous enough for tsx startup, short enough that a hang is quick. */
const DEFAULT_TIMEOUT_MS = 30_000;

/** Grace between SIGKILL of a timed-out group and giving up on collecting its output. */
const REAP_GRACE_MS = 500;

export interface CliRunResult {
  /**
   * The CLI's OWN exit status — `${PIPESTATUS[0]}`. This is the number a supervisor reads, and it
   * is NOT what `child.on("close")` reports when the command is piped.
   */
  cliExitCode: number;
  /** The whole pipeline's status under `set -o pipefail`. Equals `cliExitCode` when unpiped. */
  pipelineExitCode: number;
  stdout: string;
  stderr: string;
  /** Wall time from spawn to exit; the evidence behind "it exited promptly" claims. */
  durationMs: number;
  /** True when the run had to be killed. A hang is a failed assertion, not a slow test. */
  timedOut: boolean;
}

export interface CliRunOptions {
  /**
   * A shell redirect for stdin, verbatim. `"< /dev/null"` is the canonical headless invocation and
   * the one that hung; omit for a stdin that stays open (which is itself a termination test).
   */
  stdin?: string;
  /** A command to pipe stdout through, e.g. `"head -1"`. Sets up the PIPESTATUS[0] case. */
  pipeThrough?: string;
  timeoutMs?: number;
  env?: Record<string, string>;
  /** Allocate a real pty for the child (see `runCliOnPty`); stdout/stderr necessarily merge. */
  pty?: boolean;
}

/** Single-quote a token for the shell, the only quoting that needs no escape table. */
function shellQuote(token: string): string {
  return `'${token.replace(/'/g, `'\\''`)}'`;
}

/**
 * Kill the whole process group.
 *
 * The child is a bash that spawned tsx that spawned node. Killing the bash alone orphans the node
 * — which then keeps the port and the mock server's connection alive and hangs the NEXT test
 * instead, turning one hang into an unattributable cascade. `detached: true` at spawn gives the
 * group its own id so a negative pid reaches every descendant.
 */
function killGroup(child: ChildProcess): void {
  if (child.pid === undefined) return;
  try {
    process.kill(-child.pid, "SIGKILL");
  } catch {
    // Already gone between the timer firing and here: the ordinary race, not an error.
  }
}

/**
 * Run the CLI under bash and report what a shell would see.
 *
 * `args` are the CLI's own arguments; they are quoted here, so a test can pass control characters
 * and hostile argv without building a shell string by hand (which is how D1's payload gets in).
 */
export async function runCli(
  args: readonly string[],
  options: CliRunOptions = {},
): Promise<CliRunResult> {
  const dir = await mkdtemp(join(tmpdir(), "letta-cli-run-"));
  const outPath = join(dir, "stdout");
  const errPath = join(dir, "stderr");
  const codePath = join(dir, "cli-status");

  const cli = [TSX, CLI_ENTRY, ...args].map(shellQuote).join(" ");
  const tail = options.pipeThrough ? ` | ${options.pipeThrough}` : "";
  const stdin = options.stdin ? ` ${options.stdin}` : "";
  // The redirects bind to the CLI, not to the pipeline, so stderr stays out of the pipe and
  // `pipeThrough` sees exactly the bytes a real consumer would.
  //
  // `__ps=(…) __rc=$?` is ONE command on purpose. `PIPESTATUS` is rebuilt after every command,
  // including a plain assignment, so the obvious two-line form
  //     pipeline_status=$?
  //     echo "${PIPESTATUS[0]}"
  // reads the ASSIGNMENT's status array — measured: it reported 0 for a run that exited 2, which
  // is precisely the laundering this harness exists to detect, reproduced inside the detector.
  // Both right-hand sides expand before either assignment runs, so a single command sees the
  // pipeline's real status twice.
  const script = [
    "set -o pipefail",
    `${cli} 2>${shellQuote(errPath)}${stdin}${tail} >${shellQuote(outPath)}`,
    '__ps=("${PIPESTATUS[@]}") __rc=$?',
    `echo "\${__ps[0]}" >${shellQuote(codePath)}`,
    "exit $__rc",
  ].join("\n");

  const started = Date.now();
  const child = spawn(SHELL, ["-c", script], {
    cwd: PACKAGE_ROOT,
    // Its own process group, so a timeout can reap the whole tsx→node tree. See killGroup.
    detached: true,
    stdio: ["inherit", "ignore", "ignore"],
    env: { ...process.env, ...options.env },
  });

  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    killGroup(child);
  }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  const pipelineExitCode = await new Promise<number>((resolveExit) => {
    child.on("close", (code, signal) => resolveExit(code ?? (signal ? 128 : 1)));
  });
  clearTimeout(timer);
  if (timedOut) await new Promise((r) => setTimeout(r, REAP_GRACE_MS));

  const read = async (path: string): Promise<string> => {
    try {
      return await readFile(path, "utf-8");
    } catch {
      // A killed shell may never have created the file; absent output is empty output.
      return "";
    }
  };
  const [stdout, stderr, rawCode] = await Promise.all([read(outPath), read(errPath), read(codePath)]);
  await rm(dir, { recursive: true, force: true });

  const parsed = Number.parseInt(rawCode.trim(), 10);
  return {
    // A timed-out run never wrote its status line; report the pipeline's so the number is never
    // a stale or invented success.
    cliExitCode: Number.isNaN(parsed) ? pipelineExitCode : parsed,
    pipelineExitCode,
    stdout,
    stderr,
    durationMs: Date.now() - started,
    timedOut,
  };
}

/**
 * Run the CLI attached to a REAL pty.
 *
 * The client branches on `process.stdout.isTTY` for colour and on it again for readline's terminal
 * mode — and `main.ts` notes that tying line-editing to the colour setting is what let pasted
 * escape sequences reach the echo path verbatim. Neither branch is reachable from a pipe or a
 * file, so a pty is the only way to test the code path an operator actually runs.
 *
 * `script(1)` is the dependency-free way to get one. On a pty there is one device, so stdout and
 * stderr necessarily merge — that is a property of terminals, not a limitation here, and it is why
 * `stderr` comes back empty and everything lands in `stdout`.
 */
export async function runCliOnPty(
  args: readonly string[],
  options: Omit<CliRunOptions, "pipeThrough" | "pty"> = {},
): Promise<CliRunResult> {
  const dir = await mkdtemp(join(tmpdir(), "letta-cli-pty-"));
  const typescriptPath = join(dir, "typescript");
  const diagnosticPath = join(dir, "script-diagnostic");
  const cli = [TSX, CLI_ENTRY, ...args].map(shellQuote).join(" ");
  // BSD script (macOS): `script -q <file> <command…>`. GNU script: `script -qec <command> <file>`.
  const isBsd = process.platform === "darwin";
  const scriptCmd = isBsd
    ? `script -q ${shellQuote(typescriptPath)} ${cli}`
    : `script -qec ${shellQuote(cli)} ${shellQuote(typescriptPath)}`;
  // Redirecting `script`'s OWN stdin does not take the pty away from the child: the child's stdin
  // is the pty slave either way, so `isTTY` stays true and the terminal branches still run — this
  // only decides what gets typed at it. `/dev/null` means "nothing, then EOF", which is what a
  // one-shot wants. (`/dev/zero` would be a flood of NUL bytes into the terminal; measured.)
  const stdin = options.stdin ? ` ${options.stdin}` : " < /dev/null";

  const started = Date.now();
  // `script`'s OWN stderr is kept, not discarded. Discarding it turned a usage error into a bare
  // "exit 1 after 6ms" with nothing to diagnose — the failure mode this whole file exists to
  // prevent, committed by the file itself.
  const child = spawn(SHELL, ["-c", `${scriptCmd}${stdin} >/dev/null 2>${shellQuote(diagnosticPath)}`], {
    cwd: PACKAGE_ROOT,
    detached: true,
    stdio: ["inherit", "ignore", "ignore"],
    env: { ...process.env, ...options.env },
  });

  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    killGroup(child);
  }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  const exitCode = await new Promise<number>((resolveExit) => {
    child.on("close", (code, signal) => resolveExit(code ?? (signal ? 128 : 1)));
  });
  clearTimeout(timer);
  if (timedOut) await new Promise((r) => setTimeout(r, REAP_GRACE_MS));

  const readOrEmpty = async (path: string): Promise<string> => {
    try {
      return await readFile(path, "utf-8");
    } catch {
      return "";
    }
  };
  const [transcript, diagnostic] = await Promise.all([
    readOrEmpty(typescriptPath),
    readOrEmpty(diagnosticPath),
  ]);
  await rm(dir, { recursive: true, force: true });

  return {
    // BSD script exits with the child's status, so this IS the CLI's code — there is no pipeline.
    cliExitCode: exitCode,
    pipelineExitCode: exitCode,
    stdout: transcript,
    // Whatever `script` itself said. Empty on every healthy run; the only clue when the pty could
    // not be allocated at all, which otherwise presents as an instant, unexplained exit 1.
    stderr: diagnostic,
    durationMs: Date.now() - started,
    timedOut,
  };
}
