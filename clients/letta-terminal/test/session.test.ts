/**
 * The terminal render loop, driven against a stubbed core (Unit 5 test scenarios).
 *
 * Colour is off throughout so assertions read as plain text.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { MAX_TRACKED_ORIGINS } from "../src/render.js";
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

  it("an UNATTRIBUTABLE turn is hedged, not asserted to be another surface's", () => {
    // Attribution is inferred from stream position and cannot be made exact, so `unknown` is a
    // routine outcome. The renderer used to collapse it into "peer", which states that a second
    // surface exists when the truth is only that we cannot tell — and on a shared conversation
    // the origin label is the security signal the operator reads. A hedge is honest; a confident
    // wrong answer is not.
    core.emit({ type: "turn_start", runId: "run-mystery" });
    core.emit({
      type: "delta",
      runId: "run-mystery",
      messageId: "m1",
      messageType: "assistant_message",
      text: "who sent this?",
    });
    session.finish();

    expect(text()).toContain("origin unknown");
    expect(text()).toContain("agent? › who sent this?");
    expect(text()).not.toContain("a turn from another surface is starting");
    expect(text()).not.toContain("peer › who sent this?");
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

  it("a queue update with none of OUR messages in it prints nothing", () => {
    // update_queue is broadcast to every subscriber, so the surface whose turn is actually
    // RUNNING was being told it was queued behind itself. An operator reading their live turn as
    // blocked is likely to retype or Ctrl-C, which on a shared conversation makes it worse.
    core.queueDepth(2, false);
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

    it("neutralises control sequences in the LOCAL echo too", () => {
      // Readline swallows escapes as key events only in terminal mode, and main.ts ties that mode
      // to the colour setting — so under NO_COLOR, a non-TTY stdout, or a piped session, a pasted
      // OSC 52 reaches the echo verbatim. The user's own line is still attacker-influenced when
      // the user is pasting something an attacker wrote.
      session.handleInput(`${ESC}]52;c;cHduZWQ=${BEL}hi`);
      expect(text()).toContain("hi");
      expect(text()).not.toContain(ESC);
      expect(text()).not.toContain("52;c;");
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

    // "failed", not "ignored". A turn that was never delivered and a blank line the user typed
    // are different events; collapsing them meant a caller could not tell three swallowed
    // messages from three empty Enters, and exited 0 either way.
    expect(s2.handleInput("during a reconnect")).toBe("failed");
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

  it("origin tracking is bounded across many interrupted turns", () => {
    // Entries are normally freed at turn_finished; a finish lost across a reconnect leaks one.
    // On a client attached for days that is unbounded growth.
    for (let i = 0; i < 2000; i += 1) {
      core.ownedRuns.add(`run-${i}`);
      core.emit({ type: "turn_start", runId: `run-${i}` });
      // No turn_finished: exactly the shape a watchdog restart leaves behind.
    }
    // Completing one more turn triggers eviction; the maps must not have grown without bound.
    core.turn("run-final", ["done"], { own: true });
    session.finish();
    expect(text()).toContain("agent › done");

    // The assertion that was missing. Without it this test passed with BOTH eviction loops
    // disabled — it only ever checked that a string appeared, which is true either way.
    const tracked = session.trackedOriginCount;
    expect(tracked.session).toBeLessThanOrEqual(MAX_TRACKED_ORIGINS);
    expect(tracked.renderer).toBeLessThanOrEqual(MAX_TRACKED_ORIGINS);
  });

  describe("the transcript sink carries only the transcript", () => {
    // An automation reading the last `agent ›` line, or capturing the conversation to a file, must
    // not have client chatter interleaved into it — and `2>/dev/null` must actually suppress that
    // chatter. With one shared sink there was nothing to assert and nothing to suppress.
    function split(): { out: string[]; err: string[]; core: StubCore; session: TerminalSession } {
      const out: string[] = [];
      const err: string[] = [];
      const core = new StubCore();
      const session = new TerminalSession(core, {
        write: (t) => out.push(t),
        writeErr: (t) => err.push(t),
        color: false,
      });
      session.attach();
      return { out, err, core, session };
    }

    it("connection-state changes go to stderr, not into the transcript", () => {
      const { out, err, core } = split();
      core.setState("reconnecting");
      core.setState("connected");
      expect(err.join("")).toContain("reconnecting…");
      expect(out.join("")).toBe("");
    });

    it("errors go to stderr, not into the transcript", () => {
      const { out, err, core } = split();
      core.fail("something went wrong");
      expect(err.join("")).toContain("something went wrong");
      expect(out.join("")).toBe("");
    });

    it("approval notices go to stderr, not into the transcript", () => {
      const { out, err, core } = split();
      core.approval("Bash");
      expect(err.join("")).toContain("tool approval requested");
      expect(out.join("")).toBe("");
    });

    it("an undelivered message is reported on stderr, not echoed into the transcript", () => {
      const { out, err, core, session } = split();
      core.sendImpl = () => {
        throw new Error("cannot send `input`: socket not open");
      };
      expect(session.handleInput("during a reconnect")).toBe("failed");
      expect(err.join("")).toContain("not sent");
      expect(out.join("")).toBe("");
    });

    it("subagent activity is chatter, not conversation", () => {
      // Found LIVE, after the offline suite went green: a piped one-shot's stdout read
      //   you › …
      //   — subagents idle
      //   agent › OK
      // The tests could not see it because they gave the session ONE sink, so `writeErr` defaulted
      // back to `write` and every routing assertion was vacuous.
      const { out, err, core } = split();
      core.subagents(2);
      core.subagents(0);
      expect(err.join("")).toContain("subagents active: 2");
      expect(err.join("")).toContain("subagents idle");
      expect(out.join("")).toBe("");
    });

    it("a queue indicator and an abnormal turn ending are chatter too", () => {
      const { out, err, core, session } = split();
      session.handleInput("me next please");
      out.length = 0; // drop the echo; this test is about what follows it
      core.queueDepth(1);
      core.emit({ type: "turn_start", runId: "r" });
      core.emit({ type: "turn_finished", runId: "r", stopReason: "error" });
      expect(err.join("")).toContain("queued behind 1 turn");
      expect(err.join("")).toContain("turn ended: error");
      expect(out.join("")).toBe("");
    });

    it("a peer's turn announcement is chatter; the peer's WORDS are conversation", () => {
      const { out, err, core, session } = split();
      core.turn("run-web", ["from ", "the web"], { own: false });
      session.finish();
      expect(err.join("")).toContain("a turn from another surface is starting");
      expect(out.join("")).toContain("peer › from the web");
      expect(out.join("")).not.toContain("another surface");
    });

    it("a notice arriving mid-reply closes the transcript's line ON THE TRANSCRIPT", () => {
      // The newline that terminates an open `agent › …` line belongs to the stream that line is
      // on. Sending it to stderr would leave the transcript's last line unterminated forever.
      const { out, err, core } = split();
      core.ownedRuns.add("r");
      core.emit({ type: "turn_start", runId: "r" });
      core.emit({
        type: "delta",
        runId: "r",
        messageId: "m",
        messageType: "assistant_message",
        text: "partial",
      });
      core.setState("reconnecting");

      expect(out.join("")).toBe("agent › partial\n");
      expect(err.join("")).toContain("reconnecting…");
    });

    it("the reply and the local echo DO go to the transcript", () => {
      // The other half: routing everything to stderr would satisfy the four assertions above.
      const { out, err, core, session } = split();
      session.handleInput("what is on today?");
      core.turn("run-1", ["Two meetings."], { own: true });
      expect(out.join("")).toContain("you › what is on today?");
      expect(out.join("")).toContain("agent › Two meetings.");
      expect(err.join("")).toBe("");
    });
  });

  it("a delta for a run we never saw START is hedged, not claimed as our own", () => {
    // No turn_start means no origin was ever decided — a turn already in flight when we attached,
    // or one whose opening frames were lost across a reconnect. Treating a missing map entry as
    // `self` printed another surface's turn under our own label.
    core.emit({
      type: "delta",
      runId: "run-already-running",
      messageId: "m1",
      messageType: "assistant_message",
      text: "mid-flight",
    });
    session.finish();
    expect(text()).toContain("agent? › mid-flight");
    expect(text()).not.toContain("agent › mid-flight");
  });

  it("detaching stops all rendering", () => {
    const detach = session.attach();
    detach();
    out.length = 0;
    core.turn("run-after-detach", ["ignored"], { own: true });
    expect(text()).toBe("");
  });
});
