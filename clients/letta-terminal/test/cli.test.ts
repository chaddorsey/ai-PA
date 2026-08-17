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

  it("controller URL stays loopback-pinned without --allow-tailnet", () => {
    expect(() =>
      parseArgs(["--controller-url", "wss://dorseys-mac-mini.tailf9b999.ts.net/pa/surface"], {}),
    ).toThrow(/non-loopback/);
  });

  it("--allow-tailnet admits tailnet wss controller URLs, and ONLY those", () => {
    const argv = (url: string) => ["--allow-tailnet", "--controller-url", url];
    expect(() =>
      parseArgs(argv("wss://dorseys-mac-mini.tailf9b999.ts.net/pa/surface"), {}),
    ).not.toThrow();
    // Plaintext ws to the tailnet: refused (tailscale serve fronts the surface with TLS).
    expect(() => parseArgs(argv("ws://dorseys-mac-mini.tailf9b999.ts.net/pa/surface"), {})).toThrow(
      /wss/,
    );
    // Arbitrary internet host: refused even with the flag — not a remote escape hatch.
    expect(() => parseArgs(argv("wss://evil.example/surface"), {})).toThrow(/non-tailnet/);
    // Env form works like the flag.
    expect(() =>
      parseArgs(["--controller-url", "wss://dorseys-mac-mini.tailf9b999.ts.net/pa/surface"], {
        LETTA_CONTINUITY_ALLOW_TAILNET: "1",
      }),
    ).not.toThrow();
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

describe("agent-native surface", () => {
  it("parses one-shot, timeout and json", () => {
    const o = parseArgs(["--message", "hi", "--timeout", "30", "--json"], {});
    expect(o.message).toBe("hi");
    expect(o.timeoutSeconds).toBe(30);
    expect(o.json).toBe(true);
  });

  it("rejects a nonsense timeout instead of silently using NaN", () => {
    expect(() => parseArgs(["--timeout", "soon"], {})).toThrow(/positive number/);
    expect(() => parseArgs(["--timeout", "-5"], {})).toThrow(/positive number/);
  });

  it("rejects a timeout that would OVERFLOW the timer rather than firing in 4ms", () => {
    // setTimeout holds a signed 32-bit millisecond count. Past it the delay wraps and the timer
    // fires almost immediately, so `--timeout 9999999999` — which reads as "no real limit" —
    // produced a one-shot that gave up after ~4ms and exited 1, blaming the server.
    expect(() => parseArgs(["--timeout", "9999999999"], {})).toThrow(/overflows the timer/);
    expect(() => parseArgs(["--timeout", "2147483"], {})).not.toThrow();
  });

  it("requires --agent and --conversation together", () => {
    expect(() => parseArgs(["--agent", "agent-x"], {})).toThrow(/together/);
    expect(() => parseArgs(["--conversation", "conv-x"], {})).toThrow(/together/);
    expect(() => parseArgs(["--agent", "a", "--conversation", "c"], {})).not.toThrow();
  });

  it("resolves a relative pointer path to an absolute one", () => {
    // The bin wrapper cds to the launchpad dir before exec, so a relative --pointer was opened
    // relative to a directory the caller never chose: ENOENT at best, and at worst attaching to
    // a DIFFERENT conversation whose pointer happened to sit there.
    const o = parseArgs(["--pointer", "./p.json"], {});
    expect(o.pointerPath.startsWith("/")).toBe(true);
    expect(o.pointerPath.endsWith("/p.json")).toBe(true);
  });

  it("parses the conversations subcommands and their options", () => {
    expect(parseArgs(["conversations", "list"], {}).command).toBe("conversations-list");
    const c = parseArgs(
      ["conversations", "create", "--title", "seed", "--write-pointer", "./p.json"],
      {},
    );
    expect(c.command).toBe("conversations-create");
    expect(c.title).toBe("seed");
    expect(c.writePointer?.startsWith("/")).toBe(true);
    expect(() => parseArgs(["conversations", "destroy"], {})).toThrow(/unknown conversations/);
  });

  it("still validates the endpoint when a subcommand is used", () => {
    // Subcommand parsing slices argv; the trust check must not be skipped as a side effect.
    expect(() => parseArgs(["conversations", "list", "--url", "ws://evil.example/ws"], {})).toThrow(
      /non-loopback/,
    );
  });
});

describe("transport selection (C6)", () => {
  it("defaults to the controller; a --url FLAG implies the direct break-glass path", () => {
    expect(parseArgs([], {}).transport).toBe("controller");
    expect(parseArgs(["--url", "ws://127.0.0.1:4599/ws"], {}).transport).toBe("direct");
    expect(parseArgs(["--direct"], {}).transport).toBe("direct");
  });

  it("an ENV-supplied URL does NOT flip the transport (ambient state must not suspend guarantees)", () => {
    const o = parseArgs([], { LETTA_CONTINUITY_WS_URL: "ws://127.0.0.1:4599/ws" });
    expect(o.transport).toBe("controller");
    expect(o.url).toBe("ws://127.0.0.1:4599/ws");
  });
});
