// pa-tools — Letta Code extension exposing PA analytics tools that run in a
// PINNED Python venv (deterministic interpreter + env), sidestepping LET-9147.
//
// Pilot: collect_analytics_snapshot_ext. Pattern templates the broader
// server-tool migration. See
// docs/superpowers/specs/2026-06-07-pulse-analytics-extension-pilot-design.md
//
// Recovery if this breaks startup: `letta --no-extensions`.

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFileSync } from "node:fs";

const execFileAsync = promisify(execFile);

const VENV_PY = "/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python";
const ENTRY = "/Volumes/main-drive/ai-PA/letta/pulse-tools/_ext_run.py";
const PYPATH =
  "/Volumes/main-drive/ai-PA/letta/pulse-tools:/Volumes/main-drive/ai-PA/letta";
const ENV_FILE = "/Users/dorseyhomeserver/.letta/pa-tools.env";
const TOOL_TIMEOUT_MS = 300_000;

function loadEnvFile(path: string): Record<string, string> {
  const env: Record<string, string> = {};
  try {
    for (const line of readFileSync(path, "utf8").split("\n")) {
      const t = line.trim();
      if (!t || t.startsWith("#")) continue;
      const i = t.indexOf("=");
      if (i > 0) env[t.slice(0, i)] = t.slice(i + 1);
    }
  } catch {
    // env file optional; the python tool surfaces its own missing-config errors
  }
  return env;
}

// Run a pinned-venv Python tool via the generic entrypoint.
async function runPinned(
  module: string,
  func: string,
  kwargs: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<string> {
  const env = { ...process.env, ...loadEnvFile(ENV_FILE), PYTHONPATH: PYPATH };
  const { stdout } = await execFileAsync(
    VENV_PY,
    [ENTRY, module, func, JSON.stringify(kwargs)],
    { env, timeout: TOOL_TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024, signal },
  );
  return stdout.trim();
}

export default function activate(letta: any) {
  if (!letta.capabilities?.tools) return;

  return letta.tools.register({
    name: "collect_analytics_snapshot_ext",
    description:
      "Collect the daily analytics snapshot (Drive/Email/Slack metrics) for a " +
      "date and persist it to the analytics database. Deterministic extension " +
      "version that runs in a pinned Python venv. Pass `date` as YYYY-MM-DD; " +
      "omit for the default (last workday). Use this instead of " +
      "collect_analytics_snapshot.",
    parameters: {
      type: "object",
      properties: {
        date: {
          type: "string",
          description: "Target date YYYY-MM-DD (optional; defaults to last workday)",
        },
      },
      additionalProperties: false,
    },
    requiresApproval: false,
    parallelSafe: false,
    async run(ctx: any) {
      const date =
        ctx?.args && typeof ctx.args.date === "string" ? ctx.args.date.trim() : "";
      try {
        const out = await runPinned(
          "collect_analytics_snapshot",
          "collect_analytics_snapshot",
          date ? { date } : {},
          ctx?.signal,
        );
        return out || "(empty result)";
      } catch (err: any) {
        const stderr = err?.stderr ? String(err.stderr).slice(0, 1500) : "";
        return {
          status: "error",
          content:
            `collect_analytics_snapshot_ext failed: ${err?.message ?? err}` +
            (stderr ? `\n${stderr}` : ""),
        };
      }
    },
  });
}
