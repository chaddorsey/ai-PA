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

  it("THE MIRROR BUG: we must not answer a foreign approval while our own turn runs", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-251");
    o.onRunObserved("local-run-900"); // a peer's run, unclaimed (no armed claim left)

    // A counter would still be >0 here and would mislabel the peer's turn as ours.
    // Not "foreign": we had a run in flight when 900 appeared, so it is merely unattributable.
    expect(o.attribute("local-run-900")).toBe("unknown");
    expect(o.attribute("local-run-251")).toBe("mine");
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
