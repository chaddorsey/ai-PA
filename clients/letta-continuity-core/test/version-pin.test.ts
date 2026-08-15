/**
 * The upgrade tripwire.
 *
 * `L5` — "protocol drift fails loudly" — is not satisfied by a gate nobody runs, and the live
 * contract test is opt-in (`LETTA_LIVE_WS=1`) and wired into no hook. So instead of hoping someone
 * remembers, this test makes the ORDINARY suite fail the moment the installed `letta` binary moves
 * outside the contract-verified set.
 *
 * When it fails the fix is not to edit the array. It is:
 *   1. clone the backend (never a second writer on the live one — R1),
 *   2. start the candidate server against the clone,
 *   3. `npm run check:live` pointed at it with LETTA_LIVE_WS_EXPECT_VERSION set,
 *   4. and only then add the version to VALIDATED_SERVER_VERSIONS.
 *
 * WHY IT WAS REWRITTEN. It probed ONE hard-coded path and `skipIf`'d itself when that path was
 * missing. Measured on this host: the path was missing, so the gate had silently been a no-op
 * reporting green — while the suite's own baseline (194 passed / 5 SKIPPED) recorded the fact in a
 * number nobody read. The cause was mundane and would recur: an interrupted `npm install` had left
 * the package's `package.json` in its staging directory (`@letta-ai/.letta-code-*`), so the
 * package was installed and working but the one file the probe looked at was not where it looked.
 *
 * A gate that disables itself when its probe misses cannot distinguish "no drift" from "not
 * checked". This version resolves the version from every place it plausibly lives, and when it
 * genuinely cannot, it FAILS rather than skipping — a machine with no letta must say so out loud
 * (`LETTA_CONTINUITY_LETTA_ABSENT=1`) rather than have the tripwire quietly switch itself off.
 */

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { VALIDATED_SERVER_VERSIONS } from "../src/protocol.js";

const PACKAGE = "@letta-ai/letta-code";

/** Set to "1" on a machine that deliberately has no letta installed (CI, a laptop). */
const ABSENT_ACKNOWLEDGEMENT = "LETTA_CONTINUITY_LETTA_ABSENT";

interface VersionProbe {
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

describe("server version pin", () => {
  const probe = probeInstalledLettaVersion();

  it("actually ran — the drift gate is not silently disabled", () => {
    // THE point of this file. A gate that skips when its probe misses reports the same green as a
    // gate that checked and found nothing wrong, and those are opposite facts. If letta really is
    // absent, say so deliberately; do not let the tripwire turn itself off.
    const acknowledged = process.env[ABSENT_ACKNOWLEDGEMENT] === "1";
    expect(
      probe.version !== null || acknowledged,
      `Could not resolve the installed ${PACKAGE} version, so the server/on-disk drift gate did NOT run.\n` +
        `Probed:\n${probe.probed.map((p) => `  - ${p}`).join("\n")}\n` +
        `Fix the install, set LETTA_INSTALLED_VERSION=<version>, or — if this machine deliberately\n` +
        `has no letta — set ${ABSENT_ACKNOWLEDGEMENT}=1 to record that choice.`,
    ).toBe(true);
  });

  it("the installed letta binary is a contract-verified version", () => {
    if (probe.version === null) {
      // The preceding test owns the "gate did not run" failure; failing twice for one cause just
      // makes the report harder to read.
      expect(process.env[ABSENT_ACKNOWLEDGEMENT]).toBe("1");
      return;
    }
    expect(
      VALIDATED_SERVER_VERSIONS as readonly string[],
      `Installed ${PACKAGE} is ${probe.version} (from ${probe.source}), which is not contract-verified.\n` +
        `Do NOT just add it to VALIDATED_SERVER_VERSIONS — run \`npm run check:live\` against a CLONED\n` +
        `backend first (never a second writer on the live one).`,
    ).toContain(probe.version);
  });

  it("every validated version is a plausible semver, and the pin is one of them", async () => {
    const { PINNED_SERVER_VERSION } = await import("../src/protocol.js");
    for (const v of VALIDATED_SERVER_VERSIONS) expect(v).toMatch(/^\d+\.\d+\.\d+$/);
    // Guards against the pin becoming `string | undefined` again via an index expression.
    expect(VALIDATED_SERVER_VERSIONS as readonly string[]).toContain(PINNED_SERVER_VERSION);
  });
});
