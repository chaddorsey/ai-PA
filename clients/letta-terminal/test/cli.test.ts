import { describe, expect, it } from "vitest";
import { CliError, DEFAULT_POINTER_PATH, parseArgs } from "../src/cli.js";

describe("parseArgs", () => {
  it("defaults to the shared pointer path and the core's URL", () => {
    const o = parseArgs([], {});
    expect(o.pointerPath).toBe(DEFAULT_POINTER_PATH);
    expect(o.url).toBeUndefined();
    expect(o.showReasoning).toBe(false);
    expect(o.strictVersion).toBe(false);
    expect(o.help).toBe(false);
  });

  it("env supplies pointer and URL", () => {
    const o = parseArgs([], {
      LETTA_CONTINUITY_POINTER: "/tmp/p.json",
      LETTA_CONTINUITY_WS_URL: "ws://127.0.0.1:4599/ws",
    });
    expect(o.pointerPath).toBe("/tmp/p.json");
    expect(o.url).toBe("ws://127.0.0.1:4599/ws");
  });

  it("flags override env", () => {
    const o = parseArgs(["--pointer", "/tmp/flag.json", "--url", "ws://x/ws"], {
      LETTA_CONTINUITY_POINTER: "/tmp/env.json",
      LETTA_CONTINUITY_WS_URL: "ws://env/ws",
    });
    expect(o.pointerPath).toBe("/tmp/flag.json");
    expect(o.url).toBe("ws://x/ws");
  });

  it("parses the boolean flags", () => {
    const o = parseArgs(["--reasoning", "--strict-version", "--no-color"], {});
    expect(o.showReasoning).toBe(true);
    expect(o.strictVersion).toBe(true);
    expect(o.color).toBe(false);
  });

  it("honours NO_COLOR", () => {
    expect(parseArgs([], { NO_COLOR: "1" }).color).toBe(false);
    expect(parseArgs([], {}).color).toBeUndefined(); // decided from isTTY at runtime
  });

  it("-h / --help request usage", () => {
    expect(parseArgs(["-h"], {}).help).toBe(true);
    expect(parseArgs(["--help"], {}).help).toBe(true);
  });

  it("a value-taking flag with no value is an error, not a silent default", () => {
    expect(() => parseArgs(["--pointer"], {})).toThrow(CliError);
    expect(() => parseArgs(["--url"], {})).toThrow(CliError);
  });

  it("an unknown option is rejected with usage", () => {
    expect(() => parseArgs(["--backend", "local"], {})).toThrow(/unknown option: --backend/);
  });
});
