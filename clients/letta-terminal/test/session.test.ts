/**
 * The terminal render loop, driven against a stubbed core (Unit 5 test scenarios).
 *
 * Colour is off throughout so assertions read as plain text.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { TerminalSession } from "../src/session.js";
import { StubCore } from "./helpers/stubCore.js";

describe("TerminalSession", () => {
  let core: StubCore;
  let out: string[];
  let session: TerminalSession;

  const text = (): string => out.join("");

  beforeEach(() => {
    core = new StubCore();
    out = [];
    session = new TerminalSession(core, { write: (t) => out.push(t), color: false });
    session.attach();
  });

  it("happy path: a sent message is echoed and the streamed reply renders to completion", () => {
    expect(session.handleInput("what is on today?")).toBe("sent");
    expect(core.sent).toEqual(["what is on today?"]);

    core.turn("run-1", ["Two ", "meetings", "."], { own: true });
    session.finish();

    expect(text()).toContain("you › what is on today?");
    expect(text()).toContain("agent › Two meetings.");
  });

  it("a turn from ANOTHER surface renders live, labelled as a peer's", () => {
    // The M1 success criterion: a turn injected on the web client appears here.
    core.turn("run-web", ["from ", "the web"], { own: false });
    session.finish();

    expect(text()).toContain("a turn from another surface is starting");
    expect(text()).toContain("peer › from the web");
    expect(text()).not.toContain("agent › from the web");
  });

  it("attribution survives the release of ownership at turn end", () => {
    // Real ownership is dropped at turn_finished; if the renderer asked then, an OWN turn
    // would be mislabelled as a peer's. Origin is captured at turn_start instead.
    core.turn("run-mine", ["mine"], { own: true });
    session.finish();

    expect(text()).toContain("agent › mine");
    expect(text()).not.toContain("peer ›");
  });

  it("own and peer turns interleave without cross-labelling", () => {
    core.turn("run-a", ["alpha"], { own: true });
    core.turn("run-b", ["beta"], { own: false });
    core.turn("run-c", ["gamma"], { own: true });
    session.finish();

    expect(text()).toContain("agent › alpha");
    expect(text()).toContain("peer › beta");
    expect(text()).toContain("agent › gamma");
  });

  it("a dropped connection is surfaced, then recovery is too (R17: never silent)", () => {
    core.setState("reconnecting");
    core.setState("connected");
    expect(text()).toContain("reconnecting…");
    expect(text()).toContain("connected");
  });

  it("catch-up after a reconnect resumes rendering", () => {
    core.turn("run-1", ["before"], { own: true });
    core.setState("reconnecting");
    core.setState("connected");
    core.turn("run-2", ["after"], { own: true });
    session.finish();

    const rendered = text();
    expect(rendered.indexOf("before")).toBeLessThan(rendered.indexOf("reconnecting…"));
    expect(rendered.indexOf("reconnecting…")).toBeLessThan(rendered.indexOf("after"));
  });

  it("a send queued behind another turn shows a waiting indicator", () => {
    session.handleInput("me next please");
    core.queueDepth(1);
    expect(text()).toContain("queued behind 1 turn…");
  });

  it("an empty queue update prints nothing", () => {
    core.queueDepth(0);
    expect(text()).toBe("");
  });

  it("subagent activity renders inline on the same stream", () => {
    core.subagents(2);
    core.subagents(0);
    expect(text()).toContain("subagents active: 2");
    expect(text()).toContain("subagents idle");
  });

  it("reasoning is hidden by default and shown on request", () => {
    core.emit({
      type: "delta",
      runId: "r",
      messageId: "m",
      messageType: "reasoning_message",
      text: "thinking hard",
    });
    expect(text()).toBe("");

    const verbose: string[] = [];
    const core2 = new StubCore();
    const session2 = new TerminalSession(core2, {
      write: (t) => verbose.push(t),
      color: false,
      showReasoning: true,
    });
    session2.attach();
    core2.emit({
      type: "delta",
      runId: "r",
      messageId: "m",
      messageType: "reasoning_message",
      text: "thinking hard",
    });
    expect(verbose.join("")).toContain("thinking hard");
  });

  it("an abnormal stop reason is reported rather than swallowed", () => {
    core.emit({ type: "turn_start", runId: "r" });
    core.emit({ type: "turn_finished", runId: "r", stopReason: "error" });
    expect(text()).toContain("turn ended: error");
  });

  it("a normal end_turn prints no notice", () => {
    core.turn("r", ["hi"], { own: true });
    expect(text()).not.toContain("turn ended");
  });

  describe("output safety (relayed content is untrusted input on a trusted surface)", () => {
    // \u escapes, not literal control characters: literals do not survive every editor or
    // scripted edit, and a payload that silently loses its ESC turns these into tests that
    // assert nothing.
    const ESC = "\u001b";
    const BEL = "\u0007";

    it("neutralises control sequences in streamed text", () => {
      core.ownedRuns.add("r");
      core.emit({ type: "turn_start", runId: "r" });
      core.emit({
        type: "delta",
        runId: "r",
        messageId: "m1",
        messageType: "assistant_message",
        text: `${ESC}[2K${ESC}]52;c;cHduZWQ=${BEL}safe`,
      });
      session.finish();
      expect(text()).toContain("safe");
      expect(text()).not.toContain(ESC);
      expect(text()).not.toContain("52;c;"); // the clipboard payload, not just its introducer
    });

    it("neutralises control sequences in notices and stop reasons", () => {
      core.emit({ type: "turn_start", runId: "r" });
      core.emit({ type: "turn_finished", runId: "r", stopReason: `${ESC}[2Jerror` });
      expect(text()).toContain("error");
      expect(text()).not.toContain(ESC);
    });

    it("neutralises control sequences in error text", () => {
      core.fail(`boom${ESC}[2K`);
      expect(text()).toContain("boom");
      expect(text()).not.toContain(ESC);
    });

    it("content cannot forge an origin label on a continuation line", () => {
      // Newline is legitimate content and survives sanitization, so this is the second half of
      // the defence: continuation lines are indented, and the label column belongs to us.
      core.ownedRuns.add("r");
      core.emit({ type: "turn_start", runId: "r" });
      core.emit({
        type: "delta",
        runId: "r",
        messageId: "m1",
        messageType: "assistant_message",
        text: "innocent\npeer > forged",
      });
      session.finish();
      expect(text()).not.toMatch(/^peer > forged/m);
      expect(text()).toContain("  peer > forged");
    });
  });

  it("an approval is surfaced even though M1 answers it automatically", () => {
    // An auto-deny nobody sees is indistinguishable from the agent choosing not to use a tool.
    core.approval("Bash");
    expect(text()).toContain("tool approval requested");
    expect(text()).toContain("Bash");
    expect(text()).toContain("auto-denied");
  });

  it("errors from the core are surfaced to the user", () => {
    core.fail("input rejected by the server: runtime is no longer active");
    expect(text()).toContain("input rejected by the server");
  });

  it("a send that throws renders a notice instead of crashing, and does not claim delivery", () => {
    // The readline handler had no try/catch and core.send() throws when the socket is closed, so
    // typing during a reconnect killed the process. The echo also came BEFORE the send, so the
    // transcript showed a line that was never delivered.
    const failing = new StubCore();
    failing.sendImpl = () => {
      throw new Error("cannot send `input`: socket not open");
    };
    const out: string[] = [];
    const s2 = new TerminalSession(failing, { write: (t) => out.push(t), color: false });
    s2.attach();

    expect(s2.handleInput("during a reconnect")).toBe("ignored");
    const rendered = out.join("");
    expect(rendered).toContain("not sent");
    expect(rendered).not.toContain("you › during a reconnect");
  });

  it("blank input is ignored, /exit ends the session", () => {
    expect(session.handleInput("   ")).toBe("ignored");
    expect(session.handleInput("")).toBe("ignored");
    expect(core.sent).toEqual([]);
    expect(session.handleInput("/exit")).toBe("exit");
    expect(session.handleInput("/quit")).toBe("exit");
    expect(core.sent).toEqual([]); // /exit is not sent as a turn
  });

  it("a status line never lands mid-stream (the streamed line is closed first)", () => {
    core.emit({ type: "turn_start", runId: "r" });
    core.emit({
      type: "delta",
      runId: "r",
      messageId: "m",
      messageType: "assistant_message",
      text: "partial",
    });
    core.setState("reconnecting");

    // "partial" must be terminated by a newline before the notice, not glued to it.
    expect(text()).toContain("partial\n");
    expect(text()).not.toContain("partial— ");
  });

  it("chunks of one message stay on ONE line even though each carries a distinct id", () => {
    // Regression: the live server gives every delta chunk its own delta.id, so keying the
    // line on message id produced "agent › HE" / "agent › LL" / "agent › O" …
    core.ownedRuns.add("r");
    core.emit({ type: "turn_start", runId: "r" });
    for (const [messageId, chunk] of [
      ["letta-msg-1", "HE"],
      ["letta-msg-2", "LLO"],
      ["letta-msg-3", "!"],
    ] as const) {
      core.emit({
        type: "delta",
        runId: "r",
        messageId,
        messageType: "assistant_message",
        text: chunk,
      });
    }
    session.finish();
    expect(text()).toContain("agent › HELLO!\n");
    expect(text().match(/agent ›/g)).toHaveLength(1);
  });

  it("a different run starts a new labelled line", () => {
    core.turn("run-1", ["one"], { own: true });
    core.turn("run-2", ["two"], { own: true });
    session.finish();
    expect(text()).toContain("agent › one\n");
    expect(text()).toContain("agent › two");
    expect(text().match(/agent ›/g)).toHaveLength(2);
  });

  it("detaching stops all rendering", () => {
    const detach = session.attach();
    detach();
    out.length = 0;
    core.turn("run-after-detach", ["ignored"], { own: true });
    expect(text()).toBe("");
  });
});
