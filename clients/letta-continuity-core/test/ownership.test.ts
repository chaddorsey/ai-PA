/**
 * Run-ownership attribution (followup finding #1).
 *
 * The scenarios here are the ones a bare outstanding-turn counter gets WRONG, which is why
 * the counter was replaced: a foreign turn finishing while ours is in flight, and our own
 * turn finishing while a foreign one is in flight.
 *
 * The frame sequences are transcribed from live captures against 0.30.19 (:4577) — see the
 * two-client concurrency probe: A acks `started` and takes local-run-251, B acks `queued`,
 * appears in update_queue as CM-B, is `dequeued` after A's turn_finished, and takes 252.
 */

import { describe, expect, it } from "vitest";
import { RunOwnership } from "../src/ownership.js";

describe("RunOwnership", () => {
  it("a `started` ack claims the next new run, and turn_finished releases it", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-251");

    expect(o.owns("local-run-251")).toBe(true);
    expect(o.attribute("local-run-251")).toBe("mine");

    o.onTurnFinished("local-run-251");
    expect(o.owns("local-run-251")).toBe(false);
    expect(o.hasOutstanding()).toBe(false);
  });

  it("a foreign run is never claimed when we have nothing outstanding", () => {
    const o = new RunOwnership();
    o.onRunObserved("local-run-999");
    expect(o.owns("local-run-999")).toBe(false);
    // Positively foreign: we held nothing outstanding, so nothing of ours could have started.
    expect(o.attribute("local-run-999")).toBe("foreign");
  });

  it("THE COUNTER BUG: a foreign turn_finished must not release our claim", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-251");

    // A peer's turn completes while ours is still running. A counter would hit zero here and
    // the injector would then NOT deny its own approval → the turn hangs on every surface.
    o.onTurnFinished("local-run-900");

    expect(o.owns("local-run-251")).toBe(true);
    expect(o.attribute("local-run-251")).toBe("mine");
  });

  /**
   * PREMISE CORRECTED, deliberately. This used to feed a second run while ours was in flight and
   * call it "a peer's run", asserting `unknown`. The server serializes turns per
   * {agent, conversation} — the assumption this whole module rests on — so a peer's turn CANNOT
   * start while ours is running; it is queued. A new run there is a continuation of our own turn,
   * which is what the live tool-using capture shows. The property worth keeping from the original
   * is the one about the counter: a turn ending must not release the wrong claim.
   */
  it("THE MIRROR BUG: a peer's turn_finished must not release our run, and ours stays ours", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-251");

    // A run the peer finished BEFORE ours started (we simply never saw it begin).
    o.onTurnFinished("local-run-900");

    expect(o.attribute("local-run-251")).toBe("mine");
    expect(o.owns("local-run-251")).toBe(true);
  });

  it("once the runtime reports itself IDLE, a new run is a peer's and not a continuation", () => {
    // The bound on continuation inheritance, and it comes from the wire rather than from a
    // timeout: WAITING_ON_INPUT is the server stating that no turn is executing.
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A", "tab-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-251");
    o.onIdle();

    o.onRunObserved("local-run-900");
    expect(o.attribute("local-run-900")).toBe("foreign");
    expect(o.originOf("local-run-900")).toBeUndefined();
  });

  it("a run parked on an approval survives the idle sweep", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-700");
    o.onTurnFinished("local-run-700", "requires_approval");

    o.onIdle(); // the runtime is idle because it is WAITING for the approval

    expect(o.owns("local-run-700")).toBe(true);
  });

  it("a `queued` ack waits for OUR dequeue before claiming a run", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-B", "CM-B");
    o.onInputAccepted("REQ-B", true, "queued");

    // The peer's turn runs first — we must not claim it.
    o.onRunObserved("local-run-251");
    expect(o.owns("local-run-251")).toBe(false);
    o.onTurnFinished("local-run-251");

    // A peer's queue entry leaving is not ours.
    o.onQueueRemovals([{ client_message_id: "CM-OTHER", disposition: "dequeued" }]);
    o.onRunObserved("local-run-252");
    expect(o.owns("local-run-252")).toBe(false);

    // Our dequeue arms the claim; the next new run is ours.
    o.onQueueRemovals([{ client_message_id: "CM-B", disposition: "dequeued" }]);
    o.onRunObserved("local-run-253");
    expect(o.owns("local-run-253")).toBe(true);
  });

  it("a cancelled queue entry never claims a run", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-B", "CM-B");
    o.onInputAccepted("REQ-B", true, "queued");
    o.onQueueRemovals([{ client_message_id: "CM-B", disposition: "cancelled" }]);
    o.onRunObserved("local-run-260");
    expect(o.owns("local-run-260")).toBe(false);
    expect(o.hasOutstanding()).toBe(false);
  });

  it("a rejected input claims nothing", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", false);
    o.onRunObserved("local-run-261");
    expect(o.owns("local-run-261")).toBe(false);
    expect(o.hasOutstanding()).toBe(false);
  });

  describe("replay resistance (ids are broadcast, so unpredictability is not a defense)", () => {
    it("a replayed `cancelled` does NOT drop an already-armed claim", () => {
      // The dangerous replay: previously this deleted the claim, so we never owned our run,
      // never answered its approval, and hung the turn — the non-recoverable failure.
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "queued");
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "dequeued" }]);

      const anomalies: string[] = [];
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "cancelled" }], (m) =>
        anomalies.push(m),
      );

      o.onRunObserved("local-run-1");
      expect(o.owns("local-run-1")).toBe(true);
      expect(anomalies).toHaveLength(1);
    });

    it("a replayed `dequeued` after the claim is bound is a no-op anomaly, not a re-arm", () => {
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "queued");
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "dequeued" }]);
      o.onRunObserved("local-run-1");
      // Our turn completes and the runtime goes idle, so the next run genuinely is a peer's —
      // without this the sequence describes a state the serializing server cannot produce.
      o.onTurnFinished("local-run-1");
      o.onIdle();

      const anomalies: string[] = [];
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "dequeued" }], (m) =>
        anomalies.push(m),
      );

      // Without single-shot transitions this would arm a phantom claim that then steals a peer.
      o.onRunObserved("local-run-peer");
      expect(o.owns("local-run-peer")).toBe(false);
      expect(anomalies).toHaveLength(1);
    });

    it("a removal for an id we never minted is silent (that is just a peer's message)", () => {
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "queued");
      const anomalies: string[] = [];
      o.onQueueRemovals([{ client_message_id: "CM-PEER", disposition: "dequeued" }], (m) =>
        anomalies.push(m),
      );
      expect(anomalies).toEqual([]);
      o.onRunObserved("local-run-peer");
      expect(o.owns("local-run-peer")).toBe(false);
    });

    it("a removal arriving before the ack (claim still awaiting-ack) is ignored, not applied", () => {
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A");
      const anomalies: string[] = [];
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "dequeued" }], (m) =>
        anomalies.push(m),
      );
      expect(anomalies).toHaveLength(1);
      o.onRunObserved("local-run-1");
      expect(o.owns("local-run-1")).toBe(false); // still awaiting its own ack
    });
  });

  it("acks and dequeues for other clients' ids are ignored", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-PEER", true, "started"); // a peer's ack, seen on our socket
    o.onQueueRemovals([{ client_message_id: "CM-PEER", disposition: "dequeued" }]);
    o.onRunObserved("local-run-270");
    expect(o.owns("local-run-270")).toBe(false); // our claim is still awaiting its OWN ack
  });

  it("two of our own sends claim two runs in submission order", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-1", "CM-1");
    o.onInputAccepted("REQ-1", true, "started");
    o.beginSend("REQ-2", "CM-2");
    o.onInputAccepted("REQ-2", true, "queued");

    o.onRunObserved("local-run-300"); // REQ-1's
    expect(o.owns("local-run-300")).toBe(true);
    o.onTurnFinished("local-run-300");

    o.onQueueRemovals([{ client_message_id: "CM-2", disposition: "dequeued" }]);
    o.onRunObserved("local-run-301"); // REQ-2's
    expect(o.owns("local-run-301")).toBe(true);
  });

  it("repeat sightings of one run do not consume additional claims", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-1", "CM-1");
    o.onInputAccepted("REQ-1", true, "started");
    o.beginSend("REQ-2", "CM-2");
    o.onInputAccepted("REQ-2", true, "started");

    o.onRunObserved("local-run-310");
    o.onRunObserved("local-run-310"); // every delta of the same run repeats the id
    o.onRunObserved("local-run-310");

    expect(o.snapshot().owned).toEqual(["local-run-310"]);
    expect(o.snapshot().pending).toBe(1); // the second claim is still unbound
  });

  /**
   * ASSERTION CHANGE, deliberate. The four tests replaced here asserted a fail-CLOSED approval
   * policy driven by `degraded` — "an unattributable approval is answered by us". That premise is
   * gone: the server broadcasts approvals to every subscriber and settles the race itself, so
   * answering is unconditional and never consults attribution
   * (docs/plans/2026-08-13-approval-contract-findings.md). One of them —
   * "degraded mode still refuses a run already attributed to someone else" — was additionally
   * WRONG on its own terms: that run had merely been seen while we were unarmed, which is not the
   * same as being positively a peer's, and conflating the two is what made a lost ack silently
   * unattributable. `degraded` survives only as a diagnostic.
   */
  it("a reconnect with work outstanding degrades (diagnostic) and demotes armed claims", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onReconnect();

    expect(o.snapshot().degraded).toBe(true);
    // The armed claim must NOT bind the first run on the new connection: across the gap an
    // unknown number of runs may have begun and ended, so it could easily be a peer's.
    o.onRunObserved("local-run-after-gap");
    expect(o.owns("local-run-after-gap")).toBe(false);
    expect(o.attribute("local-run-after-gap")).toBe("unknown");
  });

  it("a reconnect with nothing outstanding does not degrade", () => {
    const o = new RunOwnership();
    o.onReconnect();
    expect(o.snapshot().degraded).toBe(false);
  });

  it("a run seen while we hold a QUEUED claim is unknown, not foreign", () => {
    // The distinction the old `seenRuns` conflation lost. Our dequeue notice may still be in
    // flight, so this run can still turn out to be ours.
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "queued");
    o.onRunObserved("local-run-600");
    expect(o.attribute("local-run-600")).toBe("unknown");
  });

  it("a run seen while we hold NOTHING is positively foreign", () => {
    const o = new RunOwnership();
    o.onRunObserved("local-run-601");
    expect(o.attribute("local-run-601")).toBe("foreign");
  });

  it("degraded clears once all outstanding work drains", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-500");
    o.onReconnect();
    expect(o.snapshot().degraded).toBe(true);

    o.onTurnFinished("local-run-500");
    expect(o.snapshot().degraded).toBe(false);
  });

  it("turn_finished with requires_approval does NOT release the run", () => {
    // The turn is parked awaiting an approval, not finished. Releasing here would make a late
    // approval read as a peer's and would let expiry reap a run that is very much alive.
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-700");
    o.onTurnFinished("local-run-700", "requires_approval");
    expect(o.owns("local-run-700")).toBe(true);

    o.onTurnFinished("local-run-700", "end_turn");
    expect(o.owns("local-run-700")).toBe(false);
  });

  describe("expiry (keyed on stream INACTIVITY, not elapsed time since submission)", () => {
    it("reaps a claim whose stream has gone quiet, clearing degraded", () => {
      let now = 1_000;
      const o = new RunOwnership({ clock: () => now });
      o.beginSend("REQ-A", "CM-A"); // ack lost in a drop
      o.onReconnect();
      expect(o.snapshot().degraded).toBe(true);

      now += 60_000;
      const reaped = o.reapIdle(30_000, now);
      expect(reaped.claims).toBe(1);
      expect(o.hasOutstanding()).toBe(false);
      expect(o.snapshot().degraded).toBe(false);
    });

    it("does NOT reap while the stream is still active — turns here run 51s-600s", () => {
      let now = 1_000;
      const o = new RunOwnership({ clock: () => now });
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "started");
      o.onRunObserved("local-run-800");

      now += 120_000;
      o.onRunObserved("local-run-800"); // still streaming: activity, even on a known run
      const reaped = o.reapIdle(30_000, now);
      expect(reaped).toEqual({ claims: 0, runs: 0 });
      expect(o.owns("local-run-800")).toBe(true);
    });
  });

  it("`submitting` arms like `started`", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "submitting");
    o.onRunObserved("local-run-600");
    expect(o.owns("local-run-600")).toBe(true);
  });

  /**
   * Properties the mutation table proved were unasserted. Each of these fails against a
   * one-component revert of the fix it covers — that is the whole point of writing them from the
   * property rather than from the code.
   */
  describe("properties the suite could not previously disprove", () => {
    it("claims bind to runs in SUBMISSION order, not in reverse", () => {
      // Reversing the scan (findIndex → findLastIndex) left the suite green, because every test
      // that had two claims outstanding could not tell which one bound: they carried no identity.
      // The origin is that identity, and on a bridge binding them backwards hands one browser
      // another browser's reply.
      const o = new RunOwnership();
      o.beginSend("REQ-1", "CM-1", "tab-A");
      o.onInputAccepted("REQ-1", true, "started");
      o.beginSend("REQ-2", "CM-2", "tab-B");
      o.onInputAccepted("REQ-2", true, "started");

      o.onRunObserved("local-run-1");
      o.onRunObserved("local-run-2");

      expect(o.originOf("local-run-1")).toBe("tab-A");
      expect(o.originOf("local-run-2")).toBe("tab-B");
    });

    it("an unrecognised queue disposition HOLDS the claim rather than destroying it", () => {
      // `else = cancelled` was the wrong default: a renamed or newly-added disposition would
      // silently destroy a live claim, after which our own turns render under the peer label.
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "queued");

      const anomalies: string[] = [];
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "deferred" }], (m) =>
        anomalies.push(m),
      );

      expect(o.snapshot().pending).toBe(1); // held — a drop would read 0
      expect(o.snapshot().degraded).toBe(true);
      expect(anomalies).toHaveLength(1);

      // And it is still resolvable: the claim was parked, not consumed.
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "dequeued" }]);
      o.onRunObserved("local-run-1");
      expect(o.owns("local-run-1")).toBe(true);
    });

    it("ownsAnyMessage answers for the ASKING origin, not for the core as a whole", () => {
      // One core, N browsers: a queue notice belongs to the browser whose message is in it. An
      // implementation that ignores the argument tells every browser it is queued.
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A", "tab-A");

      expect(o.ownsAnyMessage(["CM-A"], "tab-A")).toBe(true);
      expect(o.ownsAnyMessage(["CM-A"], "tab-B")).toBe(false);
      expect(o.ownsAnyMessage(["CM-A"])).toBe(true); // no origin asked: any of ours counts
    });

    it("a claim demoted by a reconnect is still resolvable by its own dequeue notice", () => {
      // `lost` was terminal: the demoted claim could never bind and never drain, so `pending`
      // stayed 1 for the process lifetime and hasOutstanding() pinned the positivelyForeign
      // branch off. A dequeue naming our own client_message_id is DIRECT evidence, not the
      // positional inference the reconnect invalidated, so it may re-arm.
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "queued");
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "dequeued" }]);
      o.onReconnect(); // armed → lost

      const anomalies: string[] = [];
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "dequeued" }], (m) =>
        anomalies.push(m),
      );
      o.onRunObserved("local-run-after-gap");

      expect(o.owns("local-run-after-gap")).toBe(true);
      expect(anomalies).toEqual([]);
      expect(o.snapshot().pending).toBe(0);
    });

    it("a cancel resolves a claim the reconnect demoted, instead of stranding it", () => {
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "queued");
      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "dequeued" }]);
      o.onReconnect();

      o.onQueueRemovals([{ client_message_id: "CM-A", disposition: "cancelled" }]);
      expect(o.hasOutstanding()).toBe(false);
    });

    it("a stranded claim is reaped even while PEER traffic keeps the stream busy", () => {
      // The reaper measured from a SINGLE global `lastActivity`, which every peer frame bumped.
      // On a shared conversation — M1's entire target state — that is the normal case, so the
      // reaper could not fire on the only deployment where a stranded claim actually hurts.
      let now = 1_000;
      const o = new RunOwnership({ clock: () => now });
      o.beginSend("REQ-A", "CM-A"); // its ack died in a socket drop

      for (let i = 0; i < 12; i += 1) {
        now += 10_000; // a peer turn every 10s, well inside the 30s idle budget
        o.onRunObserved(`peer-run-${i}`);
        o.onTurnFinished(`peer-run-${i}`);
      }

      expect(o.reapIdle(30_000, now)).toEqual({ claims: 1, runs: 0 });
      expect(o.hasOutstanding()).toBe(false);
    });

    it("an owned run that IS still streaming survives the same sweep", () => {
      // The other half of the property: per-item ageing must not reap live work.
      let now = 1_000;
      const o = new RunOwnership({ clock: () => now });
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "started");
      o.onRunObserved("local-run-800");

      for (let i = 0; i < 12; i += 1) {
        now += 10_000;
        o.onRunObserved("local-run-800"); // still streaming
      }

      expect(o.reapIdle(30_000, now)).toEqual({ claims: 0, runs: 0 });
      expect(o.owns("local-run-800")).toBe(true);
    });
  });

  /**
   * A multi-step agentic reply spans SEVERAL runs and the run our send starts is never closed —
   * captured live on 0.30.20. The server serializes turns per {agent, conversation}, so a new run
   * appearing while one of ours is still active is a CONTINUATION of our turn, not a peer's.
   * That inference is exactly as strong as "an armed claim takes the next new run", which this
   * module already depends on.
   */
  describe("continuation runs (the tool-using shape)", () => {
    it("a run that starts while ours is still active inherits our attribution and origin", () => {
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A", "tab-A");
      o.onInputAccepted("REQ-A", true, "started");
      o.onRunObserved("local-run-320"); // ours

      o.onRunObserved("local-run-321"); // the continuation carrying the reply

      expect(o.attribute("local-run-321")).toBe("mine");
      expect(o.originOf("local-run-321")).toBe("tab-A");
    });

    it("finishing the continuation releases the orphaned parent too", () => {
      // 320 never emits turn_finished, on this turn or any later one. Without releasing it here
      // the only thing that ever clears it is the idle reaper, 15 minutes later — during which
      // hasOutstanding() stays true and every peer turn attributes as `unknown`.
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A", "tab-A");
      o.onInputAccepted("REQ-A", true, "started");
      o.onRunObserved("local-run-320");
      o.onRunObserved("local-run-321");

      o.onTurnFinished("local-run-321", "end_turn");

      expect(o.hasOutstanding()).toBe(false);
      expect(o.snapshot().owned).toEqual([]);
    });

    it("a run seen while we own NOTHING is still positively foreign", () => {
      // The inheritance must not swallow the foreign case: it is conditioned on our own run
      // being active, which is what the server's per-conversation serialization guarantees.
      const o = new RunOwnership();
      o.beginSend("REQ-A", "CM-A");
      o.onInputAccepted("REQ-A", true, "started");
      o.onRunObserved("local-run-1");
      o.onTurnFinished("local-run-1");

      o.onRunObserved("local-run-2");
      expect(o.attribute("local-run-2")).toBe("foreign");
    });

    it("inheritance is refused when it would be a guess between two of our own runs", () => {
      // Two owned runs means we cannot tell which one the continuation belongs to, and on a
      // bridge a wrong answer routes one consumer's reply to another. Say unknown instead.
      const o = new RunOwnership();
      o.beginSend("REQ-1", "CM-1", "tab-A");
      o.onInputAccepted("REQ-1", true, "started");
      o.beginSend("REQ-2", "CM-2", "tab-B");
      o.onInputAccepted("REQ-2", true, "started");
      o.onRunObserved("run-1");
      o.onRunObserved("run-2");

      o.onRunObserved("run-3");
      expect(o.attribute("run-3")).toBe("unknown");
      expect(o.originOf("run-3")).toBeUndefined();
    });
  });

  it("an UNKNOWN future disposition PARKS rather than arms", () => {
    // ASSERTION REVERSED, deliberate. This previously asserted the opposite, justified as
    // "over-denying beats hanging every surface" — arming meant we would still answer our own
    // approval. That justification died with the approval coupling: answering no longer consults
    // attribution, so arming on an unrecognised disposition now only risks binding a run that is
    // not ours and mislabelling it. Parking yields "unknown", which is the honest answer.
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "some-future-disposition");
    o.onRunObserved("local-run-601");
    expect(o.owns("local-run-601")).toBe(false);
    expect(o.attribute("local-run-601")).toBe("unknown");
  });
});
