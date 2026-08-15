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

import { describe, expect, it } from "vitest";
import { VALIDATED_SERVER_VERSIONS } from "../src/protocol.js";
import {
  ABSENT_ACKNOWLEDGEMENT,
  PACKAGE,
  probeInstalledLettaVersion,
} from "./helpers/installedVersion.js";

describe("server version pin", () => {
  const probe = probeInstalledLettaVersion();

  it("actually ran — the drift gate is not silently disabled", () => {
    // THE point of this file. A gate that skips when its probe misses reports the same green as a
    // gate that checked and found nothing wrong, and those are opposite facts. If letta really is
    // absent, say so deliberately; do not let the tripwire turn itself off.
    const acknowledged = process.env[ABSENT_ACKNOWLEDGEMENT] === "1";
    const probedList = probe.probed.map((p) => `  - ${p}`).join("\n");
    expect(
      probe.version !== null || acknowledged,
      [
        `Could not resolve the installed ${PACKAGE} version, so the server/on-disk drift gate did NOT run.`,
        `Probed:\n${probedList}`,
        "Fix the install, set LETTA_INSTALLED_VERSION=<version>, or — if this machine deliberately",
        `has no letta — set ${ABSENT_ACKNOWLEDGEMENT}=1 to record that choice.`,
      ].join("\n"),
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
      [
        `Installed ${PACKAGE} is ${probe.version} (from ${probe.source}), which is not contract-verified.`,
        "Do NOT just add it to VALIDATED_SERVER_VERSIONS — run `npm run check:live` against a CLONED",
        "backend first (never a second writer on the live one).",
      ].join("\n"),
    ).toContain(probe.version);
  });

  it("every validated version is a plausible semver, and the pin is one of them", async () => {
    const { PINNED_SERVER_VERSION } = await import("../src/protocol.js");
    for (const v of VALIDATED_SERVER_VERSIONS) expect(v).toMatch(/^\d+\.\d+\.\d+$/);
    // Guards against the pin becoming `string | undefined` again via an index expression.
    expect(VALIDATED_SERVER_VERSIONS as readonly string[]).toContain(PINNED_SERVER_VERSION);
  });
});
