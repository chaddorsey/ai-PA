import { describe, expect, it } from "vitest";
import { CliError, DEFAULT_POINTER_PATH, parseArgs } from "../src/cli.js";

describe("endpoint validation (loopback is the trust boundary)", () => {
  // The App Server takes no client auth because it binds loopback. A client that dials anywhere
  // and then trusts the peer inverts that: everything typed — and the whole history, via
  // conversation_messages_list — goes to the remote host in cleartext, and what it streams back
  // renders under the agent's own label.
  it("accepts loopback in its usual spellings", () => {
    for (const url of ["ws://127.0.0.1:4577/ws", "ws://localhost:4577/ws", "ws://[::1]:4577/ws"]) {
      expect(() => parseArgs(["--url", url], {})).not.toThrow();
    }
  });

  it("refuses a non-loopback host", () => {
    expect(() => parseArgs(["--url", "ws://evil.example/ws"], {})).toThrow(/non-loopback/);
    expect(() => parseArgs(["--url", "ws://10.0.0.5:4577/ws"], {})).toThrow(/non-loopback/);
  });

  it("refuses a non-loopback host supplied through the ENVIRONMENT too", () => {
    // The likelier attack: one edited rc file or plist entry, not a typed flag.
    expect(() => parseArgs([], { LETTA_CONTINUITY_WS_URL: "ws://evil.example/ws" })).toThrow(
      /non-loopback/,
    );
  });

  it("refuses a non-ws scheme", () => {
    expect(() => parseArgs(["--url", "http://127.0.0.1:4577/ws"], {})).toThrow(/ws:\/\/ or wss/);
  });

  it("allows remote only with an explicit opt-in", () => {
    expect(() => parseArgs(["--url", "ws://evil.example/ws", "--allow-remote"], {})).not.toThrow();
  });
});

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
    const o = parseArgs(["--pointer", "/tmp/flag.json", "--url", "ws://127.0.0.1:4599/ws"], {
      LETTA_CONTINUITY_POINTER: "/tmp/env.json",
      LETTA_CONTINUITY_WS_URL: "ws://127.0.0.1:1/ws",
    });
    expect(o.pointerPath).toBe("/tmp/flag.json");
    expect(o.url).toBe("ws://127.0.0.1:4599/ws");
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
