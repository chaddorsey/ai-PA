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
 * Skipped when letta-code is not installed (CI, another machine), because a missing binary is not
 * evidence of drift.
 */

import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { VALIDATED_SERVER_VERSIONS } from "../src/protocol.js";

/** Where Homebrew's npm global install puts letta-code on this host. */
const LETTA_PACKAGE_JSON = "/opt/homebrew/lib/node_modules/@letta-ai/letta-code/package.json";

function installedLettaVersion(): string | null {
  const override = process.env.LETTA_INSTALLED_VERSION;
  if (override) return override;
  if (!existsSync(LETTA_PACKAGE_JSON)) return null;
  try {
    const pkg = JSON.parse(readFileSync(LETTA_PACKAGE_JSON, "utf-8")) as { version?: string };
    return typeof pkg.version === "string" ? pkg.version : null;
  } catch {
    return null;
  }
}

describe("server version pin", () => {
  const installed = installedLettaVersion();

  it.skipIf(installed === null)("the installed letta binary is a contract-verified version", () => {
    expect(VALIDATED_SERVER_VERSIONS as readonly string[]).toContain(installed as string);
  });

  it("every validated version is a plausible semver, and the pin is one of them", async () => {
    const { PINNED_SERVER_VERSION } = await import("../src/protocol.js");
    for (const v of VALIDATED_SERVER_VERSIONS) expect(v).toMatch(/^\d+\.\d+\.\d+$/);
    // Guards against the pin becoming `string | undefined` again via an index expression.
    expect(VALIDATED_SERVER_VERSIONS as readonly string[]).toContain(PINNED_SERVER_VERSION);
  });
});
