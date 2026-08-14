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
    expect(o.shouldRespondToApproval("local-run-251")).toBe(true);

    o.onTurnFinished("local-run-251");
    expect(o.owns("local-run-251")).toBe(false);
    expect(o.hasOutstanding()).toBe(false);
  });

  it("a foreign run is never claimed when we have nothing outstanding", () => {
    const o = new RunOwnership();
    o.onRunObserved("local-run-999");
    expect(o.owns("local-run-999")).toBe(false);
    expect(o.shouldRespondToApproval("local-run-999")).toBe(false);
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
    expect(o.shouldRespondToApproval("local-run-251")).toBe(true);
  });

  it("THE MIRROR BUG: we must not answer a foreign approval while our own turn runs", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onRunObserved("local-run-251");
    o.onRunObserved("local-run-900"); // a peer's run, unclaimed (no armed claim left)

    // A counter would still be >0 here and would wrongly deny the peer's approval.
    expect(o.shouldRespondToApproval("local-run-900")).toBe(false);
    expect(o.shouldRespondToApproval("local-run-251")).toBe(true);
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

  it("after a reconnect with work outstanding, an UNKNOWN approval fails CLOSED", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onReconnect(); // the ack/dequeue/turn_finished we needed may have been missed

    expect(o.snapshot().degraded).toBe(true);
    // Unattributable → deny (bounded error) rather than risk hanging both surfaces.
    expect(o.shouldRespondToApproval(undefined)).toBe(true);
    expect(o.shouldRespondToApproval("local-run-unknown")).toBe(true);
  });

  it("a reconnect with nothing outstanding does not degrade, and stays silent", () => {
    const o = new RunOwnership();
    o.onReconnect();
    expect(o.snapshot().degraded).toBe(false);
    expect(o.shouldRespondToApproval(undefined)).toBe(false);
  });

  it("degraded mode still refuses a run already attributed to someone else", () => {
    const o = new RunOwnership();
    o.onRunObserved("local-run-400"); // a peer's run, seen before our send
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "started");
    o.onReconnect();

    expect(o.snapshot().degraded).toBe(true);
    expect(o.shouldRespondToApproval("local-run-400")).toBe(false);
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
    expect(o.shouldRespondToApproval(undefined)).toBe(false);
  });

  it("`submitting` arms like `started`", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "submitting");
    o.onRunObserved("local-run-600");
    expect(o.owns("local-run-600")).toBe(true);
  });

  it("an UNKNOWN future disposition arms — over-denying beats hanging every surface", () => {
    const o = new RunOwnership();
    o.beginSend("REQ-A", "CM-A");
    o.onInputAccepted("REQ-A", true, "some-future-disposition");
    o.onRunObserved("local-run-601");
    expect(o.owns("local-run-601")).toBe(true);
  });
});
