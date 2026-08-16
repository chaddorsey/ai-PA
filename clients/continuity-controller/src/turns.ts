/**
 * turns.ts — the sole-submitter turn pipeline: durable per-runtime queue, exactly-once
 * submission, the terminality disjunction, and visible failure for every exit (G5).
 *
 * The load-bearing order of operations (plan, Key Technical Decisions; C1 S3/S4):
 *
 *  1. `accept` writes a DURABLE queue row before anything touches a socket — a message can
 *     never die with a connection (closes Q3; S4server showed the server-side queue does
 *     exactly that).
 *  2. The row moves to `submitting` BEFORE the socket write, so a crash in the write→ack
 *     window is reconcilable: recovery checks `conversation_messages_list` for the
 *     `client_message_id` (it comes back as the user row's `otid` — C1 S3) and resubmits
 *     ONLY on confirmed absence. Duplicate turns on a shared conversation are the documented
 *     hazard; a lost message is the visible, recoverable failure.
 *  3. At most one active controller-submitted turn per runtime; the next row submits only on
 *     the current turn's terminality.
 *  4. The wall-clock backstop is COUPLED to abort: timeout → `abort_message` → confirmation →
 *     FAILED-VISIBLE → only then does the queue release. An unconfirmed abort HOLDS the queue
 *     and escalates (`onWedged` → the worker bounces the connection; recovery reconciles).
 */

import { randomUUID } from "node:crypto";
import type { DatabaseSync } from "node:sqlite";
import type { protocol } from "@ai-pa/letta-continuity-core";
import {
  Outbound,
  buildAbortMessage,
  buildConversationMessagesList,
  buildInput,
} from "@ai-pa/letta-continuity-core/protocol";
import type { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import type { TurnJournal } from "./journal.js";
import type { RuntimeRef } from "./registry.js";
import { TerminalityTracker } from "./terminality.js";

type ServerFrame = protocol.ServerFrame;

export interface QueueRow {
  id: number;
  agent_id: string;
  conversation_id: string;
  client_message_id: string;
  content: string;
  origin: Record<string, unknown>;
  state: "queued" | "submitting" | "submitted" | "terminal";
  outcome: string | null;
}

export interface TurnPipelineOptions {
  db: DatabaseSync;
  journal: TurnJournal;
  getConnection: () => WsConnection | null;
  /** Wall-clock backstop for one turn. */
  turnTimeoutMs: number;
  /** Bound on the abort round-trip before the wedge escalates. */
  abortConfirmMs: number;
  /** Escalation: abort unconfirmed — the worker should bounce the connection. */
  onWedged?: (runtime: RuntimeRef, detail: string) => void;
  /**
   * Submission gate: is the worker SUBSCRIBED to this runtime? A freshly-warmed specialist
   * (C8 routes a cold target hot) must not receive its input before the hotset pass
   * subscribes — the row waits, queued and durable, until the subscription exists.
   */
  isSubscribed?: (runtime: RuntimeRef) => boolean;
  onWarn?: (msg: string) => void;
}

const key = (r: RuntimeRef): string => `${r.agent_id}:${r.conversation_id}`;

/**
 * The durable-acceptance primitive, usable from OUTSIDE the worker process too (the enqueue
 * CLI and, later, ingress adapters): a queue row + journal record, nothing socket-shaped. The
 * running worker's queue poll picks the row up. Exactly the property S4local proved: a message
 * in the controller's durable queue survives any socket's death.
 */
export function enqueueDurable(
  db: DatabaseSync,
  journal: TurnJournal,
  runtime: RuntimeRef,
  content: string,
  origin: Record<string, unknown> = {},
): string {
  const clientMessageId = `cm-${randomUUID().slice(0, 13)}`;
  const now = new Date().toISOString();
  db.prepare(
    `INSERT INTO turn_queue
       (agent_id, conversation_id, client_message_id, content, origin, state, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)`,
  ).run(
    runtime.agent_id,
    runtime.conversation_id,
    clientMessageId,
    content,
    JSON.stringify(origin),
    now,
    now,
  );
  journal.record({ runtime, clientMessageId, kind: "turn_accepted", payload: { origin } });
  return clientMessageId;
}

/** Delta message types worth journaling (content + terminality; statuses stay in memory). */
const JOURNALED_DELTAS = new Set([
  "assistant_message",
  "reasoning_message",
  "tool_call_message",
  "tool_return_message",
  "client_tool_start",
  "client_tool_end",
  "stop_reason",
  "loop_error",
]);

interface ActiveTurn {
  clientMessageId: string;
  timer: ReturnType<typeof setTimeout> | null;
  aborting: boolean;
}

export class TurnPipeline {
  private readonly terminality = new TerminalityTracker();
  private readonly active = new Map<string, ActiveTurn>();
  /** Latest loop status per runtime, fed by the frame stream (idle-fallback evidence). */
  private readonly statusByRuntime = new Map<string, string>();
  /** Connection generation — stamped into journal rows so event_seq ordering is per-epoch. */
  private generation = 0;

  constructor(private readonly opts: TurnPipelineOptions) {}

  /** Durable acceptance. The receipt is the client_message_id; delivery is now inspectable. */
  accept(runtime: RuntimeRef, content: string, origin: Record<string, unknown> = {}): string {
    const clientMessageId = enqueueDurable(
      this.opts.db,
      this.opts.journal,
      runtime,
      content,
      origin,
    );
    this.pump();
    return clientMessageId;
  }

  /** Feed every inbound frame here. Journals it, tracks status, drives terminality. */
  onFrame(frame: ServerFrame): void {
    const runtime = frame.runtime as RuntimeRef | undefined;
    if (!runtime || typeof runtime.agent_id !== "string") return;

    if (frame.type === "update_loop_status") {
      const status = (frame.loop_status as { status?: string } | undefined)?.status;
      if (typeof status === "string") this.statusByRuntime.set(key(runtime), status);
      return;
    }

    const activeTurn = this.active.get(key(runtime));
    if (frame.type === "stream_delta") {
      const delta = frame.delta as { message_type?: string } | undefined;
      if (delta?.message_type && JOURNALED_DELTAS.has(delta.message_type)) {
        this.opts.journal.record({
          runtime,
          clientMessageId: activeTurn?.clientMessageId ?? null,
          eventSeq: typeof frame.event_seq === "number" ? frame.event_seq : null,
          idempotencyKey: typeof frame.idempotency_key === "string" ? frame.idempotency_key : null,
          kind:
            typeof frame.subagent_id === "string"
              ? `subagent:${delta.message_type}`
              : delta.message_type,
          payload: { delta: frame.delta, gen: this.generation },
        });
      }
    } else if (frame.type === "turn_finished" || frame.type === "update_queue") {
      this.opts.journal.record({
        runtime,
        clientMessageId: activeTurn?.clientMessageId ?? null,
        eventSeq: typeof frame.event_seq === "number" ? frame.event_seq : null,
        idempotencyKey: typeof frame.idempotency_key === "string" ? frame.idempotency_key : null,
        kind: frame.type,
        payload: { frame: { ...frame, type: undefined }, gen: this.generation },
      });
    } else if (frame.type === "input_accepted") {
      this.onInputAccepted(frame);
      return;
    }

    const signal = activeTurn ? this.terminality.observe(frame, runtime) : null;
    if (signal && activeTurn)
      this.finishTurn(
        runtime,
        activeTurn,
        signal.failed
          ? `failed:${signal.stopReason ?? signal.kind}`
          : (signal.stopReason ?? signal.kind),
        signal,
      );
  }

  /**
   * Recovery + (re)start, called by the worker AFTER its replay-complete subscriptions are up.
   * Reconciles every non-terminal row against the transcript, then pumps.
   */
  /**
   * Open a new journal generation for a fresh connection. Called by the worker BEFORE any
   * frame of the new connection can be journaled (replay frames arrive during subscription).
   *
   * The generation is PERSISTED, not a process-local counter: `event_seq` is per-connection,
   * so the journal's ordering audit groups by generation — and a process restart that reused
   * generation numbers would interleave two connections' sequences under one label (found
   * live in the first P3 run: ordered in truth, "violated" in the audit).
   */
  beginGeneration(): void {
    this.opts.db
      .prepare(
        `INSERT INTO meta (key, value) VALUES ('journal_generation', '1')
         ON CONFLICT (key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)`,
      )
      .run();
    const generationRow = this.opts.db
      .prepare("SELECT value FROM meta WHERE key = 'journal_generation'")
      .get() as { value: string };
    this.generation = Number.parseInt(generationRow.value, 10);
    // Stale actives die WITH their timers: a leftover wall-clock timer would fire against a
    // turn the coming recovery is about to reconcile, aborting or failing a row it no longer
    // owns.
    for (const [, turn] of this.active) if (turn.timer) clearTimeout(turn.timer);
    this.active.clear();
  }

  async recover(conn: WsConnection): Promise<void> {
    const pending = this.rows(["submitting", "submitted"]);
    for (const row of pending) {
      const runtime = { agent_id: row.agent_id, conversation_id: row.conversation_id };
      let transcript: Array<Record<string, unknown>>;
      try {
        const resp = await conn.request(
          (rid) => buildConversationMessagesList(rid, runtime),
          Outbound.conversationMessagesList,
        );
        transcript = (resp.messages as Array<Record<string, unknown>>) ?? [];
      } catch (e) {
        // Connection died mid-recovery: leave the row for the NEXT recovery. Never guess.
        this.opts.onWarn?.(
          `recovery deferred for ${row.client_message_id}: ${e instanceof Error ? e.message : String(e)}`,
        );
        continue;
      }
      // Newest-first list (C1 probe): our user row at index i; anything BEFORE i is newer.
      const userIndex = transcript.findIndex((m) => m.otid === row.client_message_id);
      if (userIndex === -1) {
        // Confirmed ABSENT → the submitting-window crash lost it before the server saw it.
        // Requeue for exactly-once resubmission.
        this.setState(row.client_message_id, "queued", null);
        this.opts.journal.record({
          runtime,
          clientMessageId: row.client_message_id,
          kind: "reconciled_absent_requeued",
          payload: { was: row.state },
        });
        continue;
      }
      const newerAssistant = transcript
        .slice(0, userIndex)
        .some((m) => m.message_type === "assistant_message");
      const status = this.statusByRuntime.get(key(runtime));
      const busy = status !== undefined && status !== "WAITING_ON_INPUT";
      if (busy) {
        // The turn is STILL RUNNING (the anchor held it through our restart). Re-adopt it.
        this.adopt(runtime, row.client_message_id);
        this.setState(row.client_message_id, "submitted", null);
        this.opts.journal.record({
          runtime,
          clientMessageId: row.client_message_id,
          kind: "reconciled_still_running",
          payload: { status },
        });
      } else if (newerAssistant) {
        // Completed while we were away — transcript truth closes it.
        this.setState(row.client_message_id, "terminal", "end_turn:reconciled");
        this.opts.journal.record({
          runtime,
          clientMessageId: row.client_message_id,
          kind: "turn_terminal",
          payload: { outcome: "end_turn:reconciled", via: "transcript" },
        });
      } else {
        // Idle, submitted, no reply: the App Server restarted out from under the turn.
        // FAILED-VISIBLE, never silently absent (proof P4).
        this.setState(row.client_message_id, "terminal", "FAILED-VISIBLE:lost-to-restart");
        this.opts.journal.record({
          runtime,
          clientMessageId: row.client_message_id,
          kind: "turn_failed_visible",
          payload: { reason: "lost-to-restart", idleStatus: status ?? "unknown" },
        });
      }
    }
    this.pump();
  }

  /** Submit the head of every idle runtime's queue. Cheap; call on any queue/terminal change. */
  pump(): void {
    const conn = this.opts.getConnection();
    if (!conn) return;
    for (const row of this.rows(["queued"])) {
      const runtime = { agent_id: row.agent_id, conversation_id: row.conversation_id };
      if (this.active.has(key(runtime))) continue;
      if (this.opts.isSubscribed && !this.opts.isSubscribed(runtime)) continue;
      this.submit(conn, runtime, row);
    }
  }

  /** Queue rows in the given states, oldest first (submission order). */
  rows(states: QueueRow["state"][]): QueueRow[] {
    const placeholders = states.map(() => "?").join(",");
    const raw = this.opts.db
      .prepare(`SELECT * FROM turn_queue WHERE state IN (${placeholders}) ORDER BY id ASC`)
      .all(...states) as Array<Record<string, unknown>>;
    return raw.map((r) => ({
      id: r.id as number,
      agent_id: r.agent_id as string,
      conversation_id: r.conversation_id as string,
      client_message_id: r.client_message_id as string,
      content: r.content as string,
      origin: JSON.parse(r.origin as string) as Record<string, unknown>,
      state: r.state as QueueRow["state"],
      outcome: (r.outcome as string | null) ?? null,
    }));
  }

  rowFor(clientMessageId: string): QueueRow | null {
    const r = this.opts.db
      .prepare("SELECT * FROM turn_queue WHERE client_message_id = ?")
      .get(clientMessageId) as Record<string, unknown> | undefined;
    if (!r) return null;
    return {
      id: r.id as number,
      agent_id: r.agent_id as string,
      conversation_id: r.conversation_id as string,
      client_message_id: r.client_message_id as string,
      content: r.content as string,
      origin: JSON.parse(r.origin as string) as Record<string, unknown>,
      state: r.state as QueueRow["state"],
      outcome: (r.outcome as string | null) ?? null,
    };
  }

  stop(): void {
    for (const [, turn] of this.active) if (turn.timer) clearTimeout(turn.timer);
    this.active.clear();
  }

  private submit(conn: WsConnection, runtime: RuntimeRef, row: QueueRow): void {
    // Durable `submitting` BEFORE the socket write — the reconcilable crash window.
    this.setState(row.client_message_id, "submitting", null);
    try {
      conn.send(
        buildInput(runtime, row.content, {
          requestId: `in-${row.client_message_id}`,
          clientMessageId: row.client_message_id,
        }),
      );
    } catch (e) {
      // The socket refused synchronously — nothing reached the server. Back to queued; the
      // next recovery/pump retries. (An UNKNOWN outcome only exists after a successful write.)
      this.setState(row.client_message_id, "queued", null);
      this.opts.onWarn?.(
        `submit write failed for ${row.client_message_id}: ${e instanceof Error ? e.message : String(e)}`,
      );
      return;
    }
    this.adopt(runtime, row.client_message_id);
    this.opts.journal.record({
      runtime,
      clientMessageId: row.client_message_id,
      kind: "turn_submitted",
      payload: { gen: this.generation },
    });
  }

  private onInputAccepted(frame: ServerFrame): void {
    const requestId = typeof frame.request_id === "string" ? frame.request_id : "";
    if (!requestId.startsWith("in-")) return;
    const clientMessageId = requestId.slice(3);
    const runtime = frame.runtime as RuntimeRef;
    if (frame.accepted === true) {
      this.setState(clientMessageId, "submitted", null);
      this.opts.journal.record({
        runtime,
        clientMessageId,
        kind: "input_accepted",
        payload: { disposition: frame.disposition ?? null },
      });
    } else {
      const turn = this.active.get(key(runtime));
      if (turn?.clientMessageId === clientMessageId) this.clearActive(runtime, turn);
      this.setState(clientMessageId, "terminal", "FAILED-VISIBLE:rejected");
      this.opts.journal.record({
        runtime,
        clientMessageId,
        kind: "turn_failed_visible",
        payload: { reason: "rejected", error: frame.error ?? null },
      });
      this.pump();
    }
  }

  private adopt(runtime: RuntimeRef, clientMessageId: string): void {
    const turn: ActiveTurn = { clientMessageId, timer: null, aborting: false };
    turn.timer = setTimeout(() => void this.timeoutTurn(runtime, turn), this.opts.turnTimeoutMs);
    turn.timer.unref?.();
    this.active.set(key(runtime), turn);
  }

  private finishTurn(
    runtime: RuntimeRef,
    turn: ActiveTurn,
    outcome: string,
    signal: { kind: string; runId: string | null; stopReason: string | null },
  ): void {
    this.clearActive(runtime, turn);
    this.setState(turn.clientMessageId, "terminal", outcome);
    this.opts.journal.record({
      runtime,
      clientMessageId: turn.clientMessageId,
      kind: "turn_terminal",
      payload: { outcome, via: signal.kind, run_id: signal.runId },
    });
    this.pump();
  }

  /**
   * The wall-clock backstop. Timeout → abort → CONFIRMED → FAILED-VISIBLE → release. The
   * queue is NOT released while the server may still be running the turn — an unconfirmed
   * abort holds it and escalates instead (head-of-line serial timeouts were the alternative).
   */
  private async timeoutTurn(runtime: RuntimeRef, turn: ActiveTurn): Promise<void> {
    if (turn.aborting) return;
    turn.aborting = true;
    this.opts.journal.record({
      runtime,
      clientMessageId: turn.clientMessageId,
      kind: "turn_timeout_abort_sent",
      payload: { timeoutMs: this.opts.turnTimeoutMs },
    });
    const conn = this.opts.getConnection();
    try {
      if (!conn) throw new Error("no connection to abort on");
      await conn.request(
        (rid) => buildAbortMessage(rid, runtime),
        Outbound.abortMessage,
        this.opts.abortConfirmMs,
      );
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e);
      this.opts.journal.record({
        runtime,
        clientMessageId: turn.clientMessageId,
        kind: "abort_unconfirmed",
        payload: { detail },
      });
      // Queue stays HELD; the worker bounces and recovery reconciles the turn's true fate.
      this.opts.onWedged?.(runtime, detail);
      return;
    }
    this.clearActive(runtime, turn);
    this.setState(turn.clientMessageId, "terminal", "FAILED-VISIBLE:timeout");
    this.opts.journal.record({
      runtime,
      clientMessageId: turn.clientMessageId,
      kind: "turn_failed_visible",
      payload: { reason: "timeout", abortConfirmed: true },
    });
    this.pump();
  }

  /**
   * Operator-initiated abort (the C5 `abort` capability): kill the runtime's active
   * controller-submitted turn. Confirmed against the server before the queue releases —
   * same coupling as the wall-clock arm. Returns false when nothing was active.
   */
  async abortActive(runtime: RuntimeRef, by: string): Promise<boolean> {
    const turn = this.active.get(key(runtime));
    if (!turn || turn.aborting) return false;
    turn.aborting = true;
    const conn = this.opts.getConnection();
    if (!conn) {
      turn.aborting = false;
      return false;
    }
    await conn.request(
      (rid) => buildAbortMessage(rid, runtime),
      Outbound.abortMessage,
      this.opts.abortConfirmMs,
    );
    this.clearActive(runtime, turn);
    this.setState(turn.clientMessageId, "terminal", "aborted:operator");
    this.opts.journal.record({
      runtime,
      clientMessageId: turn.clientMessageId,
      kind: "turn_terminal",
      payload: { outcome: "aborted:operator", via: "abort", by },
    });
    this.pump();
    return true;
  }

  private clearActive(runtime: RuntimeRef, turn: ActiveTurn): void {
    if (turn.timer) clearTimeout(turn.timer);
    turn.timer = null;
    if (this.active.get(key(runtime)) === turn) this.active.delete(key(runtime));
  }

  private setState(
    clientMessageId: string,
    state: QueueRow["state"],
    outcome: string | null,
  ): void {
    this.opts.db
      .prepare(
        "UPDATE turn_queue SET state = ?, outcome = ?, updated_at = ? WHERE client_message_id = ?",
      )
      .run(state, outcome, new Date().toISOString(), clientMessageId);
  }
}
