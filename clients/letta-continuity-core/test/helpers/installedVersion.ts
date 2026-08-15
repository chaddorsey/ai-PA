/**
 * installedVersion.ts — resolve the letta-code version that is INSTALLED on this host.
 *
 * Extracted from version-pin.test.ts so two different gates can share one probe: the offline pin
 * check (is what is on disk contract-verified?) and the live check (is what is RUNNING the same
 * build as what is on disk?). Those are different questions, and on 2026-08-15 they had different
 * answers — a half-finished `npm install` left 0.30.20 on disk while a 0.30.19 process kept
 * running, and every gate reported green because each only asked its own half.
 */

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

export const PACKAGE = "@letta-ai/letta-code";

/** Set to "1" on a machine that deliberately has no letta installed (CI, a laptop). */
export const ABSENT_ACKNOWLEDGEMENT = "LETTA_CONTINUITY_LETTA_ABSENT";

export interface VersionProbe {
  version: string | null;
  /** Where it was found, or every place looked when it was not. Reported in the failure. */
  source: string;
  probed: string[];
}

/** Global `node_modules` roots, most likely first. `npm root -g` is authoritative but slow. */
function globalRoots(): string[] {
  const roots = [
    "/opt/homebrew/lib/node_modules",
    "/usr/local/lib/node_modules",
    "/usr/lib/node_modules",
  ];
  try {
    const fromNpm = execFileSync("npm", ["root", "-g"], {
      encoding: "utf-8",
      timeout: 15_000,
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    if (fromNpm) roots.unshift(fromNpm);
  } catch {
    // npm missing or slow: the hard-coded roots still cover every install this project supports.
  }
  return [...new Set(roots)];
}

function versionFrom(packageJsonPath: string): string | null {
  if (!existsSync(packageJsonPath)) return null;
  try {
    const pkg = JSON.parse(readFileSync(packageJsonPath, "utf-8")) as {
      name?: string;
      version?: string;
    };
    // The staging directories below belong to arbitrary packages, so the name must be checked;
    // otherwise a half-installed neighbour would be reported as letta's version.
    if (pkg.name !== PACKAGE) return null;
    return typeof pkg.version === "string" ? pkg.version : null;
  } catch {
    return null;
  }
}

export function probeInstalledLettaVersion(): VersionProbe {
  const probed: string[] = [];
  const override = process.env.LETTA_INSTALLED_VERSION;
  if (override) return { version: override, source: "LETTA_INSTALLED_VERSION", probed };

  for (const root of globalRoots()) {
    const canonical = join(root, PACKAGE, "package.json");
    probed.push(canonical);
    const found = versionFrom(canonical);
    if (found) return { version: found, source: canonical, probed };

    // An interrupted or atomic npm install leaves the real package.json in a sibling staging
    // directory (`@letta-ai/.letta-code-<hash>`) while the package itself is already in place.
    // That is exactly the state this host was in, and the state the old probe read as "absent".
    const scope = join(root, "@letta-ai");
    if (!existsSync(scope)) continue;
    try {
      for (const entry of readdirSync(scope)) {
        if (!entry.startsWith(".letta-code")) continue;
        const staged = join(scope, entry, "package.json");
        probed.push(staged);
        const stagedVersion = versionFrom(staged);
        if (stagedVersion) return { version: stagedVersion, source: staged, probed };
      }
    } catch {
      // Unreadable scope directory: nothing to learn here, keep probing the other roots.
    }
  }
  return { version: null, source: "not found", probed };
}
